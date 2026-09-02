from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException, Depends
from pymongo.errors import DuplicateKeyError
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase
from db import get_db
from models import TranscriptionBody, FulfilmentBody, CorrectionBody, OtScheduleBody, SpecsScheduleBody
from helpers import now_utc, iso, DIAGNOSIS_OPTIONS
from serializers import ser_patient, ser_person
from security import require_clinical, require_admin, require_any
import sms

router = APIRouter(prefix="/api/clinical", tags=["clinical"])


def ser_trans(t: dict) -> Dict[str, Any]:
    return {
        "id": str(t["_id"]),
        "patient_id": str(t["patient_id"]),
        "person_id": str(t["person_id"]) if t.get("person_id") else None,
        "camp_id": str(t["camp_id"]) if t.get("camp_id") else None,
        "diagnosis_options": t.get("diagnosis_options", []),
        "diagnosis_other": t.get("diagnosis_other"),
        "blood_sugar": t.get("blood_sugar"),
        "bp": t.get("bp"),
        "remarks": t.get("remarks"),
        "specs_measurements": t.get("specs_measurements"),
        "ot_eye": t.get("ot_eye"),
        "ot_procedure": t.get("ot_procedure"),
        "ot_notes": t.get("ot_notes"),
        "locked": t.get("locked", False),
        "created_at": iso(t.get("created_at")),
    }


def ser_fulfil(f: dict) -> Dict[str, Any]:
    return {
        "id": str(f["_id"]),
        "transcription_id": str(f["transcription_id"]),
        "item_type": f["item_type"],
        "status": f["status"],
        "collection_date": f.get("collection_date"),
        "collection_venue": f.get("collection_venue"),
        "ot_schedule_day_id": str(f["ot_schedule_day_id"]) if f.get("ot_schedule_day_id") else None,
        "specs_collection_day_id": str(f["specs_collection_day_id"]) if f.get("specs_collection_day_id") else None,
        "created_at": iso(f.get("created_at")),
    }


def ser_slip(s: dict) -> Dict[str, Any]:
    return {
        "id": str(s["_id"]),
        "transcription_id": str(s["transcription_id"]),
        "item_type": s["item_type"],
        "version": s["version"],
        "active": s.get("active", True),
        "cancelled": s.get("cancelled", False),
        "collection_date": s.get("collection_date"),
        "collection_venue": s.get("collection_venue"),
        "instructions": s.get("instructions"),
        "created_at": iso(s.get("created_at")),
    }


def ser_ot_day(d: dict) -> Dict[str, Any]:
    return {
        "id": str(d["_id"]),
        "camp_id": str(d["camp_id"]),
        "day_date": d["day_date"],
        "venue": d["venue"],
        "seat_limit": d["seat_limit"],
        "seats_taken": d.get("seats_taken", 0),
        "seats_free": d["seat_limit"] - d.get("seats_taken", 0),
    }


def ser_specs_day(d: dict) -> Dict[str, Any]:
    return {
        "id": str(d["_id"]),
        "camp_id": str(d["camp_id"]),
        "day_date": d["day_date"],
        "venue": d["venue"],
        "seat_limit": d["seat_limit"],
        "seats_taken": d.get("seats_taken", 0),
        "seats_free": d["seat_limit"] - d.get("seats_taken", 0),
    }


def normalize_ot_eye(v: Optional[str]) -> Optional[str]:
    if not v:
        return None
    m = {"r": "R", "right": "R", "l": "L", "left": "L", "b": "B", "both": "B"}
    return m.get(str(v).strip().lower(), None)


@router.get("/diagnosis-options")
async def diagnosis_options(actor: dict = Depends(require_any)) -> Dict[str, Any]:
    return {"options": DIAGNOSIS_OPTIONS}


async def _fetch_clinical_bundle(db: AsyncIOMotorDatabase, patient: dict) -> Dict[str, Any]:
    person = await db.persons.find_one({"_id": patient["person_id"]}) if patient.get("person_id") else None
    trans = await db.transcriptions.find_one({"patient_id": patient["_id"]})
    fulfilments = await db.fulfilments.find({"transcription_id": trans["_id"]}).to_list(20) if trans else []
    slips = await db.deferred_slips.find({"transcription_id": trans["_id"], "active": True}).to_list(20) if trans else []
    return {
        "registration": ser_patient(patient),
        "person": ser_person(person) if person else None,
        "transcription": ser_trans(trans) if trans else None,
        "fulfilments": [ser_fulfil(f) for f in fulfilments],
        "slips": [ser_slip(s) for s in slips],
    }


def _parse_lookup_identifier(raw_value: str) -> str:
    val = str(raw_value).strip()
    if val.startswith("snp:"):
        val = val[4:]
    if "/p/" in val:
        val = val.split("/p/")[-1]
    return val


@router.post("/lookup")
async def clinical_lookup(body: dict, actor: dict = Depends(require_clinical)) -> Dict[str, Any]:
    db = get_db()
    value = _parse_lookup_identifier(body.get("value", ""))
    p = await db.patients.find_one({"patient_qr": value})
    if not p and value.isdigit():
        p = await db.patients.find_one({"reg_no": int(value)})
    if not p:
        raise HTTPException(status_code=404, detail="No matching registration found")
    if p.get("queue_status") != "seen":
        raise HTTPException(status_code=409, detail={
            "code": "not_seen",
            "message": "This registration is not yet eligible (not marked seen).",
        })
    return await _fetch_clinical_bundle(db, p)


@router.post("/transcription")
async def create_transcription(body: TranscriptionBody, actor: dict = Depends(require_clinical)) -> Dict[str, Any]:
    db = get_db()
    p = await db.patients.find_one({"_id": ObjectId(body.patient_id)})
    if not p:
        raise HTTPException(status_code=404, detail="Registration not found")
    if p.get("queue_status") != "seen":
        raise HTTPException(status_code=409, detail="Registration is not eligible (not seen)")
    existing = await db.transcriptions.find_one({"patient_id": p["_id"]})
    if not existing:
        doc = {
            "patient_id": p["_id"],
            "person_id": p.get("person_id"),
            "camp_id": p["camp_id"],
            "diagnosis_options": body.diagnosis_options,
            "diagnosis_other": body.diagnosis_other,
            "blood_sugar": body.blood_sugar,
            "bp": body.bp,
            "remarks": body.remarks,
            "specs_measurements": body.specs_measurements,
            "ot_eye": normalize_ot_eye(body.ot_eye),
            "ot_procedure": body.ot_procedure,
            "ot_notes": body.ot_notes,
            "locked": False,
            "created_by": str(actor["_id"]),
            "created_at": now_utc(),
        }
        try:
            res = await db.transcriptions.insert_one(doc)
            doc["_id"] = res.inserted_id
            return {"transcription": ser_trans(doc)}
        except DuplicateKeyError:
            existing = await db.transcriptions.find_one({"patient_id": p["_id"]})
            if not existing:
                raise
    if existing.get("locked"):
        raise HTTPException(status_code=409, detail="Transcription is locked; use a correction")
    await db.transcriptions.update_one({"_id": existing["_id"]}, {"$set": {
        "diagnosis_options": body.diagnosis_options,
        "diagnosis_other": body.diagnosis_other,
        "blood_sugar": body.blood_sugar,
        "bp": body.bp,
        "remarks": body.remarks,
        "specs_measurements": body.specs_measurements,
        "ot_eye": normalize_ot_eye(body.ot_eye),
        "ot_procedure": body.ot_procedure,
        "ot_notes": body.ot_notes,
    }})
    t = await db.transcriptions.find_one({"_id": existing["_id"]})
    return {"transcription": ser_trans(t)}


def _validate_fulfilment_matrix(item_type: str, status: str) -> None:
    valid = {
        "medicine": {"fulfilled", "not_available", "not_required"},
        "specs": {"fulfilled", "deferred", "not_required"},
        "ot": {"fulfilled", "deferred", "not_required"},
    }
    if item_type not in valid or status not in valid[item_type]:
        raise HTTPException(status_code=400, detail="Invalid fulfilment item/status")


async def _consume_seat(collection: AsyncIOMotorCollection, day_id: str) -> Optional[dict]:
    return await collection.find_one_and_update(
        {"_id": ObjectId(day_id),
         "$expr": {"$lt": ["$seats_taken", "$seat_limit"]}},
        {"$inc": {"seats_taken": 1}},
        return_document=True,
    )


DEFERRAL_CONFIG = {
    "specs": {
        "id_field": "specs_collection_day_id",
        "collection_attr": "specs_collection_days",
        "missing_err": "Spectacles to be made deferral needs a Specs collection day",
        "full_err": "Specs collection day is full or not found",
        "none_free_err": "Every Specs collection day is full. Call the admin to add a Specs collection day.",
        "instructions": "Collect spectacles on the scheduled date.",
        "slip_kwarg": "specs_collection_day_id",
        "message_type": "specs_token",
    },
    "ot": {
        "id_field": "ot_schedule_day_id",
        "collection_attr": "ot_schedule_days",
        "missing_err": "OT deferral needs a scheduled day",
        "full_err": "OT day is full or not found",
        "none_free_err": "Every OT Schedule Day is full. Call the admin to add an OT Schedule Day.",
        "instructions": "Report for surgery on the scheduled OT date.",
        "slip_kwarg": "ot_schedule_day_id",
        "message_type": "ot_token",
    },
}


async def _refuse_full(collection: AsyncIOMotorCollection, day: dict, cfg: dict) -> None:
    """A single full day is a retry; every day of the type full is an admin problem."""
    free = await collection.count_documents({
        "camp_id": day.get("camp_id"),
        "$expr": {"$lt": ["$seats_taken", "$seat_limit"]},
    })
    if free == 0:
        raise HTTPException(status_code=409, detail={
            "code": "NO_CLINICAL_DAY_AVAILABLE",
            "message": cfg["none_free_err"],
        })
    raise HTTPException(status_code=409, detail=cfg["full_err"])


def _assert_specs_measurements(item_type: str, status: str, transcription: dict) -> None:
    if item_type != "specs" or status not in ("fulfilled", "deferred"):
        return
    m = transcription.get("specs_measurements") or {}
    if not (str(m.get("r_sph") or "").strip() and str(m.get("l_sph") or "").strip()):
        raise HTTPException(status_code=400, detail={
            "code": "SPECS_MEASUREMENTS_REQUIRED",
            "message": "Record the prescribed power for both eyes before recording a spectacles line.",
        })


async def _process_deferral(db: AsyncIOMotorDatabase, t: dict, body: FulfilmentBody, prior: dict | None = None) -> Optional[dict]:
    if body.status != "deferred" or body.item_type not in DEFERRAL_CONFIG:
        return None

    cfg = DEFERRAL_CONFIG[body.item_type]
    target_day_id = getattr(body, cfg["id_field"])
    if not target_day_id:
        raise HTTPException(status_code=400, detail=cfg["missing_err"])

    held = bool(
        prior
        and prior.get("status") == "deferred"
        and str(prior.get(cfg["id_field"])) == target_day_id
    )
    collection = getattr(db, cfg["collection_attr"])
    if held:
        day = await collection.find_one({"_id": ObjectId(target_day_id)})
        if not day:
            raise HTTPException(status_code=409, detail=cfg["full_err"])
    else:
        day = await _consume_seat(collection, target_day_id)
        if not day:
            target = await collection.find_one({"_id": ObjectId(target_day_id)})
            if not target:
                raise HTTPException(status_code=409, detail=cfg["full_err"])
            await _refuse_full(collection, target, cfg)
    slip_kwargs = {cfg["slip_kwarg"]: day["_id"]}
    return await _make_slip(t, body.item_type, day["day_date"], day["venue"], cfg["instructions"], **slip_kwargs)


async def _cleanup_prior_fulfilment(
    db: AsyncIOMotorDatabase,
    transcription_id: ObjectId | str,
    item_type: str,
    keep_ot: Optional[ObjectId | str] = None,
    keep_specs: Optional[ObjectId | str] = None,
) -> None:
    prior = await db.fulfilments.find({"transcription_id": transcription_id, "item_type": item_type}).to_list(20)
    for pf in prior:
        if pf.get("status") != "deferred":
            continue
        oid = pf.get("ot_schedule_day_id")
        if oid and oid != keep_ot:
            await db.ot_schedule_days.update_one(
                {"_id": oid, "seats_taken": {"$gt": 0}},
                {"$inc": {"seats_taken": -1}},
            )
        sid = pf.get("specs_collection_day_id")
        if sid and sid != keep_specs:
            await db.specs_collection_days.update_one(
                {"_id": sid, "seats_taken": {"$gt": 0}},
                {"$inc": {"seats_taken": -1}},
            )
    await db.fulfilments.delete_many({"transcription_id": transcription_id, "item_type": item_type})


def _deferred_day_id(body: FulfilmentBody, item_type: str) -> Optional[ObjectId]:
    """A day is only booked for the line that owns it: a specs line never holds an OT seat."""
    if body.status != "deferred" or body.item_type != item_type:
        return None
    raw = getattr(body, DEFERRAL_CONFIG[item_type]["id_field"])
    return ObjectId(raw) if raw else None


def _build_fulfilment_doc(body: FulfilmentBody, transcription_id: ObjectId | str, slip: dict | None, actor_id: str) -> dict:
    return {
        "transcription_id": transcription_id,
        "item_type": body.item_type,
        "status": body.status,
        "collection_date": (slip or {}).get("collection_date") or body.collection_date,
        "collection_venue": (slip or {}).get("collection_venue") or body.collection_venue,
        "ot_schedule_day_id": _deferred_day_id(body, "ot"),
        "specs_collection_day_id": _deferred_day_id(body, "specs"),
        "created_by": actor_id,
        "created_at": now_utc(),
    }


async def _ensure_transcription_locked(db: AsyncIOMotorDatabase, transcription: dict) -> None:
    if not transcription.get("locked"):
        await db.transcriptions.update_one({"_id": transcription["_id"]}, {"$set": {"locked": True}})


@router.post("/fulfilment")
async def record_fulfilment(body: FulfilmentBody, actor: dict = Depends(require_clinical)) -> Dict[str, Any]:
    db = get_db()
    t = await db.transcriptions.find_one({"_id": ObjectId(body.transcription_id)})
    if not t:
        raise HTTPException(status_code=404, detail="Transcription not found")
    patient = await db.patients.find_one({"_id": t["patient_id"]}) if t.get("patient_id") else None
    if not patient or patient.get("queue_status") != "seen":
        raise HTTPException(status_code=409, detail={
            "code": "not_seen",
            "message": "This registration is not yet eligible (not marked seen).",
        })

    _validate_fulfilment_matrix(body.item_type, body.status)
    _assert_specs_measurements(body.item_type, body.status, t)
    prior = await db.fulfilments.find_one({"transcription_id": t["_id"], "item_type": body.item_type})
    if body.status != "deferred":
        await db.deferred_slips.update_many(
            {"transcription_id": t["_id"], "item_type": body.item_type, "active": True},
            {"$set": {"active": False, "cancelled": True, "cancelled_at": now_utc()}},
        )
    slip = await _process_deferral(db, t, body, prior)

    doc = _build_fulfilment_doc(body, t["_id"], slip, str(actor["_id"]))
    keep_ot = doc["ot_schedule_day_id"] if body.status == "deferred" else None
    keep_specs = doc["specs_collection_day_id"] if body.status == "deferred" else None
    await _cleanup_prior_fulfilment(db, t["_id"], body.item_type, keep_ot=keep_ot, keep_specs=keep_specs)

    res = await db.fulfilments.insert_one(doc)
    doc["_id"] = res.inserted_id

    await _ensure_transcription_locked(db, t)
    if slip:
        await sms.send_patient_sms(
            db, patient, DEFERRAL_CONFIG[body.item_type]["message_type"],
            slip["collection_date"], slip["collection_venue"],
        )
    return {"fulfilment": ser_fulfil(doc), "slip": ser_slip(slip) if slip else None}


async def _make_slip(
    t: dict,
    item_type: str,
    coll_date: str,
    venue: str,
    instructions: str,
    ot_schedule_day_id: Optional[ObjectId | str] = None,
    specs_collection_day_id: Optional[ObjectId | str] = None,
) -> dict:
    db = get_db()
    await db.deferred_slips.update_many(
        {"transcription_id": t["_id"], "item_type": item_type, "active": True},
        {"$set": {"active": False, "cancelled": True, "cancelled_at": now_utc()}},
    )
    count = await db.deferred_slips.count_documents({"transcription_id": t["_id"], "item_type": item_type})
    doc = {
        "transcription_id": t["_id"],
        "patient_id": t["patient_id"],
        "item_type": item_type,
        "version": count + 1,
        "active": True,
        "cancelled": False,
        "collection_date": coll_date,
        "collection_venue": venue,
        "ot_schedule_day_id": ot_schedule_day_id,
        "specs_collection_day_id": specs_collection_day_id,
        "instructions": instructions,
        "created_at": now_utc(),
    }
    res = await db.deferred_slips.insert_one(doc)
    doc["_id"] = res.inserted_id
    return doc


@router.get("/slip/{slip_id}")
async def get_slip(slip_id: str, actor: dict = Depends(require_clinical)) -> Dict[str, Any]:
    db = get_db()
    s = await db.deferred_slips.find_one({"_id": ObjectId(slip_id)})
    if not s:
        raise HTTPException(status_code=404, detail="Slip not found")
    p = await db.patients.find_one({"_id": s["patient_id"]})
    camp = await db.camps.find_one({"_id": p["camp_id"]}) if p and p.get("camp_id") else None
    return {
        "slip": ser_slip(s),
        "registration": ser_patient(p) if p else None,
        "camp_name": camp["name"] if camp else None,
    }


@router.post("/correction")
async def add_correction(body: CorrectionBody, actor: dict = Depends(require_clinical)) -> Dict[str, Any]:
    db = get_db()
    t = await db.transcriptions.find_one({"_id": ObjectId(body.transcription_id)})
    if not t:
        raise HTTPException(status_code=404, detail="Transcription not found")
    doc = {
        "transcription_id": t["_id"],
        "patient_id": t["patient_id"],
        "reason": body.reason,
        "changes": body.changes,
        "created_by": str(actor["_id"]),
        "created_at": now_utc(),
    }
    res = await db.corrections.insert_one(doc)
    # apply changes to transcription (append-only history preserved in corrections)
    allowed = {"diagnosis_options", "diagnosis_other", "blood_sugar", "bp", "remarks",
               "specs_measurements", "ot_eye", "ot_procedure", "ot_notes"}
    updates = {k: v for k, v in body.changes.items() if k in allowed}
    if updates:
        await db.transcriptions.update_one({"_id": t["_id"]}, {"$set": updates})
    return {"correction_id": str(res.inserted_id)}


@router.get("/corrections/{transcription_id}")
async def list_corrections(transcription_id: str, actor: dict = Depends(require_clinical)) -> Dict[str, Any]:
    db = get_db()
    items = await db.corrections.find({"transcription_id": ObjectId(transcription_id)}).sort("created_at", 1).to_list(100)
    return {"corrections": [{
        "id": str(c["_id"]), "reason": c["reason"], "changes": c["changes"],
        "created_at": iso(c["created_at"]),
    } for c in items]}


@router.get("/history/{person_id}")
async def clinical_history(person_id: str, actor: dict = Depends(require_clinical)) -> Dict[str, Any]:
    db = get_db()
    items = await db.transcriptions.find({"person_id": ObjectId(person_id)}).sort("created_at", -1).to_list(100)
    out = []
    for t in items:
        p = await db.patients.find_one({"_id": t["patient_id"]})
        camp = await db.camps.find_one({"_id": t["camp_id"]}) if t.get("camp_id") else None
        out.append({
            "transcription": ser_trans(t),
            "camp_name": camp["name"] if camp else None,
            "reg_no": p["reg_no"] if p else None,
        })
    return {"history": out}


# ---- OT schedule ----
@router.post("/ot-days")
async def create_ot_day(body: OtScheduleBody, actor: dict = Depends(require_admin)) -> Dict[str, Any]:
    db = get_db()
    existing = await db.ot_schedule_days.find_one({"camp_id": ObjectId(body.camp_id), "day_date": body.day_date})
    if existing:
        assigned = existing.get("seats_taken", 0)
        if body.seat_limit < assigned:
            raise HTTPException(status_code=409, detail={
                "code": "SEAT_LIMIT_BELOW_ASSIGNED",
                "message": f"Cannot set below {assigned} already-assigned seats",
            })
        await db.ot_schedule_days.update_one({"_id": existing["_id"]},
                                             {"$set": {"seat_limit": body.seat_limit, "venue": body.venue}})
        d = await db.ot_schedule_days.find_one({"_id": existing["_id"]})
    else:
        res = await db.ot_schedule_days.insert_one({
            "camp_id": ObjectId(body.camp_id), "day_date": body.day_date,
            "venue": body.venue, "seat_limit": body.seat_limit, "seats_taken": 0,
            "created_at": now_utc(),
        })
        d = await db.ot_schedule_days.find_one({"_id": res.inserted_id})
    return {"ot_day": ser_ot_day(d)}


@router.get("/ot-days")
async def list_ot_days(actor: dict = Depends(require_any)) -> Dict[str, Any]:
    db = get_db()
    camp = await db.camps.find_one({"is_active": True})
    if not camp:
        return {"ot_days": []}
    days = await db.ot_schedule_days.find({"camp_id": camp["_id"]}).sort("day_date", 1).to_list(100)
    return {"ot_days": [ser_ot_day(d) for d in days]}


@router.post("/specs-days")
async def create_specs_day(body: SpecsScheduleBody, actor: dict = Depends(require_admin)) -> Dict[str, Any]:
    db = get_db()
    existing = await db.specs_collection_days.find_one({"camp_id": ObjectId(body.camp_id), "day_date": body.day_date})
    if existing:
        assigned = existing.get("seats_taken", 0)
        if body.seat_limit < assigned:
            raise HTTPException(status_code=409, detail={
                "code": "SEAT_LIMIT_BELOW_ASSIGNED",
                "message": f"Cannot set below {assigned} already-assigned seats",
            })
        await db.specs_collection_days.update_one({"_id": existing["_id"]},
                                                  {"$set": {"seat_limit": body.seat_limit, "venue": body.venue}})
        d = await db.specs_collection_days.find_one({"_id": existing["_id"]})
    else:
        res = await db.specs_collection_days.insert_one({
            "camp_id": ObjectId(body.camp_id), "day_date": body.day_date,
            "venue": body.venue, "seat_limit": body.seat_limit, "seats_taken": 0,
            "created_at": now_utc(),
        })
        d = await db.specs_collection_days.find_one({"_id": res.inserted_id})
    return {"specs_day": ser_specs_day(d)}


@router.get("/specs-days")
async def list_specs_days(actor: dict = Depends(require_any)) -> Dict[str, Any]:
    db = get_db()
    camp = await db.camps.find_one({"is_active": True})
    if not camp:
        return {"specs_days": []}
    days = await db.specs_collection_days.find({"camp_id": camp["_id"]}).sort("day_date", 1).to_list(100)
    return {"specs_days": [ser_specs_day(d) for d in days]}
