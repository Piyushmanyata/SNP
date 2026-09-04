import io
import csv
from datetime import timedelta
from typing import Any, Dict, List
from bson import ObjectId
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse, JSONResponse
from motor.motor_asyncio import AsyncIOMotorDatabase
from db import get_db
from helpers import iso, ist_day_bounds, now_utc, today_ist_str
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
        return {"volunteers": []}
    entries = await db.roster.find({"camp_id": camp["_id"]}).to_list(1000)
    volunteers = []
    for e in entries:
        eid = str(e["_id"])
        registrations = await db.patients.count_documents(
            {"camp_id": camp["_id"], "created_roster_id": eid}
        )
        arrivals = await db.patients.count_documents(
            {"camp_id": camp["_id"], "arrived_roster_id": eid}
        )
        volunteers.append({
            "name": e["name"],
            "registrations": registrations,
            "arrivals": arrivals,
            "points": registrations + arrivals,
        })
    volunteers.sort(key=lambda x: (-x["points"], x["name"]))
    return {"volunteers": volunteers}


EXPORT_COLUMNS = [
    "reg_no", "full_name", "age", "gender", "phone", "address", "aadhaar_last4",
    "manual_entry", "camp_day", "registered_at", "arrived_at", "seen_at",
    "diagnosis", "bp", "blood_sugar",
    "r_sph", "r_cyl", "r_axis", "l_sph", "l_cyl", "l_axis", "add",
    "medicine", "fixed_power_specs", "spectacles_to_be_made", "ot",
    "ot_day", "ot_venue", "specs_day", "specs_venue",
]


def _line_statuses(fulfilments: dict) -> List[str]:
    return [
        fulfilments.get("medicine", {}).get("status", ""),
        fulfilments.get("specs_fixed", {}).get("status", ""),
        fulfilments.get("specs_made", {}).get("status", ""),
        fulfilments.get("ot", {}).get("status", ""),
    ]


def _diagnosis(t: dict) -> str:
    parts = list(t.get("diagnosis_options") or [])
    if t.get("diagnosis_other"):
        parts.append(t["diagnosis_other"])
    return ";".join(parts)


async def _export_row(db: AsyncIOMotorDatabase, p: dict, day_dates: dict) -> List[Any]:
    t = await db.transcriptions.find_one({"patient_id": p["_id"]}) or {}
    fulfilments = {}
    if t:
        for f in await db.fulfilments.find({"transcription_id": t["_id"]}).to_list(20):
            fulfilments[f["item_type"]] = f
    m = t.get("specs_measurements") or {}
    ot = fulfilments.get("ot", {})
    specs = fulfilments.get("specs_made", {})
    return [
        p.get("reg_no", ""), p.get("full_name", ""), p.get("age", ""),
        p.get("gender", ""), p.get("phone", ""), p.get("address", ""),
        p.get("aadhaar_last4", ""),
        "yes" if (p.get("manual_entry") or p.get("manual_exception")) else "no",
        day_dates.get(p.get("camp_day_id"), ""),
        iso(p.get("created_at")) or "", iso(p.get("arrived_at")) or "", iso(p.get("seen_at")) or "",
        _diagnosis(t), t.get("bp", "") or "", t.get("blood_sugar", "") or "",
        *[m.get(k, "") or "" for k in ("r_sph", "r_cyl", "r_axis", "l_sph", "l_cyl", "l_axis", "add")],
        *_line_statuses(fulfilments),
        ot.get("collection_date", "") or "", ot.get("collection_venue", "") or "",
        specs.get("collection_date", "") or "",
        specs.get("collection_venue", "") or "",
    ]


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
        for p in pts:
            writer.writerow(await _export_row(db, p, day_dates))
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=camp_records.csv"})


@router.get("/board")
async def camp_day_board(actor: dict = Depends(require_lead)) -> Dict[str, Any]:
    db = get_db()
    empty = {
        "camp": None, "day": None, "arrived_today": 0, "seen_today": 0,
        "transcription_backlog": 0, "desks": [],
        "lines": {"medicine": 0, "specs_fixed": 0, "specs_made": 0, "ot": 0},
        "next_ot_day": None, "next_specs_day": None, "sms_failed_today": 0,
    }
    camp = await db.camps.find_one({"is_active": True})
    if not camp:
        return empty
    today = today_ist_str()
    start, end = ist_day_bounds(today)
    now = now_utc()
    day = await db.camp_days.find_one({"camp_id": camp["_id"], "day_date": today})
    arrived_today = await db.patients.count_documents(
        {"camp_id": camp["_id"], "arrived_at": {"$gte": start, "$lt": end}}
    )
    seen_today = await db.patients.count_documents(
        {"camp_id": camp["_id"], "seen_at": {"$gte": start, "$lt": end}}
    )
    seen_rows = await db.patients.find(
        {"camp_id": camp["_id"], "seen_at": {"$gte": start, "$lt": end}}
    ).to_list(100000)
    seen_ids = [p["_id"] for p in seen_rows]
    tx_rows = await db.transcriptions.find({"patient_id": {"$in": seen_ids}}).to_list(100000) if seen_ids else []
    tx_ids = {t["patient_id"] for t in tx_rows}
    backlog = len([i for i in seen_ids if i not in tx_ids])
    desks = []
    users = await db.users.find({"role": "volunteer", "disabled_at": None}).to_list(1000)
    users.sort(key=lambda u: u.get("name") or "")
    for u in users:
        uid = str(u["_id"])
        last_60m = await db.patients.count_documents({
            "arrived_by": uid, "arrived_at": {"$gte": now - timedelta(minutes=60)},
        })
        last_15m = await db.patients.count_documents({
            "arrived_by": uid, "arrived_at": {"$gte": now - timedelta(minutes=15)},
        })
        today_arrivals = await db.patients.find({
            "arrived_by": uid, "arrived_at": {"$gte": start, "$lt": end},
        }).to_list(10000)
        last_at = max((p["arrived_at"] for p in today_arrivals), default=None)
        desks.append({
            "account_id": uid,
            "name": u.get("name"),
            "last_15m": last_15m,
            "last_60m": last_60m,
            "last_arrival_at": iso(last_at),
            "quiet": last_15m == 0,
        })
    lines = {"medicine": 0, "specs_fixed": 0, "specs_made": 0, "ot": 0}
    fulfilments = await db.fulfilments.find(
        {"created_at": {"$gte": start, "$lt": end}}
    ).to_list(100000)
    for f in fulfilments:
        k = f.get("item_type")
        if k in lines:
            lines[k] += 1

    async def _next_day(coll):
        rows = await coll.find({
            "camp_id": camp["_id"], "day_date": {"$gte": today},
        }).to_list(1000)
        if not rows:
            return None
        chosen = min(rows, key=lambda d: d["day_date"])
        return {
            "day_date": chosen["day_date"],
            "seats_left": chosen.get("seat_limit", 0) - chosen.get("seats_taken", 0),
        }

    sms_failed_today = await db.reminder_ledger.count_documents(
        {"status": "failed", "created_at": {"$gte": start, "$lt": end}}
    )
    return {
        "camp": {"id": str(camp["_id"]), "name": camp["name"]},
        "day": {"id": str(day["_id"]), "day_date": day["day_date"]} if day else None,
        "arrived_today": arrived_today,
        "seen_today": seen_today,
        "transcription_backlog": backlog,
        "desks": desks,
        "lines": lines,
        "next_ot_day": await _next_day(db.ot_schedule_days),
        "next_specs_day": await _next_day(db.specs_collection_days),
        "sms_failed_today": sms_failed_today,
    }


@router.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness() -> Dict[str, Any]:
    db = get_db()
    try:
        await db.command("ping")
        n_active = await db.camps.count_documents({"is_active": True})
        if n_active > 1:
            return JSONResponse(status_code=503, content={"ready": False, "reason": "multiple active camps"})
        return {"ready": True, "db": "reachable", "active_camps": n_active}
    except Exception:
        return JSONResponse(status_code=503, content={"ready": False, "reason": "db unreachable"})
