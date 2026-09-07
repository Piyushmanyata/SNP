import asyncio
from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId
from pymongo.errors import DuplicateKeyError
from db import get_db
from models import CreateStaffBody, PatchStaffLineBody
from helpers import now_utc, normalize_name
from security import (
    hash_pin,
    serialize_user,
    require_admin,
    require_lead,
    get_current_user,
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

    doc = {
        "name": name,
        "name_normalized": norm,
        "pin_hash": await asyncio.to_thread(hash_pin, "1234"),
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
    return {"staff": serialize_user(doc)}


@router.get("")
async def list_staff(actor: dict = Depends(require_lead)) -> Dict[str, Any]:
    db = get_db()
    query = {}
    if actor["role"] == "team_lead":
        query = {"role": "volunteer", "team_lead_id": str(actor["_id"])}
    users = await db.users.find(query).sort("created_at", -1).to_list(500)
    return {"staff": [serialize_user(u) for u in users]}


@router.get("/team-leads")
async def team_leads(actor: dict = Depends(require_admin)) -> Dict[str, Any]:
    db = get_db()
    users = await db.users.find({"role": "team_lead", "disabled_at": None}).to_list(200)
    return {"team_leads": [serialize_user(u) for u in users]}


@router.post("/{staff_id}/reset-pin")
async def reset_staff_pin(staff_id: str, actor: dict = Depends(get_current_user)) -> Dict[str, Any]:
    db = get_db()
    user = await db.users.find_one({"_id": ObjectId(staff_id)})
    if not user:
        raise HTTPException(status_code=404, detail="Staff not found")

    if actor["role"] == "admin":
        pass
    elif actor["role"] == "team_lead":
        if user.get("role") != "volunteer" or user.get("team_lead_id") != str(actor["_id"]):
            raise HTTPException(status_code=403, detail="Cannot reset PIN for this volunteer")
    else:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"pin_hash": await asyncio.to_thread(hash_pin, "1234"), "must_change_pin": True},
         "$inc": {"session_version": 1}},
    )
    return {"ok": True, "message": "PIN reset to 1234"}


@router.patch("/{staff_id}")
async def patch_staff_line(staff_id: str, body: PatchStaffLineBody, actor: dict = Depends(require_admin)) -> Dict[str, Any]:
    db = get_db()
    user = await db.users.find_one({"_id": ObjectId(staff_id)})
    if not user:
        raise HTTPException(status_code=404, detail="Staff not found")
    line = assigned_line(user["role"], body.line)
    await db.users.update_one({"_id": user["_id"]}, {"$set": {"line": line}})
    user["line"] = line
    return {"staff": serialize_user(user)}


@router.patch("/{staff_id}/disable")
async def disable_staff(staff_id: str, actor: dict = Depends(get_current_user)) -> Dict[str, Any]:
    db = get_db()
    user = await db.users.find_one({"_id": ObjectId(staff_id)})
    if not user:
        raise HTTPException(status_code=404, detail="Staff not found")
    if actor["role"] == "admin":
        pass
    elif actor["role"] == "team_lead":
        if user.get("role") != "volunteer" or user.get("team_lead_id") != str(actor["_id"]):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
    else:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    await db.users.update_one(
        {"_id": user["_id"]}, {"$set": {"disabled_at": now_utc()}, "$inc": {"session_version": 1}}
    )
    return {"ok": True}


@router.patch("/{staff_id}/enable")
async def enable_staff(staff_id: str, actor: dict = Depends(get_current_user)) -> Dict[str, Any]:
    db = get_db()
    user = await db.users.find_one({"_id": ObjectId(staff_id)})
    if not user:
        raise HTTPException(status_code=404, detail="Staff not found")
    if actor["role"] == "admin":
        pass
    elif actor["role"] == "team_lead":
        if user.get("role") != "volunteer" or user.get("team_lead_id") != str(actor["_id"]):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
    else:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    await db.users.update_one(
        {"_id": user["_id"]}, {"$set": {"disabled_at": None}}
    )
    return {"ok": True}
