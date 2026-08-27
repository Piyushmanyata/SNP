from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId
from db import get_db
from models import TranscriptionBody, FulfilmentBody, CorrectionBody, OtScheduleBody
from helpers import now_utc, iso, DIAGNOSIS_OPTIONS
from serializers import ser_patient, ser_person
from security import require_clinical, require_admin, require_any

router = APIRouter(prefix="/api/clinical", tags=["clinical"])


def ser_trans(t: dict) -> dict:
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


def ser_fulfil(f: dict) -> dict:
    return {
        "id": str(f["_id"]),
        "transcription_id": str(f["transcription_id"]),
        "item_type": f["item_type"],
        "status": f["status"],
        "collection_date": f.get("collection_date"),
        "collection_venue": f.get("collection_venue"),
        "ot_schedule_day_id": str(f["ot_schedule_day_id"]) if f.get("ot_schedule_day_id") else None,
        "created_at": iso(f.get("created_at")),
    }


def ser_slip(s: dict) -> dict:
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


def ser_ot_day(d: dict) -> dict:
    return {
        "id": str(d["_id"]),
        "camp_id": str(d["camp_id"]),
        "day_date": d["day_date"],
        "venue": d["venue"],
        "seat_limit": d["seat_limit"],
        "seats_taken": d.get("seats_taken", 0),
        "seats_free": d["seat_limit"] - d.get("seats_taken", 0),
    }


def normalize_ot_eye(v):
    if not v:
        return None
    m = {"r": "R", "right": "R", "l": "L", "left": "L", "b": "B", "both": "B"}
    return m.get(str(v).strip().lower(), None)


@router.get("/diagnosis-options")
async def diagnosis_options(actor: dict = Depends(require_any)):
    return {"options": DIAGNOSIS_OPTIONS}


@router.post("/lookup")
async def clinical_lookup(body: dict, actor: dict = Depends(require_clinical)):
    """Lookup an eligible (seen) registration by reg_no or patient QR."""
    db = get_db()
    value = str(body.get("value", "")).strip()
    if value.startswith("snp:"):
        value = value[4:]
    if "/p/" in value:
        value = value.split("/p/")[-1]
    p = await db.patients.find_one({"patient_qr": value})
    if not p and value.isdigit():
        p = await db.patients.find_one({"reg_no": int(value)})
    if not p:
        raise HTTPException(status_code=404, detail="No matching registration found")
    if p.get("queue_status") != "seen":
        # refusal without exposing PHI
        raise HTTPException(status_code=409, detail={
            "code": "not_seen",
            "message": "This registration is not yet eligible (not marked seen).",
        })
    person = await db.persons.find_one({"_id": p["person_id"]}) if p.get("person_id") else None
    trans = await db.transcriptions.find_one({"patient_id": p["_id"]})
    fulfilments = await db.fulfilments.find({"transcription_id": trans["_id"]}).to_list(20) if trans else []
    slips = await db.deferred_slips.find({"transcription_id": trans["_id"], "active": True}).to_list(20) if trans else []
    return {
        "registration": ser_patient(p),
        "person": ser_person(person) if person else None,
        "transcription": ser_trans(trans) if trans else None,
        "fulfilments": [ser_fulfil(f) for f in fulfilments],
        "slips": [ser_slip(s) for s in slips],
    }


@router.post("/transcription")
async def create_transcription(body: TranscriptionBody, actor: dict = Depends(require_clinical)):
    db = get_db()
    p = await db.patients.find_one({"_id": ObjectId(body.patient_id)})
    if not p:
        raise HTTPException(status_code=404, detail="Registration not found")
    if p.get("queue_status") != "seen":
        raise HTTPException(status_code=409, detail="Registration is not eligible (not seen)")
    existing = await db.transcriptions.find_one({"patient_id": p["_id"]})
    if existing:
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
    res = await db.transcriptions.insert_one(doc)
    doc["_id"] = res.inserted_id
    return {"transcription": ser_trans(doc)}


@router.post("/fulfilment")
async def record_fulfilment(body: FulfilmentBody, actor: dict = Depends(require_clinical)):
    db = get_db()
    t = await db.transcriptions.find_one({"_id": ObjectId(body.transcription_id)})
    if not t:
        raise HTTPException(status_code=404, detail="Transcription not found")

    valid = {
        "medicine": {"fulfilled", "not_available", "not_required"},
        "specs": {"fulfilled", "deferred", "not_required"},
        "ot": {"fulfilled", "deferred", "not_required"},
    }
    if body.item_type not in valid or body.status not in valid[body.item_type]:
        raise HTTPException(status_code=400, detail="Invalid fulfilment item/status")

    slip = None
    # deferral readiness + slip generation
    if body.status == "deferred":
        if body.item_type == "specs":
            if not body.collection_date or not body.collection_venue:
                raise HTTPException(status_code=400, detail="Specs deferral needs collection date and venue")
            slip = await _make_slip(t, "specs", body.collection_date, body.collection_venue,
                                    "Collect spectacles on the scheduled date.")
        elif body.item_type == "ot":
            if not body.ot_schedule_day_id:
                raise HTTPException(status_code=400, detail="OT deferral needs a scheduled day")
            ot_day = await db.ot_schedule_days.find_one_and_update(
                {"_id": ObjectId(body.ot_schedule_day_id),
                 "$expr": {"$lt": ["$seats_taken", "$seat_limit"]}},
                {"$inc": {"seats_taken": 1}},
                return_document=True,
            )
            if not ot_day:
                raise HTTPException(status_code=409, detail="OT day is full or not found")
            slip = await _make_slip(t, "ot", ot_day["day_date"], ot_day["venue"],
                                    "Report for surgery on the scheduled OT date.",
                                    ot_schedule_day_id=ot_day["_id"])

    doc = {
        "transcription_id": t["_id"],
        "item_type": body.item_type,
        "status": body.status,
        "collection_date": body.collection_date,
        "collection_venue": body.collection_venue,
        "ot_schedule_day_id": ObjectId(body.ot_schedule_day_id) if body.ot_schedule_day_id else None,
        "created_by": str(actor["_id"]),
        "created_at": now_utc(),
    }
    # replace existing fulfilment of same type; release any previously booked OT seat
    prior = await db.fulfilments.find({"transcription_id": t["_id"], "item_type": body.item_type}).to_list(20)
    for pf in prior:
        if pf.get("ot_schedule_day_id"):
            await db.ot_schedule_days.update_one(
                {"_id": pf["ot_schedule_day_id"], "seats_taken": {"$gt": 0}},
                {"$inc": {"seats_taken": -1}},
            )
    await db.fulfilments.delete_many({"transcription_id": t["_id"], "item_type": body.item_type})
    res = await db.fulfilments.insert_one(doc)
    doc["_id"] = res.inserted_id

    # lock transcription on first fulfilment
    if not t.get("locked"):
        await db.transcriptions.update_one({"_id": t["_id"]}, {"$set": {"locked": True}})

    return {"fulfilment": ser_fulfil(doc), "slip": ser_slip(slip) if slip else None}


async def _make_slip(t, item_type, coll_date, venue, instructions, ot_schedule_day_id=None):
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
        "instructions": instructions,
        "created_at": now_utc(),
    }
    res = await db.deferred_slips.insert_one(doc)
    doc["_id"] = res.inserted_id
    return doc


@router.get("/slip/{slip_id}")
async def get_slip(slip_id: str, actor: dict = Depends(require_clinical)):
    db = get_db()
    s = await db.deferred_slips.find_one({"_id": ObjectId(slip_id)})
    if not s:
        raise HTTPException(status_code=404, detail="Slip not found")
    p = await db.patients.find_one({"_id": s["patient_id"]})
    return {"slip": ser_slip(s), "registration": ser_patient(p) if p else None}


@router.post("/correction")
async def add_correction(body: CorrectionBody, actor: dict = Depends(require_clinical)):
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
async def list_corrections(transcription_id: str, actor: dict = Depends(require_clinical)):
    db = get_db()
    items = await db.corrections.find({"transcription_id": ObjectId(transcription_id)}).sort("created_at", 1).to_list(100)
    return {"corrections": [{
        "id": str(c["_id"]), "reason": c["reason"], "changes": c["changes"],
        "created_at": iso(c["created_at"]),
    } for c in items]}


@router.get("/history/{person_id}")
async def clinical_history(person_id: str, actor: dict = Depends(require_clinical)):
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
async def create_ot_day(body: OtScheduleBody, actor: dict = Depends(require_admin)):
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
async def list_ot_days(actor: dict = Depends(require_any)):
    db = get_db()
    camp = await db.camps.find_one({"is_active": True})
    if not camp:
        return {"ot_days": []}
    days = await db.ot_schedule_days.find({"camp_id": camp["_id"]}).sort("day_date", 1).to_list(100)
    return {"ot_days": [ser_ot_day(d) for d in days]}
