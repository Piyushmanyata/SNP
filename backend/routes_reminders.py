import hmac
import os
from typing import Any, Dict, List, Tuple

from fastapi import APIRouter, HTTPException, Request
from motor.motor_asyncio import AsyncIOMotorDatabase

from db import get_db
import helpers
import msg91
import sms

router = APIRouter(prefix="/api", tags=["cron"])


def _require_cron_secret(request: Request) -> None:
    expected = os.environ.get("CRON_SECRET") or ""
    got = request.headers.get("X-Cron-Secret") or ""
    if not expected or not hmac.compare_digest(expected, got):
        raise HTTPException(status_code=401, detail="Unauthorized")


async def _send_each(
    db: AsyncIOMotorDatabase,
    message_type: str,
    targets: List[Tuple],
    event_date: str,
) -> int:
    sent = 0
    for item in targets:
        patient, venue, *window = item
        start = window[0] if len(window) > 0 else None
        end = window[1] if len(window) > 1 else None
        if await sms.send_patient_sms(
            db, patient, message_type, event_date, venue,
            start_time=start, end_time=end,
        ):
            sent += 1
    return sent


async def _camp_targets(db: AsyncIOMotorDatabase, event_date: str) -> List[Tuple[dict, str]]:
    days = await db.camp_days.find({"day_date": event_date}).to_list(2000)
    targets: List[Tuple[dict, str]] = []
    for day in days:
        camp = await db.camps.find_one({"_id": day["camp_id"]})
        venue = camp["venue"] if camp else ""
        patients = await db.patients.find({"camp_day_id": day["_id"]}).to_list(10000)
        targets.extend((p, venue) for p in patients)
    return targets


async def _token_targets(
    db: AsyncIOMotorDatabase, item_type: str, event_date: str
) -> List[Tuple[dict, str, str | None, str | None]]:
    slips = await db.deferred_slips.find({
        "item_type": item_type,
        "active": True,
        "collection_date": event_date,
    }).to_list(10000)
    day_collection = db.ot_schedule_days if item_type == "ot" else db.specs_collection_days
    day_field = "ot_schedule_day_id" if item_type == "ot" else "specs_collection_day_id"
    targets = []
    for s in slips:
        if s.get("cancelled"):
            continue
        patient = await db.patients.find_one({"_id": s["patient_id"]})
        if not patient:
            continue
        venue = s.get("collection_venue") or ""
        if item_type != "specs_made" and s.get(day_field):
            day = await day_collection.find_one({"_id": s[day_field]})
            if day:
                venue = day.get("venue_sms") or day["venue"]
        targets.append((
            patient, venue,
            s.get("collection_start_time"), s.get("collection_end_time"),
        ))
    return targets


async def send_d1_reminders() -> Dict[str, Any]:
    if not msg91.configured():
        return {"ok": True, "sent": 0, "reason": "msg91_unconfigured"}
    today = helpers.today_ist_str()
    tomorrow = helpers.tomorrow_ist_str()
    db = get_db()
    sent = await _send_each(db, "camp", await _camp_targets(db, tomorrow), tomorrow)
    sent += await _send_each(db, "ot", await _token_targets(db, "ot", tomorrow), tomorrow)
    sent += await _send_each(db, "specs", await _token_targets(db, "specs_made", tomorrow), tomorrow)
    failed = await db.reminder_ledger.count_documents({
        "event_date": tomorrow, "message_type": {"$in": ["camp", "ot", "specs"]}, "status": "failed",
    })
    return {"ok": failed == 0, "sent": sent, "failed": failed, "event_date": tomorrow, "send_date": today}


@router.post("/cron/reminders")
async def cron_reminders(request: Request) -> Dict[str, Any]:
    _require_cron_secret(request)
    return await send_d1_reminders()
