import os
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


def get_db() -> AsyncIOMotorDatabase:
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


PERSON_CAMP_INDEX_NAME = "person_id_1_camp_id_1"
PERSON_CAMP_INDEX = {
    "keys": [("person_id", ASCENDING), ("camp_id", ASCENDING)],
    "unique": True,
    "partialFilterExpression": {"person_id": {"$type": "objectId"}},
}
TRANSCRIPTION_PATIENT_INDEX = {"keys": "patient_id", "unique": True}

LEDGER_INDEX_NAME = "patient_id_1_message_type_1_event_date_1"
LEDGER_PARTIAL_FILTER = {"patient_id": {"$exists": True}}


def should_drop_person_camp_index(index_info: dict) -> bool:
    old = index_info.get(PERSON_CAMP_INDEX_NAME)
    return bool(old) and not old.get("unique")


def should_drop_ledger_index(index_info: dict) -> bool:
    old = index_info.get(LEDGER_INDEX_NAME)
    return bool(old) and old.get("partialFilterExpression") != LEDGER_PARTIAL_FILTER


async def init_indexes() -> None:
    db = get_db()
    await db.users.create_index("email", unique=True)
    await db.login_attempts.create_index("identifier")
    await db.login_attempts.create_index("locked_until", expireAfterSeconds=900)
    await db.camps.create_index(
        "is_active", unique=True, partialFilterExpression={"is_active": True}
    )
    await db.camp_days.create_index(
        [("camp_id", ASCENDING), ("day_date", ASCENDING)], unique=True
    )
    await db.persons.create_index("aadhaar_key", unique=True, sparse=True)
    await db.persons.create_index("person_no", unique=True)
    await db.patients.create_index("reg_no", unique=True)
    await db.patients.create_index("patient_qr", unique=True)
    await db.patients.create_index(
        "registration_request_id", unique=True, sparse=True
    )
    await db.patients.create_index([("camp_id", ASCENDING), ("full_name_normalized", ASCENDING)])
    patient_indexes = await db.patients.index_information()
    if should_drop_person_camp_index(patient_indexes):
        await db.patients.drop_index(PERSON_CAMP_INDEX_NAME)
    await db.patients.create_index(
        PERSON_CAMP_INDEX["keys"],
        unique=PERSON_CAMP_INDEX["unique"],
        partialFilterExpression=PERSON_CAMP_INDEX["partialFilterExpression"],
    )
    await db.transcriptions.create_index(
        TRANSCRIPTION_PATIENT_INDEX["keys"],
        unique=TRANSCRIPTION_PATIENT_INDEX["unique"],
    )
    await db.ot_schedule_days.create_index(
        [("camp_id", ASCENDING), ("day_date", ASCENDING)], unique=True
    )
    await db.specs_collection_days.create_index(
        [("camp_id", ASCENDING), ("day_date", ASCENDING)], unique=True
    )
    if should_drop_ledger_index(await db.reminder_ledger.index_information()):
        await db.reminder_ledger.drop_index(LEDGER_INDEX_NAME)
    await db.reminder_ledger.create_index(
        [
            ("patient_id", ASCENDING),
            ("message_type", ASCENDING),
            ("event_date", ASCENDING),
        ],
        unique=True,
        partialFilterExpression=LEDGER_PARTIAL_FILTER,
    )
