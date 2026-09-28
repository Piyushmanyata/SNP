import asyncio
import logging
import re
import string
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

import helpers
import msg91
from db import aggregate_list

logger = logging.getLogger(__name__)

REGISTRATION_CONFIRMATION = "Sikar Zilla Welfare Trust के {camp_no}वें नेत्र शिविर में आपका पंजीकरण हो गया है। क्रमांक: {reg_no} दिनांक: {date} शिविर स्थल: {venue}। कृपया शिविर के दिन अपना आधार कार्ड अवश्य साथ लाएँ।"
CAMP_REMINDER = "कल ({date}) को Sikar Zilla Welfare Trust के {camp_no} वें नेत्र शिविर में आपका नेत्र परीक्षण है। कृपया समय पर {venue} पहुँचें। यह टोकन शिविर स्थल पर दिखाएँ। क्रमांक: {reg_no}। कृपया शिविर के दिन अपना आधार कार्ड अवश्य साथ लाएँ।"
OT_TOKEN = "Sikar Zilla Welfare Trust के {camp_no} वें नेत्र शिविर में आपका ऑपरेशन {date} को निर्धारित हुआ है। पर्चा, टोकन ({reg_no}), आधार कार्ड, राशन कार्ड और मोबाइल नंबर अवश्य साथ लाएँ। स्थल: {venue}।"
OT_REMINDER = "कल ({date}) को Sikar Zilla Welfare Trust के {camp_no} वें नेत्र शिविर में आपका नेत्र ऑपरेशन निर्धारित है। पर्चा, टोकन ({reg_no}), आधार कार्ड, राशन कार्ड और मोबाइल नंबर साथ अवश्य लाएँ। स्थल: {venue}।"
SPECS_PICKUP_START_TIME = "10:00"
SPECS_PICKUP_END_TIME = "17:00"
SPECS_TOKEN = "Sikar Zilla Welfare Trust के {camp_no} वें नेत्र शिविर में जाँच के बाद आपके लिए बनाया गया चश्मा {date} से {end_date} के बीच {venue} पर आपको दिया जाएगा। आपका चश्मा टोकन क्रमांक: {reg_no}।"
SPECS_REMINDER = "Sikar Zilla Welfare Trust के {camp_no} वें नेत्र शिविर में बना आपका चश्मा तैयार है। कृपया {date} से {end_date} के बीच {venue} पर आकर प्राप्त करें। टोकन क्रमांक {reg_no} अवश्य साथ लाएँ।"
OT_CHANGE = "Sikar Zilla Welfare Trust के {camp_no} वें नेत्र शिविर में आपके ऑपरेशन की तारीख या स्थान बदल गया है। नई तारीख: {date}। स्थल: {venue}। पुराने टोकन पर लिखी तारीख और स्थान अब मान्य नहीं हैं। क्रमांक: {reg_no}।"
SPECS_CHANGE = "Sikar Zilla Welfare Trust के {camp_no} वें नेत्र शिविर में आपके चश्मे लेने की तारीख या स्थान बदल गया है। चश्मा {date} से {end_date} तक प्रतिदिन 10:00 AM से 5:00 PM तक {venue} में मिलेगा। पुराने टोकन पर लिखी तारीख और स्थान अब मान्य नहीं हैं। क्रमांक: {reg_no}।"

MESSAGE_COPY = {
    "registration": REGISTRATION_CONFIRMATION,
    "camp": CAMP_REMINDER,
    "ot_token": OT_TOKEN,
    "ot": OT_REMINDER,
    "specs_token": SPECS_TOKEN,
    "specs": SPECS_REMINDER,
    "ot_change": OT_CHANGE,
    "specs_change": SPECS_CHANGE,
}
RETRY_AFTER = timedelta(minutes=10)
VARIABLE_LIMIT = 30
SMS_VENUE_MIN = 3
_LINK = re.compile(r"https?://|www\.|\.(?:com|in|org|net|io|co|info|app|link|ly|me)\b", re.IGNORECASE)
_PHONE = re.compile(r"\d(?:[\s-]?\d){6,}")
_PLACEHOLDERS = {"na", "n/a", "nil", "none", "null", "tbd", "tba", "test"}
REPORT_STATUS = {"1": "delivered", "2": "failed", "9": "failed", "16": "failed", "17": "failed", "20": "failed", "25": "failed"}
_DLT_STATUS = {"16", "25"}
_DLT_REASON = re.compile(r"dlt|template|header|entity|scrub|consent", re.IGNORECASE)


def clean_sms_venue(raw: Optional[str]) -> str:
    return " ".join((raw or "").split())


def sms_venue_problem(venue: str) -> Optional[str]:
    if not SMS_VENUE_MIN <= len(venue) <= VARIABLE_LIMIT:
        return f"SMS venue must be {SMS_VENUE_MIN} to {VARIABLE_LIMIT} characters"
    if _LINK.search(venue):
        return "SMS venue must not contain a link"
    if _PHONE.search(venue):
        return "SMS venue must not contain a phone number"
    if venue.strip(" .-").casefold() in _PLACEHOLDERS:
        return "SMS venue must name the place, not a placeholder"
    return None


def valid_phone(raw: Optional[str]) -> Optional[str]:
    n = helpers.normalize_phone(raw)
    if not n or helpers.is_dummy_phone(n):
        return None
    return n


QUEUED_RESEND_AFTER = timedelta(seconds=30)
PENDING_UNCERTAIN_AFTER = timedelta(minutes=5)
THROTTLE_BACKOFF = timedelta(minutes=5)
CANARY_WAIT = timedelta(minutes=10)
MAX_ATTEMPTS = 3
REGISTRATION_DAILY_CAP = 6
NOTICE_TYPES = ("ot_change", "specs_change")

_provider: Any = msg91
SEND_SECONDS = 10
_sends = ThreadPoolExecutor(max_workers=8, thread_name_prefix="sms-send")


def use_provider(adapter: Any) -> Any:
    """Installs the SMS provider adapter and returns the one it replaced."""
    global _provider
    previous, _provider = _provider, adapter
    return previous


def configured() -> bool:
    return bool(_provider.configured())


def template_id(message_type: str) -> str:
    return _provider.template_id(message_type)


def token_key(token: dict) -> str:
    return str(token["_id"])


def edit_key(revision: Any) -> str:
    return f"edit:{revision}"


async def _over_daily_cap(db: AsyncDatabase, number: str, now: datetime) -> bool:
    start, end = helpers.ist_day_bounds(now.astimezone(helpers.IST).date().isoformat())
    return await db.reminder_ledger.count_documents({
        "number": number, "message_type": "registration", "status": {"$ne": "skipped"},
        "created_at": {"$gte": start, "$lt": end},
    }, limit=REGISTRATION_DAILY_CAP) >= REGISTRATION_DAILY_CAP


async def paused(db: AsyncDatabase, message_type: str, session=None) -> bool:
    control = await db.sms_controls.find_one({"_id": message_type}, session=session)
    return bool(control and control.get("paused"))


async def controls(db: AsyncDatabase) -> Dict[str, dict]:
    return {row["_id"]: row for row in await db.sms_controls.find({}).to_list(None)}


async def paused_types(db: AsyncDatabase) -> List[str]:
    return [row["_id"] for row in await db.sms_controls.find({"paused": True}, {"_id": 1}).to_list(None)]


async def _claim(
    db: AsyncDatabase,
    patient_id: Any,
    message_type: str,
    event_date: str,
    event_key: Optional[str],
    number: str,
    venue: str,
    copy: str,
    now: datetime,
    retry_after: Optional[timedelta] = None,
    camp_id: Any = None,
    variables: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    existing = await db.reminder_ledger.find_one({
        "patient_id": patient_id,
        "message_type": message_type,
        "event_date": event_date,
        "event_key": event_key,
    })
    if existing:
        status = existing.get("status")
        if status == "rejected":
            control = await db.sms_controls.find_one({"_id": message_type}) or {}
            resumed_at = control.get("resumed_at")
            if (not resumed_at or existing.get("resumed_retry")
                    or helpers.as_utc(existing["created_at"]) >= helpers.as_utc(resumed_at)):
                return None
        elif status not in ("failed", "paused"):
            return None
        attempts = int(existing.get("attempts") or 0)
        if attempts >= MAX_ATTEMPTS:
            await db.reminder_ledger.update_one(
                {"_id": existing["_id"], "status": status},
                {"$set": {"status": "abandoned"}},
            )
            return None
        retryable: Dict[str, Any] = {"_id": existing["_id"], "status": status}
        if retry_after and status == "failed":
            retryable["created_at"] = {"$lte": now - retry_after}
        fields = {
            "status": "pending", "attempts": attempts + 1, "created_at": now,
            "copy": copy, "number": number, "venue": venue, "camp_id": camp_id,
            "variables": variables or {},
        }
        if status == "rejected":
            fields["resumed_retry"] = True
        return await db.reminder_ledger.find_one_and_update(
            retryable, {"$set": fields}, return_document=True,
        )
    doc = {
        "patient_id": patient_id,
        "message_type": message_type,
        "event_date": event_date,
        "event_key": event_key,
        "number": number,
        "venue": venue,
        "copy": copy,
        "status": "queued",
        "variables": variables or {},
        "attempts": 0,
        "provider_id": None,
        "camp_id": camp_id,
        "created_at": now,
    }
    try:
        res = await db.reminder_ledger.insert_one(doc)
    except DuplicateKeyError:
        return None
    doc["_id"] = res.inserted_id
    return doc


async def _record_unsent(
    db: AsyncDatabase, patient_id: Any, message_type: str, event_date: str, event_key: Optional[str],
    number: str, venue: str, copy: str, status: str, now: datetime, reason: Optional[str] = None,
    camp_id: Any = None,
) -> None:
    try:
        await db.reminder_ledger.insert_one({
            "patient_id": patient_id, "message_type": message_type, "event_date": event_date,
            "event_key": event_key, "camp_id": camp_id,
            "number": number, "venue": venue, "copy": copy, "status": status, "attempts": 0,
            "provider_id": None, "created_at": now,
            **({"reason": reason} if reason else {}),
        })
    except DuplicateKeyError:
        pass


def _template_variables(template: str, values: Dict[str, Any]) -> Dict[str, Any]:
    return {name: values[name] for _, name, _, _ in string.Formatter().parse(template) if name}


async def _recipients(db: AsyncDatabase, patients: List[dict], session=None) -> Tuple[Dict[Any, dict], Dict[str, Optional[str]]]:
    """The camps and registrar phones a batch of patient SMS needs, fetched once."""
    camp_ids = list({p["camp_id"] for p in patients if p.get("camp_id")})
    registrar_ids = list({ObjectId(str(p["created_by"])) for p in patients
                          if p.get("created_by") and ObjectId.is_valid(str(p["created_by"]))})
    camps = await db.camps.find({"_id": {"$in": camp_ids}}, session=session).to_list(None) if camp_ids else []
    staff = await db.users.find(
        {"_id": {"$in": registrar_ids}}, {"phone": 1}, session=session,
    ).to_list(None) if registrar_ids else []
    return ({c["_id"]: c for c in camps},
            {str(u["_id"]): helpers.normalize_phone(u.get("phone")) for u in staff})


def _compose(
    patient: dict,
    message_type: str,
    event_date: str,
    venue: str,
    end_date: Optional[str],
    camps: Dict[Any, dict],
    staff_phones: Dict[str, Optional[str]],
) -> Optional[Tuple[str, Dict[str, Any], str]]:
    """The number, DLT variables and copy of a patient SMS, or None when it must not be sent."""
    if not configured() or not template_id(message_type):
        return None
    number = valid_phone(patient.get("phone_normalized") or patient.get("phone"))
    reg_no = patient.get("reg_no")
    if not number or reg_no is None:
        return None
    if staff_phones.get(str(patient.get("created_by"))) == number:
        return None
    camp = camps.get(patient.get("camp_id")) or {}
    template = MESSAGE_COPY[message_type]
    variables = _template_variables(template, {
        "reg_no": reg_no,
        "camp_no": str(camp.get("camp_number") or ""),
        "date": helpers.display_date(event_date),
        "end_date": helpers.display_date(end_date or event_date),
        "venue": venue,
    })
    missing = [name for name, value in variables.items() if value == ""]
    if missing:
        logger.warning("Patient SMS %s not sent: no %s", message_type, ", ".join(missing))
        return None
    too_long = [name for name, value in variables.items() if len(str(value)) > VARIABLE_LIMIT]
    if too_long:
        logger.warning("Patient SMS %s not sent: %s exceeds DLT variable limit", message_type, ", ".join(too_long))
        return None
    venue_problem = sms_venue_problem(str(venue))
    if venue_problem:
        logger.warning("Patient SMS %s not sent: %s", message_type, venue_problem)
        return None
    return number, variables, template.format(**variables)


async def _submit(message_type: str, number: str, variables: Dict[str, Any]) -> str:
    """Calls the provider on the SMS threads: up to SEND_SECONDS to get a thread, then SEND_SECONDS to answer (ADR 0096).

    A call still waiting for a thread is withdrawn and raises Unsent, so it can be tried again. A call handed to the
    provider that does not answer raises TimeoutError and is settled uncertain, never sent twice.
    """
    loop = asyncio.get_running_loop()
    lock = threading.Lock()
    handed = asyncio.Event()
    state = "queued"

    def call() -> str:
        nonlocal state
        with lock:
            if state == "withdrawn":
                raise msg91.Unsent("withdrawn before it reached the provider")
            state = "handed"
        loop.call_soon_threadsafe(handed.set)
        return _provider.send(message_type, number, variables)

    future = loop.run_in_executor(_sends, call)
    try:
        await asyncio.wait_for(handed.wait(), SEND_SECONDS)
    except TimeoutError:
        with lock:
            if state == "queued":
                state = "withdrawn"
                raise msg91.Unsent(f"no free sender within {SEND_SECONDS} s")
    done, _pending = await asyncio.wait({future}, timeout=SEND_SECONDS)
    if not done:
        raise TimeoutError(f"MSG91 did not answer within {SEND_SECONDS} s")
    return future.result()


async def _settle(db: AsyncDatabase, row: Dict[str, Any], variables: Dict[str, Any], now: datetime) -> str:
    """Submits one pending intent and records the provider's outcome as its status."""
    update: Dict[str, Any]
    try:
        provider_id = await _submit(row["message_type"], row["number"], variables)
    except msg91.Throttled as exc:
        update = {"status": "failed", "error": str(exc)[:200], "retry_after": now + THROTTLE_BACKOFF}
    except msg91.Unsent as exc:
        update = {"status": "failed", "error": str(exc)[:200]}
    except msg91.Rejected as exc:
        update = {"status": "rejected", "error": str(exc)[:200]}
    except Exception as exc:
        update = {"status": "uncertain", "error": f"{type(exc).__name__}: {exc}"[:200]}
    else:
        update = {"status": "sent", "provider_id": provider_id}
    if update["status"] != "sent":
        logger.warning("Patient SMS %s %s: %s", row["message_type"], update["status"], update["error"])
    try:
        await db.reminder_ledger.update_one({"_id": row["_id"]}, {"$set": update})
    except Exception:
        logger.exception("Could not record patient SMS %s", update["status"])
    return update["status"]


async def record_and_send(
    db: AsyncDatabase,
    patient: dict,
    message_type: str,
    event_date: str,
    venue: str,
    end_date: Optional[str] = None,
    *,
    now: datetime,
    retry_after: Optional[timedelta] = None,
    event_key: Optional[str] = None,
    camps: Optional[Dict[Any, dict]] = None,
    staff_phones: Optional[Dict[str, Optional[str]]] = None,
    fresh: bool = False,
) -> str:
    """Returns sent, failed, uncertain, rejected, paused, or skipped. Never raises."""
    row = None
    venue = clean_sms_venue(venue)
    try:
        if camps is None or staff_phones is None:
            camps, staff_phones = await _recipients(db, [patient])
        composed = _compose(patient, message_type, event_date, venue, end_date, camps, staff_phones)
        if not composed:
            return "skipped"
        number, variables, copy = composed
        if await paused(db, message_type):
            await _record_unsent(
                db, patient["_id"], message_type, event_date, event_key, number, venue, copy, "paused", now,
                camp_id=patient.get("camp_id"),
            )
            return "paused"
        if message_type == "registration" and await _over_daily_cap(db, number, now):
            await _record_unsent(
                db, patient["_id"], message_type, event_date, event_key, number, venue, copy, "skipped", now,
                "daily_cap", camp_id=patient.get("camp_id"),
            )
            return "skipped"
        if fresh:
            doc = {
                "patient_id": patient["_id"], "message_type": message_type, "event_date": event_date,
                "event_key": event_key, "number": number, "venue": venue, "copy": copy,
                "variables": variables, "status": "queued", "attempts": 0, "provider_id": None,
                "camp_id": patient.get("camp_id"), "created_at": now,
            }
            try:
                inserted = await db.reminder_ledger.insert_one(doc)
            except DuplicateKeyError:
                return "skipped"
            return await send_queued(db, inserted.inserted_id, now)
        row = await _claim(
            db, patient["_id"], message_type, event_date, event_key, number, venue, copy, now,
            retry_after=retry_after, camp_id=patient.get("camp_id"), variables=variables,
        )
        if not row:
            return "skipped"
        if row.get("status") == "queued":
            return await send_queued(db, row["_id"], now)
        return await _settle(db, row, variables, now)
    except Exception as exc:
        logger.exception("Patient SMS processing failed")
        if row:
            try:
                await db.reminder_ledger.update_one(
                    {"_id": row["_id"]},
                    {"$set": {"status": "failed", "error": str(exc)[:200]}},
                )
            except Exception:
                logger.exception("Could not record patient SMS failure")
        return "failed"


async def record(
    db: AsyncDatabase,
    patients: List[dict],
    message_type: str,
    event_date: str,
    venue: str,
    end_date: Optional[str] = None,
    *,
    event_key: str,
    session,
    now: datetime,
) -> List[ObjectId]:
    """Writes one SMS intent per patient inside the caller's transaction and returns the queued ids to send after commit."""
    venue = clean_sms_venue(venue)
    camps, staff_phones = await _recipients(db, patients, session)
    status = "paused" if await paused(db, message_type, session) else "queued"
    rows = []
    for patient in patients:
        composed = _compose(patient, message_type, event_date, venue, end_date, camps, staff_phones)
        if not composed:
            continue
        number, variables, copy = composed
        rows.append({
            "patient_id": patient["_id"], "message_type": message_type, "event_date": event_date,
            "event_key": event_key, "number": number, "venue": venue, "copy": copy, "variables": variables,
            "status": status, "attempts": 0, "provider_id": None, "camp_id": patient.get("camp_id"),
            "created_at": now,
        })
    if not rows:
        return []
    res = await db.reminder_ledger.insert_many(rows, session=session)
    return res.inserted_ids if status == "queued" else []


async def send_queued(db: AsyncDatabase, row_id: ObjectId, now: datetime) -> str:
    row = await db.reminder_ledger.find_one_and_update(
        {"_id": row_id, "status": "queued"},
        {"$set": {"status": "pending"}, "$inc": {"attempts": 1}},
        return_document=True,
    )
    if not row:
        return "skipped"
    return await _settle(db, row, row["variables"], now)


async def _send_queued_rows(db: AsyncDatabase, row_ids: List[ObjectId], now: datetime) -> None:
    for row_id in row_ids:
        try:
            await send_queued(db, row_id, now)
        except Exception:
            logger.exception("Queued patient SMS could not be sent")


async def dispatch(background_tasks: Any, db: AsyncDatabase, row_ids: List[ObjectId], now: datetime) -> None:
    """Sends committed intents after the response; without a request context, sends them now."""
    if not row_ids:
        return
    if background_tasks is None:
        await _send_queued_rows(db, row_ids, now)
    else:
        background_tasks.add_task(_send_queued_rows, db, row_ids, now)


async def abandon_if_gone(db: AsyncDatabase, row: dict) -> bool:
    """A failed intent whose patient, or whose active Token for that date, is gone is never retried."""
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


async def due_retries(db: AsyncDatabase, message_type: str, event_date: str, now: datetime, limit: int) -> List[dict]:
    return await db.reminder_ledger.find({
        "message_type": message_type, "event_date": event_date, "status": "failed",
        "created_at": {"$lte": now - RETRY_AFTER},
    }).to_list(limit)


async def recorded(db: AsyncDatabase, patient_ids: List[Any], message_type: str, event_date: str) -> set:
    """The patients that already have an intent of this type for this date."""
    if not patient_ids:
        return set()
    rows = await db.reminder_ledger.find({
        "patient_id": {"$in": patient_ids}, "message_type": message_type, "event_date": event_date,
    }, {"patient_id": 1}).to_list(len(patient_ids))
    return {row["patient_id"] for row in rows}


async def used(db: AsyncDatabase, message_type: str, event_date: str) -> int:
    """Intents of this type and date that reached, or tried to reach, the provider."""
    return await db.reminder_ledger.count_documents({
        "message_type": message_type, "event_date": event_date,
        "status": {"$in": ["sent", "rejected", "uncertain", "failed"]},
    })


async def status_counts(db: AsyncDatabase) -> Dict[str, int]:
    return {
        status: await db.reminder_ledger.count_documents({"status": status})
        for status in ("queued", "failed", "uncertain")
    }


async def sweep(db: AsyncDatabase, now: datetime, limit: int) -> Tuple[int, int]:
    """One outbox pass: pending intents go uncertain, old queued intents are sent and due failures are retried."""
    await db.reminder_ledger.update_many(
        {"status": "pending", "created_at": {"$lte": now - PENDING_UNCERTAIN_AFTER}},
        {"$set": {"status": "uncertain"}},
    )
    queued = await db.reminder_ledger.find({
        "status": "queued", "created_at": {"$lte": now - QUEUED_RESEND_AFTER},
    }).limit(limit).to_list(limit)
    failed_rows = await db.reminder_ledger.find({
        "status": "failed", "retry_after": {"$lte": now},
    }).limit(limit).to_list(limit)
    sem = asyncio.Semaphore(4)

    async def send_one(row_id: Any) -> None:
        async with sem:
            await send_queued(db, row_id, now)

    await asyncio.gather(*(send_one(row["_id"]) for row in queued))
    retried = 0
    for row in failed_rows:
        if await abandon_if_gone(db, row):
            continue
        await db.reminder_ledger.update_one(
            {"_id": row["_id"], "status": "failed"}, {"$set": {"status": "queued"}},
        )
        await send_one(row["_id"])
        retried += 1
    return len(queued), retried


async def canary(db: AsyncDatabase, message_type: str, event_date: str, now: datetime) -> str:
    """paused, canary (send one), waiting (hold the batch for the first message's Delivery report) or open."""
    control = await db.sms_controls.find_one({"_id": message_type}) or {}
    if control.get("paused"):
        return "paused"
    query: Dict[str, Any] = {
        "message_type": message_type, "event_date": event_date,
        "status": {"$in": ["sent", "uncertain", "rejected"]},
    }
    if control.get("resumed_at"):
        query["created_at"] = {"$gte": control["resumed_at"]}
    first = await db.reminder_ledger.find(query).sort("created_at", 1).limit(1).to_list(1)
    if not first:
        return "canary"
    row = first[0]
    settled = row["status"] == "rejected" or row.get("delivery")
    if settled or helpers.as_utc(row["created_at"]) <= now - CANARY_WAIT:
        return "open"
    return "waiting"


async def pause_after_rejection(db: AsyncDatabase, message_type: str, event_date: str, now: datetime) -> None:
    """A rejected Canary pauses its type, naming the provider's reason."""
    row = await db.reminder_ledger.find({
        "message_type": message_type, "event_date": event_date, "status": "rejected",
    }).sort("created_at", -1).limit(1).to_list(1)
    if row:
        await _pause(db, row[0], row[0].get("error") or "Rejected", now)


def _notice_status(row: dict, stuck_before: datetime) -> str:
    if row.get("delivery") == "failed":
        return "failed"
    if row["status"] in ("queued", "pending") and helpers.as_utc(row["created_at"]) <= stuck_before:
        return "not_sent"
    return row["status"]


async def notice_states(db: AsyncDatabase, notices: List[Tuple[Any, Any]], now: datetime) -> Dict[Tuple[Any, Any], str]:
    """The SMS state of each Schedule edit notice, by (patient id, edit revision). A missing or stuck notice is not_sent."""
    if not notices:
        return {}
    rows = await db.reminder_ledger.find({
        "patient_id": {"$in": list({patient_id for patient_id, _revision in notices})},
        "message_type": {"$in": list(NOTICE_TYPES)},
        "event_key": {"$in": [edit_key(revision) for _patient_id, revision in notices]},
    }, {"patient_id": 1, "event_key": 1, "status": 1, "delivery": 1, "created_at": 1}).to_list(None)
    stuck_before = now - RETRY_AFTER
    found = {(row["patient_id"], row["event_key"]): _notice_status(row, stuck_before) for row in rows}
    return {
        (patient_id, revision): found.get((patient_id, edit_key(revision)), "not_sent")
        for patient_id, revision in notices
    }


def _credit(raw: Any) -> float:
    try:
        return max(float(raw), 0.0)
    except (TypeError, ValueError):
        return 0.0


async def record_delivery_report(db: AsyncDatabase, report: Dict[str, Any], now: datetime) -> bool:
    request_id = str(report.get("requestId") or "").strip()
    code = str(report.get("status") or "").strip()
    delivery = REPORT_STATUS.get(code)
    if not request_id or not delivery:
        return False
    row = await db.reminder_ledger.find_one({"provider_id": request_id})
    if not row:
        return False
    tel = "".join(ch for ch in str(report.get("telNum") or "") if ch.isdigit())
    if tel and not tel.endswith(row["number"]):
        return False
    reason = str(report.get("failureReason") or "").strip()[:200]
    dlt_failure = delivery == "failed" and not reason.upper().startswith("DND") and (
        code in _DLT_STATUS or bool(_DLT_REASON.search(reason))
    )
    await db.reminder_ledger.update_one({"_id": row["_id"]}, {"$set": {
        "delivery": delivery, "delivery_reason": reason or None, "dlt_failure": dlt_failure,
        "credit": _credit(report.get("credit")), "reported_at": now,
    }})
    if dlt_failure:
        await _pause(db, row, reason or f"Operator status {code}", now)
    return True


async def _pause(db: AsyncDatabase, row: Dict[str, Any], reason: str, now: datetime) -> None:
    control = await db.sms_controls.find_one({"_id": row["message_type"]}) or {}
    resumed_at = control.get("resumed_at")
    if control.get("paused") or (resumed_at and helpers.as_utc(row["created_at"]) < helpers.as_utc(resumed_at)):
        return
    await db.sms_controls.update_one(
        {"_id": row["message_type"]},
        {"$set": {"paused": True, "paused_at": now, "paused_reason": reason,
                  "paused_request_id": row.get("provider_id")}},
        upsert=True,
    )
    logger.warning("SMS %s paused after a DLT failure: %s", row["message_type"], reason)


async def ledger_groups(db: AsyncDatabase, match: Dict[str, Any], *, by_camp: bool) -> List[dict]:
    """One $group of ledger rows. Callers never load the rows themselves."""
    identity: Dict[str, str] = {
        "event_date": "$event_date",
        "message_type": "$message_type",
        "status": "$status",
    }
    if by_camp:
        identity = {"camp_id": "$camp_id", **identity}
    return await aggregate_list(db.reminder_ledger, [
        {"$match": match},
        {"$group": {
            "_id": identity,
            "n": {"$sum": 1},
            "credits": {"$sum": {"$ifNull": ["$credit", 0]}},
            "delivered": {"$sum": {"$cond": [{"$eq": ["$delivery", "delivered"]}, 1, 0]}},
            "dlt_failed": {"$sum": {"$cond": [{"$and": [
                {"$eq": ["$delivery", "failed"]}, {"$eq": ["$dlt_failure", True]},
            ]}, 1, 0]}},
            "other_failed": {"$sum": {"$cond": [{"$and": [
                {"$eq": ["$delivery", "failed"]}, {"$ne": ["$dlt_failure", True]},
            ]}, 1, 0]}},
        }},
    ])


async def resume(db: AsyncDatabase, message_type: str, actor_id: str, now: datetime) -> None:
    await db.sms_controls.update_one(
        {"_id": message_type},
        {"$set": {"paused": False, "resumed_at": now, "resumed_by": actor_id}},
        upsert=True,
    )
