"""Arrival: the patient is here. Stamped once, onto the Operating day, never against Camp-day capacity (ADR 0042)."""

from datetime import datetime
from typing import Any, Dict, Optional

from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase

import printing
from helpers import api_error, now_utc


def fields_at_creation(arrived_by: Optional[str], now: datetime) -> Dict[str, Any]:
    """The Arrival fields of a new registration; a Door walk-in, scanned or typed, is created already arrived."""
    fields: Dict[str, Any] = {"arrived_at": None, "arrived_by": None, "camp_day_changed_from": None}
    if arrived_by:
        fields.update(arrived_at=now, arrived_by=arrived_by, queue_status="arrived")
    return fields


def require_arrivable(patient: dict) -> None:
    if not (patient.get("no_card_print") or patient.get("arrived_at")):
        raise printing.error("NEEDS_DOOR_SCAN")


async def stamp(db: AsyncDatabase, patient: dict, actor_id: str, printing_state: dict) -> dict:
    """Stamps Arrival once and moves the patient onto the Operating day, recording the day they had booked."""
    if patient.get("arrived_at"):
        return patient
    printing.require_open(printing_state)
    updates: Dict[str, Any] = {
        "arrived_at": now_utc(),
        "arrived_by": actor_id,
        "queue_status": "arrived" if patient.get("queue_status") == "registered" else patient.get("queue_status"),
    }
    operating = None
    if printing_state.get("operating_day_id"):
        operating = await db.camp_days.find_one({"_id": ObjectId(printing_state["operating_day_id"])})
    if operating and operating["_id"] != patient.get("camp_day_id"):
        booked = await db.camp_days.find_one({"_id": patient["camp_day_id"]})
        updates["camp_day_id"] = operating["_id"]
        updates["camp_day_changed_from"] = booked["day_date"] if booked else None
    arrived = await db.patients.find_one_and_update(
        {"_id": patient["_id"], "arrived_at": None}, {"$set": updates}, return_document=True,
    )
    if not arrived:
        arrived = await db.patients.find_one({"_id": patient["_id"]})
    if not arrived:
        raise api_error(404, "REGISTRATION_NOT_FOUND", 'Registration not found')
    return arrived
