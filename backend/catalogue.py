import math
import re
from typing import Any, Dict, List

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException

MAX_NAME_LEN = 120
POWER_MIN = -20.0
POWER_MAX = 20.0
_WHITESPACE = re.compile(r"\s+")


def normalize_medicine_name(raw: Any) -> str:
    name = _WHITESPACE.sub(" ", str(raw or "").strip())
    if not name:
        raise HTTPException(status_code=400, detail="Medicine name is required")
    if len(name) > MAX_NAME_LEN:
        raise HTTPException(
            status_code=400,
            detail=f"Medicine name must be {MAX_NAME_LEN} characters or fewer",
        )
    return name


def medicine_key(raw: Any) -> str:
    return normalize_medicine_name(raw).casefold()


def parse_power(raw: Any) -> float:
    if isinstance(raw, bool):
        raise HTTPException(status_code=400, detail="Power must be a number")
    try:
        value = float(str(raw).strip())
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Power must be a number")
    if not math.isfinite(value):
        raise HTTPException(status_code=400, detail="Power must be a number")
    value = round(value, 2)
    if value == 0:
        value = 0.0
    if not POWER_MIN <= value <= POWER_MAX:
        raise HTTPException(
            status_code=400,
            detail=f"Power must be between {POWER_MIN:+.2f} and {POWER_MAX:+.2f} dioptres",
        )
    return value


def format_power(value: Any) -> str:
    return f"{parse_power(value):+.2f}"


def ser_medicine(doc: dict) -> Dict[str, Any]:
    return {
        "id": str(doc["_id"]),
        "name": doc["name"],
        "active": bool(doc.get("active", True)),
    }


def ser_power(doc: dict) -> Dict[str, Any]:
    return {
        "id": str(doc["_id"]),
        "value": doc["value"],
        "label": format_power(doc["value"]),
        "active": bool(doc.get("active", True)),
    }


def _medicine_oid(raw: Any) -> ObjectId:
    try:
        return ObjectId(str(raw))
    except (InvalidId, TypeError, ValueError):
        raise HTTPException(status_code=400, detail={
            "code": "unknown_medicine",
            "message": "That medicine is not in the camp's list.",
        })


async def resolve_medicines(db, ids: List[Any], *, active_only: bool) -> List[Dict[str, Any]]:
    """Snapshot catalogue names onto the prescription so later catalogue edits cannot rewrite it."""
    ordered: List[str] = []
    for raw in ids or []:
        key = str(raw)
        if key not in ordered:
            ordered.append(key)
    if not ordered:
        return []
    query: Dict[str, Any] = {"_id": {"$in": [_medicine_oid(k) for k in ordered]}}
    if active_only:
        query["active"] = {"$ne": False}
    rows = await db.medicines.find(query).to_list(len(ordered))
    names = {str(row["_id"]): row["name"] for row in rows}
    if set(names) != set(ordered):
        raise HTTPException(status_code=400, detail={
            "code": "unknown_medicine",
            "message": "That medicine is not in the camp's list.",
        })
    return [{"medicine_id": key, "name": names[key]} for key in ordered]


async def stocked_power(db, raw: Any, *, active_only: bool) -> Any:
    if raw is None:
        return None
    value = parse_power(raw)
    query: Dict[str, Any] = {"value": value}
    if active_only:
        query["active"] = {"$ne": False}
    if not await db.fixed_powers.find_one(query):
        raise HTTPException(status_code=400, detail={
            "code": "unknown_power",
            "message": f"{format_power(value)} is not one of the camp's fixed powers.",
        })
    return value
