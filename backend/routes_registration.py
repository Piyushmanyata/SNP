from typing import Any, Dict, List, Optional, Tuple
from fastapi import APIRouter, HTTPException, Depends, Request, BackgroundTasks
from bson import ObjectId
from pymongo.errors import DuplicateKeyError
from motor.motor_asyncio import AsyncIOMotorDatabase
from db import get_db, next_seq
from models import AadhaarDecodeBody, RegisterBody, DuplicateCheckBody
from helpers import (
    now_utc, normalize_name, normalize_phone, is_dummy_phone,
    person_key, new_patient_code, age_from_dob,
)
from serializers import ser_patient
from security import require_staff, require_any
from aadhaar import decode_aadhaar
from aadhaar_extract import extract_document
import sms
from datetime import date, timedelta
import re

router = APIRouter(prefix="/api", tags=["registration"])

# rate limit for self-register (per IP)
_rl: dict = {}


@router.post("/aadhaar/extract")
async def aadhaar_extract(request: Request) -> Dict[str, Any]:
    return await extract_document(request)


@router.post("/aadhaar/decode")
async def aadhaar_decode(body: AadhaarDecodeBody) -> Dict[str, Any]:
    result = decode_aadhaar(body.payload or "")
    if result["outcome"] == "card":
        result["data"]["age"] = age_from_dob(result["data"].get("dob") or "")
    return result


# ---------- soft duplicate check ----------
@router.post("/register/duplicate-check")
async def duplicate_check(body: DuplicateCheckBody, actor: dict = Depends(require_staff)) -> Dict[str, Any]:
    db = get_db()
    camp = await db.camps.find_one({"is_active": True})
    if not camp:
        return {"likely_duplicates": []}
    q = {"camp_id": camp["_id"], "full_name_normalized": normalize_name(body.full_name)}
    if body.age is not None:
        q["age"] = body.age
    dups = await db.patients.find(q).limit(5).to_list(5)
    return {"likely_duplicates": [ser_patient(d) for d in dups]}


async def _resolve_person(data: dict) -> Tuple[Dict[str, Any], bool]:
    """Find or create a Person from scanned aadhaar data. Returns (person, created)."""
    db = get_db()
    key = person_key(data["aadhaar_last4"], data["full_name"], data.get("dob", ""), data.get("gender", ""))
    person = await db.persons.find_one({"aadhaar_key": key})
    if person:
        return person, False
    person_no = await next_seq("person_no")
    doc = {
        "aadhaar_key": key,
        "person_no": person_no,
        "name_verbatim": data["full_name"],
        "latin_display_name": data.get("latin_display_name"),
        "dob": data.get("dob"),
        "gender": data.get("gender"),
        "last4": data["aadhaar_last4"],
        "locked": True,
        "merged_into": None,
        "created_at": now_utc(),
    }
    try:
        res = await db.persons.insert_one(doc)
    except DuplicateKeyError:
        person = await db.persons.find_one({"aadhaar_key": key})
        if person:
            return person, False
        raise
    doc["_id"] = res.inserted_id
    return doc, True


async def _validate_camp_and_day(db: AsyncIOMotorDatabase, camp_day_id: str) -> tuple[dict, dict]:
    camp = await db.camps.find_one({"is_active": True})
    if not camp:
        raise HTTPException(status_code=409, detail="No active camp")

    day = await db.camp_days.find_one({"_id": ObjectId(camp_day_id), "camp_id": camp["_id"]})
    if not day:
        raise HTTPException(status_code=404, detail="Camp day not found")
    return camp, day


def _is_manual(p: dict) -> bool:
    return bool(p.get("manual_entry") or p.get("manual_exception"))


def _is_scanned_row(p: dict) -> bool:
    return bool(p.get("aadhaar_scanned") or p.get("person_id"))


def _dup_409(row: dict) -> HTTPException:
    return HTTPException(status_code=409, detail={
        "code": "DUPLICATE_IN_CAMP",
        "message": "Already registered in this camp",
        "registration": ser_patient(row),
    })


def _build_duplicate_queries(body: RegisterBody, person: dict | None = None) -> list[dict]:
    queries = []
    if person:
        queries.append({"person_id": person["_id"]})
    norm = normalize_name(body.full_name)
    if body.aadhaar_last4 and norm:
        queries.append({"aadhaar_last4": body.aadhaar_last4, "full_name_normalized": norm})
    if body.aadhaar_last4 and body.dob:
        queries.append({"aadhaar_last4": body.aadhaar_last4, "dob": body.dob})
    phone = normalize_phone(body.phone)
    age = body.age if body.age is not None else (age_from_dob(body.dob) if body.dob else None)
    if norm and age is not None and phone:
        queries.append({
            "full_name_normalized": norm,
            "age": age,
            "phone_normalized": phone,
        })
    return queries


async def _duplicate_hits(
    db: AsyncIOMotorDatabase,
    camp_id: ObjectId | str,
    body: RegisterBody,
    person: dict | None = None,
) -> List[Dict[str, Any]]:
    queries = _build_duplicate_queries(body, person)
    hits = []
    seen = set()
    for q in queries:
        docs = await db.patients.find({"camp_id": camp_id, **q}).to_list(20)
        for d in docs:
            if d["_id"] not in seen:
                seen.add(d["_id"])
                hits.append(d)
    return hits


async def _assert_capacity(db: AsyncIOMotorDatabase, day: dict) -> None:
    limit = day.get("seat_limit") or 0
    if limit <= 0:
        return
    updated = await db.camp_days.find_one_and_update(
        {"_id": day["_id"], "$expr": {"$lt": ["$booked", "$seat_limit"]}},
        {"$inc": {"booked": 1}},
        return_document=True,
    )
    if not updated:
        raise HTTPException(status_code=409, detail={
            "code": "CAMP_DAY_FULL",
            "message": "This camp day is full.",
        })


async def _release_capacity(db: AsyncIOMotorDatabase, day_id) -> None:
    await db.camp_days.update_one(
        {"_id": day_id, "booked": {"$gt": 0}},
        {"$inc": {"booked": -1}},
    )


async def _overwrite_manual(
    db: AsyncIOMotorDatabase,
    target: dict,
    body: RegisterBody,
    person: Optional[dict],
    age: Optional[int],
) -> Tuple[Dict[str, Any], bool]:
    norm = normalize_name(body.full_name)
    if age is None and body.dob:
        age = age_from_dob(body.dob)
    updates = {
        "full_name": body.full_name,
        "full_name_normalized": norm,
        "latin_display_name": body.latin_display_name,
        "gender": body.gender,
        "age": age,
        "address": body.address,
        "aadhaar_last4": body.aadhaar_last4,
        "dob": body.dob,
        "aadhaar_scanned": True,
        "person_id": person["_id"] if person else None,
        "manual_entry": False,
        "manual_exception": None,
    }
    try:
        p = await db.patients.find_one_and_update(
            {"_id": target["_id"], "aadhaar_scanned": {"$ne": True}, "person_id": None},
            {"$set": updates}, return_document=True,
        )
    except DuplicateKeyError:
        if person:
            existing = await db.patients.find_one({"person_id": person["_id"], "camp_id": target["camp_id"]})
            if existing:
                raise _dup_409(existing)
        raise
    if not p:
        raise HTTPException(status_code=409, detail={
            "code": "NOT_A_MANUAL_ENTRY",
            "message": "This registration already has Aadhaar on file. Scan again.",
        })
    return ser_patient(p), False


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
    is_manual = (body.manual_entry or body.manual_exception) and not body.aadhaar_scanned

    return {
        "person_id": person_id,
        "camp_id": camp_id,
        "camp_day_id": camp_day_id,
        "booked_camp_day_id": camp_day_id,
        "reg_no": reg_no,
        "full_name": body.full_name,
        "full_name_normalized": norm,
        "latin_display_name": body.latin_display_name,
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
        "arrived_at": None,
        "arrived_by": None,
        "camp_day_changed_from": None,
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
        "issue_auth_op": None,
        "identity_recheck_required": is_manual,
        "manual_entry": is_manual,
        "manual_exception": True if is_manual else None,
        **({"registration_request_id": body.registration_request_id} if body.registration_request_id else {}),
        "reminder_sms_sent_at": None,
        "created_at": now_utc(),
    }


async def _resolve_registration_conflict(
    db: AsyncIOMotorDatabase,
    hits: list[dict],
    body: RegisterBody,
    person: dict | None,
    is_self: bool,
) -> Optional[Tuple[Dict[str, Any], bool]]:
    if not body.aadhaar_scanned:
        if hits:
            raise _dup_409(hits[0])
        return None

    scanned_hits = [h for h in hits if _is_scanned_row(h)]
    manual_hits = [h for h in hits if _is_manual(h) and not _is_scanned_row(h)]
    if scanned_hits:
        raise _dup_409(scanned_hits[0])
    if len(manual_hits) > 1:
        raise HTTPException(status_code=409, detail={
            "code": "AMBIGUOUS_MANUAL_ENTRY",
            "message": "Multiple Manual entries match this card",
            "registrations": [ser_patient(h) for h in manual_hits],
        })
    if len(manual_hits) == 1:
        if is_self:
            raise _dup_409(manual_hits[0])
        age = body.age if body.age is not None else (age_from_dob(body.dob) if body.dob else None)
        return await _overwrite_manual(db, manual_hits[0], body, person, age)
    return None


def _replay_registration(existing: dict, body: RegisterBody, camp_id: ObjectId | str) -> Tuple[Dict[str, Any], bool]:
    matches = (
        str(existing.get("camp_id")) == str(camp_id)
        and str(existing.get("booked_camp_day_id") or existing.get("camp_day_id")) == body.camp_day_id
        and normalize_name(existing.get("full_name") or "") == normalize_name(body.full_name)
    )
    if body.aadhaar_scanned:
        matches = matches and all(existing.get(field) == getattr(body, field) for field in ("aadhaar_last4", "dob"))
    if not matches:
        raise HTTPException(status_code=409, detail={
            "code": "REGISTRATION_REQUEST_CONFLICT",
            "message": "This request ID was already used for a different registration. Start a new registration.",
        })
    return ser_patient(existing), False


async def _insert_patient_document(
    db: AsyncIOMotorDatabase,
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
                    raise _dup_409(existing)
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
    camp, day = await _validate_camp_and_day(db, body.camp_day_id)

    if body.registration_request_id:
        existing = await db.patients.find_one({"registration_request_id": body.registration_request_id})
        if existing:
            return _replay_registration(existing, body, camp["_id"])

    phone = normalize_phone(body.phone)
    if is_self and (not phone or is_dummy_phone(phone)):
        raise HTTPException(status_code=400, detail="A valid 10-digit mobile number is required")
    if phone and is_dummy_phone(phone):
        raise HTTPException(status_code=400, detail="Please enter a valid 10-digit mobile number")

    person = None
    if body.aadhaar_scanned and body.aadhaar_last4 and body.dob:
        person, _ = await _resolve_person({
            "aadhaar_last4": body.aadhaar_last4,
            "full_name": body.full_name,
            "dob": body.dob,
            "gender": body.gender,
            "latin_display_name": body.latin_display_name,
        })

    hits = await _duplicate_hits(db, camp["_id"], body, person)
    conflict_result = await _resolve_registration_conflict(db, hits, body, person, is_self)
    if conflict_result is not None:
        return conflict_result

    await _assert_capacity(db, day)
    try:
        age = body.age if body.age is not None else (age_from_dob(body.dob) if body.dob else None)
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
        patient, created = await _insert_patient_document(db, doc, body, person, camp["_id"])
        if not created:
            await _release_capacity(db, day["_id"])
        return patient, created
    except Exception:
        await _release_capacity(db, day["_id"])
        raise


async def _confirm_registration(patient: Dict[str, Any]) -> None:
    db = get_db()
    row = await db.patients.find_one({"_id": ObjectId(patient["id"])})
    day = await db.camp_days.find_one({"_id": ObjectId(patient["camp_day_id"])})
    camp = await db.camps.find_one({"_id": ObjectId(patient["camp_id"])})
    if not row or not day or not camp:
        return
    await sms.send_patient_sms(db, row, "registration", day["day_date"], camp["venue"])


def _validate_manual_identity(body: RegisterBody, now) -> None:
    body.full_name = (body.full_name or '').strip()
    if not body.full_name or len(body.full_name) > 120:
        raise HTTPException(status_code=400, detail="Enter a full name of up to 120 characters")
    body.dob = (body.dob or '').strip() or None
    if body.dob:
        year_only = bool(re.fullmatch(r'[0-9]{4}', body.dob))
        if not year_only and not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', body.dob):
            raise HTTPException(status_code=400, detail="Enter a valid date of birth as YYYY-MM-DD or a four-digit year")
        try:
            dob = date.fromisoformat(body.dob + '-01-01' if year_only else body.dob)
        except ValueError:
            raise HTTPException(status_code=400, detail="Enter a valid date of birth as YYYY-MM-DD or a four-digit year")
        if dob > now.date() or now.year - dob.year > 130:
            raise HTTPException(status_code=400, detail="Enter a date of birth within the last 130 years")
        if body.age is None:
            body.age = age_from_dob(dob.isoformat())
    if body.age is None or not 0 <= body.age <= 130:
        raise HTTPException(status_code=400, detail="Enter an age between 0 and 130, or a valid date of birth")


@router.post("/register")
async def desk_register(
    body: RegisterBody,
    request: Request,
    background_tasks: BackgroundTasks,
    actor: dict = Depends(require_staff),
) -> Dict[str, Any]:
    if not body.full_name or not body.full_name.strip():
        raise HTTPException(status_code=400, detail="Full name is required")
    if not body.aadhaar_scanned:
        _validate_manual_identity(body, now_utc())
    phone_norm = normalize_phone(body.phone)
    if not phone_norm or is_dummy_phone(phone_norm):
        raise HTTPException(status_code=400, detail="A valid 10-digit household mobile number is required")
    patient, created = await _create_registration(
        body, actor["_id"], False, request,
    )
    if created:
        if background_tasks is not None:
            background_tasks.add_task(_confirm_registration, patient)
        else:
            await _confirm_registration(patient)
    return {"registration": patient, "created": created}


@router.post("/self-register")
async def self_register(body: RegisterBody, request: Request, background_tasks: BackgroundTasks) -> Dict[str, Any]:
    ip = request.client.host if request.client else "unknown"
    now = now_utc()
    cutoff = now - timedelta(minutes=10)
    for seen_ip in [k for k, w in _rl.items() if w[-1] <= cutoff]:
        del _rl[seen_ip]
    window = _rl.setdefault(ip, [])
    window[:] = [t for t in window if t > cutoff]
    if len(window) >= 300:
        raise HTTPException(status_code=429, detail="Too many attempts. Please try again later.")
    window.append(now)

    decoded = decode_aadhaar(body.qr_payload or "")
    if decoded.get("outcome") == "card" and decoded.get("data"):
        card = decoded["data"]
        body.full_name = card.get("full_name") or ""
        body.gender = card.get("gender")
        body.dob = card.get("dob")
        body.age = card.get("age")
        body.aadhaar_last4 = card.get("aadhaar_last4")
        body.address = card.get("address")
        body.aadhaar_scanned = True
        body.manual_entry = False
        body.manual_exception = False
    else:
        raise HTTPException(status_code=400, detail={
            "code": "AADHAAR_QR_REQUIRED",
            "message": "We could not read the QR code on this Aadhaar card. Please register at the camp desk.",
        })
    body.is_self_registered = True
    try:
        patient, created = await _create_registration(body, None, True, request)
    except HTTPException as exc:
        if isinstance(exc.detail, dict):
            raise HTTPException(status_code=exc.status_code, detail={
                key: value for key, value in exc.detail.items() if key in {"code", "message"}
            }) from exc
        raise
    if created:
        if background_tasks is not None:
            background_tasks.add_task(_confirm_registration, patient)
        else:
            await _confirm_registration(patient)
    db = get_db()
    camp = await db.camps.find_one({"is_active": True})
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
