"""Limits on the public endpoints, counted in MongoDB so a restart forgets nothing (ADR 0095)."""

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

from helpers import api_error, now_utc


def too_many() -> HTTPException:
    return api_error(429, "TOO_MANY_ATTEMPTS_PLEASE_TRY_AGAIN_LATER", 'Too many attempts. Please try again later.')


async def spend(db: AsyncDatabase, scope: str, subject: str, limit: int, window: timedelta) -> None:
    """Counts one attempt in the current fixed window and refuses once the window holds more than limit."""
    span = int(window.total_seconds())
    start = int(now_utc().timestamp()) // span * span
    counter = await db.rate_limits.find_one_and_update(
        {"_id": f"{scope}:{subject}:{start}"},
        {"$inc": {"count": 1}, "$setOnInsert": {"expires_at": datetime.fromtimestamp(start + span, timezone.utc)}},
        upsert=True, return_document=ReturnDocument.AFTER,
    )
    assert counter is not None
    if counter["count"] > limit:
        raise too_many()


async def refuse_at(db: AsyncDatabase, key: str, ceiling: int) -> None:
    """Refuses once a daily ceiling counted by add already holds ceiling successes."""
    counter = await db.rate_limits.find_one({"_id": key})
    if counter and counter["count"] >= ceiling:
        raise too_many()


async def add(db: AsyncDatabase, key: str) -> None:
    await db.rate_limits.update_one(
        {"_id": key}, {"$inc": {"count": 1}, "$setOnInsert": {"expires_at": now_utc() + timedelta(days=2)}}, upsert=True,
    )
