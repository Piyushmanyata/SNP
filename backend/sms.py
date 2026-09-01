from typing import Any, Dict, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

import helpers
import msg91

REGISTRATION_CONFIRMATION = "SNP नेत्र शिविर पंजीकरण हुआ। क्रमांक {reg_no}, दिनांक {date}, स्थान {venue}।"
CAMP_REMINDER = "कल SNP नेत्र शिविर। क्रमांक {reg_no}, दिनांक {date}, स्थान {venue}। समय पर पहुँचें।"
OT_TOKEN = "SNP ऑपरेशन नियत। क्रमांक {reg_no}, दिनांक {date}, स्थान {venue}। टोकन साथ लाएँ।"
OT_REMINDER = "कल SNP ऑपरेशन। क्रमांक {reg_no}, दिनांक {date}, स्थान {venue}। टोकन साथ लाएँ।"
SPECS_TOKEN = "SNP चश्मा वितरण नियत। क्रमांक {reg_no}, दिनांक {date}, स्थान {venue}। टोकन साथ लाएँ।"
SPECS_REMINDER = "कल SNP से चश्मा लें। क्रमांक {reg_no}, दिनांक {date}, स्थान {venue}। टोकन साथ लाएँ।"

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
        return None
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


async def send_patient_sms(
    db: AsyncIOMotorDatabase,
    patient: dict,
    message_type: str,
    event_date: str,
    venue: str,
) -> bool:
    """Best-effort per-patient DLT send, recorded once per patient/type/event date.

    Never raises: the registration or deferral is the durable outcome.
    """
    try:
        return await _send(db, patient, message_type, event_date, venue)
    except Exception:
        return False


async def _send(
    db: AsyncIOMotorDatabase,
    patient: dict,
    message_type: str,
    event_date: str,
    venue: str,
) -> bool:
    if not msg91.configured():
        return False
    number = valid_phone(patient.get("phone_normalized") or patient.get("phone"))
    if not number:
        return False
    reg_no = patient.get("reg_no")
    if reg_no is None:
        return False
    copy = MESSAGE_COPY[message_type].format(reg_no=reg_no, date=event_date, venue=venue)
    row = await _claim(db, patient["_id"], message_type, event_date, number, venue, copy)
    if not row:
        return False
    try:
        provider_id = msg91.send_dlt_sms(message_type, number, reg_no, event_date, venue)
    except Exception as exc:
        await db.reminder_ledger.update_one(
            {"_id": row["_id"]},
            {"$set": {"status": "failed", "error": str(exc)[:200]}},
        )
        return False
    await db.reminder_ledger.update_one(
        {"_id": row["_id"]},
        {"$set": {"status": "sent", "provider_id": provider_id}},
    )
    return True
