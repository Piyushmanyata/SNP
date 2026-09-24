from helpers import api_error
import asyncio
import hmac
import os
import time
from datetime import timedelta
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple
from uuid import uuid4

from fastapi import APIRouter, Request
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from db import get_db
import helpers
import msg91
import sms

router = APIRouter(prefix="/api", tags=["cron"])

PAGE_SIZE = 200
SEND_LIMIT = 200
SWEEP_SECONDS = 60
LEASE_SECONDS = 90
CANARY_WAIT = timedelta(minutes=10)
REMINDER_TYPES = (("ot", "ot"), ("specs", "specs_made"), ("camp", None))

Target = Tuple[dict, str, str | None]


def _require_cron_secret(request: Request) -> None:
    expected = os.environ.get("CRON_SECRET") or ""
    got = request.headers.get("X-Cron-Secret") or ""
    if not expected or not hmac.compare_digest(expected, got):
        raise api_error(401, "UNAUTHORIZED", 'Unauthorized')


async def _pages(
    collection: AsyncCollection, query: Dict[str, Any]
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


async def _camp_targets(db: AsyncDatabase, event_date: str) -> AsyncGenerator[Target, None]:
    days = await db.camp_days.find({"day_date": event_date}).to_list(None)
    for day in days:
        camp = await db.camps.find_one({"_id": day["camp_id"]})
        venue = (camp.get("venue_sms") or camp["venue"]) if camp else ""
        async for page in _pages(db.patients, {"camp_day_id": day["_id"]}):
            for patient in page:
                yield patient, venue, None


async def _token_targets(
    db: AsyncDatabase, item_type: str, event_date: str
) -> AsyncGenerator[Target, None]:
    query = {"item_type": item_type, "active": True, "collection_date": event_date}
    async for page in _pages(db.deferred_slips, query):
        for s in page:
            patient = await db.patients.find_one({"_id": s["patient_id"]})
            if not patient:
                continue
            venue = s.get("collection_venue_sms") or s.get("collection_venue") or ""
            if item_type == "ot" and s.get("ot_schedule_day_id"):
                day = await db.ot_schedule_days.find_one({"_id": s["ot_schedule_day_id"]})
                if day:
                    venue = day.get("venue_sms") or day["venue"]
            yield patient, venue, s.get("collection_end_date")


async def _gate(db: AsyncDatabase, message_type: str, event_date: str) -> str:
    control = await db.sms_controls.find_one({"_id": message_type}) or {}
    if control.get("paused"):
        return "paused"
    return await _canary(db, message_type, event_date, control.get("resumed_at"))


async def _canary(db: AsyncDatabase, message_type: str, event_date: str, resumed_at: Any) -> str:
    query: Dict[str, Any] = {
        "message_type": message_type, "event_date": event_date,
        "status": {"$in": ["sent", "uncertain", "rejected"]},
    }
    if resumed_at:
        query["created_at"] = {"$gte": resumed_at}
    first = await db.reminder_ledger.find(query).sort("created_at", 1).limit(1).to_list(1)
    if not first:
        return "canary"
    row = first[0]
    settled = row["status"] == "rejected" or row.get("delivery")
    if settled or helpers.as_utc(row["created_at"]) <= helpers.now_utc() - CANARY_WAIT:
        return "open"
    return "waiting"


async def _acquire_lease(db: AsyncDatabase) -> Optional[str]:
    now = helpers.now_utc()
    holder = uuid4().hex
    expires = now + timedelta(seconds=LEASE_SECONDS)
    updated = await db.sms_controls.update_one(
        {"_id": "reminder_lease", "expires_at": {"$lte": now}},
        {"$set": {"holder": holder, "expires_at": expires}},
    )
    if updated.matched_count:
        return holder
    try:
        await db.sms_controls.insert_one({
            "_id": "reminder_lease", "holder": holder, "expires_at": expires, "cursor": None,
        })
    except DuplicateKeyError:
        return None
    return holder


def _sweep_finished(cursor: Any) -> bool:
    return isinstance(cursor, dict) and all(cursor.get(name) == "done" for name, _item in REMINDER_TYPES)


async def _release_lease(db: AsyncDatabase, holder: str, cursor: Any) -> None:
    if _sweep_finished(cursor):
        await db.sms_controls.delete_one({"_id": "reminder_lease", "holder": holder})
        return
    await db.sms_controls.update_one(
        {"_id": "reminder_lease", "holder": holder},
        {"$set": {"holder": None, "expires_at": helpers.now_utc(), "cursor": cursor}},
    )


def _cursor_state(doc: Optional[dict]) -> Tuple[int, Any]:
    cursor = (doc or {}).get("cursor") or {}
    return int(cursor.get("type_index") or 0), cursor.get("last_id")


async def _write_ops(db: AsyncDatabase, *, complete: bool, error: Optional[str] = None) -> None:
    now = helpers.now_utc()
    counts = {
        status: await db.reminder_ledger.count_documents({"status": status})
        for status in ("queued", "failed", "uncertain")
    }
    paused = [
        row["_id"] for row in await db.sms_controls.find({"paused": True}).to_list(None)
        if row["_id"] != "reminder_lease"
    ]
    fields: Dict[str, Any] = {
        "last_call_at": now, "last_error": error,
        "queued": counts["queued"], "failed": counts["failed"], "uncertain": counts["uncertain"],
        "paused_types": paused,
    }
    if complete:
        ist = helpers.now_ist()
        slot = "20" if ist.hour >= 20 else "10"
        fields["last_complete_at"] = now
        fields[f"sweeps.{ist.date().isoformat()}.{slot}"] = True
    await db.ops_status.update_one({"_id": "reminders"}, {"$set": fields}, upsert=True)


def _result(sent: int, failed: int, complete: bool, waiting: bool, **extra: Any) -> Dict[str, Any]:
    today = helpers.today_ist_str()
    tomorrow = helpers.tomorrow_ist_str()
    body = {
        "ok": failed == 0, "sent": sent, "failed": failed, "complete": complete, "waiting": waiting,
        "event_date": tomorrow, "send_date": today,
    }
    body.update(extra)
    return body


async def _context(db: AsyncDatabase) -> Tuple[Dict[Any, dict], Dict[str, Optional[str]], Dict[Any, dict]]:
    camps = {row["_id"]: row for row in await db.camps.find({}).to_list(None)}
    staff = {
        str(row["_id"]): helpers.normalize_phone(row.get("phone"))
        for row in await db.users.find({}, {"phone": 1}).to_list(None)
    }
    days = {row["_id"]: row for row in await db.ot_schedule_days.find({}).to_list(None)}
    return camps, staff, days


async def _due_failures(db: AsyncDatabase, message_type: str, event_date: str) -> List[dict]:
    return await db.reminder_ledger.find({
        "message_type": message_type, "event_date": event_date, "status": "failed",
        "created_at": {"$lte": helpers.now_utc() - sms.RETRY_AFTER},
    }).to_list(SEND_LIMIT)


async def _abandon_if_gone(db: AsyncDatabase, row: dict) -> bool:
    patient = await db.patients.find_one({"_id": row.get("patient_id")})
    message_type = row.get("message_type")
    live = False
    if patient is not None and message_type in ("ot", "specs"):
        item = "ot" if message_type == "ot" else "specs_made"
        slip = await db.deferred_slips.find_one({
            "patient_id": patient["_id"], "item_type": item, "active": True,
            "collection_date": row.get("event_date"),
        })
        live = bool(slip)
    elif patient is not None:
        live = True
    if live:
        return False
    await db.reminder_ledger.update_one({"_id": row["_id"], "status": "failed"}, {"$set": {"status": "abandoned"}})
    return True


async def _camp_page(db: AsyncDatabase, event_date: str, last_id: Any, camps: Dict[Any, dict]) -> List[tuple]:
    days = await db.camp_days.find({"day_date": event_date}).to_list(None)
    query: Dict[str, Any] = {"camp_day_id": {"$in": [day["_id"] for day in days]}}
    if last_id not in (None, "done"):
        query["_id"] = {"$gt": last_id}
    patients = await db.patients.find(query).sort("_id", 1).limit(PAGE_SIZE).to_list(PAGE_SIZE)
    rows = []
    for patient in patients:
        camp = camps.get(patient.get("camp_id")) or {}
        rows.append((patient, camp.get("venue_sms") or camp.get("venue") or "", None, patient["_id"]))
    return rows


async def _slip_page(
    db: AsyncDatabase, item_type: str, event_date: str, last_id: Any, ot_days: Dict[Any, dict],
) -> List[tuple]:
    query: Dict[str, Any] = {"item_type": item_type, "active": True, "collection_date": event_date}
    if last_id not in (None, "done"):
        query["_id"] = {"$gt": last_id}
    slips = await db.deferred_slips.find(query).sort("_id", 1).limit(PAGE_SIZE).to_list(PAGE_SIZE)
    if not slips:
        return []
    patients = {
        row["_id"]: row
        for row in await db.patients.find({"_id": {"$in": [slip["patient_id"] for slip in slips]}}).to_list(len(slips))
    }
    rows = []
    for slip in slips:
        patient = None if slip.get("cancelled") else patients.get(slip["patient_id"])
        venue = slip.get("collection_venue_sms") or slip.get("collection_venue") or ""
        day = ot_days.get(slip.get("ot_schedule_day_id"))
        if day:
            venue = day.get("venue_sms") or day["venue"]
        rows.append((patient, venue, slip.get("collection_end_date"), slip["_id"]))
    return rows


async def _send_fresh(
    db: AsyncDatabase, message_type: str, event_date: str, chosen: List[tuple],
    camps: Dict[Any, dict], staff: Dict[str, Optional[str]], gate: str,
) -> Tuple[int, int, int, bool]:
    sem = asyncio.Semaphore(4)

    async def one(patient: dict, venue: str, end_date: Optional[str]) -> str:
        async with sem:
            return await sms.deliver_patient_sms(
                db, patient, message_type, event_date, venue, end_date,
                retry_after=sms.RETRY_AFTER, camps=camps, staff_phones=staff, fresh=True,
            )

    first = await one(*chosen[0][:3])
    outcomes = [first]
    if first not in ("paused",) and not (gate == "canary" and first == "rejected") and len(chosen) > 1:
        if not await sms.paused(db, message_type):
            outcomes.extend(await asyncio.gather(*(
                one(patient, venue, end_date) for patient, venue, end_date, _cursor in chosen[1:]
            )))
    sent = failed = used = 0
    rejected = False
    for outcome in outcomes:
        if outcome == "skipped":
            continue
        used += 1
        if outcome == "failed":
            failed += 1
        elif outcome in ("sent", "uncertain"):
            sent += 1
        elif outcome == "rejected" and gate == "canary":
            rejected = True
    if rejected:
        row = await db.reminder_ledger.find({
            "message_type": message_type, "event_date": event_date, "status": "rejected",
        }).sort("created_at", -1).limit(1).to_list(1)
        if row:
            await sms._pause(db, row[0], row[0].get("error") or "Rejected")
    return sent, failed, used, rejected


async def send_d1_reminders() -> Dict[str, Any]:
    if not msg91.configured():
        return {"ok": True, "sent": 0, "complete": True, "reason": "msg91_unconfigured"}
    db = get_db()
    holder = await _acquire_lease(db)
    if holder is None:
        await _write_ops(db, complete=False)
        return _result(0, 0, False, True)
    lease = await db.sms_controls.find_one({"_id": "reminder_lease"})
    cursor = dict((lease or {}).get("cursor") or {})
    sent = failed = used = 0
    waiting = False
    paused_hit = False
    paused_used = 0
    complete = True
    started = time.monotonic()
    tomorrow = helpers.tomorrow_ist_str()
    try:
        camps, staff, ot_days = await _context(db)
        for message_type, item_type in REMINDER_TYPES:
            if time.monotonic() - started >= SWEEP_SECONDS or used >= SEND_LIMIT:
                complete = False
                break
            gate = await _gate(db, message_type, tomorrow)
            if gate == "paused":
                waiting = True
                complete = False
                paused_hit = True
                paused_used += await db.reminder_ledger.count_documents({
                    "message_type": message_type, "event_date": tomorrow,
                    "status": {"$in": ["sent", "rejected", "uncertain", "failed"]},
                })
                continue
            if gate == "waiting":
                waiting = True
                complete = False
                continue
            for row in await _due_failures(db, message_type, tomorrow):
                if used >= SEND_LIMIT or time.monotonic() - started >= SWEEP_SECONDS:
                    complete = False
                    break
                if await _abandon_if_gone(db, row):
                    continue
                patient = await db.patients.find_one({"_id": row["patient_id"]})
                if not patient:
                    continue
                outcome = await sms.deliver_patient_sms(
                    db, patient, message_type, tomorrow, row.get("venue") or "",
                    retry_after=sms.RETRY_AFTER, event_key=row.get("event_key"),
                    camps=camps, staff_phones=staff,
                )
                if outcome == "skipped":
                    continue
                used += 1
                if outcome == "failed":
                    failed += 1
                elif outcome in ("sent", "uncertain"):
                    sent += 1
            if cursor.get(message_type) == "done" or used >= SEND_LIMIT:
                if used >= SEND_LIMIT:
                    complete = False
                    break
                continue
            last_id = cursor.get(message_type)
            budget = 1 if gate == "canary" else SEND_LIMIT - used
            while budget > 0 and time.monotonic() - started < SWEEP_SECONDS:
                page = (
                    await _camp_page(db, tomorrow, last_id, camps) if item_type is None
                    else await _slip_page(db, item_type, tomorrow, last_id, ot_days)
                )
                if not page:
                    cursor[message_type] = "done"
                    break
                ids = [patient["_id"] for patient, _venue, _end, _cursor in page if patient]
                known = await db.reminder_ledger.find({
                    "patient_id": {"$in": ids}, "message_type": message_type, "event_date": tomorrow,
                }).to_list(max(len(ids), 1)) if ids else []
                have = {row["patient_id"] for row in known}
                chosen = []
                for patient, venue, end_date, cursor_id in page:
                    last_id = cursor_id
                    if not patient or patient["_id"] in have:
                        continue
                    if not sms.valid_phone(patient.get("phone_normalized") or patient.get("phone")):
                        continue
                    chosen.append((patient, venue, end_date, cursor_id))
                    if len(chosen) == budget:
                        break
                if chosen:
                    resume_at = cursor.get(message_type)
                    page_sent, page_failed, page_used, rejected = await _send_fresh(
                        db, message_type, tomorrow, chosen, camps, staff, gate,
                    )
                    if page_used == 0:
                        cursor[message_type] = resume_at
                        complete = False
                        break
                    sent += page_sent
                    failed += page_failed
                    used += page_used
                    budget -= page_used
                    last_id = chosen[min(page_used, len(chosen)) - 1][3]
                    cursor[message_type] = last_id
                    if rejected or await sms.paused(db, message_type):
                        waiting = True
                        complete = False
                        paused_hit = True
                        paused_used = max(paused_used, page_used)
                        break
                    if gate == "canary":
                        waiting = True
                        complete = False
                        break
                    if last_id == page[-1][3] and len(page) < PAGE_SIZE:
                        cursor[message_type] = "done"
                        break
                    if used >= SEND_LIMIT:
                        complete = False
                        break
                if len(page) < PAGE_SIZE and len(chosen) < budget:
                    cursor[message_type] = "done"
                    break
                if not chosen and len(page) == PAGE_SIZE:
                    if cursor.get(message_type) == page[-1][3]:
                        cursor[message_type] = "done"
                        break
                    cursor[message_type] = page[-1][3]
                    last_id = page[-1][3]
                    continue
                if not chosen:
                    cursor[message_type] = "done"
                    break
            if gate == "open" and cursor.get(message_type) != "done" and used >= SEND_LIMIT:
                break
        if all(cursor.get(message_type) == "done" for message_type, _item in REMINDER_TYPES) and not waiting:
            complete = True
    finally:
        await _release_lease(db, holder, cursor)
    await _write_ops(db, complete=complete and not waiting)
    extra: Dict[str, Any] = {}
    if paused_hit:
        extra["paused"] = True
        extra["used"] = paused_used or used
    return _result(sent, failed, complete, waiting, **extra)


async def drain_outbox() -> Dict[str, Any]:
    db = get_db()
    now = helpers.now_utc()
    await db.reminder_ledger.update_many(
        {"status": "pending", "created_at": {"$lte": now - timedelta(minutes=5)}},
        {"$set": {"status": "uncertain"}},
    )
    queued = await db.reminder_ledger.find({
        "status": "queued", "created_at": {"$lte": now - timedelta(seconds=30)},
    }).limit(PAGE_SIZE).to_list(PAGE_SIZE)
    failed_rows = await db.reminder_ledger.find({
        "status": "failed", "retry_after": {"$lte": now},
    }).limit(PAGE_SIZE).to_list(PAGE_SIZE)
    sem = asyncio.Semaphore(4)

    async def send_one(row_id: Any) -> None:
        async with sem:
            await sms.send_queued(db, row_id)

    await asyncio.gather(*(send_one(row["_id"]) for row in queued))
    retried = 0
    for row in failed_rows:
        if await _abandon_if_gone(db, row):
            continue
        await db.reminder_ledger.update_one(
            {"_id": row["_id"], "status": "failed"}, {"$set": {"status": "queued"}},
        )
        await send_one(row["_id"])
        retried += 1
    await _write_ops(db, complete=False)
    return {"ok": True, "queued": len(queued), "retried": retried}


@router.post("/cron/reminders")
async def cron_reminders(request: Request) -> Dict[str, Any]:
    _require_cron_secret(request)
    return await send_d1_reminders()


@router.post("/cron/heartbeat")
async def cron_heartbeat(request: Request) -> Dict[str, bool]:
    _require_cron_secret(request)
    await get_db().ops_status.update_one(
        {"_id": "reminders"}, {"$set": {"heartbeat_at": helpers.now_utc()}}, upsert=True,
    )
    return {"ok": True}


@router.post("/cron/outbox")
async def cron_outbox(request: Request) -> Dict[str, Any]:
    _require_cron_secret(request)
    return await drain_outbox()
