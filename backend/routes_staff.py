from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId
from db import get_db
from models import CreateStaffBody, PatchStaffLineBody
from helpers import now_utc
from security import (
    hash_password,
    validate_password_policy,
    serialize_user,
    require_admin,
    require_staff,
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

    # permission model
    if actor["role"] == "admin":
        pass
    elif actor["role"] == "team_lead":
        if body.role != "volunteer":
            raise HTTPException(status_code=403, detail="Team leads can only create volunteers")
    else:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    err = validate_password_policy(body.password)
    if err:
        raise HTTPException(status_code=400, detail=err)

    email = body.email.lower().strip()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=409, detail="Email already exists")

    team_lead_id = body.team_lead_id
    if actor["role"] == "team_lead":
        team_lead_id = str(actor["_id"])

    doc = {
        "email": email,
        "password_hash": hash_password(body.password),
        "name": body.name,
        "role": body.role,
        "phone": body.phone,
        "team_lead_id": team_lead_id if body.role == "volunteer" else None,
        "line": assigned_line(body.role, body.line),
        "disabled_at": None,
        "created_at": now_utc(),
        "created_by": str(actor["_id"]),
    }
    res = await db.users.insert_one(doc)
    doc["_id"] = res.inserted_id
    return {"staff": serialize_user(doc)}


@router.get("")
async def list_staff(actor: dict = Depends(require_staff)) -> Dict[str, Any]:
    db = get_db()
    query = {}
    if actor["role"] == "team_lead":
        query = {"$or": [{"team_lead_id": str(actor["_id"])}, {"_id": actor["_id"]}]}
    users = await db.users.find(query).sort("created_at", -1).to_list(500)
    return {"staff": [serialize_user(u) for u in users]}


@router.get("/team-leads")
async def team_leads(actor: dict = Depends(require_admin)) -> Dict[str, Any]:
    db = get_db()
    users = await db.users.find({"role": "team_lead", "disabled_at": None}).to_list(200)
    return {"team_leads": [serialize_user(u) for u in users]}


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
async def disable_staff(staff_id: str, actor: dict = Depends(require_admin)) -> Dict[str, Any]:
    db = get_db()
    res = await db.users.update_one(
        {"_id": ObjectId(staff_id)}, {"$set": {"disabled_at": now_utc()}}
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Staff not found")
    return {"ok": True}


@router.patch("/{staff_id}/enable")
async def enable_staff(staff_id: str, actor: dict = Depends(require_admin)) -> Dict[str, Any]:
    db = get_db()
    res = await db.users.update_one(
        {"_id": ObjectId(staff_id)}, {"$set": {"disabled_at": None}}
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Staff not found")
    return {"ok": True}
