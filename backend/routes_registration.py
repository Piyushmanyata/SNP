from fastapi import APIRouter, HTTPException, Depends, Request
from bson import ObjectId
from db import get_db, next_seq
from models import AadhaarDecodeBody, RegisterBody, DuplicateCheckBody
from helpers import (
    now_utc, normalize_name, normalize_phone, is_dummy_phone,
    person_key, new_uuid, age_from_dob, today_ist_str,
)
from serializers import ser_patient, ser_person
from security import require_staff, require_any
from aadhaar import decode_aadhaar
from datetime import timedelta

router = APIRouter(prefix="/api", tags=["registration"])

# rate limit for self-register (per IP)
_rl: dict = {}


# ---------- Aadhaar Secure QR decode (genuine offline parse; demo payload also supported) ----------
@router.post("/aadhaar/decode")
async def aadhaar_decode(body: AadhaarDecodeBody):
    result = decode_aadhaar(body.payload or "")
    if result["outcome"] == "card":
        result["data"]["age"] = age_from_dob(result["data"].get("dob") or "")
    return result


# ---------- soft duplicate check ----------
@router.post("/register/duplicate-check")
async def duplicate_check(body: DuplicateCheckBody, actor: dict = Depends(require_staff)):
    db = get_db()
    camp = await db.camps.find_one({"is_active": True})
    if not camp:
        return {"likely_duplicates": []}
    q = {"camp_id": camp["_id"], "full_name_normalized": normalize_name(body.full_name)}
    if body.age is not None:
        q["age"] = body.age
    dups = await db.patients.find(q).limit(5).to_list(5)
    return {"likely_duplicates": [ser_patient(d) for d in dups]}


async def _resolve_person(data: dict):
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
    res = await db.persons.insert_one(doc)
    doc["_id"] = res.inserted_id
    return doc, True


async def _validate_camp_and_day(db, camp_day_id: str) -> tuple[dict, dict]:
    camp = await db.camps.find_one({"is_active": True})
    if not camp:
        raise HTTPException(status_code=409, detail="No active camp")

    day = await db.camp_days.find_one({"_id": ObjectId(camp_day_id), "camp_id": camp["_id"]})
    if not day:
        raise HTTPException(status_code=404, detail="Camp day not found")
    return camp, day


async def _check_registration_duplicates(db, camp_id, body: RegisterBody, person: dict | None = None):
    if person:
        existing_reg = await db.patients.find_one({"person_id": person["_id"], "camp_id": camp_id})
        if existing_reg:
            return existing_reg

    norm = normalize_name(body.full_name)
    if body.aadhaar_last4 and not body.override_duplicate:
        clash = await db.patients.find_one({
            "camp_id": camp_id,
            "aadhaar_last4": body.aadhaar_last4,
            "full_name_normalized": norm,
        })
        if clash:
            raise HTTPException(status_code=409, detail={
                "code": "DUPLICATE_IN_CAMP",
                "message": "Already registered in this camp",
                "registration": ser_patient(clash),
            })
    return None


def _build_patient_document(
    camp_id,
    camp_day_id,
    reg_no: int,
    body: RegisterBody,
    person_id,
    phone: str | None,
    age: int | None,
    actor_id,
    is_self: bool,
) -> dict:
    norm = normalize_name(body.full_name)
    manual = None
    if body.manual_exception:
        manual = {
            "actor": str(actor_id) if actor_id else "self",
            "reason": body.manual_reason,
            "failed_scan_attempts": body.failed_scan_attempts,
            "at": now_utc(),
        }

    return {
        "person_id": person_id,
        "camp_id": camp_id,
        "camp_day_id": camp_day_id,
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
        "aadhaar_scanned": body.aadhaar_scanned,
        "queue_status": "registered",
        "patient_qr": new_uuid(),
        "printed_at": None,
        "seen_at": None,
        "seen_by": None,
        "checked_in_by": None,
        "created_by": str(actor_id) if actor_id else None,
        "is_self_registered": is_self,
        "manual_exception": manual,
        "registration_request_id": body.registration_request_id,
        "reminder_sms_sent_at": None,
        "created_at": now_utc(),
    }


async def _create_registration(body: RegisterBody, actor_id, is_self: bool, request: Request):
    db = get_db()
    camp, day = await _validate_camp_and_day(db, body.camp_day_id)

    # idempotency
    if body.registration_request_id:
        existing = await db.patients.find_one({"registration_request_id": body.registration_request_id})
        if existing:
            return ser_patient(existing), False

    # phone rule (household) - required for desk unless manual/self handled by caller
    phone = normalize_phone(body.phone)
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

    existing_dup = await _check_registration_duplicates(db, camp["_id"], body, person)
    if existing_dup:
        return ser_patient(existing_dup), False

    reg_no = await next_seq("reg_no")
    age = body.age
    if age is None and body.dob:
        age = age_from_dob(body.dob)

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
    )
    res = await db.patients.insert_one(doc)
    doc["_id"] = res.inserted_id
    return ser_patient(doc), True


@router.post("/register")
async def desk_register(body: RegisterBody, request: Request, actor: dict = Depends(require_staff)):
    if not body.full_name or not body.full_name.strip():
        raise HTTPException(status_code=400, detail="Full name is required")
    if body.age is None and not body.aadhaar_scanned:
        raise HTTPException(status_code=400, detail="Age is required")
    phone_norm = normalize_phone(body.phone)
    if not phone_norm or is_dummy_phone(phone_norm):
        raise HTTPException(status_code=400, detail="A valid 10-digit household mobile number is required")
    if body.manual_exception and actor["role"] == "clinical_desk_operator":
        raise HTTPException(status_code=403, detail="Not permitted")
    patient, created = await _create_registration(body, actor["_id"], False, request)
    return {"registration": patient, "created": created}


@router.post("/self-register")
async def self_register(body: RegisterBody, request: Request):
    ip = request.client.host if request.client else "unknown"
    now = now_utc()
    window = _rl.setdefault(ip, [])
    window[:] = [t for t in window if t > now - timedelta(minutes=10)]
    if len(window) >= 300:
        raise HTTPException(status_code=429, detail="Too many attempts. Please try again later.")
    window.append(now)

    if not body.aadhaar_scanned:
        raise HTTPException(status_code=400, detail="Aadhaar scan required for self-registration")
    body.is_self_registered = True
    patient, created = await _create_registration(body, None, True, request)
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
async def name_search(q: str, actor: dict = Depends(require_any)):
    db = get_db()
    camp = await db.camps.find_one({"is_active": True})
    if not camp:
        return {"results": []}
    norm = normalize_name(q)
    if not norm:
        return {"results": []}
    results = await db.patients.find({
        "camp_id": camp["_id"],
        "full_name_normalized": {"$regex": "^" + norm},
    }).limit(25).to_list(25)
    return {"results": [ser_patient(r) for r in results]}


@router.get("/patients")
async def list_patients(actor: dict = Depends(require_any)):
    db = get_db()
    camp = await db.camps.find_one({"is_active": True})
    if not camp:
        return {"patients": []}
    pts = await db.patients.find({"camp_id": camp["_id"]}).sort("created_at", -1).limit(200).to_list(200)
    return {"patients": [ser_patient(p) for p in pts]}
