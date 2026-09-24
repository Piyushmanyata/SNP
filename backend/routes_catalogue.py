from typing import Any, Dict, List

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends
from pymongo import ASCENDING
from pymongo.errors import DuplicateKeyError

from catalogue import (
    medicine_key,
    normalize_medicine_name,
    parse_power,
    ser_medicine,
    ser_power,
)
from db import get_db
from helpers import now_utc, api_error
from models import CatalogueActiveBody, FixedPowerBody, MedicineBody
from security import require_admin, require_any

router = APIRouter(prefix="/api/catalogue", tags=["catalogue"])


def _oid(raw: str) -> ObjectId:
    try:
        return ObjectId(raw)
    except (InvalidId, TypeError, ValueError):
        raise api_error(404, "NOT_FOUND", 'Not found')


async def _list(collection, sort_key: str, include_inactive: bool, serialize) -> List[Dict[str, Any]]:
    query = {} if include_inactive else {"active": True}
    rows = await collection.find(query).sort(sort_key, ASCENDING).to_list(1000)
    return [serialize(row) for row in rows]


async def _add(collection, key_field: str, key: Any, doc: dict, serialize, actor: dict) -> Dict[str, Any]:
    """Re-adding something the admin retired brings it back rather than colliding with it."""
    existing = await collection.find_one({key_field: key})
    if existing:
        await collection.update_one({"_id": existing["_id"]}, {"$set": {**doc, "active": True}})
        return serialize({**existing, **doc, "active": True})
    record = {
        **doc,
        key_field: key,
        "active": True,
        "created_by": str(actor["_id"]),
        "created_at": now_utc(),
    }
    try:
        result = await collection.insert_one(record)
    except DuplicateKeyError:
        found = await collection.find_one({key_field: key})
        if not found:
            raise
        return serialize(found)
    return serialize({**record, "_id": result.inserted_id})


async def _set_active(collection, item_id: str, active: bool, serialize) -> Dict[str, Any]:
    row = await collection.find_one_and_update(
        {"_id": _oid(item_id)},
        {"$set": {"active": active}},
        return_document=True,
    )
    if not row:
        raise api_error(404, "NOT_FOUND", 'Not found')
    return serialize(row)


@router.get("/medicines")
async def list_medicines(
    include_inactive: bool = False,
    actor: dict = Depends(require_any),
) -> Dict[str, Any]:
    return {"medicines": await _list(get_db().medicines, "name", include_inactive, ser_medicine)}


@router.post("/medicines")
async def add_medicine(body: MedicineBody, actor: dict = Depends(require_admin)) -> Dict[str, Any]:
    name = normalize_medicine_name(body.name)
    return {"medicine": await _add(
        get_db().medicines, "name_key", medicine_key(name), {"name": name}, ser_medicine, actor,
    )}


@router.patch("/medicines/{medicine_id}")
async def set_medicine_active(
    medicine_id: str,
    body: CatalogueActiveBody,
    actor: dict = Depends(require_admin),
) -> Dict[str, Any]:
    return {"medicine": await _set_active(get_db().medicines, medicine_id, body.active, ser_medicine)}


@router.get("/powers")
async def list_powers(
    include_inactive: bool = False,
    actor: dict = Depends(require_any),
) -> Dict[str, Any]:
    return {"powers": await _list(get_db().fixed_powers, "value", include_inactive, ser_power)}


@router.post("/powers")
async def add_power(body: FixedPowerBody, actor: dict = Depends(require_admin)) -> Dict[str, Any]:
    return {"power": await _add(
        get_db().fixed_powers, "value", parse_power(body.value), {}, ser_power, actor,
    )}


@router.patch("/powers/{power_id}")
async def set_power_active(
    power_id: str,
    body: CatalogueActiveBody,
    actor: dict = Depends(require_admin),
) -> Dict[str, Any]:
    return {"power": await _set_active(get_db().fixed_powers, power_id, body.active, ser_power)}
