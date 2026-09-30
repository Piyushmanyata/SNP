from helpers import api_error
import asyncio
import hmac
import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from fastapi import APIRouter, Request
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from db import get_db
import helpers
import sms

router = APIRouter(prefix="/api", tags=["cron"])

PAGE_SIZE = 200
SEND_LIMIT = 200
SWEEP_SECONDS = 60
LEASE_SECONDS = 90
REMINDER_TYPES = (("ot", "ot"), ("specs", "specs_made"), ("camp", None))

def _require_cron_secret(request: Request) -> None:
    expected = (os.environ.get("CRON_SECRET") or "").encode()
    got = (request.headers.get("X-Cron-Secret") or "").encode()
    if not expected or not hmac.compare_digest(expected, got):
        raise api_error(401, "UNAUTHORIZED", 'Unauthorized')


async def _gate(db: AsyncDatabase, message_type: str, event_date: str, now: datetime) -> str:
    return await sms.canary(db, message_type, event_date, now)


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


async def _release_lease(db: AsyncDatabase, holder: str, cursor: Any, event_date: str) -> None:
    if _sweep_finished(cursor):
        await db.sms_controls.delete_one({"_id": "reminder_lease", "holder": holder})
        return
    await db.sms_controls.update_one(
        {"_id": "reminder_lease", "holder": holder},
        {"$set": {"holder": None, "expires_at": helpers.now_utc(), "cursor": cursor, "event_date": event_date}},
    )


async def _write_ops(db: AsyncDatabase, *, complete: bool, error: Optional[str] = None) -> None:
    now = helpers.now_utc()
    counts = await sms.status_counts(db)
    paused = await sms.paused_types(db)
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


async def _context(db: AsyncDatabase) -> Tuple[Dict[Any, dict], Dict[str, Optional[str]]]:
    camps = {row["_id"]: row for row in await db.camps.find({}).to_list(None)}
    staff = {
        str(row["_id"]): helpers.normalize_phone(row.get("phone"))
        for row in await db.users.find({}, {"phone": 1}).to_list(None)
    }
    return camps, staff


async def _camp_page(db: AsyncDatabase, event_date: str, last_id: Any, camps: Dict[Any, dict]) -> List[tuple]:
    days = await db.camp_days.find({"day_date": event_date}).to_list(None)
    query: Dict[str, Any] = {"camp_day_id": {"$in": [day["_id"] for day in days]}}
    if last_id not in (None, "done"):
        query["_id"] = {"$gt": last_id}
    patients = await db.patients.find(query).sort("_id", 1).limit(PAGE_SIZE).to_list(PAGE_SIZE)
    rows = []
    for patient in patients:
        rows.append((patient, sms.sms_venue(camps.get(patient.get("camp_id"))), None, patient["_id"]))
    return rows


async def _slip_page(db: AsyncDatabase, item_type: str, event_date: str, last_id: Any) -> List[tuple]:
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
        rows.append((patient, sms.sms_venue(slip), slip.get("collection_end_date"), slip["_id"]))
    return rows


async def _send_fresh(
    db: AsyncDatabase, message_type: str, event_date: str, chosen: List[tuple],
    camps: Dict[Any, dict], staff: Dict[str, Optional[str]], gate: str, deadline: float,
) -> Tuple[int, int, int, bool, bool, int]:
    sem = asyncio.Semaphore(4)

    async def one(patient: dict, venue: str, end_date: Optional[str]) -> str:
        async with sem:
            if time.monotonic() >= deadline:
                return "deferred"
            return await sms.record_and_send(
                db, patient, message_type, event_date, venue, end_date,
                now=helpers.now_utc(), camps=camps, staff_phones=staff, fresh=True,
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
        if outcome in ("skipped", "deferred"):
            continue
        used += 1
        if outcome == "failed":
            failed += 1
        elif outcome in ("sent", "uncertain"):
            sent += 1
        elif outcome == "rejected" and gate == "canary":
            rejected = True
    if rejected:
        await sms.pause_after_rejection(db, message_type, event_date, helpers.now_utc())
    attempted = outcomes.index("deferred") if "deferred" in outcomes else len(outcomes)
    return sent, failed, used, rejected, "deferred" in outcomes, attempted


async def send_d1_reminders() -> Dict[str, Any]:
    if not sms.configured():
        return {"ok": True, "sent": 0, "complete": True, "reason": "msg91_unconfigured"}
    db = get_db()
    holder = await _acquire_lease(db)
    if holder is None:
        await _write_ops(db, complete=False)
        return _result(0, 0, False, True)
    tomorrow = helpers.tomorrow_ist_str()
    lease = await db.sms_controls.find_one({"_id": "reminder_lease"}) or {}
    cursor = dict(lease.get("cursor") or {}) if lease.get("event_date") == tomorrow else {}
    sent = failed = used = 0
    waiting = False
    paused_hit = False
    paused_used = 0
    started = time.monotonic()
    try:
        camps, staff = await _context(db)
        for message_type, item_type in REMINDER_TYPES:
            if time.monotonic() - started >= SWEEP_SECONDS or used >= SEND_LIMIT:
                break
            gate = await _gate(db, message_type, tomorrow, helpers.now_utc())
            if gate == "paused":
                waiting = True
                paused_hit = True
                paused_used += await sms.used(db, message_type, tomorrow)
                continue
            if gate == "waiting":
                waiting = True
                continue
            for row in await sms.due_retries(db, message_type, tomorrow, helpers.now_utc(), SEND_LIMIT):
                if used >= SEND_LIMIT or time.monotonic() - started >= SWEEP_SECONDS:
                    break
                if await sms.abandon_if_gone(db, row):
                    continue
                patient = await db.patients.find_one({"_id": row["patient_id"]})
                if not patient:
                    continue
                slip = await db.deferred_slips.find_one({
                    "patient_id": patient["_id"], "item_type": item_type, "active": True, "collection_date": tomorrow,
                }) if item_type == "specs_made" else None
                outcome = await sms.record_and_send(
                    db, patient, message_type, tomorrow, row.get("venue") or "", (slip or {}).get("collection_end_date"),
                    now=helpers.now_utc(), retry_after=sms.RETRY_AFTER, event_key=row.get("event_key"),
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
                    break
                continue
            last_id = cursor.get(message_type)
            budget = 1 if gate == "canary" else SEND_LIMIT - used
            while budget > 0 and time.monotonic() - started < SWEEP_SECONDS:
                page = (
                    await _camp_page(db, tomorrow, last_id, camps) if item_type is None
                    else await _slip_page(db, item_type, tomorrow, last_id)
                )
                if not page:
                    cursor[message_type] = "done"
                    break
                ids = [patient["_id"] for patient, _venue, _end, _cursor in page if patient]
                have = await sms.recorded(db, ids, message_type, tomorrow)
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
                    page_sent, page_failed, page_used, rejected, deferred, attempted = await _send_fresh(
                        db, message_type, tomorrow, chosen, camps, staff, gate, started + SWEEP_SECONDS,
                    )
                    if not attempted:
                        cursor[message_type] = resume_at
                        break
                    sent += page_sent
                    failed += page_failed
                    used += page_used
                    budget -= page_used
                    last_id = chosen[attempted - 1][3]
                    cursor[message_type] = last_id
                    if rejected or await sms.paused(db, message_type):
                        waiting = True
                        paused_hit = True
                        paused_used = max(paused_used, page_used)
                        break
                    if deferred:
                        break
                    if gate == "canary" and page_used:
                        waiting = True
                        break
                    if last_id == page[-1][3] and len(page) < PAGE_SIZE:
                        cursor[message_type] = "done"
                        break
                    if used >= SEND_LIMIT:
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
        complete = not waiting and all(cursor.get(message_type) == "done" for message_type, _item in REMINDER_TYPES)
    finally:
        await _release_lease(db, holder, cursor, tomorrow)
    await _write_ops(db, complete=complete)
    extra: Dict[str, Any] = {}
    if paused_hit:
        extra["paused"] = True
        extra["used"] = paused_used or used
    return _result(sent, failed, complete, waiting, **extra)


async def drain_outbox() -> Dict[str, Any]:
    db = get_db()
    queued, retried = await sms.sweep(db, helpers.now_utc(), PAGE_SIZE)
    await _write_ops(db, complete=False)
    return {"ok": True, "queued": queued, "retried": retried}


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
