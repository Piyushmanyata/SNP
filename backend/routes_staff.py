import asyncio
from datetime import timedelta
from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId
from pymongo.errors import DuplicateKeyError
from db import aggregate_list, get_db
from models import CreateStaffBody, PatchStaffLineBody, PatchStaffTeamLeadBody
from helpers import iso, now_utc, normalize_name
from routes_auth import MAX_ATTEMPTS
from security import (
    hash_pin,
    serialize_user,
    require_admin,
    require_lead,
    get_current_user,
    temporary_pin,
)

router = APIRouter(prefix="/api/staff", tags=["staff"])

VALID_ROLES = {"admin", "team_lead", "volunteer", "clinical_desk_operator"}
VALID_LINES = {"rx", "medicine", "specs_fixed", "specs_made", "ot"}
CLINICAL_ROLE = "clinical_desk_operator"


def assigned_line(role: str, line: Optional[str]) -> Optional[str]:
    if role != CLINICAL_ROLE:
        return None
    if line is None or line == "":
        return None
    if line not in VALID_LINES:
        raise HTTPException(status_code=400, detail="Invalid line")
    return line


@router.post("")
async def create_staff(body: CreateStaffBody, actor: dict = Depends(get_current_user)) -> Dict[str, Any]:
    db = get_db()
    if body.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail="Invalid role")

    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")

    norm = normalize_name(name)
    if not norm:
        raise HTTPException(status_code=400, detail="Valid name is required")

    # permission model
    if actor["role"] == "admin":
        pass
    elif actor["role"] == "team_lead":
        if body.role != "volunteer":
            raise HTTPException(status_code=403, detail="Team leads can only create volunteers")
    else:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    if await db.users.find_one({"name_normalized": norm}):
        raise HTTPException(status_code=409, detail="Name already exists")

    team_lead_id = body.team_lead_id
    if actor["role"] == "team_lead":
        team_lead_id = str(actor["_id"])
    elif body.role == "volunteer" and team_lead_id:
        try:
            tl_oid = ObjectId(team_lead_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid team lead id")
        lead = await db.users.find_one({"_id": tl_oid, "role": "team_lead", "disabled_at": None})
        if not lead:
            raise HTTPException(status_code=400, detail="Team lead not found or inactive")

    pin = temporary_pin(body.role)
    doc = {
        "name": name,
        "name_normalized": norm,
        "pin_hash": await asyncio.to_thread(hash_pin, pin),
        "must_change_pin": True,
        "role": body.role,
        "phone": body.phone,
        "team_lead_id": team_lead_id if body.role == "volunteer" else None,
        "line": assigned_line(body.role, body.line),
        "disabled_at": None,
        "created_at": now_utc(),
        "created_by": str(actor["_id"]),
    }
    try:
        res = await db.users.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="Name already exists")
    doc["_id"] = res.inserted_id
    return {"staff": serialize_user(doc), "temporary_pin": pin}


@router.get("")
async def list_staff(actor: dict = Depends(require_lead)) -> Dict[str, Any]:
    db = get_db()
    query: Dict[str, Any] = {"deleted_at": None}
    if actor["role"] == "team_lead":
        query.update({"role": "volunteer", "team_lead_id": str(actor["_id"])})
    users = await db.users.find(query).sort("created_at", -1).to_list(500)
    now = now_utc()
    names = [u["name_normalized"] for u in users]
    locked = {
        a["identifier"].removeprefix("name:"): a["locked_until"]
        for a in await db.login_attempts.find({
            "identifier": {"$in": [f"name:{n}" for n in names]},
            "count": {"$gte": MAX_ATTEMPTS}, "locked_until": {"$gt": now},
        }).to_list(None)
    }
    lockouts = {row["_id"]: row for row in await aggregate_list(db.login_lockouts, [
        {"$match": {"name_normalized": {"$in": names}, "at": {"$gte": now - timedelta(hours=24)}}},
        {"$group": {"_id": "$name_normalized", "count": {"$sum": 1}, "sources": {"$addToSet": "$source"}}},
    ])}
    return {"staff": [{
        **serialize_user(u),
        "locked_until": iso(locked.get(u["name_normalized"])),
        "lockouts_24h": lockouts.get(u["name_normalized"], {}).get("count", 0),
        "lockout_sources_24h": len(lockouts.get(u["name_normalized"], {}).get("sources", [])),
    } for u in users]}


@router.get("/team-leads")
async def team_leads(actor: dict = Depends(require_admin)) -> Dict[str, Any]:
    db = get_db()
    users = await db.users.find({"role": "team_lead", "disabled_at": None, "deleted_at": None}).to_list(200)
    return {"team_leads": [serialize_user(u) for u in users]}


async def _managed(db: Any, staff_id: str, actor: dict) -> dict:
    if not ObjectId.is_valid(staff_id):
        raise HTTPException(status_code=400, detail="Invalid staff id")
    user = await db.users.find_one({"_id": ObjectId(staff_id), "deleted_at": None})
    if not user:
        raise HTTPException(status_code=404, detail="Staff not found")
    if actor["role"] == "team_lead":
        if user.get("role") != "volunteer" or user.get("team_lead_id") != str(actor["_id"]):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
    elif actor["role"] != "admin":
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return user


async def _recover(db: Any, user: dict, actor: dict, action: str) -> None:
    await db.login_attempts.delete_one({"identifier": f"name:{user['name_normalized']}"})
    await db.staff_audit.insert_one({
        "action": action, "target_id": str(user["_id"]), "actor_id": str(actor["_id"]), "at": now_utc(),
    })


@router.post("/{staff_id}/reset-pin")
async def reset_staff_pin(staff_id: str, actor: dict = Depends(get_current_user)) -> Dict[str, Any]:
    db = get_db()
    user = await _managed(db, staff_id, actor)
    pin = temporary_pin(user["role"])
    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"pin_hash": await asyncio.to_thread(hash_pin, pin), "must_change_pin": True},
         "$inc": {"session_version": 1}},
    )
    await _recover(db, user, actor, "reset_pin")
    return {"ok": True, "temporary_pin": pin}


@router.post("/{staff_id}/unlock")
async def unlock_staff(staff_id: str, actor: dict = Depends(get_current_user)) -> Dict[str, Any]:
    db = get_db()
    await _recover(db, await _managed(db, staff_id, actor), actor, "unlock")
    return {"ok": True}


@router.patch("/{staff_id}")
async def patch_staff_line(staff_id: str, body: PatchStaffLineBody, actor: dict = Depends(require_admin)) -> Dict[str, Any]:
    db = get_db()
    user = await db.users.find_one({"_id": ObjectId(staff_id), "deleted_at": None})
    if not user:
        raise HTTPException(status_code=404, detail="Staff not found")
    line = assigned_line(user["role"], body.line)
    await db.users.update_one({"_id": user["_id"]}, {"$set": {"line": line}})
    user["line"] = line
    return {"staff": serialize_user(user)}


@router.patch("/{staff_id}/team-lead")
async def reassign_volunteer(staff_id: str, body: PatchStaffTeamLeadBody, actor: dict = Depends(require_admin)) -> Dict[str, Any]:
    db = get_db()
    if not ObjectId.is_valid(staff_id):
        raise HTTPException(status_code=400, detail="Invalid staff id")
    user = await db.users.find_one({"_id": ObjectId(staff_id), "role": "volunteer", "deleted_at": None})
    if not user:
        raise HTTPException(status_code=404, detail="Volunteer not found")
    lead_id = body.team_lead_id
    if lead_id:
        if not ObjectId.is_valid(lead_id):
            raise HTTPException(status_code=400, detail="Invalid team lead id")
        lead = await db.users.find_one({
            "_id": ObjectId(lead_id), "role": "team_lead", "disabled_at": None, "deleted_at": None,
        })
        if not lead:
            raise HTTPException(status_code=400, detail="Team lead not found or inactive")
    await db.users.update_one({"_id": user["_id"]}, {"$set": {"team_lead_id": lead_id}})
    user["team_lead_id"] = lead_id
    return {"staff": serialize_user(user)}


@router.patch("/{staff_id}/disable")
async def disable_staff(staff_id: str, actor: dict = Depends(get_current_user)) -> Dict[str, Any]:
    db = get_db()
    user = await _managed(db, staff_id, actor)
    if user["_id"] == actor["_id"]:
        raise HTTPException(status_code=409, detail={
            "code": "CANNOT_DISABLE_SELF",
            "message": "You cannot disable your own account.",
        })

    await db.users.update_one(
        {"_id": user["_id"]}, {"$set": {"disabled_at": now_utc()}, "$inc": {"session_version": 1}}
    )
    if (
        user.get("role") == "admin" and not user.get("disabled_at")
        and not await db.users.count_documents({"role": "admin", "disabled_at": None})
    ):
        await db.users.update_one({"_id": user["_id"]}, {"$set": {"disabled_at": None}})
        raise HTTPException(status_code=409, detail={
            "code": "LAST_ADMIN",
            "message": "At least one admin must stay enabled.",
        })
    return {"ok": True}


@router.patch("/{staff_id}/enable")
async def enable_staff(staff_id: str, actor: dict = Depends(get_current_user)) -> Dict[str, Any]:
    db = get_db()
    user = await _managed(db, staff_id, actor)
    await db.users.update_one(
        {"_id": user["_id"]}, {"$set": {"disabled_at": None}}
    )
    return {"ok": True}


@router.delete("/{staff_id}")
async def delete_staff(staff_id: str, actor: dict = Depends(get_current_user)) -> Dict[str, Any]:
    db = get_db()
    user = await _managed(db, staff_id, actor)
    if user["_id"] == actor["_id"]:
        raise HTTPException(status_code=409, detail="You cannot delete your own account.")
    if user["role"] == "admin" and not user.get("disabled_at"):
        enabled = await db.users.count_documents({"role": "admin", "disabled_at": None, "deleted_at": None})
        if enabled <= 1:
            raise HTTPException(status_code=409, detail="At least one admin must stay enabled.")
    if user["role"] == "team_lead" and await db.users.find_one({
        "role": "volunteer", "team_lead_id": str(user["_id"]), "deleted_at": None,
    }):
        raise HTTPException(status_code=409, detail="Reassign this team lead's volunteers before deletion.")
    now = now_utc()
    await db.users.update_one({"_id": user["_id"], "deleted_at": None}, {
        "$set": {
            "deleted_at": now,
            "disabled_at": now,
            "name_normalized": f"deleted:{user['_id']}",
        },
        "$inc": {"session_version": 1},
    })
    if user["role"] == "admin" and not user.get("disabled_at") and not await db.users.count_documents({
        "role": "admin", "disabled_at": None, "deleted_at": None,
    }):
        await db.users.update_one({"_id": user["_id"], "deleted_at": now}, {"$set": {
            "deleted_at": None,
            "disabled_at": user.get("disabled_at"),
            "name_normalized": user.get("name_normalized"),
        }})
        raise HTTPException(status_code=409, detail="At least one admin must stay enabled.")
    return {"ok": True}
