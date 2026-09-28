import asyncio
import hmac
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from fastapi import HTTPException, APIRouter, Depends
from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase
from db import get_db
from models import NoCardBody, PaperCheckBody, QrLookupBody, ScanBody, ScanConfirmBody
from helpers import IST, now_ist, now_utc, age_from_dob, parse_patient_identifier, api_error
from serializers import ser_patient
from security import require_staff, sign
from routes_camps import effective_printing
import arrival
from aadhaar import decode_aadhaar
import lock_resolution
from lock_resolution import duplicate_in_camp, is_manual
from routes_registration import CARD_IN_HAND, checked_manual_note
router = APIRouter(prefix="/api/desk", tags=["desk"])

MAX_REG_NO_DIGITS = 12
SHEET_STAMP = "sheet-stamp"


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


async def _overwrite(db: AsyncDatabase, patient: dict, card: dict) -> dict:
    person = None
    if card["aadhaar_last4"] and card["dob"]:
        person, _ = await lock_resolution.resolve_person(db, card)
    return await lock_resolution.overwrite(db, patient, card, person)


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
    person = await lock_resolution.find_person(db, card)
    candidates = await lock_resolution.find_candidates(db, camp["_id"], card, person, scanned=True)
    outcome = lock_resolution.classify(card, candidates, person)
    if outcome.kind in ("own", "overwrite"):
        patient = outcome.registration
        if outcome.kind == "overwrite":
            patient = await _overwrite(db, patient, card)
        arrived = await arrival.stamp(db, patient, str(actor["_id"]), state)
        return {
            "outcome": "arrived",
            "registration": ser_patient(arrived),
            "prescription": await _printable_prescription(db, arrived, camp, state),
            **({"overwritten": True} if outcome.kind == "overwrite" else {}),
        }
    if outcome.kind in ("scanned_elsewhere", "review"):
        return {
            "outcome": "mismatch_review",
            "registration": ser_patient(outcome.registration),
            "card": card,
            "diff": outcome.diff,
        }
    if outcome.kind == "ambiguous":
        return {"outcome": "ambiguous", "registrations": [ser_patient(h) for h in outcome.registrations]}
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
    person = await lock_resolution.find_person(db, card)
    candidates = await lock_resolution.find_candidates(db, camp["_id"], card, person, scanned=True)
    if all(candidate["_id"] != patient["_id"] for candidate in candidates):
        holder = next((c for c in candidates if person and c.get("person_id") == person["_id"]), None)
        if holder:
            raise duplicate_in_camp(holder)
        raise api_error(409, "STALE_CANDIDATE", 'That registration does not match this card.')
    if is_manual(patient):
        patient = await _overwrite(db, patient, card)
    arrived = await arrival.stamp(db, patient, str(actor["_id"]), state)
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
    arrival.require_arrivable(p)
    state = await _printing_state(db, camp)
    arrived = await arrival.stamp(db, p, str(actor["_id"]), state)
    return {"registration": ser_patient(arrived), "prescription": await _printable_prescription(db, arrived, camp, state)}


def _print_refusal(p: dict, state: dict, fetched_while_open: bool = False) -> Optional[HTTPException]:
    if p.get("queue_status") == "seen":
        return api_error(409, "ALREADY_SEEN", 'The doctor has already seen this patient. The prescription cannot be printed again.')
    if not p.get("arrived_at"):
        return api_error(409, "NOT_ARRIVED", 'Scan the patient in at the door before printing.')
    if p.get("printed_at"):
        return None
    if not state.get("printing_open") and not fetched_while_open:
        return api_error(409, "PRINT_WINDOW_CLOSED", 'The print window is closed.')
    if p.get("identity_recheck_required"):
        return api_error(409, "NEEDS_DOOR_SCAN", "Scan this patient's Aadhaar card at the door, or record a No-card print.")
    return None


def _sheet_signature(p: dict, fetched_ms: str) -> str:
    return sign(SHEET_STAMP, "|".join((str(p["_id"]), fetched_ms)))


def _sheet_stamp(p: dict) -> str:
    """Signs the moment a first-print sheet left the server while the Print window was open (ADR 0093)."""
    fetched_ms = str(int(now_utc().timestamp() * 1000))
    return f"{fetched_ms}.{_sheet_signature(p, fetched_ms)}"


def _fetched_while_open(p: dict, stamp: Optional[str]) -> bool:
    fetched_ms, _, signature = (stamp or "").partition(".")
    if not fetched_ms.isdecimal() or not hmac.compare_digest(signature, _sheet_signature(p, fetched_ms)):
        return False
    fetched = datetime.fromtimestamp(int(fetched_ms) / 1000, timezone.utc)
    return fetched <= now_utc() and fetched.astimezone(IST).date() == now_ist().date()


async def _prescription_payload(
    db, p: dict, actor: dict, stamp: bool, camp: dict, sheet_stamp: Optional[str] = None,
) -> Dict[str, Any]:
    state = await _printing_state(db, camp)
    refusal = _print_refusal(p, state, stamp and _fetched_while_open(p, sheet_stamp))
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
    return {"registration": ser_patient(p), "prescription": _sheet(p, camp, day["day_date"])}


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


def _sheet(p: dict, camp: dict, day_date: str) -> Dict[str, Any]:
    prescription = _prescription(p, camp, day_date)
    if not p.get("printed_at"):
        prescription["sheet_stamp"] = _sheet_stamp(p)
    return prescription


async def _printable_prescription(db: AsyncDatabase, p: dict, camp: dict, state: dict) -> Optional[Dict[str, Any]]:
    if p.get("printed_at") or _print_refusal(p, state):
        return None
    day = await db.camp_days.find_one({"_id": p["camp_day_id"]})
    return _sheet(p, camp, day["day_date"]) if day else None


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
    body: Optional[PaperCheckBody] = None,
    actor: dict = Depends(require_staff),
) -> Dict[str, Any]:
    db = get_db()
    camp = await _active_camp(db)
    p = await db.patients.find_one({"_id": ObjectId(patient_id)})
    if not p:
        raise api_error(404, "REGISTRATION_NOT_FOUND", 'Registration not found')
    _require_in_camp(p, camp)
    return await _prescription_payload(db, p, actor, True, camp, body.sheet_stamp if body else None)


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
    if p.get("queue_status") == "seen":
        raise api_error(409, "ALREADY_SEEN", 'The doctor has already seen this patient. The prescription cannot be printed again.')
    if p.get("arrived_at"):
        return {"registration": ser_patient(p)}
    if lock_resolution.is_scanned(p) and body.reason in CARD_IN_HAND:
        if not body.aadhaar_last4:
            raise api_error(400, "AADHAAR_LAST4_REQUIRED", 'The card is here: type the last 4 digits of its Aadhaar number.')
        if body.aadhaar_last4 != p.get("aadhaar_last4"):
            raise api_error(409, "NO_CARD_LAST4_MISMATCH", "These last 4 digits do not match this patient's booking. Check the card and the patient.")
    recorded = await db.patients.find_one_and_update(
        {"_id": p["_id"], "arrived_at": None, "queue_status": {"$ne": "seen"}, "no_card_print": None},
        {"$set": {
            "identity_recheck_required": False,
            "no_card_print": {"reason": body.reason, "note": note, "by": str(actor["_id"]), "at": now_utc()},
        }},
        return_document=True,
    )
    current = recorded or await db.patients.find_one({"_id": p["_id"]})
    if not current:
        raise api_error(404, "REGISTRATION_NOT_FOUND", 'Registration not found')
    return {"registration": ser_patient(current)}
