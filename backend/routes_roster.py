from typing import Any, Dict, List, Optional
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Request

from db import get_db
from helpers import iso, normalize_name, now_utc
from models import RosterBulkBody
from security import get_current_user, require_admin, require_any

router = APIRouter(prefix="/api/roster", tags=["roster"])


def ser_roster(e: dict) -> dict:
    return {
        "id": str(e["_id"]),
        "camp_id": str(e["camp_id"]),
        "name": e["name"],
        "disabled_at": iso(e.get("disabled_at")) if e.get("disabled_at") else None,
    }


async def _resolve_roster(raw: str) -> Optional[dict]:
    try:
        oid = ObjectId(raw)
    except (InvalidId, TypeError, ValueError):
        return None
    db = get_db()
    entry = await db.roster.find_one({"_id": oid})
    if not entry or entry.get("disabled_at") is not None:
        return None
    camp = await db.camps.find_one({"is_active": True})
    if not camp or entry.get("camp_id") != camp["_id"]:
        return None
    return entry


async def on_desk_volunteer(
    request: Request, actor: dict = Depends(get_current_user),
) -> Optional[dict]:
    header = request.headers.get("X-Roster-Id")
    role = actor.get("role")
    if role in ("admin", "team_lead"):
        if not header:
            return None
        return await _resolve_roster(header)
    if role in ("volunteer", "clinical_desk_operator"):
        if not header:
            raise HTTPException(status_code=428, detail={
                "code": "ROSTER_REQUIRED",
                "message": "Pick your name before posting.",
            })
        entry = await _resolve_roster(header)
        if not entry:
            raise HTTPException(status_code=428, detail={
                "code": "ROSTER_INVALID",
                "message": "That roster name is not valid for this camp. Pick again.",
            })
        return entry
    return None


@router.post("")
async def bulk_add(body: RosterBulkBody, actor: dict = Depends(require_admin)) -> Dict[str, Any]:
    names: List[str] = []
    for raw in body.names:
        name = (raw or "").strip()
        if name:
            names.append(name)
    if not names:
        raise HTTPException(status_code=400, detail="No names given")
    db = get_db()
    camp_id = ObjectId(body.camp_id)
    created, skipped = [], []
    seen = set()
    for name in names:
        norm = normalize_name(name)
        if norm in seen:
            skipped.append(name)
            continue
        existing = await db.roster.find_one({"camp_id": camp_id, "name_normalized": norm})
        if existing:
            skipped.append(name)
            continue
        seen.add(norm)
        doc = {
            "camp_id": camp_id,
            "name": name,
            "name_normalized": norm,
            "created_at": now_utc(),
            "created_by": str(actor["_id"]),
            "disabled_at": None,
        }
        res = await db.roster.insert_one(doc)
        doc["_id"] = res.inserted_id
        created.append(ser_roster(doc))
    return {"entries": created, "skipped": skipped}


@router.get("")
async def list_roster(
    camp_id: Optional[str] = None,
    include_disabled: bool = False,
    actor: dict = Depends(require_any),
) -> Dict[str, Any]:
    db = get_db()
    if camp_id:
        cid = ObjectId(camp_id)
    else:
        camp = await db.camps.find_one({"is_active": True})
        if not camp:
            return {"entries": []}
        cid = camp["_id"]
    query: Dict[str, Any] = {"camp_id": cid}
    if not include_disabled:
        query["disabled_at"] = None
    rows = await db.roster.find(query).sort("name", 1).to_list(1000)
    return {"entries": [ser_roster(e) for e in rows]}


@router.patch("/{entry_id}/disable")
async def disable_entry(entry_id: str, actor: dict = Depends(require_admin)) -> Dict[str, Any]:
    db = get_db()
    entry = await db.roster.find_one({"_id": ObjectId(entry_id)})
    if not entry:
        raise HTTPException(status_code=404, detail="Roster entry not found")
    await db.roster.update_one({"_id": entry["_id"]}, {"$set": {"disabled_at": now_utc()}})
    return {"ok": True}


@router.patch("/{entry_id}/enable")
async def enable_entry(entry_id: str, actor: dict = Depends(require_admin)) -> Dict[str, Any]:
    db = get_db()
    entry = await db.roster.find_one({"_id": ObjectId(entry_id)})
    if not entry:
        raise HTTPException(status_code=404, detail="Roster entry not found")
    await db.roster.update_one({"_id": entry["_id"]}, {"$set": {"disabled_at": None}})
    return {"ok": True}
