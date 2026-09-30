"""Queue stage: who waits for what between the door and the doctor, defined once for a camp (ADR 0099)."""

from datetime import datetime
from typing import Any, Dict, List, Tuple

from bson import ObjectId

PENDING_SORT: List[Tuple[str, int]] = [("printed_at", 1)]


def awaiting_print(camp_id: ObjectId) -> Dict[str, Any]:
    return {"camp_id": camp_id, "queue_status": "arrived", "printed_at": None}


def pending(camp_id: ObjectId) -> Dict[str, Any]:
    return {"camp_id": camp_id, "queue_status": "arrived", "printed_at": {"$type": "date"}}


def doctor_seen(camp_id: ObjectId) -> Dict[str, Any]:
    return {"camp_id": camp_id, "queue_status": "seen"}


def seen_fields(actor_id: str, now: datetime) -> Dict[str, Any]:
    return {"queue_status": "seen", "seen_at": now, "seen_by": actor_id}


def unseen_fields() -> Dict[str, Any]:
    return {"queue_status": "arrived", "seen_at": None, "seen_by": None}


def board_pipeline(camp_id: ObjectId, day_start: datetime) -> List[Dict[str, Any]]:
    unprinted = {"$lte": ["$printed_at", None]}
    printed = {"$gt": ["$printed_at", None]}
    earlier = {"$lt": ["$arrived_at", day_start]}
    return [
        {"$match": {"camp_id": camp_id, "queue_status": "arrived"}},
        {"$group": {
            "_id": None,
            "unprinted": {"$sum": {"$cond": [unprinted, 1, 0]}},
            "unprinted_earlier": {"$sum": {"$cond": [{"$and": [unprinted, earlier]}, 1, 0]}},
            "printed": {"$sum": {"$cond": [printed, 1, 0]}},
            "printed_earlier": {"$sum": {"$cond": [{"$and": [printed, earlier]}, 1, 0]}},
        }},
    ]


def board_stages(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    row = rows[0] if rows else {}
    printed, printed_earlier = row.get("printed", 0), row.get("printed_earlier", 0)
    return {
        "awaiting_print": row.get("unprinted", 0),
        "awaiting_seen": printed,
        "transcription_backlog": printed,
        "earlier_days": {
            "awaiting_print": row.get("unprinted_earlier", 0),
            "awaiting_seen": printed_earlier,
            "transcription_backlog": printed_earlier,
        },
    }
