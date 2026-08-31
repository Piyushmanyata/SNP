import os
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING

_client: AsyncIOMotorClient | None = None
_db = None


def get_db():
    global _client, _db
    if _db is None:
        _client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        _db = _client[os.environ["DB_NAME"]]
    return _db


async def next_seq(name: str) -> int:
    db = get_db()
    doc = await db.counters.find_one_and_update(
        {"_id": name},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True,
    )
    return int(doc["seq"])


async def init_indexes():
    db = get_db()
    # staff / users
    await db.users.create_index("email", unique=True)
    await db.login_attempts.create_index("identifier")
    await db.login_attempts.create_index("locked_until", expireAfterSeconds=900)
    # camps: exactly one active
    await db.camps.create_index(
        "is_active", unique=True, partialFilterExpression={"is_active": True}
    )
    await db.camp_days.create_index(
        [("camp_id", ASCENDING), ("day_date", ASCENDING)], unique=True
    )
    # persons: one person per aadhaar key
    await db.persons.create_index("aadhaar_key", unique=True, sparse=True)
    await db.persons.create_index("person_no", unique=True)
    # registrations
    await db.patients.create_index("reg_no", unique=True)
    await db.patients.create_index("patient_qr", unique=True)
    await db.patients.create_index(
        "registration_request_id", unique=True, sparse=True
    )
    await db.patients.create_index([("camp_id", ASCENDING), ("full_name_normalized", ASCENDING)])
    await db.patients.create_index([("person_id", ASCENDING), ("camp_id", ASCENDING)])
    # ot schedule
    await db.ot_schedule_days.create_index(
        [("camp_id", ASCENDING), ("day_date", ASCENDING)], unique=True
    )
    await db.specs_collection_days.create_index(
        [("camp_id", ASCENDING), ("day_date", ASCENDING)], unique=True
    )
    await db.reminder_ledger.create_index(
        [
            ("number", ASCENDING),
            ("reminder_type", ASCENDING),
            ("event_date", ASCENDING),
            ("send_date", ASCENDING),
        ],
        unique=True,
    )
