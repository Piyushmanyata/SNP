from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId
from db import get_db
from models import QrLookupBody
from helpers import now_utc, today_ist_str, iso, as_utc
from serializers import ser_patient
from security import require_staff
from datetime import timedelta

router = APIRouter(prefix="/api/desk", tags=["desk"])


async def _resolve(value: str):
    db = get_db()
    v = (value or "").strip()
    if v.startswith("snp:"):
        v = v[4:]
    if "/p/" in v:
        v = v.split("/p/")[-1]
    # try patient qr uuid
    p = await db.patients.find_one({"patient_qr": v})
    if p:
        return p
    # try reg_no
    if v.isdigit():
        p = await db.patients.find_one({"reg_no": int(v)})
        if p:
            return p
    return None


@router.post("/lookup")
async def lookup(body: QrLookupBody, actor: dict = Depends(require_staff)):
    p = await _resolve(body.value)
    if not p:
        raise HTTPException(status_code=404, detail="No matching registration found")
    return {"registration": ser_patient(p)}


@router.post("/print/{patient_id}")
async def print_prescription(patient_id: str, actor: dict = Depends(require_staff)):
    db = get_db()
    p = await db.patients.find_one({"_id": ObjectId(patient_id)})
    if not p:
        raise HTTPException(status_code=404, detail="Registration not found")

    day = await db.camp_days.find_one({"_id": p["camp_day_id"]})
    if not day:
        raise HTTPException(status_code=404, detail="Camp day not found")

    # print window gate: today IST AND printing_open
    if day["day_date"] != today_ist_str() or not day.get("printing_open", False):
        raise HTTPException(status_code=409, detail={
            "code": "PRINT_WINDOW_CLOSED",
            "message": "The print window is closed for today.",
        })

    # presence written once, idempotent
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
async def mark_seen(patient_id: str, actor: dict = Depends(require_staff)):
    db = get_db()
    p = await db.patients.find_one({"_id": ObjectId(patient_id)})
    if not p:
        raise HTTPException(status_code=404, detail="Registration not found")
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
async def undo_seen(patient_id: str, actor: dict = Depends(require_staff)):
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
    await db.patients.update_one(
        {"_id": p["_id"]},
        {"$set": {"queue_status": "registered", "seen_at": None, "seen_by": None}},
    )
    p = await db.patients.find_one({"_id": p["_id"]})
    return {"registration": ser_patient(p)}
