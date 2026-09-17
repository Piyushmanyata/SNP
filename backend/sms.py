import asyncio
import logging
from typing import Any, Dict, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

import helpers
import msg91

logger = logging.getLogger(__name__)

REGISTRATION_CONFIRMATION = "SNP नेत्र शिविर में आपका पंजीकरण हो गया है। क्रमांक: {reg_no} दिनांक: {date} शिविर स्थल: {venue}। कृपया शिविर के दिन अपना आधार कार्ड साथ लाएँ।"
CAMP_REMINDER = "कल ({date}) को SNP नेत्र शिविर में आपका नेत्र परीक्षण है। कृपया समय पर {venue} पहुँचें। यह टोकन शिविर स्थल पर दिखाएँ। क्रमांक: {reg_no}। कृपया शिविर के दिन अपना आधार कार्ड साथ लाएँ।"
OT_TOKEN = "SNP नेत्र शिविर में आपका ऑपरेशन बजाज हॉस्पिटल में {date} को निर्धारित हुआ है। पर्चा, टोकन ({reg_no}), आधार कार्ड, वोटर आईडी और मोबाइल नंबर साथ लाएँ। स्थल: {venue}।"
OT_REMINDER = "कल ({date}) को आपका नेत्र ऑपरेशन बजाज हॉस्पिटल में निर्धारित है। पर्चा, टोकन ({reg_no}), आधार कार्ड, वोटर आईडी और मोबाइल नंबर साथ लाएँ। स्थल: {venue}।"
SPECS_TOKEN = "SNP द्वारा आपका चश्मा {date}{window} पर {venue} में दिया जाएगा। कृपया चश्मे का टोकन ({reg_no}) लेकर आएँ।"
SPECS_REMINDER = "कल SNP से चश्मा लें। क्रमांक {reg_no}, दिनांक {date}{window}, स्थान {venue}। टोकन साथ लाएँ।"

MESSAGE_COPY = {
    "registration": REGISTRATION_CONFIRMATION,
    "camp": CAMP_REMINDER,
    "ot_token": OT_TOKEN,
    "ot": OT_REMINDER,
    "specs_token": SPECS_TOKEN,
    "specs": SPECS_REMINDER,
}


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
) -> Optional[Dict[str, Any]]:
    existing = await db.reminder_ledger.find_one({
        "patient_id": patient_id,
        "message_type": message_type,
        "event_date": event_date,
    })
    if existing:
        if existing.get("status") != "failed":
            return None
        return await db.reminder_ledger.find_one_and_update(
            {"_id": existing["_id"], "status": "failed"},
            {"$set": {"status": "pending", "created_at": helpers.now_utc(),
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
        "provider_id": None,
        "created_at": helpers.now_utc(),
    }
    res = await db.reminder_ledger.insert_one(doc)
    doc["_id"] = res.inserted_id
    return doc


def _window_text(start_time: Optional[str], end_time: Optional[str]) -> str:
    if start_time and end_time:
        return f", समय {start_time}–{end_time}"
    return ""


async def send_patient_sms(
    db: AsyncIOMotorDatabase,
    patient: dict,
    message_type: str,
    event_date: str,
    venue: str,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
) -> bool:
    """Best-effort per-patient DLT send, recorded once per patient/type/event date.

    Never raises: the registration or deferral is the durable outcome.
    """
    row = None
    sent = False
    try:
        if not msg91.configured():
            return False
        number = valid_phone(patient.get("phone_normalized") or patient.get("phone"))
        reg_no = patient.get("reg_no")
        if not number or reg_no is None:
            return False
        fields = {"reg_no": reg_no, "date": helpers.display_date(event_date), "venue": venue}
        if "{window}" in MESSAGE_COPY[message_type]:
            fields["window"] = _window_text(start_time, end_time)
        copy = MESSAGE_COPY[message_type].format(**fields)
        row = await _claim(db, patient["_id"], message_type, event_date, number, venue, copy)
        if not row:
            return False
        provider_id = await asyncio.to_thread(
            msg91.send_dlt_sms, message_type, number, reg_no, fields["date"] + fields.get("window", ""), venue
        )
        sent = True
        await db.reminder_ledger.update_one(
            {"_id": row["_id"]},
            {"$set": {"status": "sent", "provider_id": provider_id}},
        )
        return True
    except Exception as exc:
        logger.exception("Patient SMS processing failed; provider accepted=%s", sent)
        if row and not sent:
            try:
                await db.reminder_ledger.update_one(
                    {"_id": row["_id"]},
                    {"$set": {"status": "failed", "error": str(exc)[:200]}},
                )
            except Exception:
                logger.exception("Could not record patient SMS failure")
        return sent
