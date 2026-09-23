import asyncio
import logging
import re
import string
from datetime import timedelta
from typing import Any, Dict, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

import helpers
import msg91

logger = logging.getLogger(__name__)

REGISTRATION_CONFIRMATION = "Sikar Zilla Welfare Trust के {camp_no}वें नेत्र शिविर में आपका पंजीकरण हो गया है। क्रमांक: {reg_no} दिनांक: {date} शिविर स्थल: {venue}। कृपया शिविर के दिन अपना आधार कार्ड अवश्य साथ लाएँ।"
CAMP_REMINDER = "कल ({date}) को Sikar Zilla Welfare Trust के {camp_no} वें नेत्र शिविर में आपका नेत्र परीक्षण है। कृपया समय पर {venue} पहुँचें। यह टोकन शिविर स्थल पर दिखाएँ। क्रमांक: {reg_no}। कृपया शिविर के दिन अपना आधार कार्ड अवश्य साथ लाएँ।"
OT_TOKEN = "Sikar Zilla Welfare Trust के {camp_no} वें नेत्र शिविर में आपका ऑपरेशन {date} को निर्धारित हुआ है। पर्चा, टोकन ({reg_no}), आधार कार्ड, राशन कार्ड और मोबाइल नंबर अवश्य साथ लाएँ। स्थल: {venue}।"
OT_REMINDER = "कल ({date}) को Sikar Zilla Welfare Trust के {camp_no} वें नेत्र शिविर में आपका नेत्र ऑपरेशन निर्धारित है। पर्चा, टोकन ({reg_no}), आधार कार्ड, राशन कार्ड और मोबाइल नंबर साथ अवश्य लाएँ। स्थल: {venue}।"
SPECS_PICKUP_START_TIME = "10:00"
SPECS_PICKUP_END_TIME = "17:00"
SPECS_TOKEN = "Sikar Zilla Welfare Trust के {camp_no} वें नेत्र शिविर में आपको चश्मा {date} से {end_date} तक प्रतिदिन 10:00 AM से 5:00 PM तक {venue} में दिया जाएगा। कृपया चश्मे का टोकन ({reg_no}) लेकर अवश्य आएँ।"
SPECS_REMINDER = "Sikar Zilla Welfare Trust के {camp_no} वे शिविर के चश्मे बनकर तैयार हैं। चश्मे {date} से {end_date} तक प्रतिदिन 10:00 AM से 5:00 PM तक {venue} आकर ले जाएँ। टोकन क्रमांक {reg_no} अवश्य साथ लाएँ।"

MESSAGE_COPY = {
    "registration": REGISTRATION_CONFIRMATION,
    "camp": CAMP_REMINDER,
    "ot_token": OT_TOKEN,
    "ot": OT_REMINDER,
    "specs_token": SPECS_TOKEN,
    "specs": SPECS_REMINDER,
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


async def paused(db: AsyncIOMotorDatabase, message_type: str) -> bool:
    control = await db.sms_controls.find_one({"_id": message_type})
    return bool(control and control.get("paused"))


async def _claim(
    db: AsyncIOMotorDatabase,
    patient_id: Any,
    message_type: str,
    event_date: str,
    number: str,
    venue: str,
    copy: str,
    retry_after: Optional[timedelta] = None,
) -> Optional[Dict[str, Any]]:
    existing = await db.reminder_ledger.find_one({
        "patient_id": patient_id,
        "message_type": message_type,
        "event_date": event_date,
    })
    if existing:
        status = existing.get("status")
        if status not in ("failed", "paused"):
            return None
        attempts = int(existing.get("attempts") or 0)
        if attempts >= 3:
            await db.reminder_ledger.update_one(
                {"_id": existing["_id"], "status": status},
                {"$set": {"status": "abandoned"}},
            )
            return None
        retryable: Dict[str, Any] = {"_id": existing["_id"], "status": status}
        if retry_after and status == "failed":
            retryable["created_at"] = {"$lte": helpers.now_utc() - retry_after}
        return await db.reminder_ledger.find_one_and_update(
            retryable,
            {"$set": {"status": "pending", "attempts": attempts + 1, "created_at": helpers.now_utc(),
                      "copy": copy, "number": number, "venue": venue}},
            return_document=True,
        )
    doc = {
        "patient_id": patient_id,
        "message_type": message_type,
        "event_date": event_date,
        "number": number,
        "venue": venue,
        "copy": copy,
        "status": "pending",
        "attempts": 1,
        "provider_id": None,
        "created_at": helpers.now_utc(),
    }
    try:
        res = await db.reminder_ledger.insert_one(doc)
    except DuplicateKeyError:
        return None
    doc["_id"] = res.inserted_id
    return doc


async def _record_paused(
    db: AsyncIOMotorDatabase, patient_id: Any, message_type: str, event_date: str,
    number: str, venue: str, copy: str,
) -> None:
    try:
        await db.reminder_ledger.insert_one({
            "patient_id": patient_id, "message_type": message_type, "event_date": event_date,
            "number": number, "venue": venue, "copy": copy, "status": "paused", "attempts": 0,
            "provider_id": None, "created_at": helpers.now_utc(),
        })
    except DuplicateKeyError:
        pass


def specs_pickup_hours_match(start_time: Optional[str], end_time: Optional[str]) -> bool:
    return (start_time, end_time) == (SPECS_PICKUP_START_TIME, SPECS_PICKUP_END_TIME)


def _template_variables(template: str, values: Dict[str, Any]) -> Dict[str, Any]:
    return {name: values[name] for _, name, _, _ in string.Formatter().parse(template) if name}


async def deliver_patient_sms(
    db: AsyncIOMotorDatabase,
    patient: dict,
    message_type: str,
    event_date: str,
    venue: str,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    end_date: Optional[str] = None,
    retry_after: Optional[timedelta] = None,
) -> str:
    """Returns sent, failed, uncertain, rejected, paused, or skipped. Never raises."""
    row = None
    submitted = False
    venue = clean_sms_venue(venue)
    try:
        if not msg91.configured() or not msg91.template_id(message_type):
            return "skipped"
        number = valid_phone(patient.get("phone_normalized") or patient.get("phone"))
        reg_no = patient.get("reg_no")
        if not number or reg_no is None:
            return "skipped"
        if message_type in ("specs_token", "specs") and not specs_pickup_hours_match(start_time, end_time):
            return "skipped"
        camp = await db.camps.find_one({"_id": patient["camp_id"]}) if patient.get("camp_id") else None
        template = MESSAGE_COPY[message_type]
        variables = _template_variables(template, {
            "reg_no": reg_no,
            "camp_no": str((camp or {}).get("camp_number") or ""),
            "date": helpers.display_date(event_date),
            "end_date": helpers.display_date(end_date or event_date),
            "venue": venue,
        })
        missing = [name for name, value in variables.items() if value == ""]
        if missing:
            logger.warning("Patient SMS %s not sent: no %s", message_type, ", ".join(missing))
            return "skipped"
        too_long = [name for name, value in variables.items() if len(str(value)) > VARIABLE_LIMIT]
        if too_long:
            logger.warning("Patient SMS %s not sent: %s exceeds DLT variable limit", message_type, ", ".join(too_long))
            return "skipped"
        venue_problem = sms_venue_problem(str(venue))
        if venue_problem:
            logger.warning("Patient SMS %s not sent: %s", message_type, venue_problem)
            return "skipped"
        copy = template.format(**variables)
        if await paused(db, message_type):
            await _record_paused(db, patient["_id"], message_type, event_date, number, venue, copy)
            return "paused"
        row = await _claim(
            db, patient["_id"], message_type, event_date, number, venue, copy,
            retry_after=retry_after,
        )
        if not row:
            return "skipped"
        update: Dict[str, Any]
        try:
            provider_id = await asyncio.to_thread(msg91.send_dlt_sms, message_type, number, variables)
        except msg91.Unsent as exc:
            update = {"status": "failed", "error": str(exc)[:200]}
        except msg91.Rejected as exc:
            update = {"status": "rejected", "error": str(exc)[:200]}
        except Exception as exc:
            submitted = True
            update = {"status": "uncertain", "error": f"{type(exc).__name__}: {exc}"[:200]}
        else:
            submitted = True
            update = {"status": "sent", "provider_id": provider_id}
        if update["status"] != "sent":
            logger.warning("Patient SMS %s %s: %s", message_type, update["status"], update["error"])
        await db.reminder_ledger.update_one({"_id": row["_id"]}, {"$set": update})
        return update["status"]
    except Exception as exc:
        logger.exception("Patient SMS processing failed; submitted=%s", submitted)
        if submitted:
            return "uncertain"
        if row:
            try:
                await db.reminder_ledger.update_one(
                    {"_id": row["_id"]},
                    {"$set": {"status": "failed", "error": str(exc)[:200]}},
                )
            except Exception:
                logger.exception("Could not record patient SMS failure")
        return "failed"


async def send_patient_sms(
    db: AsyncIOMotorDatabase,
    patient: dict,
    message_type: str,
    event_date: str,
    venue: str,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    end_date: Optional[str] = None,
) -> bool:
    """Best-effort per-patient DLT send, recorded once per patient/type/event date.

    Never raises: the registration or deferral is the durable outcome.
    True means the request reached the provider, including when its reply was lost.
    """
    return (await deliver_patient_sms(
        db, patient, message_type, event_date, venue, start_time, end_time, end_date,
    )) in ("sent", "uncertain")


def _credit(raw: Any) -> float:
    try:
        return max(float(raw), 0.0)
    except (TypeError, ValueError):
        return 0.0


async def record_delivery_report(db: AsyncIOMotorDatabase, report: Dict[str, Any]) -> bool:
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
    dlt_failure = delivery == "failed" and (code in _DLT_STATUS or bool(_DLT_REASON.search(reason)))
    await db.reminder_ledger.update_one({"_id": row["_id"]}, {"$set": {
        "delivery": delivery, "delivery_reason": reason or None, "dlt_failure": dlt_failure,
        "credit": _credit(report.get("credit")), "reported_at": helpers.now_utc(),
    }})
    if dlt_failure:
        await _pause(db, row, reason or f"Operator status {code}")
    return True


async def _pause(db: AsyncIOMotorDatabase, row: Dict[str, Any], reason: str) -> None:
    control = await db.sms_controls.find_one({"_id": row["message_type"]}) or {}
    resumed_at = control.get("resumed_at")
    if control.get("paused") or (resumed_at and helpers.as_utc(row["created_at"]) < helpers.as_utc(resumed_at)):
        return
    await db.sms_controls.update_one(
        {"_id": row["message_type"]},
        {"$set": {"paused": True, "paused_at": helpers.now_utc(), "paused_reason": reason,
                  "paused_request_id": row.get("provider_id")}},
        upsert=True,
    )
    logger.warning("SMS %s paused after a DLT failure: %s", row["message_type"], reason)


async def resume(db: AsyncIOMotorDatabase, message_type: str, actor_id: str) -> None:
    await db.sms_controls.update_one(
        {"_id": message_type},
        {"$set": {"paused": False, "resumed_at": helpers.now_utc(), "resumed_by": actor_id}},
        upsert=True,
    )
