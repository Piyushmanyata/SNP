import asyncio
import logging
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
SPECS_TOKEN = "Sikar Zilla Welfare Trust के {camp_no} वें नेत्र शिविर में आपको चश्मा {date} से {end_date} तक सुबह  {start_time} बजे से शाम {end_time} बजे तक {venue} में दिया जाएगा। कृपया चश्मे का टोकन ({reg_no}) लेकर अवश्य आएँ।"
SPECS_REMINDER = "Sikar Zilla Welfare Trust के {camp_no} वे शिविर के चश्मे बनकर  तैयार है।  चश्में {date} से {end_date} तक सुबह  {start_time} बजे से शाम {end_time} बजे तक {venue} आकर ले जावें। टोकन क्रमांक {reg_no} अवश्य साथ लाएँ।"

MESSAGE_COPY = {
    "registration": REGISTRATION_CONFIRMATION,
    "camp": CAMP_REMINDER,
    "ot_token": OT_TOKEN,
    "ot": OT_REMINDER,
    "specs_token": SPECS_TOKEN,
    "specs": SPECS_REMINDER,
}
RETRY_AFTER = timedelta(minutes=10)


def valid_phone(raw: Optional[str]) -> Optional[str]:
    n = helpers.normalize_phone(raw)
    if not n or helpers.is_dummy_phone(n):
        return None
    return n


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
        if existing.get("status") != "failed":
            return None
        attempts = int(existing.get("attempts") or 1)
        if attempts >= 3:
            await db.reminder_ledger.update_one(
                {"_id": existing["_id"], "status": "failed"},
                {"$set": {"status": "abandoned"}},
            )
            return None
        retryable: Dict[str, Any] = {"_id": existing["_id"], "status": "failed"}
        if retry_after:
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


def morning_to_evening(start_time: Optional[str], end_time: Optional[str]) -> bool:
    return bool(start_time and end_time and start_time < "12:00" <= end_time)


def _clock(hhmm: str) -> str:
    hour, minute = hhmm.split(":")
    return f"{(int(hour) - 1) % 12 + 1:02d}:{minute}"


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
    """Returns sent, failed, uncertain, or skipped. Never raises."""
    row = None
    accepted = False
    try:
        if not msg91.configured() or not msg91.template_id(message_type):
            return "skipped"
        number = valid_phone(patient.get("phone_normalized") or patient.get("phone"))
        reg_no = patient.get("reg_no")
        if not number or reg_no is None:
            return "skipped"
        camp = await db.camps.find_one({"_id": patient["camp_id"]}) if patient.get("camp_id") else None
        hours = morning_to_evening(start_time, end_time)
        template = MESSAGE_COPY[message_type]
        variables = _template_variables(template, {
            "reg_no": reg_no,
            "camp_no": str((camp or {}).get("camp_number") or ""),
            "date": helpers.display_date(event_date),
            "end_date": helpers.display_date(end_date or event_date),
            "start_time": _clock(str(start_time)) if hours else "",
            "end_time": _clock(str(end_time)) if hours else "",
            "venue": venue,
        })
        missing = [name for name, value in variables.items() if value == ""]
        if missing:
            logger.warning("Patient SMS %s not sent: no %s", message_type, ", ".join(missing))
            return "skipped"
        copy = template.format(**variables)
        row = await _claim(
            db, patient["_id"], message_type, event_date, number, venue, copy,
            retry_after=retry_after,
        )
        if not row:
            return "skipped"
        provider_id = await asyncio.to_thread(msg91.send_dlt_sms, message_type, number, variables)
        accepted = True
        await db.reminder_ledger.update_one(
            {"_id": row["_id"]},
            {"$set": {"status": "sent", "provider_id": provider_id}},
        )
        return "sent"
    except Exception as exc:
        logger.exception("Patient SMS processing failed; provider accepted=%s", accepted)
        if row and not accepted:
            try:
                await db.reminder_ledger.update_one(
                    {"_id": row["_id"]},
                    {"$set": {"status": "failed", "error": str(exc)[:200]}},
                )
            except Exception:
                logger.exception("Could not record patient SMS failure")
            return "failed"
        if accepted:
            return "uncertain"
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
    True means the provider accepted the message, including an uncertain ledger write.
    """
    return (await deliver_patient_sms(
        db, patient, message_type, event_date, venue, start_time, end_time, end_date,
    )) in ("sent", "uncertain")
