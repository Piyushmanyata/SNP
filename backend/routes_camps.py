from typing import Any, Dict
from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId
from db import get_db
from models import CampBody, CampDayBody, PrintWindowBody
from helpers import now_utc, iso, today_ist_str
from security import require_admin, require_any

router = APIRouter(prefix="/api/camps", tags=["camps"])


def ser_camp(c: dict) -> Dict[str, Any]:
    return {
        "id": str(c["_id"]),
        "name": c["name"],
        "venue": c["venue"],
        "camp_date": c["camp_date"],
        "is_active": c.get("is_active", False),
        "created_at": iso(c.get("created_at")),
    }


def ser_day(d: dict) -> Dict[str, Any]:
    return {
        "id": str(d["_id"]),
        "camp_id": str(d["camp_id"]),
        "day_date": d["day_date"],
        "seat_limit": d.get("seat_limit", 0),
        "printing_open": d.get("printing_open", False),
        "is_today": d["day_date"] == today_ist_str(),
    }


@router.post("")
async def create_camp(body: CampBody, actor: dict = Depends(require_admin)) -> Dict[str, Any]:
    db = get_db()
    res = await db.camps.insert_one({
        "name": body.name, "venue": body.venue, "camp_date": body.camp_date,
        "is_active": False, "created_at": now_utc(),
    })
    c = await db.camps.find_one({"_id": res.inserted_id})
    return {"camp": ser_camp(c)}


@router.get("")
async def list_camps(actor: dict = Depends(require_any)) -> Dict[str, Any]:
    db = get_db()
    camps = await db.camps.find().sort("created_at", -1).to_list(500)
    return {"camps": [ser_camp(c) for c in camps]}


@router.get("/active")
async def active_camp(actor: dict = Depends(require_any)) -> Dict[str, Any]:
    db = get_db()
    c = await db.camps.find_one({"is_active": True})
    if not c:
        return {"camp": None, "days": []}
    days = await db.camp_days.find({"camp_id": c["_id"]}).sort("day_date", 1).to_list(100)
    return {"camp": ser_camp(c), "days": [ser_day(d) for d in days]}


@router.get("/active/public")
async def active_camp_public() -> Dict[str, Any]:
    """Public (no auth) projection for patient self-registration. No PHI."""
    db = get_db()
    c = await db.camps.find_one({"is_active": True})
    if not c:
        return {"camp": None, "days": []}
    days = await db.camp_days.find({"camp_id": c["_id"]}).sort("day_date", 1).to_list(100)
    grouped = await db.patients.aggregate([
        {"$match": {"camp_id": c["_id"]}},
        {"$group": {"_id": "$camp_day_id", "n": {"$sum": 1}}},
    ]).to_list(1000)
    per_day = {g["_id"]: g["n"] for g in grouped}
    today = today_ist_str()
    out = []
    total_seats = 0
    for d in days:
        n = per_day.get(d["_id"], 0)
        limit = d.get("seat_limit") or 0
        total_seats += limit
        out.append({
            "id": str(d["_id"]),
            "day_date": d["day_date"],
            "is_today": d["day_date"] == today,
            "registered": n,
            "seat_limit": limit,
            "remaining": max(0, limit - n),
        })
    return {
        "camp": {"id": str(c["_id"]), "name": c["name"], "venue": c["venue"]},
        "total_seats": total_seats,
        "total_registered": sum(per_day.values()),
        "days": out,
    }


@router.patch("/{camp_id}")
async def update_camp(camp_id: str, body: CampBody, actor: dict = Depends(require_admin)) -> Dict[str, Any]:
    db = get_db()
    await db.camps.update_one({"_id": ObjectId(camp_id)}, {"$set": {
        "name": body.name, "venue": body.venue, "camp_date": body.camp_date}})
    c = await db.camps.find_one({"_id": ObjectId(camp_id)})
    if not c:
        raise HTTPException(status_code=404, detail="Camp not found")
    return {"camp": ser_camp(c)}


@router.post("/{camp_id}/activate")
async def activate_camp(camp_id: str, actor: dict = Depends(require_admin)) -> Dict[str, Any]:
    db = get_db()
    oid = ObjectId(camp_id)
    if not await db.camps.find_one({"_id": oid}):
        raise HTTPException(status_code=404, detail="Camp not found")
    # exactly one active: deactivate others first (partial unique index guards)
    await db.camps.update_many({"is_active": True}, {"$set": {"is_active": False}})
    await db.camps.update_one({"_id": oid}, {"$set": {"is_active": True}})
    return {"ok": True}


@router.post("/{camp_id}/deactivate")
async def deactivate_camp(camp_id: str, actor: dict = Depends(require_admin)) -> Dict[str, Any]:
    db = get_db()
    await db.camps.update_one({"_id": ObjectId(camp_id)}, {"$set": {"is_active": False}})
    return {"ok": True}


@router.delete("/{camp_id}")
async def delete_camp(camp_id: str, actor: dict = Depends(require_admin)) -> Dict[str, Any]:
    db = get_db()
    oid = ObjectId(camp_id)
    if await db.patients.find_one({"camp_id": oid}):
        raise HTTPException(status_code=409, detail="Camp has registrations; cannot delete")
    await db.camp_days.delete_many({"camp_id": oid})
    await db.camps.delete_one({"_id": oid})
    return {"ok": True}


@router.post("/days")
async def upsert_camp_day(body: CampDayBody, actor: dict = Depends(require_admin)) -> Dict[str, Any]:
    db = get_db()
    camp_oid = ObjectId(body.camp_id)
    if not await db.camps.find_one({"_id": camp_oid}):
        raise HTTPException(status_code=404, detail="Camp not found")
    existing = await db.camp_days.find_one({"camp_id": camp_oid, "day_date": body.day_date})
    if existing:
        await db.camp_days.update_one({"_id": existing["_id"]},
                                      {"$set": {"seat_limit": body.seat_limit}})
        d = await db.camp_days.find_one({"_id": existing["_id"]})
    else:
        res = await db.camp_days.insert_one({
            "camp_id": camp_oid, "day_date": body.day_date,
            "seat_limit": body.seat_limit, "printing_open": False,
            "created_at": now_utc(),
        })
        d = await db.camp_days.find_one({"_id": res.inserted_id})
    return {"day": ser_day(d)}


@router.get("/{camp_id}/days")
async def list_days(camp_id: str, actor: dict = Depends(require_any)) -> Dict[str, Any]:
    db = get_db()
    days = await db.camp_days.find({"camp_id": ObjectId(camp_id)}).sort("day_date", 1).to_list(100)
    return {"days": [ser_day(d) for d in days]}


@router.patch("/days/{day_id}/print-window")
async def toggle_print_window(day_id: str, body: PrintWindowBody, actor: dict = Depends(require_admin)) -> Dict[str, Any]:
    db = get_db()
    res = await db.camp_days.update_one(
        {"_id": ObjectId(day_id)}, {"$set": {"printing_open": body.printing_open}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Day not found")
    d = await db.camp_days.find_one({"_id": ObjectId(day_id)})
    return {"day": ser_day(d)}


@router.delete("/days/{day_id}")
async def delete_day(day_id: str, actor: dict = Depends(require_admin)) -> Dict[str, Any]:
    db = get_db()
    oid = ObjectId(day_id)
    if await db.patients.find_one({"camp_day_id": oid}):
        raise HTTPException(status_code=409, detail="Day has registrations; cannot delete")
    await db.camp_days.delete_one({"_id": oid})
    return {"ok": True}
