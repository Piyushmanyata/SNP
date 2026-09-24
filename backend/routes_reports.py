import asyncio
import io
import csv
import shutil
from datetime import datetime, timedelta
from typing import Any, Dict, List
from bson import ObjectId
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse, JSONResponse
from catalogue import format_power
from db import aggregate_list, get_db
from helpers import IST, as_utc, display_date, display_timestamp, iso, ist_day_bounds, now_utc, today_ist_str
from security import require_admin, require_staff, require_any, require_lead
import sms

router = APIRouter(prefix="/api", tags=["reports"])


@router.get("/kpis")
async def kpis(actor: dict = Depends(require_any)) -> Dict[str, Any]:
    db = get_db()
    camp = await db.camps.find_one({"is_active": True})
    if not camp:
        return {"active_camp": None, "registered": 0, "seen": 0, "pending": 0}
    registered, seen = await asyncio.gather(
        db.patients.count_documents({"camp_id": camp["_id"]}),
        db.patients.count_documents({"camp_id": camp["_id"], "queue_status": "seen"}),
    )
    return {
        "active_camp": {"id": str(camp["_id"]), "name": camp["name"]},
        "registered": registered,
        "seen": seen,
        "pending": registered - seen,
    }


@router.get("/leaderboard")
async def leaderboard(actor: dict = Depends(require_staff)) -> Dict[str, Any]:
    db = get_db()
    camp = await db.camps.find_one({"is_active": True})
    if not camp:
        return {"volunteers": [], "team_leads": []}

    registered = {"camp_id": camp["_id"]}
    staff_rows, counted = await asyncio.gather(
        db.users.find({"role": {"$in": ["volunteer", "team_lead"]}}).to_list(None),
        aggregate_list(db.patients, [
            {"$match": registered},
            {"$facet": {
                "registrations": [{"$group": {"_id": "$created_by", "count": {"$sum": 1}}}],
                "completed": [
                    {"$match": {"committed_revision_id": {"$ne": None}, "is_self_registered": {"$ne": True}}},
                    {"$group": {"_id": "$created_by", "count": {"$sum": 1}}},
                ],
                "team_registrations": [{"$group": {"_id": "$registrar_team_lead_id", "count": {"$sum": 1}}}],
                "team_completed": [
                    {"$match": {"committed_revision_id": {"$ne": None}, "is_self_registered": {"$ne": True}}},
                    {"$group": {"_id": "$registrar_team_lead_id", "count": {"$sum": 1}}},
                ],
            }},
        ]),
    )
    staff = staff_rows
    facet = counted[0] if counted else {}

    def _tallies(name: str) -> Dict[str, int]:
        return {row["_id"]: row["count"] for row in facet.get(name) or [] if row["_id"]}

    registrations, points = _tallies("registrations"), _tallies("completed")
    team_registrations, team_points = _tallies("team_registrations"), _tallies("team_completed")

    volunteers = [{
        "id": str(u["_id"]),
        "name": u["name"],
        "registrations": registrations.get(str(u["_id"]), 0),
        "completed": points.get(str(u["_id"]), 0),
        "team_lead_id": u.get("team_lead_id"),
    } for u in staff if u.get("role") == "volunteer"]
    volunteers.sort(key=lambda x: (-x["completed"], x["name"]))

    team_leads = [{
        "id": str(u["_id"]),
        "name": u["name"],
        "personal_registrations": registrations.get(str(u["_id"]), 0),
        "personal_completed": points.get(str(u["_id"]), 0),
        "registrations": team_registrations.get(str(u["_id"]), 0),
        "completed": team_points.get(str(u["_id"]), 0),
    } for u in staff if u.get("role") == "team_lead"]
    team_leads.sort(key=lambda x: (-x["completed"], x["name"]))

    return {"volunteers": volunteers, "team_leads": team_leads}


EXPORT_COLUMNS = [
    "reg_no", "full_name", "age", "gender", "phone", "address", "aadhaar_last4",
    "manual_entry", "camp_day", "registered_at", "arrived_at", "seen_at",
    "diagnosis", "bp", "blood_sugar",
    "r_sph", "r_cyl", "r_axis", "l_sph", "l_cyl", "l_axis", "add",
    "medicines_prescribed", "medicines_not_given",
    "fixed_power_r", "fixed_power_l", "issued_power_r", "issued_power_l",
    "medicine", "fixed_power_specs", "spectacles_to_be_made", "ot",
    "ot_day", "ot_venue", "specs_day", "specs_venue", "specs_start", "specs_end",
]


def _line_statuses(fulfilments: dict) -> List[str]:
    return [
        fulfilments.get("medicine", {}).get("status", ""),
        fulfilments.get("specs_fixed", {}).get("status", ""),
        fulfilments.get("specs_made", {}).get("status", ""),
    ]


def _hospital_outcome(ot: dict, revision: dict) -> str:
    if ot.get("status") == "deferred":
        return "scheduled"
    if ot.get("status") == "declined":
        return "declined"
    if "ot" in (revision.get("prescribed_lines") or []) and revision.get("ot_outcome") == "referral":
        return "referred"
    return ""


def _diagnosis(t: dict) -> str:
    parts = list(t.get("diagnosis_options") or [])
    if t.get("diagnosis_other"):
        parts.append(t["diagnosis_other"])
    return ";".join(parts)


def csv_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    if text[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text


def _power_cell(value: Any) -> str:
    return "" if value is None else format_power(value)


def _medicine_cells(t: dict, medicine: dict) -> List[str]:
    prescribed = [m.get("name", "") for m in (t.get("prescribed_medicines") or [])]
    not_given = [
        o.get("name", "") for o in (medicine.get("medicine_outcomes") or []) if not o.get("given")
    ]
    return [";".join(prescribed), ";".join(not_given)]


def _export_row(p: dict, t: dict, fulfilments: dict, day_dates: dict, revision: dict) -> List[Any]:
    m = t.get("specs_measurements") or {}
    ot = fulfilments.get("ot", {})
    hospital = _hospital_outcome(ot, revision)
    scheduled = ot if hospital == "scheduled" else {}
    specs = fulfilments.get("specs_made", {})
    fixed = fulfilments.get("specs_fixed", {})
    cells = [
        p.get("reg_no", ""), p.get("full_name", ""), p.get("age", ""),
        p.get("gender", ""), p.get("phone", ""), p.get("address", ""),
        p.get("aadhaar_last4", ""),
        "yes" if (p.get("manual_entry") or p.get("manual_exception")) else "no",
        display_date(day_dates.get(p.get("camp_day_id"))),
        display_timestamp(p.get("created_at")), display_timestamp(p.get("arrived_at")),
        display_timestamp(p.get("seen_at")),
        _diagnosis(t), t.get("bp", "") or "", t.get("blood_sugar", "") or "",
        *[m.get(k, "") or "" for k in ("r_sph", "r_cyl", "r_axis", "l_sph", "l_cyl", "l_axis", "add")],
        *_medicine_cells(t, fulfilments.get("medicine", {})),
        _power_cell(t.get("fixed_power_r")), _power_cell(t.get("fixed_power_l")),
        _power_cell(fixed.get("issued_power_r")), _power_cell(fixed.get("issued_power_l")),
        *_line_statuses(fulfilments), hospital,
        display_date(scheduled.get("collection_date")), scheduled.get("collection_venue", "") or "",
        display_date(specs.get("collection_date")),
        specs.get("collection_venue", "") or "",
        *((sms.SPECS_PICKUP_START_TIME, sms.SPECS_PICKUP_END_TIME) if specs.get("collection_date") else ("", "")),
    ]
    return [csv_cell(c) for c in cells]


_EXPORT_BATCH = 200


def _csv_chunk(rows: List[List[Any]]) -> str:
    buf = io.StringIO()
    csv.writer(buf).writerows(rows)
    return buf.getvalue()


async def _export_batch(db: Any, patients: List[dict], day_dates: Dict[Any, Any]) -> str:
    rev_ids = [p["committed_revision_id"] for p in patients if p.get("committed_revision_id")]
    pids = [p["_id"] for p in patients]
    rev_rows = await db.prescription_revisions.find({"_id": {"$in": rev_ids}}).to_list(len(rev_ids) or 1) if rev_ids else []
    tx_rows = await db.transcriptions.find({"patient_id": {"$in": pids}}).to_list(len(pids) or 1) if pids else []
    tx_by_patient = {t["patient_id"]: t for t in tx_rows}
    tx_ids = [t["_id"] for t in tx_rows]
    fulfil_rows = await db.fulfilments.find({"transcription_id": {"$in": tx_ids}}).to_list(None) if tx_ids else []
    fulfil_by_tx: Dict[Any, Dict[str, dict]] = {}
    for row in fulfil_rows:
        fulfil_by_tx.setdefault(row["transcription_id"], {})[row["item_type"]] = row
    rev_by_id = {row["_id"]: row for row in rev_rows}
    lines = []
    for patient in patients:
        transcription = tx_by_patient.get(patient["_id"]) or {}
        lines.append(_export_row(
            patient, transcription,
            fulfil_by_tx.get(transcription["_id"], {}) if transcription else {},
            day_dates, rev_by_id.get(patient.get("committed_revision_id")) or {},
        ))
    return _csv_chunk(lines)


async def _camp_record_chunks(db: Any, camp: dict | None):
    yield _csv_chunk([EXPORT_COLUMNS])
    if not camp:
        return
    days = await db.camp_days.find({"camp_id": camp["_id"]}).to_list(None)
    day_dates = {day["_id"]: day["day_date"] for day in days}
    batch: List[dict] = []
    async for patient in db.patients.find({"camp_id": camp["_id"]}):
        batch.append(patient)
        if len(batch) == _EXPORT_BATCH:
            yield await _export_batch(db, batch, day_dates)
            batch = []
    if batch:
        yield await _export_batch(db, batch, day_dates)


@router.get("/exports/camp-records")
async def export_camp_records(camp_id: str | None = None, actor: dict = Depends(require_admin)) -> StreamingResponse:
    """One wide row per patient in the camp, including no-shows."""
    db = get_db()
    camp = await db.camps.find_one({"_id": ObjectId(camp_id)}) if camp_id else await db.camps.find_one({"is_active": True})
    return StreamingResponse(
        _camp_record_chunks(db, camp), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=camp_records.csv"},
    )


def _empty_board(as_of: str, state: str) -> Dict[str, Any]:
    return {
        "as_of": as_of,
        "state": state,
        "camp": None,
        "day": None,
        "stages": {
            "arrived": 0,
            "awaiting_print": 0,
            "awaiting_seen": 0,
            "seen": 0,
            "transcription_backlog": 0,
        },
        "fulfilment": {
            "medicine": {"fulfilled": 0, "not_available": 0, "partially_fulfilled": 0},
            "specs_fixed": {"fulfilled": 0},
            "specs_made": {"deferred": 0},
            "ot": {"deferred": 0, "declined": 0},
        },
        "activity": [],
        "quiet_count": 0,
        "sms_failures": 0,
        "sms_not_sent": 0,
        "sms_paused": [],
        "next_ot": None,
        "next_specs": None,
        "server_time": as_of,
    }


@router.get("/board")
async def camp_day_board(actor: dict = Depends(require_lead)) -> Dict[str, Any]:
    db = get_db()
    now = now_utc()
    as_of = iso(now)
    today = today_ist_str()
    start, end = ist_day_bounds(today)
    system, camp = await asyncio.gather(_system(db), db.camps.find_one({"is_active": True}))
    backups_failing = system["levels"]["backup"] == "red"
    if not camp:
        return {**_empty_board(as_of, "no_camp"), "backups_failing": backups_failing}
    quiet_cutoff = now - timedelta(minutes=15)
    hour_cutoff = now - timedelta(minutes=60)
    camp_id = camp["_id"]
    arrival_filter = {"camp_id": camp_id, "arrived_at": {"$gte": start, "$lt": end}}
    sms_match = {
        "camp_id": camp_id,
        "created_at": {"$gte": start, "$lt": end},
        "$or": [
            {"status": {"$in": ["failed", "abandoned", "rejected", "paused"]}},
            {"delivery": "failed"},
        ],
    }
    day, counted, seen_today, fulfilments, sms_groups, (paused_rows, ot_day, specs_day) = await asyncio.gather(
        db.camp_days.find_one({"camp_id": camp_id, "day_date": today}),
        aggregate_list(db.patients, [
            {"$match": arrival_filter},
            {"$project": {
                "_id": 0, "arrived_at": 1, "arrived_by": 1,
                "printed_at": 1, "seen_at": 1, "committed_revision_id": 1,
            }},
            {"$facet": {
                "totals": [{"$group": {
                    "_id": None,
                    "arrived": {"$sum": 1},
                    "awaiting_print": {"$sum": {"$cond": [{"$eq": ["$printed_at", None]}, 1, 0]}},
                    "awaiting_seen": {"$sum": {"$cond": [
                        {"$and": [{"$ne": ["$printed_at", None]}, {"$eq": ["$seen_at", None]}]}, 1, 0,
                    ]}},
                    "backlog": {"$sum": {"$cond": [
                        {"$and": [
                            {"$ne": ["$printed_at", None]},
                            {"$eq": ["$committed_revision_id", None]},
                        ]}, 1, 0,
                    ]}},
                }}],
                "activity": [{"$group": {
                    "_id": "$arrived_by",
                    "last": {"$max": "$arrived_at"},
                    "last_15m": {"$sum": {"$cond": [{"$gte": ["$arrived_at", quiet_cutoff]}, 1, 0]}},
                    "last_60m": {"$sum": {"$cond": [{"$gte": ["$arrived_at", hour_cutoff]}, 1, 0]}},
                }}],
            }},
        ]),
        db.patients.count_documents({"camp_id": camp_id, "seen_at": {"$gte": start, "$lt": end}}),
        aggregate_list(db.fulfilments, [
            {"$match": {"camp_id": camp_id, "patient_seen_at": {"$gte": start, "$lt": end}}},
            {"$group": {"_id": {"item_type": "$item_type", "status": "$status"}, "count": {"$sum": 1}}},
        ]),
        sms.ledger_groups(db, sms_match, by_camp=True),
        asyncio.gather(
            db.sms_controls.find({"paused": True}, {"_id": 1}).to_list(None),
            db.ot_schedule_days.find_one(
                {"camp_id": camp_id, "day_date": {"$gte": today}},
                sort=[("day_date", 1)],
            ),
            db.specs_collection_days.find_one(
                {"camp_id": camp_id, "$or": [{"day_date": {"$gte": today}}, {"end_date": {"$gte": today}}]},
                sort=[("day_date", 1)],
            ),
        ),
    )
    if not day:
        empty = _empty_board(as_of, "no_day")
        empty["camp"] = {"id": str(camp_id), "name": camp["name"]}
        empty["backups_failing"] = backups_failing
        return empty

    facet = counted[0] if counted else {}
    totals = (facet.get("totals") or [{}])[0]
    arrived = totals.get("arrived", 0)
    awaiting_print = totals.get("awaiting_print", 0)
    awaiting_seen = totals.get("awaiting_seen", 0)
    backlog = totals.get("backlog", 0)
    volunteer_rows = facet.get("activity") or []
    by_vol = {row["_id"]: row for row in volunteer_rows if row["_id"]}
    vol_ids = [ObjectId(v) for v in by_vol if ObjectId.is_valid(v)]
    volunteers = await db.users.find({"_id": {"$in": vol_ids}}).to_list(None) if vol_ids else []
    activity = []
    for u in volunteers:
        uid = str(u["_id"])
        stats = by_vol.get(uid) or {}
        last = stats.get("last")
        quiet = bool(last and as_utc(last) < quiet_cutoff)
        activity.append({
            "id": uid,
            "name": u.get("name"),
            "last_arrival_at": iso(last),
            "last_15m": int(stats.get("last_15m") or 0),
            "last_60m": int(stats.get("last_60m") or 0),
            "quiet": quiet,
        })
    activity.sort(key=lambda r: r["name"] or "")
    quiet_count = sum(1 for r in activity if r["quiet"])

    fulfil_counts = _empty_board(as_of, "current")["fulfilment"]
    for f in fulfilments:
        bucket = fulfil_counts.get(f["_id"].get("item_type"))
        status = f["_id"].get("status")
        if bucket is not None and status in bucket:
            bucket[status] += f["count"]

    sms_failures = 0
    sms_not_sent = 0
    for group in sms_groups:
        status = group["_id"].get("status")
        count = group["n"]
        if status in ("failed", "abandoned", "rejected"):
            sms_failures += count
        elif status == "paused":
            sms_not_sent += count
        else:
            sms_failures += group["dlt_failed"] + group["other_failed"]
    sms_paused = [c["_id"] for c in paused_rows]

    next_ot = None
    if ot_day:
        next_ot = {
            "day_date": ot_day["day_date"],
            "venue": ot_day.get("venue"),
            "seats_left": ot_day.get("seat_limit", 0) - ot_day.get("seats_taken", 0),
        }
    next_specs = None
    if specs_day:
        next_specs = {
            "day_date": specs_day["day_date"],
            "end_date": specs_day.get("end_date") or specs_day["day_date"],
            "venue": specs_day.get("venue"),
        }

    return {
        "as_of": as_of,
        "state": "current",
        "backups_failing": backups_failing,
        "camp": {"id": str(camp["_id"]), "name": camp["name"]},
        "day": {"id": str(day["_id"]), "day_date": day["day_date"]},
        "stages": {
            "arrived": arrived,
            "awaiting_print": awaiting_print,
            "awaiting_seen": awaiting_seen,
            "seen": seen_today,
            "transcription_backlog": backlog,
        },
        "fulfilment": fulfil_counts,
        "activity": activity,
        "quiet_count": quiet_count,
        "sms_failures": sms_failures,
        "sms_not_sent": sms_not_sent,
        "sms_paused": sms_paused,
        "next_ot": next_ot,
        "next_specs": next_specs,
        "server_time": as_of,
    }


@router.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready", response_model=Dict[str, Any])
async def readiness() -> Dict[str, Any] | JSONResponse:
    db = get_db()
    try:
        await db.command("ping")
        n_active = await db.camps.count_documents({"is_active": True})
        if n_active > 1:
            return JSONResponse(status_code=503, content={"ready": False, "reason": "multiple active camps"})
        return {"ready": True, "db": "reachable", "active_camps": n_active}
    except Exception:
        return JSONResponse(status_code=503, content={"ready": False, "reason": "db unreachable"})


LEVELS = ("green", "amber", "red")
BACKUP_FIELDS = (
    "last_success_at", "last_error_at", "last_error", "remote_configured", "remote_last_success_at",
    "interval_seconds", "bytes", "patients_count",
)


def _backup_level(backup: Dict[str, Any] | None, now: datetime) -> str:
    last = as_utc(backup.get("last_success_at")) if backup else None
    if backup is None or last is None:
        return "red"
    interval = timedelta(seconds=backup.get("interval_seconds") or 3600)
    if now - last > max(timedelta(hours=6), 3 * interval):
        return "red"
    remote = as_utc(backup.get("remote_last_success_at"))
    error = as_utc(backup.get("last_error_at"))
    if (now - last > 2 * interval or not backup.get("remote_configured") or remote is None
            or now - remote > 2 * interval or (error is not None and error >= last)):
        return "amber"
    return "green"


def _disk() -> Dict[str, int] | str:
    try:
        usage = shutil.disk_usage("/backups")
    except OSError:
        return "unknown"
    return {"free_bytes": usage.free, "total_bytes": usage.total}


def _disk_level(disk: Dict[str, int] | str) -> str:
    if isinstance(disk, str):
        return "green"
    free = disk["free_bytes"] / disk["total_bytes"]
    return "red" if free < 0.1 else "amber" if free < 0.2 else "green"


def _reminder_level(reminders: Dict[str, Any] | None, now: datetime) -> str:
    beat = as_utc(reminders.get("heartbeat_at")) if reminders else None
    if beat is None or now - beat > timedelta(minutes=5):
        return "red"
    ist = now.astimezone(IST)
    done = ((reminders or {}).get("sweeps") or {}).get(ist.date().isoformat()) or {}
    minutes = ist.hour * 60 + ist.minute
    if minutes >= 10 * 60 + 30 and not done.get("10"):
        return "red"
    if minutes >= 20 * 60 + 30 and not done.get("20"):
        return "red"
    return "green"


async def _system(db: Any) -> Dict[str, Any]:
    backup = await db.ops_status.find_one({"_id": "backup"})
    reminders = await db.ops_status.find_one({"_id": "reminders"})
    disk = _disk()
    now = now_utc()
    levels = {
        "backup": _backup_level(backup, now),
        "disk": _disk_level(disk),
        "reminders": _reminder_level(reminders, now),
    }
    return {
        "status": max(levels.values(), key=LEVELS.index),
        "levels": levels,
        "backup": {
            field: iso(backup.get(field)) if field.endswith("_at") else backup.get(field)
            for field in BACKUP_FIELDS
        } if backup else None,
        "disk": disk,
        "reminders": {
            "heartbeat_at": iso(reminders.get("heartbeat_at")),
            "last_call_at": iso(reminders.get("last_call_at")),
            "last_complete_at": iso(reminders.get("last_complete_at")),
            "last_error": reminders.get("last_error"),
            "queued": reminders.get("queued", 0),
            "failed": reminders.get("failed", 0),
            "uncertain": reminders.get("uncertain", 0),
            "paused_types": reminders.get("paused_types") or [],
        } if reminders else None,
    }


@router.get("/admin/system")
async def system_status(actor: dict = Depends(require_admin)) -> Dict[str, Any]:
    return await _system(get_db())
