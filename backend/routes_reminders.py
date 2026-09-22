import hmac
import os
from typing import Any, AsyncGenerator, Dict, List, Tuple

from fastapi import APIRouter, HTTPException, Request
from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase

from db import get_db
import helpers
import msg91
import sms

router = APIRouter(prefix="/api", tags=["cron"])

PAGE_SIZE = 500
SEND_LIMIT = 200

Target = Tuple[dict, str, str | None, str | None]


def _require_cron_secret(request: Request) -> None:
    expected = os.environ.get("CRON_SECRET") or ""
    got = request.headers.get("X-Cron-Secret") or ""
    if not expected or not hmac.compare_digest(expected, got):
        raise HTTPException(status_code=401, detail="Unauthorized")


async def _pages(
    collection: AsyncIOMotorCollection, query: Dict[str, Any]
) -> AsyncGenerator[List[dict], None]:
    after: Any = None
    while True:
        scoped = dict(query)
        if after is not None:
            scoped["_id"] = {"$gt": after}
        page = await collection.find(scoped).sort("_id", 1).limit(PAGE_SIZE).to_list(PAGE_SIZE)
        if not page:
            return
        yield page
        if len(page) < PAGE_SIZE:
            return
        after = page[-1]["_id"]


async def _camp_targets(db: AsyncIOMotorDatabase, event_date: str) -> AsyncGenerator[Target, None]:
    days = await db.camp_days.find({"day_date": event_date}).to_list(None)
    for day in days:
        camp = await db.camps.find_one({"_id": day["camp_id"]})
        venue = camp["venue"] if camp else ""
        async for page in _pages(db.patients, {"camp_day_id": day["_id"]}):
            for patient in page:
                yield patient, venue, None, None


async def _token_targets(
    db: AsyncIOMotorDatabase, item_type: str, event_date: str
) -> AsyncGenerator[Target, None]:
    day_collection = db.ot_schedule_days if item_type == "ot" else db.specs_collection_days
    day_field = "ot_schedule_day_id" if item_type == "ot" else "specs_collection_day_id"
    query = {"item_type": item_type, "active": True, "collection_date": event_date}
    async for page in _pages(db.deferred_slips, query):
        for s in page:
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
            yield patient, venue, s.get("collection_start_time"), s.get("collection_end_time")


async def _send_each(
    db: AsyncIOMotorDatabase,
    message_type: str,
    targets: AsyncGenerator[Target, None],
    event_date: str,
    budget: int,
) -> Tuple[int, bool]:
    sent = 0
    complete = True
    try:
        async for patient, venue, start, end in targets:
            if sent >= budget:
                complete = False
                break
            if await sms.send_patient_sms(
                db, patient, message_type, event_date, venue,
                start_time=start, end_time=end,
            ):
                sent += 1
    finally:
        await targets.aclose()
    return sent, complete


async def send_d1_reminders() -> Dict[str, Any]:
    if not msg91.configured():
        return {"ok": True, "sent": 0, "complete": True, "reason": "msg91_unconfigured"}
    today = helpers.today_ist_str()
    tomorrow = helpers.tomorrow_ist_str()
    db = get_db()
    sent = 0
    complete = True
    for message_type, item_type in (("camp", None), ("ot", "ot"), ("specs", "specs_made")):
        if not complete:
            break
        targets = (
            _camp_targets(db, tomorrow) if item_type is None
            else _token_targets(db, item_type, tomorrow)
        )
        dispatched, complete = await _send_each(
            db, message_type, targets, tomorrow, SEND_LIMIT - sent,
        )
        sent += dispatched
    failed = await db.reminder_ledger.count_documents({
        "event_date": tomorrow, "message_type": {"$in": ["camp", "ot", "specs"]}, "status": "failed",
    })
    return {
        "ok": failed == 0, "sent": sent, "failed": failed, "complete": complete,
        "event_date": tomorrow, "send_date": today,
    }


@router.post("/cron/reminders")
async def cron_reminders(request: Request) -> Dict[str, Any]:
    _require_cron_secret(request)
    return await send_d1_reminders()
