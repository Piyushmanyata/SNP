import asyncio
import io
import csv
from datetime import timedelta
from typing import Any, Dict, List
from bson import ObjectId
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse, JSONResponse
from catalogue import format_power
from db import get_db
from helpers import as_utc, display_date, display_timestamp, iso, ist_day_bounds, now_utc, today_ist_str
from security import require_admin, require_staff, require_any, require_lead

router = APIRouter(prefix="/api", tags=["reports"])


@router.get("/kpis")
async def kpis(actor: dict = Depends(require_any)) -> Dict[str, Any]:
    db = get_db()
    camp = await db.camps.find_one({"is_active": True})
    if not camp:
        return {"active_camp": None, "registered": 0, "seen": 0, "pre_registered": 0}
    registered = await db.patients.count_documents({"camp_id": camp["_id"]})
    seen = await db.patients.count_documents({"camp_id": camp["_id"], "queue_status": "seen"})
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

    completed = {
        "camp_id": camp["_id"],
        "committed_revision_id": {"$ne": None},
        "is_self_registered": {"$ne": True},
    }
    vol_docs = await db.users.find({"role": "volunteer"}).to_list(1000)
    volunteers = []
    for v in vol_docs:
        vid = str(v["_id"])
        registrations = await db.patients.count_documents(
            {"camp_id": camp["_id"], "created_by": vid}
        )
        doctor_seen = await db.patients.count_documents({**completed, "created_by": vid})
        volunteers.append({
            "id": vid,
            "name": v["name"],
            "registrations": registrations,
            "doctor_seen": doctor_seen,
            "arrivals": doctor_seen,
            "points": doctor_seen,
            "team_lead_id": v.get("team_lead_id"),
        })
    volunteers.sort(key=lambda x: (-x["points"], x["name"]))

    lead_docs = await db.users.find({"role": "team_lead"}).to_list(200)
    team_leads = []
    for l in lead_docs:
        lid = str(l["_id"])
        personal_registrations = await db.patients.count_documents(
            {"camp_id": camp["_id"], "created_by": lid}
        )
        personal_points = await db.patients.count_documents({**completed, "created_by": lid})
        team_registrations = await db.patients.count_documents(
            {"camp_id": camp["_id"], "registrar_team_lead_id": lid}
        )
        team_points = await db.patients.count_documents({**completed, "registrar_team_lead_id": lid})
        team_leads.append({
            "id": lid,
            "name": l["name"],
            "personal_registrations": personal_registrations,
            "personal_points": personal_points,
            "registrations": team_registrations,
            "doctor_seen": team_points,
            "points": team_points,
        })
    team_leads.sort(key=lambda x: (-x["points"], x["name"]))

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
        specs.get("collection_start_time", "") or "",
        specs.get("collection_end_time", "") or "",
    ]
    return [csv_cell(c) for c in cells]


@router.get("/exports/camp-records")
async def export_camp_records(camp_id: str | None = None, actor: dict = Depends(require_admin)) -> StreamingResponse:
    """One wide row per patient in the camp, including no-shows."""
    db = get_db()
    camp = await db.camps.find_one({"_id": ObjectId(camp_id)}) if camp_id else await db.camps.find_one({"is_active": True})
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(EXPORT_COLUMNS)
    if camp:
        days = await db.camp_days.find({"camp_id": camp["_id"]}).to_list(1000)
        day_dates = {d["_id"]: d["day_date"] for d in days}
        pts = await db.patients.find({"camp_id": camp["_id"]}).to_list(100000)
        pids = [p["_id"] for p in pts]
        rev_ids = [p["committed_revision_id"] for p in pts if p.get("committed_revision_id")]
        rev_rows = await db.prescription_revisions.find({"_id": {"$in": rev_ids}}).to_list(100000) if rev_ids else []
        rev_by_id = {r["_id"]: r for r in rev_rows}
        tx_rows = await db.transcriptions.find({"patient_id": {"$in": pids}}).to_list(100000) if pids else []
        tx_by_patient = {t["patient_id"]: t for t in tx_rows}
        tx_ids = [t["_id"] for t in tx_rows]
        fulfil_rows = await db.fulfilments.find({"transcription_id": {"$in": tx_ids}}).to_list(100000) if tx_ids else []
        fulfil_by_tx: Dict[ObjectId, Dict[str, dict]] = {}
        for f in fulfil_rows:
            fulfil_by_tx.setdefault(f["transcription_id"], {})[f["item_type"]] = f
        for p in pts:
            t = tx_by_patient.get(p["_id"]) or {}
            writer.writerow(_export_row(
                p, t, fulfil_by_tx.get(t["_id"], {}) if t else {}, day_dates,
                rev_by_id.get(p.get("committed_revision_id")) or {},
            ))
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=camp_records.csv"})


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
        "next_ot": None,
        "next_specs": None,
    }


@router.get("/board")
async def camp_day_board(actor: dict = Depends(require_lead)) -> Dict[str, Any]:
    db = get_db()
    as_of = iso(now_utc())
    camp = await db.camps.find_one({"is_active": True})
    if not camp:
        return _empty_board(as_of, "no_camp")
    today = today_ist_str()
    start, end = ist_day_bounds(today)
    now = now_utc()
    day = await db.camp_days.find_one({"camp_id": camp["_id"], "day_date": today})
    if not day:
        empty = _empty_board(as_of, "no_day")
        empty["camp"] = {"id": str(camp["_id"]), "name": camp["name"]}
        return empty

    camp_filter = {"camp_id": camp["_id"]}
    arrival_filter = {**camp_filter, "arrived_at": {"$gte": start, "$lt": end}}
    arrived, awaiting_print, awaiting_seen, seen_ids, volunteer_rows = await asyncio.gather(
        db.patients.count_documents(arrival_filter),
        db.patients.count_documents({**arrival_filter, "printed_at": None}),
        db.patients.count_documents({**arrival_filter, "printed_at": {"$ne": None}, "seen_at": None}),
        db.patients.distinct("_id", {**camp_filter, "seen_at": {"$gte": start, "$lt": end}}),
        db.patients.aggregate([
            {"$match": arrival_filter},
            {"$group": {"_id": "$arrived_by", "last": {"$max": "$arrived_at"}}},
        ]).to_list(None),
    )
    seen_today = len(seen_ids)
    tx_ids = await db.transcriptions.distinct("_id", {"patient_id": {"$in": seen_ids}}) if seen_ids else []
    backlog = seen_today - len(tx_ids)

    quiet_cutoff = now - timedelta(minutes=15)
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
            "quiet": quiet,
        })
    activity.sort(key=lambda r: r["name"] or "")
    quiet_count = sum(1 for r in activity if r["quiet"])

    fulfil_counts = _empty_board(as_of, "current")["fulfilment"]
    if tx_ids:
        fulfilments = await db.fulfilments.aggregate([
            {"$match": {"transcription_id": {"$in": tx_ids}}},
            {"$group": {"_id": {"item_type": "$item_type", "status": "$status"}, "count": {"$sum": 1}}},
        ]).to_list(None)
        for f in fulfilments:
            bucket = fulfil_counts.get(f["_id"].get("item_type"))
            status = f["_id"].get("status")
            if bucket is not None and status in bucket:
                bucket[status] += f["count"]

    sms_rows = await db.reminder_ledger.aggregate([
        {"$match": {"status": "failed", "created_at": {"$gte": start, "$lt": end}}},
        {"$group": {"_id": "$patient_id", "count": {"$sum": 1}}},
    ]).to_list(None)
    sms_patient_ids = [r["_id"] for r in sms_rows if r["_id"]]
    sms_failures = 0
    if sms_patient_ids:
        camp_set = set(await db.patients.distinct("_id", {"_id": {"$in": sms_patient_ids}, **camp_filter}))
        sms_failures = sum(row["count"] for row in sms_rows if row["_id"] in camp_set)

    ot_day = await db.ot_schedule_days.find_one(
        {"camp_id": camp["_id"], "day_date": {"$gte": today}},
        sort=[("day_date", 1)],
    )
    specs_day = await db.specs_collection_days.find_one(
        {"camp_id": camp["_id"], "day_date": {"$gte": today}, "start_time": {"$gt": ""}, "end_time": {"$gt": ""}},
        sort=[("day_date", 1)],
    )
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
            "venue": specs_day.get("venue"),
            "start_time": specs_day["start_time"],
            "end_time": specs_day["end_time"],
        }

    return {
        "as_of": as_of,
        "state": "current",
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
        "next_ot": next_ot,
        "next_specs": next_specs,
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
