import os
from typing import Any, Mapping
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
PERSON_CAMP_INDEX: dict[str, Any] = {
    "keys": [("person_id", ASCENDING), ("camp_id", ASCENDING)],
    "unique": True,
    "partialFilterExpression": {"person_id": {"$type": "objectId"}},
}
TRANSCRIPTION_PATIENT_INDEX: dict[str, Any] = {"keys": "patient_id", "unique": True}

LEDGER_INDEX_NAME = "patient_id_1_message_type_1_event_date_1"
LEDGER_PARTIAL_FILTER = {"patient_id": {"$exists": True}}
HOUSEHOLD_LEDGER_INDEX_NAME = "number_1_reminder_type_1_event_date_1_send_date_1"
SETUP_REQUEST_INDEX_NAME = "setup_request_id_1"
SETUP_REQUEST_PARTIAL = {"setup_request_id": {"$type": "string"}}


def should_drop_person_camp_index(index_info: Mapping[str, Any]) -> bool:
    old = index_info.get(PERSON_CAMP_INDEX_NAME)
    return bool(old and not old.get("unique"))


def should_drop_ledger_index(index_info: Mapping[str, Any]) -> bool:
    old = index_info.get(LEDGER_INDEX_NAME)
    return bool(old and old.get("partialFilterExpression") != LEDGER_PARTIAL_FILTER)


def should_drop_household_ledger_index(index_info: Mapping[str, Any]) -> bool:
    return HOUSEHOLD_LEDGER_INDEX_NAME in index_info


def should_drop_setup_request_index(index_info: Mapping[str, Any]) -> bool:
    old = index_info.get(SETUP_REQUEST_INDEX_NAME)
    return bool(old and old.get("partialFilterExpression") != SETUP_REQUEST_PARTIAL)


async def init_indexes() -> None:
    db = get_db()
    user_indexes = await db.users.index_information()
    if "email_1" in user_indexes:
        await db.users.drop_index("email_1")

    from helpers import normalize_name
    from security import hash_pin
    seen_norms = set()
    existing_docs = await db.users.find({}, {"name_normalized": 1}).to_list(10000)
    for d in existing_docs:
        if d.get("name_normalized"):
            seen_norms.add(d["name_normalized"])

    cursor = db.users.find({"$or": [{"name_normalized": None}, {"name_normalized": {"$exists": False}}]})
    async for u in cursor:
        raw_name = u.get("name") or (u.get("email", "").split("@")[0] if u.get("email") else "user")
        if u.get("role") == "admin" and "admin" not in seen_norms:
            raw_name = "admin"
        base_norm = normalize_name(raw_name)
        norm = base_norm
        counter = 1
        while norm in seen_norms:
            norm = f"{base_norm}_{str(u['_id'])[-4:]}"
            if norm in seen_norms:
                norm = f"{base_norm}_{counter}"
                counter += 1
        seen_norms.add(norm)
        updates: dict[str, Any] = {"name_normalized": norm}
        if u.get("role") == "admin" and norm == "admin":
            updates["name"] = "admin"
        if not u.get("pin_hash"):
            if u.get("role") == "admin":
                pin = os.environ.get("ADMIN_BOOTSTRAP_PIN") or ""
                if pin.isdigit() and len(pin) == 4 and pin != "1234":
                    updates["pin_hash"] = hash_pin(pin)
                    updates["must_change_pin"] = True
            else:
                updates["pin_hash"] = hash_pin("1234")
                updates["must_change_pin"] = True
        await db.users.update_one({"_id": u["_id"]}, {"$set": updates})

    await db.users.create_index("name_normalized", unique=True)
    attempt_indexes = await db.login_attempts.index_information()
    if "identifier_1" in attempt_indexes and not attempt_indexes["identifier_1"].get("unique"):
        await db.login_attempts.drop_index("identifier_1")
    await db.login_attempts.create_index("identifier", unique=True)
    await db.login_attempts.create_index("locked_until", expireAfterSeconds=900)
    await db.camps.create_index(
        "is_active", unique=True, partialFilterExpression={"is_active": True}
    )
    camp_indexes = await db.camps.index_information()
    if should_drop_setup_request_index(camp_indexes):
        await db.camps.drop_index(SETUP_REQUEST_INDEX_NAME)
    await db.camps.create_index(
        "setup_request_id",
        unique=True,
        partialFilterExpression=SETUP_REQUEST_PARTIAL,
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
    await db.patients.create_index([("camp_id", ASCENDING), ("arrived_at", ASCENDING)])
    await db.patients.create_index([("camp_id", ASCENDING), ("seen_at", ASCENDING)])
    await db.patients.create_index([("camp_id", ASCENDING), ("aadhaar_last4", ASCENDING)])
    await db.patients.create_index([("camp_id", ASCENDING), ("phone_normalized", ASCENDING)])
    await db.patients.create_index([("camp_id", ASCENDING), ("queue_status", ASCENDING)])
    await db.reminder_ledger.create_index([("status", ASCENDING), ("created_at", ASCENDING)])
    await db.reminder_ledger.create_index("provider_id", sparse=True)
    await db.reminder_ledger.create_index("created_at")
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
    await db.medicines.create_index("name_key", unique=True)
    await db.fixed_powers.create_index("value", unique=True)
    await db.prescription_revisions.create_index("operation_id", unique=True)
    await db.prescription_revisions.create_index([("patient_id", ASCENDING), ("created_at", ASCENDING)])
    await db.clinical_operations.create_index("operation_id", unique=True)
    await db.patients.create_index([("camp_id", ASCENDING), ("created_by", ASCENDING)])
    await db.patients.create_index([("camp_id", ASCENDING), ("registrar_team_lead_id", ASCENDING)])
    await db.transcriptions.create_index([("person_id", ASCENDING), ("created_at", -1)])
    await db.deferred_slips.create_index([("transcription_id", ASCENDING), ("active", ASCENDING)])
    await db.deferred_slips.create_index([("item_type", ASCENDING), ("active", ASCENDING), ("collection_date", ASCENDING)])
    await db.corrections.create_index([("transcription_id", ASCENDING), ("created_at", ASCENDING)])
    await db.camp_days.create_index("day_date")
    await db.fulfilments.create_index(
        [("transcription_id", ASCENDING), ("item_type", ASCENDING)],
        unique=True,
    )
    await db.ot_schedule_days.create_index(
        [("camp_id", ASCENDING), ("day_date", ASCENDING)], unique=True
    )
    await db.specs_collection_days.create_index(
        [("camp_id", ASCENDING), ("day_date", ASCENDING)], unique=True
    )
    ledger_indexes = await db.reminder_ledger.index_information()
    if should_drop_household_ledger_index(ledger_indexes):
        await db.reminder_ledger.drop_index(HOUSEHOLD_LEDGER_INDEX_NAME)
    if should_drop_ledger_index(ledger_indexes):
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
