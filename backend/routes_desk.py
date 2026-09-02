from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId
from pymongo.errors import DuplicateKeyError
from motor.motor_asyncio import AsyncIOMotorDatabase
from db import get_db
from models import QrLookupBody, ScanBody, ScanConfirmBody, RegisterBody
from helpers import now_utc, as_utc, today_ist_str, age_from_dob, normalize_name, person_key
from serializers import ser_patient
from security import require_staff
from aadhaar import decode_aadhaar
from routes_registration import (
    _dup_409, _duplicate_hits, _is_manual, _is_scanned_row, _resolve_person,
)
from datetime import timedelta

router = APIRouter(prefix="/api/desk", tags=["desk"])

OVERWRITTEN_FIELDS = ("full_name", "age", "gender", "dob", "aadhaar_last4", "address")


async def _resolve(value: str) -> Optional[Dict[str, Any]]:
    db = get_db()
    v = (value or "").strip()
    if v.startswith("snp:"):
        v = v[4:]
    if "/p/" in v:
        v = v.split("/p/")[-1]
    p = await db.patients.find_one({"patient_qr": v})
    if p:
        return p
    if v.isdigit():
        p = await db.patients.find_one({"reg_no": int(v)})
        if p:
            return p
    return None


@router.post("/lookup")
async def lookup(body: QrLookupBody, actor: dict = Depends(require_staff)) -> Dict[str, Any]:
    p = await _resolve(body.value)
    if not p:
        raise HTTPException(status_code=404, detail="No matching registration found")
    return {"registration": ser_patient(p)}


def _card_values(data: dict) -> Dict[str, Any]:
    age = data.get("age")
    return {
        "full_name": data.get("full_name"),
        "age": age if age is not None else age_from_dob(data.get("dob") or ""),
        "gender": data.get("gender"),
        "dob": data.get("dob"),
        "aadhaar_last4": data.get("aadhaar_last4"),
        "address": data.get("address"),
    }


def _decode_card(payload: str) -> Dict[str, Any]:
    result = decode_aadhaar(payload or "")
    if result["outcome"] != "card":
        raise HTTPException(status_code=400, detail={
            "code": "NOT_A_CARD",
            "message": "That scan is not a readable Aadhaar Secure QR.",
        })
    return _card_values(result["data"])


def _card_as_register_body(card: dict) -> RegisterBody:
    return RegisterBody(
        full_name=card["full_name"] or "",
        age=card["age"],
        gender=card["gender"],
        address=card["address"],
        aadhaar_last4=card["aadhaar_last4"],
        dob=card["dob"],
        aadhaar_scanned=True,
        camp_day_id="",
    )


async def _known_person(db: AsyncIOMotorDatabase, card: dict) -> Optional[dict]:
    """Look up the Person this card belongs to. A scan never creates one."""
    if not (card["aadhaar_last4"] and card["full_name"]):
        return None
    key = person_key(card["aadhaar_last4"], card["full_name"], card["dob"] or "", card["gender"] or "")
    return await db.persons.find_one({"aadhaar_key": key})


async def _active_camp(db: AsyncIOMotorDatabase) -> dict:
    camp = await db.camps.find_one({"is_active": True})
    if not camp:
        raise HTTPException(status_code=409, detail="No active camp")
    return camp


async def _stamp_arrival(db: AsyncIOMotorDatabase, patient: dict, actor_id: str) -> Dict[str, Any]:
    """Arrival is a presence. It never consults camp-day capacity."""
    if patient.get("arrived_at"):
        return patient
    updates: Dict[str, Any] = {
        "arrived_at": now_utc(),
        "arrived_by": actor_id,
        "queue_status": "arrived" if patient.get("queue_status") == "registered"
                        else patient.get("queue_status"),
    }
    today_day = await db.camp_days.find_one(
        {"camp_id": patient["camp_id"], "day_date": today_ist_str()}
    )
    if today_day and today_day["_id"] != patient.get("camp_day_id"):
        booked = await db.camp_days.find_one({"_id": patient["camp_day_id"]})
        updates["camp_day_id"] = today_day["_id"]
        updates["camp_day_changed_from"] = booked["day_date"] if booked else None
    await db.patients.update_one({"_id": patient["_id"]}, {"$set": updates})
    return await db.patients.find_one({"_id": patient["_id"]})


def _diff(card: dict, stored: dict) -> List[Dict[str, Any]]:
    return [
        {"field": field, "card": card.get(field), "stored": stored.get(field)}
        for field in OVERWRITTEN_FIELDS
        if str(card.get(field) or "") != str(stored.get(field) or "")
    ]


@router.post("/scan")
async def scan(body: ScanBody, actor: dict = Depends(require_staff)) -> Dict[str, Any]:
    """Resolve a camp-day Lock against the active camp. Never creates a registration."""
    db = get_db()
    camp = await _active_camp(db)
    card = _decode_card(body.payload)
    person = await _known_person(db, card)
    hits = await _duplicate_hits(db, camp["_id"], _card_as_register_body(card), person)

    scanned_hits = [h for h in hits if _is_scanned_row(h)]
    if scanned_hits:
        arrived = await _stamp_arrival(db, scanned_hits[0], str(actor["_id"]))
        return {"outcome": "arrived", "registration": ser_patient(arrived)}

    manual_hits = [h for h in hits if _is_manual(h)]
    if len(manual_hits) > 1:
        return {"outcome": "ambiguous", "registrations": [ser_patient(h) for h in manual_hits]}
    if len(manual_hits) == 1:
        return {
            "outcome": "mismatch_review",
            "registration": ser_patient(manual_hits[0]),
            "card": card,
            "diff": _diff(card, manual_hits[0]),
        }
    return {"outcome": "no_match", "card": card}


@router.post("/scan/confirm")
async def scan_confirm(body: ScanConfirmBody, actor: dict = Depends(require_staff)) -> Dict[str, Any]:
    """Apply the Aadhaar overwrite to a Manual entry and stamp Arrival in one operation."""
    db = get_db()
    await _active_camp(db)
    card = _decode_card(body.payload)
    patient = await db.patients.find_one({"_id": ObjectId(body.patient_id)})
    if not patient:
        raise HTTPException(status_code=404, detail="Registration not found")
    if not _is_manual(patient):
        raise HTTPException(status_code=409, detail={
            "code": "NOT_A_MANUAL_ENTRY",
            "message": "This registration already has Aadhaar on file.",
        })
    person = None
    if card["aadhaar_last4"] and card["dob"]:
        person, _ = await _resolve_person({
            "aadhaar_last4": card["aadhaar_last4"],
            "full_name": card["full_name"],
            "dob": card["dob"],
            "gender": card["gender"],
        })
    try:
        await db.patients.update_one({"_id": patient["_id"]}, {"$set": {
            **{field: card[field] for field in OVERWRITTEN_FIELDS},
            "full_name_normalized": normalize_name(card["full_name"] or ""),
            "aadhaar_scanned": True,
            "person_id": person["_id"] if person else None,
            "manual_entry": False,
            "manual_exception": None,
        }})
    except DuplicateKeyError:
        if person:
            existing = await db.patients.find_one(
                {"person_id": person["_id"], "camp_id": patient["camp_id"]}
            )
            if existing:
                raise _dup_409(existing)
        raise
    patient = await db.patients.find_one({"_id": patient["_id"]})
    arrived = await _stamp_arrival(db, patient, str(actor["_id"]))
    return {"outcome": "arrived", "registration": ser_patient(arrived)}


@router.post("/arrive/{patient_id}")
async def arrive(patient_id: str, actor: dict = Depends(require_staff)) -> Dict[str, Any]:
    db = get_db()
    p = await db.patients.find_one({"_id": ObjectId(patient_id)})
    if not p:
        raise HTTPException(status_code=404, detail="Registration not found")
    arrived = await _stamp_arrival(db, p, str(actor["_id"]))
    return {"registration": ser_patient(arrived)}


@router.post("/print/{patient_id}")
async def print_prescription(patient_id: str, actor: dict = Depends(require_staff)) -> Dict[str, Any]:
    db = get_db()
    p = await db.patients.find_one({"_id": ObjectId(patient_id)})
    if not p:
        raise HTTPException(status_code=404, detail="Registration not found")

    if not p.get("arrived_at"):
        raise HTTPException(status_code=409, detail={
            "code": "NOT_ARRIVED",
            "message": "Scan the patient in at the door before printing.",
        })

    day = await db.camp_days.find_one({"_id": p["camp_day_id"]})
    if not day:
        raise HTTPException(status_code=404, detail="Camp day not found")

    if not day.get("printing_open", False):
        raise HTTPException(status_code=409, detail={
            "code": "PRINT_WINDOW_CLOSED",
            "message": "The print window is closed.",
        })

    if not p.get("printed_at"):
        await db.patients.update_one(
            {"_id": p["_id"], "printed_at": None},
            {"$set": {"printed_at": now_utc(), "checked_in_by": str(actor["_id"])}},
        )
        p = await db.patients.find_one({"_id": p["_id"]})

    camp = await db.camps.find_one({"_id": p["camp_id"]})
    return {
        "registration": ser_patient(p),
        "prescription": {
            "camp_id": str(p["camp_id"]),
            "camp_name": camp["name"] if camp else None,
            "venue": camp["venue"] if camp else None,
            "reg_no": p["reg_no"],
            "full_name": p["full_name"],
            "address": p.get("address"),
            "age": p.get("age"),
            "gender": p.get("gender"),
            "phone": p.get("phone"),
            "date": day["day_date"],
            "patient_qr": p["patient_qr"],
        },
    }


@router.post("/mark-seen/{patient_id}")
async def mark_seen(patient_id: str, actor: dict = Depends(require_staff)) -> Dict[str, Any]:
    db = get_db()
    p = await db.patients.find_one({"_id": ObjectId(patient_id)})
    if not p:
        raise HTTPException(status_code=404, detail="Registration not found")
    if not p.get("arrived_at"):
        raise HTTPException(status_code=409, detail={
            "code": "NOT_ARRIVED",
            "message": "This patient has not been scanned in at the door.",
        })
    if not p.get("printed_at"):
        raise HTTPException(status_code=409, detail={
            "code": "never_printed",
            "message": "This patient's prescription was never printed.",
        })
    if p.get("seen_at"):
        return {"registration": ser_patient(p), "changed": False}
    await db.patients.update_one(
        {"_id": p["_id"], "seen_at": None},
        {"$set": {"queue_status": "seen", "seen_at": now_utc(), "seen_by": str(actor["_id"])}},
    )
    p = await db.patients.find_one({"_id": p["_id"]})
    return {"registration": ser_patient(p), "changed": True}


@router.post("/undo-seen/{patient_id}")
async def undo_seen(patient_id: str, actor: dict = Depends(require_staff)) -> Dict[str, Any]:
    db = get_db()
    p = await db.patients.find_one({"_id": ObjectId(patient_id)})
    if not p:
        raise HTTPException(status_code=404, detail="Registration not found")
    if not p.get("seen_at"):
        raise HTTPException(status_code=409, detail="Not marked seen")
    if p["seen_at"] and as_utc(p["seen_at"]) < now_utc() - timedelta(minutes=10):
        raise HTTPException(status_code=409, detail="Undo window (10 min) has passed")
    if await db.transcriptions.find_one({"patient_id": p["_id"]}):
        raise HTTPException(status_code=409, detail="Cannot undo: clinical transcription exists")
    updated = await db.patients.find_one_and_update(
        {"_id": p["_id"], "seen_at": {"$ne": None}},
        {"$set": {"queue_status": "arrived", "seen_at": None, "seen_by": None}},
        return_document=True,
    )
    if updated is None:
        p = await db.patients.find_one({"_id": p["_id"]})
        return {"registration": ser_patient(p)}
    if await db.transcriptions.find_one({"patient_id": p["_id"]}):
        await db.patients.find_one_and_update(
            {"_id": p["_id"], "seen_at": None},
            {"$set": {
                "queue_status": "seen",
                "seen_at": p["seen_at"],
                "seen_by": p.get("seen_by"),
            }},
        )
        raise HTTPException(status_code=409, detail="Cannot undo: clinical transcription exists")
    return {"registration": ser_patient(updated)}
