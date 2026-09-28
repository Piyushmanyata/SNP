from typing import Any, Dict, List, Optional, Tuple
from fastapi import APIRouter, HTTPException, Depends, Request, BackgroundTasks
from bson import ObjectId
from pymongo.errors import DuplicateKeyError
from pymongo.asynchronous.database import AsyncDatabase
from db import get_db, next_seq
from models import AadhaarDecodeBody, RegisterBody
from helpers import (
    api_error,    OVERWRITTEN_FIELDS, now_utc, normalize_name, normalize_phone, is_dummy_phone,
    new_patient_code, age_from_dob, today_ist_str,
)
from serializers import ser_patient
from security import get_current_user, require_staff, require_any
from routes_camps import effective_printing
import arrival
from aadhaar import decode_aadhaar
from aadhaar_extract import extract_document
import sms
import limits
import lock_resolution
from lock_resolution import duplicate_in_camp
from datetime import date, timedelta
from itertools import permutations
import asyncio
import logging
import re

router = APIRouter(prefix="/api", tags=["registration"])
logger = logging.getLogger(__name__)

NETWORK_WINDOW = timedelta(minutes=10)
SELF_REGISTER_PER_NETWORK = 120
DECODE_PER_NETWORK = 240
SELF_REGISTER_PER_PHONE = 12
SELF_REGISTER_PER_CAMP_DAY = 6000
HOUSEHOLD_LIMIT = 6
CARD_IN_HAND = ("card_unreadable", "scanner_down")
LOOKALIKE_AGE_SPAN = 5
LOOKALIKE_MAX_WORDS = 6


def _network(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("/aadhaar/extract")
async def aadhaar_extract(request: Request) -> Dict[str, Any]:
    return await extract_document(request)


@router.post("/aadhaar/decode")
async def aadhaar_decode(body: AadhaarDecodeBody, request: Request) -> Dict[str, Any]:
    try:
        await get_current_user(request)
    except HTTPException:
        await limits.spend(get_db(), "decode-network", _network(request), DECODE_PER_NETWORK, NETWORK_WINDOW)
    return await asyncio.to_thread(decode_aadhaar, body.payload)


async def _validate_camp_and_day(db: AsyncDatabase, camp_day_id: str) -> tuple[dict, dict, bool]:
    """Returns the active camp, the day and whether the day is the Operating day."""
    camp = await db.camps.find_one({"is_active": True})
    if not camp:
        raise api_error(409, "NO_ACTIVE_CAMP", 'No active camp')

    day = await db.camp_days.find_one({"_id": ObjectId(camp_day_id), "camp_id": camp["_id"]})
    if not day:
        raise api_error(404, "CAMP_DAY_NOT_FOUND", 'Camp day not found')
    days = await db.camp_days.find({"camp_id": camp["_id"]}).to_list(100)
    operating = effective_printing(camp, days)["operating_day_id"] == str(day["_id"])
    if day["day_date"] < today_ist_str() and not operating:
        raise api_error(409, "DAY_PASSED", 'That camp day has passed. Choose a later day.')
    return camp, day, operating


async def _lookalikes(db: AsyncDatabase, camp_id: ObjectId | str, body: RegisterBody) -> List[Dict[str, Any]]:
    tokens = normalize_name(body.full_name).split()
    if body.age is None or not tokens:
        return []
    orders = {" ".join(order) for order in permutations(tokens)} if len(tokens) <= LOOKALIKE_MAX_WORDS else {" ".join(tokens)}
    return await db.patients.find({
        "camp_id": camp_id,
        "full_name_normalized": {"$in": list(orders)},
        "age": {"$gte": body.age - LOOKALIKE_AGE_SPAN, "$lte": body.age + LOOKALIKE_AGE_SPAN},
    }).sort("reg_no", 1).to_list(20)


async def _assert_capacity(db: AsyncDatabase, day: dict, enforce_limit: bool = True) -> None:
    limit = day.get("seat_limit") or 0
    if limit <= 0:
        return
    if not enforce_limit:
        await db.camp_days.update_one({"_id": day["_id"]}, {"$inc": {"booked": 1}})
        return
    updated = await db.camp_days.find_one_and_update(
        {"_id": day["_id"], "$expr": {"$lt": ["$booked", "$seat_limit"]}},
        {"$inc": {"booked": 1}},
        return_document=True,
    )
    if not updated:
        raise api_error(409, "CAMP_DAY_FULL", 'This camp day is full.')


async def _release_capacity(db: AsyncDatabase, day_id) -> None:
    await db.camp_days.update_one(
        {"_id": day_id, "booked": {"$gt": 0}},
        {"$inc": {"booked": -1}},
    )


def _build_patient_document(
    camp_id: ObjectId | str,
    camp_day_id: ObjectId | str,
    reg_no: int,
    body: RegisterBody,
    person_id: Optional[ObjectId | str],
    phone: str | None,
    age: int | None,
    actor_id: Optional[ObjectId | str],
    is_self: bool,
    registrar_team_lead_id: Optional[str] = None,
) -> dict:
    norm = normalize_name(body.full_name)
    is_manual = not body.aadhaar_scanned

    return {
        "person_id": person_id,
        "camp_id": camp_id,
        "camp_day_id": camp_day_id,
        "booked_camp_day_id": camp_day_id,
        "reg_no": reg_no,
        "full_name": body.full_name,
        "full_name_normalized": norm,
        "gender": body.gender,
        "age": age,
        "address": body.address,
        "phone": phone,
        "phone_normalized": phone,
        "aadhaar_last4": body.aadhaar_last4,
        "dob": body.dob,
        "aadhaar_scanned": body.aadhaar_scanned,
        "queue_status": "registered",
        "patient_qr": new_patient_code(),
        "printed_at": None,
        "seen_at": None,
        "seen_by": None,
        "checked_in_by": None,
        "created_by": str(actor_id) if actor_id else None,
        "is_self_registered": is_self,
        "registration_source": "self" if is_self else "staff",
        "registrar_team_lead_id": None if is_self else registrar_team_lead_id,
        "clinical_generation": 0,
        "committed_revision_id": None,
        "identity_recheck_required": is_manual and not body.at_door,
        "manual_entry": is_manual,
        "manual_exception": True if is_manual else None,
        "manual_reason": body.manual_reason if is_manual else None,
        "manual_note": body.manual_note if is_manual else None,
        "manual_at_door": bool(body.at_door) if is_manual else False,
        **arrival.fields_at_creation(str(actor_id) if body.at_door and actor_id else None, now_utc()),
        **({"registration_request_id": body.registration_request_id} if body.registration_request_id else {}),
        "reminder_sms_sent_at": None,
        "created_at": now_utc(),
    }


def _registration_card(body: RegisterBody) -> Dict[str, Any]:
    card = {name: getattr(body, name) for name in OVERWRITTEN_FIELDS}
    if card["age"] is None and body.dob:
        card["age"] = age_from_dob(body.dob)
    return card


async def _resolve_registration_conflict(
    db: AsyncDatabase,
    candidates: list[dict],
    card: dict,
    body: RegisterBody,
    person: dict | None,
    is_self: bool,
) -> Optional[Tuple[Dict[str, Any], bool]]:
    """The registration desk's translation of the Lock Outcome."""
    outcome = lock_resolution.classify(card, candidates, person, scanned=bool(body.aadhaar_scanned))
    if outcome.kind == "none":
        return None
    if outcome.kind == "duplicate":
        raise duplicate_in_camp(outcome.registration)
    if outcome.kind in ("own", "scanned_elsewhere"):
        raise duplicate_in_camp(next(c for c in candidates if lock_resolution.is_scanned(c)))
    if outcome.kind == "ambiguous":
        raise api_error(409, "AMBIGUOUS_MANUAL_ENTRY", 'Multiple Manual entries match this card', registrations=[ser_patient(h) for h in outcome.registrations])
    target = outcome.registration
    if is_self:
        raise duplicate_in_camp(target)
    if outcome.kind == "review" and body.review_confirmed_id != str(target["_id"]):
        raise api_error(409, "MISMATCH_REVIEW_REQUIRED", 'This card differs from the Manual entry. Check the details before replacing them.', registration=ser_patient(target), card=card, diff=outcome.diff)
    updated = await lock_resolution.overwrite(
        db, target, card, person,
        {"registration_request_id": body.registration_request_id} if body.registration_request_id else None,
    )
    return ser_patient(updated), False


def _replay_registration(existing: dict, body: RegisterBody, camp_id: ObjectId | str) -> Tuple[Dict[str, Any], bool]:
    matches = (
        str(existing.get("camp_id")) == str(camp_id)
        and str(existing.get("booked_camp_day_id") or existing.get("camp_day_id")) == body.camp_day_id
        and normalize_name(existing.get("full_name") or "") == normalize_name(body.full_name)
    )
    if body.aadhaar_scanned:
        matches = matches and all(existing.get(field) == getattr(body, field) for field in ("aadhaar_last4", "dob"))
    if not matches:
        raise api_error(409, "REGISTRATION_REQUEST_CONFLICT", 'This request ID was already used for a different registration. Start a new registration.')
    return ser_patient(existing), False


async def _insert_patient_document(
    db: AsyncDatabase,
    doc: dict,
    body: RegisterBody,
    person: dict | None,
    camp_id: ObjectId | str,
) -> Tuple[Dict[str, Any], bool]:
    retries = 2
    while True:
        try:
            res = await db.patients.insert_one(doc)
            doc["_id"] = res.inserted_id
            return ser_patient(doc), True
        except DuplicateKeyError as exc:
            if body.registration_request_id:
                existing = await db.patients.find_one({"registration_request_id": body.registration_request_id})
                if existing:
                    return _replay_registration(existing, body, camp_id)
            if person:
                existing = await db.patients.find_one({"person_id": person["_id"], "camp_id": camp_id})
                if existing:
                    raise duplicate_in_camp(existing)
            if (exc.details or {}).get("keyPattern") != {"patient_qr": 1} or not retries:
                raise
            retries -= 1
            doc["patient_qr"] = new_patient_code()


async def _create_registration(
    body: RegisterBody,
    actor_id: Optional[ObjectId | str],
    is_self: bool,
    request: Request,
) -> Tuple[Dict[str, Any], bool]:
    db = get_db()
    camp, day, operating = await _validate_camp_and_day(db, body.camp_day_id)

    if body.registration_request_id:
        existing = await db.patients.find_one({"registration_request_id": body.registration_request_id})
        if existing:
            return _replay_registration(existing, body, camp["_id"])

    if is_self and not body.aadhaar_scanned:
        raise api_error(400, "MANUAL_ENTRY_NOT_ALLOWED", 'Scan the Aadhaar card. Public registration has no manual entry.')
    if is_self:
        body.at_door = False
    if not body.aadhaar_scanned:
        _reject_unscanned_staff_entry(body)
    if body.at_door and not operating:
        raise api_error(409, "NOT_OPERATING_DAY", 'The door registers patients for the Operating day only.')

    phone = normalize_phone(body.phone)
    if is_self and (not phone or is_dummy_phone(phone)):
        raise api_error(400, "A_VALID_10_DIGIT_MOBILE_NUMBER_IS_REQUIRED", 'A valid 10-digit mobile number is required')
    if phone and is_dummy_phone(phone):
        raise api_error(400, "PLEASE_ENTER_A_VALID_10_DIGIT_MOBILE_NUMBER", 'Please enter a valid 10-digit mobile number')
    if is_self and await db.patients.count_documents(
        {"camp_id": camp["_id"], "phone_normalized": phone}, limit=HOUSEHOLD_LIMIT,
    ) >= HOUSEHOLD_LIMIT:
        raise api_error(409, "HOUSEHOLD_LIMIT", f'This mobile number already has {HOUSEHOLD_LIMIT} registrations for this camp. Ask at the camp desk.')

    card = _registration_card(body)
    person = None
    if body.aadhaar_scanned and body.aadhaar_last4 and body.dob:
        person, _ = await lock_resolution.resolve_person(db, card)

    candidates = await lock_resolution.find_candidates(
        db, camp["_id"], card, person, scanned=bool(body.aadhaar_scanned), phone=body.phone,
    )
    conflict_result = await _resolve_registration_conflict(db, candidates, card, body, person, is_self)
    if conflict_result is not None:
        return conflict_result
    lookalikes = [] if body.aadhaar_scanned else await _lookalikes(db, camp["_id"], body)
    if lookalikes and not body.different_person:
        raise api_error(
            409, "LOOKALIKES", 'Someone with this name and a similar age is already registered. Check them first.',
            registrations=[ser_patient(p) for p in lookalikes],
        )

    walk_in = not is_self and operating
    await _assert_capacity(db, day, enforce_limit=not walk_in)
    try:
        age = card["age"]
        reg_no = await next_seq("reg_no")
        team_lead_id = None
        if not is_self and actor_id:
            uid = actor_id if isinstance(actor_id, ObjectId) else ObjectId(str(actor_id))
            user = await db.users.find_one({"_id": uid})
            if user:
                if user.get("role") == "team_lead":
                    team_lead_id = str(user["_id"])
                else:
                    team_lead_id = user.get("team_lead_id")
        doc = _build_patient_document(
            camp_id=camp["_id"],
            camp_day_id=day["_id"],
            reg_no=reg_no,
            body=body,
            person_id=person["_id"] if person else None,
            phone=phone,
            age=age,
            actor_id=actor_id,
            is_self=is_self,
            registrar_team_lead_id=team_lead_id,
        )
        if not body.aadhaar_scanned:
            doc["lookalikes_overridden"] = [p["_id"] for p in lookalikes]
        patient, created = await _insert_patient_document(db, doc, body, person, camp["_id"])
        if not created:
            await _release_capacity(db, day["_id"])
        return patient, created
    except Exception:
        await _release_capacity(db, day["_id"])
        raise


async def _confirm_registration(patient: Dict[str, Any], skip_walk_in: bool = False) -> None:
    db = get_db()
    row = await db.patients.find_one({"_id": ObjectId(patient["id"])})
    day = await db.camp_days.find_one({"_id": ObjectId(patient["camp_day_id"])})
    camp = await db.camps.find_one({"_id": ObjectId(patient["camp_id"])})
    if not row or not day or not camp:
        return
    if skip_walk_in:
        days = await db.camp_days.find({"camp_id": camp["_id"]}).to_list(100)
        if effective_printing(camp, days)["operating_day_id"] == str(day["_id"]):
            return
    await sms.record_and_send(
        db, row, "registration", day["day_date"], camp.get("venue_sms") or camp["venue"],
        event_key=sms.edit_key(day["edit_revision"]) if day.get("edit_revision") else None,
        now=now_utc(),
    )


async def _apply_scanned_identity(body: RegisterBody, message: str) -> None:
    decoded = await asyncio.to_thread(decode_aadhaar, body.qr_payload or "")
    card = decoded["data"] if decoded.get("outcome") == "card" else None
    if not card:
        raise api_error(400, "AADHAAR_QR_REQUIRED", message)
    body.full_name = card.get("full_name") or ""
    body.gender = card.get("gender")
    body.dob = card.get("dob")
    body.age = card.get("age")
    body.aadhaar_last4 = card.get("aadhaar_last4")
    body.address = card.get("address")
    body.aadhaar_scanned = True


def _validate_manual_identity(body: RegisterBody, now) -> None:
    body.full_name = (body.full_name or '').strip()
    if not body.full_name or len(body.full_name) > 120:
        raise api_error(400, "ENTER_A_FULL_NAME_OF_UP_TO_120_CHARACTERS", 'Enter a full name of up to 120 characters')
    body.dob = (body.dob or '').strip() or None
    if body.dob:
        year_only = bool(re.fullmatch(r'[0-9]{4}', body.dob))
        if not year_only and not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', body.dob):
            raise api_error(400, "ENTER_A_VALID_DATE_OF_BIRTH_AS_YYYY_MM_DD_OR_A_FOUR_DIGIT_YE", 'Enter a valid date of birth as YYYY-MM-DD or a four-digit year')
        if year_only:
            body.dob += '-01-01'
        try:
            dob = date.fromisoformat(body.dob)
        except ValueError:
            raise api_error(400, "ENTER_A_VALID_DATE_OF_BIRTH_AS_YYYY_MM_DD_OR_A_FOUR_DIGIT_YE", 'Enter a valid date of birth as YYYY-MM-DD or a four-digit year')
        if dob > now.date() or now.year - dob.year > 130:
            raise api_error(400, "ENTER_A_DATE_OF_BIRTH_WITHIN_THE_LAST_130_YEARS", 'Enter a date of birth within the last 130 years')
        if body.age is None:
            body.age = age_from_dob(dob.isoformat())
    if body.age is None or not 0 <= body.age <= 130:
        raise api_error(400, "ENTER_AN_AGE_BETWEEN_0_AND_130_OR_A_VALID_DATE_OF_BIRTH", 'Enter an age between 0 and 130, or a valid date of birth')
    if not body.gender:
        raise api_error(400, "GENDER_REQUIRED", "Choose the patient's gender.")


def checked_manual_note(reason: Optional[str], note: Optional[str]) -> Optional[str]:
    if not reason:
        raise api_error(400, "MANUAL_ENTRY_NOT_ALLOWED", 'Scan the Aadhaar card, or choose why it cannot be scanned.')
    if reason != "other":
        return None
    note = (note or "").strip()
    if not note:
        raise api_error(400, "MANUAL_NOTE_REQUIRED", 'Write why the card cannot be scanned.')
    return note


def _reject_unscanned_staff_entry(body: RegisterBody) -> None:
    body.manual_note = checked_manual_note(body.manual_reason, body.manual_note)
    if body.manual_reason in CARD_IN_HAND and not body.aadhaar_last4:
        raise api_error(400, "AADHAAR_LAST4_REQUIRED", 'The card is here: type the last 4 digits of its Aadhaar number.')


@router.post("/register")
async def desk_register(
    body: RegisterBody,
    request: Request,
    background_tasks: BackgroundTasks,
    actor: dict = Depends(require_staff),
) -> Dict[str, Any]:
    if body.aadhaar_scanned:
        await _apply_scanned_identity(
            body, "We could not read that Aadhaar QR. Scan the card again, or register manually.",
        )
    else:
        _validate_manual_identity(body, now_utc())
    phone_norm = normalize_phone(body.phone)
    if not phone_norm or is_dummy_phone(phone_norm):
        raise api_error(400, "A_VALID_10_DIGIT_HOUSEHOLD_MOBILE_NUMBER_IS_REQUIRED", 'A valid 10-digit household mobile number is required')
    patient, created = await _create_registration(
        body, actor["_id"], False, request,
    )
    if created:
        if background_tasks is not None:
            background_tasks.add_task(_confirm_registration, patient, True)
        else:
            await _confirm_registration(patient, True)
    return {"registration": patient, "created": created}


@router.post("/self-register")
async def self_register(body: RegisterBody, request: Request, background_tasks: BackgroundTasks) -> Dict[str, Any]:
    db = get_db()
    await limits.spend(db, "self-network", _network(request), SELF_REGISTER_PER_NETWORK, NETWORK_WINDOW)
    camp = await db.camps.find_one({"is_active": True})
    ceiling = f"self-camp:{camp['_id'] if camp else None}:{today_ist_str()}"
    await limits.refuse_at(db, ceiling, SELF_REGISTER_PER_CAMP_DAY)
    await _apply_scanned_identity(
        body, "We could not read the QR code on this Aadhaar card. Please register at the camp desk.",
    )
    phone = normalize_phone(body.phone)
    if phone:
        await limits.spend(db, "self-phone", phone, SELF_REGISTER_PER_PHONE, timedelta(hours=1))
    try:
        patient, created = await _create_registration(body, None, True, request)
    except HTTPException as exc:
        if isinstance(exc.detail, dict):
            raise api_error(
                exc.status_code,
                str(exc.detail.get("code") or "ERROR").upper(),
                str(exc.detail.get("message") or "Something went wrong. Try again."),
            ) from exc
        raise
    if created:
        if background_tasks is not None:
            background_tasks.add_task(_confirm_registration, patient)
        else:
            await _confirm_registration(patient)
        try:
            await limits.add(db, ceiling)
        except Exception:
            logger.exception("Could not count a self-registration against the camp's daily ceiling")
    day = await db.camp_days.find_one({"_id": ObjectId(body.camp_day_id)})
    return {
        "registration": patient,
        "receipt": {
            "reg_no": patient["reg_no"],
            "patient_qr": patient["patient_qr"],
            "camp_name": camp["name"] if camp else None,
            "venue": camp["venue"] if camp else None,
            "day_date": day["day_date"] if day else None,
        },
    }


@router.get("/patients/search")
async def name_search(q: str, actor: dict = Depends(require_any)) -> Dict[str, Any]:
    db = get_db()
    camp = await db.camps.find_one({"is_active": True})
    if not camp:
        return {"results": []}
    phone = normalize_phone(q)
    if phone and len(phone) == 10 and q.strip().replace(" ", "").isdigit():
        results = await db.patients.find({
            "camp_id": camp["_id"],
            "phone_normalized": phone,
        }).limit(25).to_list(25)
        return {"results": [ser_patient(r) for r in results]}
    norm = normalize_name(q)
    if not norm:
        return {"results": []}
    results = await db.patients.find({
        "camp_id": camp["_id"],
        "full_name_normalized": {"$regex": "^" + norm},
    }).limit(25).to_list(25)
    return {"results": [ser_patient(r) for r in results]}
