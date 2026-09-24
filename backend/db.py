import os
from typing import Any, Awaitable, Callable, TypeVar
from pymongo import ASCENDING, AsyncMongoClient, ReturnDocument
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.asynchronous.database import AsyncDatabase

T = TypeVar("T")

_client: AsyncMongoClient | None = None
_db: AsyncDatabase | None = None


def get_client() -> AsyncMongoClient:
    global _client
    if _client is None:
        _client = AsyncMongoClient(os.environ["MONGO_URL"])
    return _client


def get_db() -> AsyncDatabase:
    global _db
    if _db is None:
        _db = get_client()[os.environ["DB_NAME"]]
    return _db


async def in_transaction(callback: Callable[[AsyncClientSession], Awaitable[T]]) -> T:
    async with get_client().start_session() as session:
        return await session.with_transaction(callback)


async def aggregate_list(collection: AsyncCollection, pipeline: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cursor = await collection.aggregate(pipeline)
    return await cursor.to_list(None)


async def next_seq(name: str) -> int:
    db = get_db()
    doc = await db.counters.find_one_and_update(
        {"_id": name},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    assert doc is not None
    return int(doc["seq"])


async def init_indexes() -> None:
    db = get_db()
    await db.users.create_index("name_normalized", unique=True)
    await db.login_attempts.create_index("identifier", unique=True)
    await db.login_attempts.create_index("locked_until", expireAfterSeconds=900)
    await db.login_lockouts.create_index("at", expireAfterSeconds=7 * 86400)
    await db.login_sources.create_index("trusted_until", expireAfterSeconds=0)
    await db.login_lockouts.create_index([("name_normalized", ASCENDING), ("at", ASCENDING)])
    await db.camps.create_index("is_active", unique=True, partialFilterExpression={"is_active": True})
    await db.camps.create_index(
        "setup_request_id", unique=True, partialFilterExpression={"setup_request_id": {"$type": "string"}}
    )
    await db.camp_days.create_index([("camp_id", ASCENDING), ("day_date", ASCENDING)], unique=True)
    await db.camp_days.create_index("day_date")
    await db.persons.create_index("aadhaar_key", unique=True, sparse=True)
    await db.persons.create_index("person_no", unique=True)
    await db.patients.create_index("reg_no", unique=True)
    await db.patients.create_index("patient_qr", unique=True)
    await db.patients.create_index("registration_request_id", unique=True, sparse=True)
    await db.patients.create_index(
        [("person_id", ASCENDING), ("camp_id", ASCENDING)],
        unique=True,
        partialFilterExpression={"person_id": {"$type": "objectId"}},
    )
    await db.patients.create_index([("camp_id", ASCENDING), ("full_name_normalized", ASCENDING)])
    await db.patients.create_index([("camp_id", ASCENDING), ("arrived_at", ASCENDING)])
    await db.patients.create_index([("camp_id", ASCENDING), ("seen_at", ASCENDING)])
    await db.patients.create_index([("camp_id", ASCENDING), ("aadhaar_last4", ASCENDING)])
    await db.patients.create_index([("camp_id", ASCENDING), ("phone_normalized", ASCENDING)])
    await db.patients.create_index([("camp_id", ASCENDING), ("queue_status", ASCENDING)])
    await db.patients.create_index([("camp_id", ASCENDING), ("created_by", ASCENDING)])
    await db.patients.create_index([("camp_id", ASCENDING), ("registrar_team_lead_id", ASCENDING)])
    await db.transcriptions.create_index("patient_id", unique=True)
    await db.transcriptions.create_index([("person_id", ASCENDING), ("created_at", -1)])
    await db.medicines.create_index("name_key", unique=True)
    await db.fixed_powers.create_index("value", unique=True)
    await db.prescription_revisions.create_index("operation_id", unique=True)
    await db.prescription_revisions.create_index([("patient_id", ASCENDING), ("created_at", ASCENDING)])
    await db.clinical_operations.create_index("operation_id", unique=True)
    await db.deferred_slips.create_index([("transcription_id", ASCENDING), ("active", ASCENDING)])
    await db.deferred_slips.create_index([("item_type", ASCENDING), ("active", ASCENDING), ("collection_date", ASCENDING)])
    await db.deferred_slips.create_index([("ot_schedule_day_id", ASCENDING), ("active", ASCENDING)])
    await db.deferred_slips.create_index([("specs_collection_day_id", ASCENDING), ("active", ASCENDING)])
    await db.fulfilments.create_index([("ot_schedule_day_id", ASCENDING), ("status", ASCENDING)])
    await db.fulfilments.create_index([("transcription_id", ASCENDING), ("item_type", ASCENDING)], unique=True)
    await db.ot_schedule_days.create_index([("camp_id", ASCENDING), ("day_date", ASCENDING)], unique=True)
    await db.specs_collection_days.create_index([("camp_id", ASCENDING), ("day_date", ASCENDING)], unique=True)
    await db.reminder_ledger.create_index([("status", ASCENDING), ("created_at", ASCENDING)])
    await db.reminder_ledger.create_index("provider_id", sparse=True)
    await db.reminder_ledger.create_index("created_at")
    await db.reminder_ledger.create_index([("number", ASCENDING), ("message_type", ASCENDING), ("created_at", ASCENDING)])
    await db.reminder_ledger.create_index(
        [
            ("patient_id", ASCENDING),
            ("message_type", ASCENDING),
            ("event_date", ASCENDING),
            ("event_key", ASCENDING),
        ],
        unique=True,
        partialFilterExpression={"patient_id": {"$exists": True}},
    )
