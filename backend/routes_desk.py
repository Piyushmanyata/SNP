import asyncio
from typing import Any, Dict, Optional
from fastapi import HTTPException, APIRouter, Depends
from bson import ObjectId
from pymongo.errors import DuplicateKeyError
from pymongo.asynchronous.database import AsyncDatabase
from db import get_db
from models import NoCardBody, QrLookupBody, ScanBody, ScanConfirmBody, RegisterBody
from helpers import OVERWRITTEN_FIELDS, now_utc, age_from_dob, material_diff, normalize_name, parse_patient_identifier, person_key, api_error
from serializers import ser_patient
from security import require_staff
from routes_camps import effective_printing
from aadhaar import decode_aadhaar
from routes_registration import (
    _dup_409, _duplicate_hits, _is_manual, _is_scanned_row, _overwrite_refused, _resolve_person,
    checked_manual_note,
)
router = APIRouter(prefix="/api/desk", tags=["desk"])

MAX_REG_NO_DIGITS = 12


async def _resolve(value: str) -> Optional[Dict[str, Any]]:
    db = get_db()
    camp = await _active_camp(db)
    v = parse_patient_identifier(value)
    p = await db.patients.find_one({"camp_id": camp["_id"], "patient_qr": v})
    if p:
        return p
    if v.isdecimal():
        if len(v) > MAX_REG_NO_DIGITS:
            raise api_error(400, "THAT_IS_NOT_A_VALID_REGISTRATION_NUMBER", 'That is not a valid registration number')
        p = await db.patients.find_one({"camp_id": camp["_id"], "reg_no": int(v)})
        if p:
            return p
    return None


@router.post("/lookup")
async def lookup(body: QrLookupBody, actor: dict = Depends(require_staff)) -> Dict[str, Any]:
    p = await _resolve(body.value)
    if not p:
        raise api_error(404, "NO_MATCHING_REGISTRATION_FOUND", 'No matching registration found')
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


async def _decode_card(payload: str) -> Dict[str, Any]:
    result = await asyncio.to_thread(decode_aadhaar, payload)
    if result["outcome"] != "card":
        raise api_error(400, "NOT_A_CARD", 'That scan is not a readable Aadhaar Secure QR.')
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


async def _known_person(db: AsyncDatabase, card: dict) -> Optional[dict]:
    """Look up the Person this card belongs to. A scan never creates one."""
    if not (card["aadhaar_last4"] and card["full_name"]):
        return None
    key = person_key(card["aadhaar_last4"], card["full_name"], card["dob"] or "", card["gender"] or "")
    return await db.persons.find_one({"aadhaar_key": key})


async def _active_camp(db: AsyncDatabase) -> dict:
    camp = await db.camps.find_one({"is_active": True})
    if not camp:
        raise api_error(409, "NO_ACTIVE_CAMP", 'No active camp')
    return camp


async def _printing_state(db, camp: dict) -> dict:
    days = await db.camp_days.find({"camp_id": camp["_id"]}).to_list(100)
    return effective_printing(camp, days)


async def _require_door_open(db, camp: dict) -> dict:
    state = await _printing_state(db, camp)
    if not state.get("printing_open"):
        raise api_error(409, "PRINT_WINDOW_CLOSED", 'The print window is closed.')
    return state


def _require_in_camp(patient: dict, camp: dict) -> None:
    if patient.get("camp_id") != camp["_id"]:
        raise api_error(409, "WRONG_CAMP", 'That registration is not in this camp.')


async def _stamp_arrival(
    db: AsyncDatabase, patient: dict, actor_id: str,
    camp: dict, state: Optional[dict] = None,
) -> Dict[str, Any]:
    """Arrival is a presence. It never consults camp-day capacity."""
    if patient.get("arrived_at"):
        return patient
    if state is None:
        state = await _require_door_open(db, camp)
    updates: Dict[str, Any] = {
        "arrived_at": now_utc(),
        "arrived_by": actor_id,
        "queue_status": "arrived" if patient.get("queue_status") == "registered"
                        else patient.get("queue_status"),
    }
    operating = None
    if state.get("operating_day_id"):
        operating = await db.camp_days.find_one({"_id": ObjectId(state["operating_day_id"])})
    if operating and operating["_id"] != patient.get("camp_day_id"):
        booked = await db.camp_days.find_one({"_id": patient["camp_day_id"]})
        updates["camp_day_id"] = operating["_id"]
        updates["camp_day_changed_from"] = booked["day_date"] if booked else None
    arrived = await db.patients.find_one_and_update(
        {"_id": patient["_id"], "arrived_at": None}, {"$set": updates}, return_document=True,
    )
    if not arrived:
        arrived = await db.patients.find_one({"_id": patient["_id"]})
    if not arrived:
        raise api_error(404, "REGISTRATION_NOT_FOUND", 'Registration not found')
    return arrived


async def _apply_overwrite(db: AsyncDatabase, patient: dict, card: dict) -> dict:
    person = None
    if card["aadhaar_last4"] and card["dob"]:
        person, _ = await _resolve_person({
            "aadhaar_last4": card["aadhaar_last4"],
            "full_name": card["full_name"],
            "dob": card["dob"],
            "gender": card["gender"],
        })
    try:
        updated = await db.patients.find_one_and_update(
            {"_id": patient["_id"], "aadhaar_scanned": {"$ne": True}, "person_id": None,
             "printed_at": None, "queue_status": {"$ne": "seen"}}, {"$set": {
            **{field: card[field] for field in OVERWRITTEN_FIELDS},
            "full_name_normalized": normalize_name(card["full_name"] or ""),
            "aadhaar_scanned": True,
            "person_id": person["_id"] if person else None,
            "manual_entry": False,
            "manual_exception": None,
            "identity_recheck_required": False,
        }}, return_document=True)
    except DuplicateKeyError:
        if person:
            existing = await db.patients.find_one(
                {"person_id": person["_id"], "camp_id": patient["camp_id"]}
            )
            if existing:
                raise _dup_409(existing)
        raise
    if not updated:
        raise await _overwrite_refused(db, patient["_id"])
    return updated


@router.post("/scan")
async def scan(
    body: ScanBody,
    actor: dict = Depends(require_staff),
) -> Dict[str, Any]:
    """Resolve a camp-day Lock against the active camp. Never creates a registration."""
    db = get_db()
    camp = await _active_camp(db)
    state = await _require_door_open(db, camp)
    card = await _decode_card(body.payload)
    person = await _known_person(db, card)
    hits = await _duplicate_hits(db, camp["_id"], _card_as_register_body(card), person)

    scanned_hits = [h for h in hits if _is_scanned_row(h)]
    own = next((h for h in scanned_hits if person and h.get("person_id") == person["_id"]), None)
    if own:
        arrived = await _stamp_arrival(db, own, str(actor["_id"]), camp, state)
        return {
            "outcome": "arrived",
            "registration": ser_patient(arrived),
            "prescription": await _printable_prescription(db, arrived, camp, state),
        }
    if scanned_hits:
        return {
            "outcome": "mismatch_review",
            "registration": ser_patient(scanned_hits[0]),
            "card": card,
            "diff": material_diff(card, scanned_hits[0]),
        }

    manual_hits = [h for h in hits if _is_manual(h)]
    if len(manual_hits) > 1:
        return {"outcome": "ambiguous", "registrations": [ser_patient(h) for h in manual_hits]}
    if len(manual_hits) == 1:
        diff = material_diff(card, manual_hits[0])
        if not diff:
            patient = await _apply_overwrite(db, manual_hits[0], card)
            arrived = await _stamp_arrival(db, patient, str(actor["_id"]), camp, state)
            return {
                "outcome": "arrived",
                "registration": ser_patient(arrived),
                "prescription": await _printable_prescription(db, arrived, camp, state),
                "overwritten": True,
            }
        return {
            "outcome": "mismatch_review",
            "registration": ser_patient(manual_hits[0]),
            "card": card,
            "diff": diff,
        }
    return {"outcome": "no_match", "card": card}


@router.post("/scan/confirm")
async def scan_confirm(
    body: ScanConfirmBody,
    actor: dict = Depends(require_staff),
) -> Dict[str, Any]:
    """Stamp Arrival on the registration the volunteer confirmed, applying the Aadhaar overwrite to a Manual entry."""
    db = get_db()
    camp = await _active_camp(db)
    state = await _require_door_open(db, camp)
    card = await _decode_card(body.payload)
    patient = await db.patients.find_one({"_id": ObjectId(body.patient_id)})
    if not patient:
        raise api_error(404, "REGISTRATION_NOT_FOUND", 'Registration not found')
    _require_in_camp(patient, camp)
    person = await _known_person(db, card)
    hits = await _duplicate_hits(db, camp["_id"], _card_as_register_body(card), person)
    if all(hit["_id"] != patient["_id"] for hit in hits):
        holder = next((hit for hit in hits if person and hit.get("person_id") == person["_id"]), None)
        if holder:
            raise _dup_409(holder)
        raise api_error(409, "STALE_CANDIDATE", 'That registration does not match this card.')
    if _is_manual(patient):
        patient = await _apply_overwrite(db, patient, card)
    arrived = await _stamp_arrival(db, patient, str(actor["_id"]), camp, state)
    return {
        "outcome": "arrived",
        "registration": ser_patient(arrived),
        "prescription": await _printable_prescription(db, arrived, camp, state),
    }


@router.post("/arrive/{patient_id}")
async def arrive(
    patient_id: str,
    actor: dict = Depends(require_staff),
) -> Dict[str, Any]:
    db = get_db()
    camp = await _active_camp(db)
    p = await db.patients.find_one({"_id": ObjectId(patient_id)})
    if not p:
        raise api_error(404, "REGISTRATION_NOT_FOUND", 'Registration not found')
    _require_in_camp(p, camp)
    if not (p.get("aadhaar_scanned") or p.get("no_card_print") or p.get("arrived_at")):
        raise api_error(409, "NEEDS_DOOR_SCAN", "Scan this patient's Aadhaar card at the door, or record a No-card print.")
    state = await (_printing_state(db, camp) if p.get("arrived_at") else _require_door_open(db, camp))
    arrived = await _stamp_arrival(db, p, str(actor["_id"]), camp, state)
    return {"registration": ser_patient(arrived), "prescription": await _printable_prescription(db, arrived, camp, state)}


def _print_refusal(p: dict, state: dict) -> Optional[HTTPException]:
    if p.get("queue_status") == "seen":
        return api_error(409, "ALREADY_SEEN", 'The doctor has already seen this patient. The prescription cannot be printed again.')
    if not p.get("arrived_at"):
        return api_error(409, "NOT_ARRIVED", 'Scan the patient in at the door before printing.')
    if p.get("printed_at"):
        return None
    if not state.get("printing_open"):
        return api_error(409, "PRINT_WINDOW_CLOSED", 'The print window is closed.')
    if p.get("identity_recheck_required"):
        return api_error(409, "NEEDS_DOOR_SCAN", "Scan this patient's Aadhaar card at the door, or record a No-card print.")
    return None


async def _prescription_payload(db, p: dict, actor: dict, stamp: bool, camp: dict) -> Dict[str, Any]:
    refusal = _print_refusal(p, await _printing_state(db, camp))
    if refusal:
        raise refusal
    day = await db.camp_days.find_one({"_id": p["camp_day_id"]})
    if not day:
        raise api_error(404, "CAMP_DAY_NOT_FOUND", 'Camp day not found')
    if stamp and not p.get("printed_at"):
        stamped = await db.patients.find_one_and_update(
            {
                "_id": p["_id"], "printed_at": None,
                "queue_status": {"$ne": "seen"}, "identity_recheck_required": {"$ne": True},
            },
            {"$set": {
                "printed_at": now_utc(),
                "checked_in_by": str(actor["_id"]),
                "printed_by_name": actor.get("name"),
            }},
            return_document=True,
        )
        p = stamped or await db.patients.find_one({"_id": p["_id"]})
        if not p:
            raise api_error(404, "REGISTRATION_NOT_FOUND", 'Registration not found')
        if not p.get("printed_at"):
            raise api_error(409, "PRINT_CONFLICT", 'This registration changed while printing. Try again.')
    return {"registration": ser_patient(p), "prescription": _prescription(p, camp, day["day_date"])}


def _prescription(p: dict, camp: Optional[dict], day_date: str) -> Dict[str, Any]:
    return {
        "camp_id": str(p["camp_id"]),
        "camp_name": camp["name"] if camp else None,
        "venue": camp["venue"] if camp else None,
        "reg_no": p["reg_no"],
        "full_name": p["full_name"],
        "address": p.get("address"),
        "age": p.get("age"),
        "gender": p.get("gender"),
        "phone": p.get("phone"),
        "date": day_date,
        "patient_qr": p["patient_qr"],
    }


async def _printable_prescription(db: AsyncDatabase, p: dict, camp: dict, state: dict) -> Optional[Dict[str, Any]]:
    if p.get("printed_at") or _print_refusal(p, state):
        return None
    day = await db.camp_days.find_one({"_id": p["camp_day_id"]})
    return _prescription(p, camp, day["day_date"]) if day else None


@router.get("/print/{patient_id}")
async def preview_prescription(
    patient_id: str,
    actor: dict = Depends(require_staff),
) -> Dict[str, Any]:
    db = get_db()
    camp = await _active_camp(db)
    p = await db.patients.find_one({"_id": ObjectId(patient_id)})
    if not p:
        raise api_error(404, "REGISTRATION_NOT_FOUND", 'Registration not found')
    _require_in_camp(p, camp)
    return await _prescription_payload(db, p, actor, False, camp)


@router.post("/print/{patient_id}")
async def print_prescription(
    patient_id: str,
    actor: dict = Depends(require_staff),
) -> Dict[str, Any]:
    db = get_db()
    camp = await _active_camp(db)
    p = await db.patients.find_one({"_id": ObjectId(patient_id)})
    if not p:
        raise api_error(404, "REGISTRATION_NOT_FOUND", 'Registration not found')
    _require_in_camp(p, camp)
    return await _prescription_payload(db, p, actor, True, camp)


@router.post("/no-card")
async def record_no_card_print(
    body: NoCardBody,
    actor: dict = Depends(require_staff),
) -> Dict[str, Any]:
    note = checked_manual_note(body.reason, body.note)
    db = get_db()
    camp = await _active_camp(db)
    await _require_door_open(db, camp)
    p = await db.patients.find_one({"_id": ObjectId(body.patient_id)})
    if not p:
        raise api_error(404, "REGISTRATION_NOT_FOUND", 'Registration not found')
    _require_in_camp(p, camp)
    released = await db.patients.find_one_and_update(
        {"_id": p["_id"], "identity_recheck_required": True},
        {"$set": {
            "identity_recheck_required": False,
            "no_card_print": {"reason": body.reason, "note": note, "by": str(actor["_id"]), "at": now_utc()},
        }},
        return_document=True,
    )
    return {"registration": ser_patient(released or p)}
