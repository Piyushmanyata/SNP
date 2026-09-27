"""Tokens: OT seats, Token versions, Schedule edits and the Patients to phone list."""

from typing import Any, Dict, List, Optional, Tuple

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException
from pymongo import UpdateOne
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

import sms
from clinical_state import conflict
from db import in_transaction
from helpers import api_error, ist_local_instant, now_ist, now_utc

NOTICE_FIELDS = {"phone": 1, "phone_normalized": 1, "reg_no": 1, "created_by": 1, "camp_id": 1, "full_name": 1}
SENT_OR_SENDING = {"queued", "pending", "sent", "uncertain"}
OT_INSTRUCTIONS = "पर्चा, यह टोकन, आधार कार्ड, राशन कार्ड और मोबाइल फ़ोन साथ लाएँ। सहायता: 9835317006"
SPECS_INSTRUCTIONS = "Collect spectacles on the scheduled date."
DAY_KINDS = {
    "ot": ("ot_schedule_days", "ot_schedule_day_id", "ot_change"),
    "specs": ("specs_collection_days", "specs_collection_day_id", "specs_change"),
}


def oid_or_400(raw: Any) -> ObjectId:
    try:
        return ObjectId(raw)
    except (InvalidId, TypeError, ValueError):
        raise api_error(400, "INVALID_SCHEDULE_DAY", 'Invalid schedule day')


def day_exists() -> HTTPException:
    return conflict("DAY_EXISTS", "A day already uses that date. Use Edit on that day.")


def specs_window_open(day: dict) -> bool:
    return ist_local_instant(day.get("end_date") or day["day_date"], sms.SPECS_PICKUP_END_TIME) > now_ist()


def _deferred_to(prior: Optional[dict], field: str) -> Optional[ObjectId]:
    return prior.get(field) if prior and prior.get("status") == "deferred" else None


async def _release_seat(db: AsyncDatabase, day_id: ObjectId, session) -> None:
    await db.ot_schedule_days.update_one(
        {"_id": day_id, "seats_taken": {"$gt": 0}}, {"$inc": {"seats_taken": -1}}, session=session,
    )


async def _book_ot_day(db: AsyncDatabase, patient: dict, raw_day_id: Optional[str], prior: Optional[dict], session) -> dict:
    """One seat per active IOL surgery Token: re-issuing to the same day takes none, a move releases the old one."""
    if not raw_day_id:
        raise api_error(400, "DAY_REQUIRED", "OT deferral needs a scheduled day")
    day_id = oid_or_400(raw_day_id)
    target = await db.ot_schedule_days.find_one({"_id": day_id}, session=session)
    if not target:
        raise api_error(404, "DAY_NOT_FOUND", "That day is not on this camp.")
    if target.get("day_date", "") < now_ist().date().isoformat():
        raise api_error(400, "SURGERY_DATE_HAS_PASSED_CHOOSE_TODAY_OR_A_LATER_DAY", 'Surgery date has passed; choose today or a later day')
    if target.get("camp_id") != patient.get("camp_id"):
        raise api_error(400, "SCHEDULE_DAY_BELONGS_TO_ANOTHER_CAMP", 'Schedule day belongs to another camp')
    previous = _deferred_to(prior, "ot_schedule_day_id")
    if previous == day_id:
        return target
    day = await db.ot_schedule_days.find_one_and_update(
        {"_id": day_id, "$expr": {"$lt": ["$seats_taken", "$seat_limit"]}},
        {"$inc": {"seats_taken": 1}}, return_document=True, session=session,
    )
    if not day:
        free = await db.ot_schedule_days.count_documents({
            "camp_id": target.get("camp_id"),
            "day_date": {"$gte": now_ist().date().isoformat()},
            "$expr": {"$lt": ["$seats_taken", "$seat_limit"]},
        }, session=session)
        if free == 0:
            raise api_error(409, "NO_CLINICAL_DAY_AVAILABLE", "Every OT Schedule Day is full. Call the admin to add an OT Schedule Day.")
        raise api_error(409, "DAY_FULL", "OT day is full or not found")
    if previous:
        await _release_seat(db, previous, session)
    return day


async def _book_specs_day(db: AsyncDatabase, patient: dict, raw_day_id: Optional[str], session) -> dict:
    """Spectacles to be made takes no seat; each booking moves the day's booking sequence on."""
    if not raw_day_id:
        raise api_error(400, "DAY_REQUIRED", "Spectacles to be made deferral needs a Specs collection day")
    day = await db.specs_collection_days.find_one_and_update(
        {"_id": oid_or_400(raw_day_id)}, {"$inc": {"booking_seq": 1}}, return_document=True, session=session,
    )
    if not day:
        raise api_error(404, "DAY_NOT_FOUND", "That day is not on this camp.")
    if day.get("camp_id") != patient.get("camp_id"):
        raise api_error(400, "SPECS_COLLECTION_DAY_BELONGS_TO_ANOTHER_CAMP", 'Specs collection day belongs to another camp')
    if not specs_window_open(day):
        raise api_error(400, "SPECS_COLLECTION_WINDOW_IS_NOT_SELECTABLE", 'Specs collection window is not selectable')
    return day


async def _issue(db: AsyncDatabase, transcription: dict, line: str, day: dict, session) -> dict:
    """The next Token version for the line; older active versions close."""
    specs = line == "specs_made"
    count = await db.deferred_slips.count_documents(
        {"transcription_id": transcription["_id"], "item_type": line}, session=session,
    )
    token = {
        "transcription_id": transcription["_id"],
        "patient_id": transcription["patient_id"],
        "item_type": line,
        "version": count + 1,
        "active": True,
        "cancelled": False,
        "collection_date": day["day_date"],
        "collection_venue": day["venue"],
        "collection_venue_sms": day.get("venue_sms"),
        "collection_end_date": (day.get("end_date") or day["day_date"]) if specs else None,
        "ot_schedule_day_id": None if specs else day["_id"],
        "specs_collection_day_id": day["_id"] if specs else None,
        "instructions": SPECS_INSTRUCTIONS if specs else OT_INSTRUCTIONS,
        "created_at": now_utc(),
    }
    token["_id"] = (await db.deferred_slips.insert_one(token, session=session)).inserted_id
    await db.deferred_slips.update_many(
        {"transcription_id": transcription["_id"], "item_type": line, "active": True, "version": {"$lt": token["version"]}},
        {"$set": {"active": False, "cancelled": True, "cancelled_at": now_utc()}},
        session=session,
    )
    return token


async def defer(
    db: AsyncDatabase, line: str, patient: dict, transcription: dict, prior: Optional[dict],
    raw_day_id: Optional[str], session,
) -> Tuple[dict, List[ObjectId]]:
    """Defers an IOL surgery or Spectacles to be made line to a day: a new Token and its Token SMS intent."""
    if line == "ot":
        day = await _book_ot_day(db, patient, raw_day_id, prior, session)
        message_type = "ot_token"
    else:
        day = await _book_specs_day(db, patient, raw_day_id, session)
        message_type = "specs_token"
    token = await _issue(db, transcription, line, day, session)
    intent_ids = await sms.record(
        db, [patient], message_type, token["collection_date"],
        token.get("collection_venue_sms") or token["collection_venue"], token.get("collection_end_date"),
        event_key=sms.token_key(token), session=session, now=now_utc(),
    )
    return token, intent_ids


async def close(db: AsyncDatabase, line: str, transcription_id: ObjectId, prior: Optional[dict], session) -> None:
    """A non-deferred outcome closes the line's active Tokens and gives back its OT seat."""
    await db.deferred_slips.update_many(
        {"transcription_id": transcription_id, "item_type": line, "active": True},
        {"$set": {"active": False, "cancelled": True, "cancelled_at": now_utc()}},
        session=session,
    )
    previous = _deferred_to(prior, "ot_schedule_day_id")
    if line == "ot" and previous:
        await _release_seat(db, previous, session)


async def _replace_tokens(db: AsyncDatabase, day_field: str, day: dict, message_type: str, session) -> List[ObjectId]:
    """A date or venue change replaces every active Token on the day and records one notice per patient."""
    old_tokens = await db.deferred_slips.find({day_field: day["_id"], "active": True}, session=session).to_list(None)
    if not old_tokens:
        return []
    revision, end_date = day["edit_revision"], day.get("end_date")
    fields = {"collection_date": day["day_date"], "collection_venue": day["venue"],
              "collection_venue_sms": day.get("venue_sms"), "collection_end_date": end_date}
    replacements = [{
        **{key: value for key, value in old.items() if key not in ("_id", "contacted_at", "contacted_by")},
        **fields, "_id": ObjectId(), "version": old.get("version", 1) + 1, "replaces": old["_id"],
        "edit_revision": revision, "created_at": now_utc(),
    } for old in old_tokens]
    await db.deferred_slips.insert_many(replacements, session=session)
    await db.deferred_slips.bulk_write([UpdateOne(
        {"_id": new["replaces"]},
        {"$set": {"active": False, "superseded_by": new["_id"], "superseded_at": now_utc()}},
    ) for new in replacements], session=session)
    await db.fulfilments.bulk_write([UpdateOne(
        {"transcription_id": new["transcription_id"], "item_type": new["item_type"], "status": "deferred"},
        {"$set": {"slip_id": new["_id"], "collection_date": day["day_date"], "collection_venue": day["venue"]}},
    ) for new in replacements], session=session)
    patients = await db.patients.find(
        {"_id": {"$in": [token["patient_id"] for token in old_tokens]}}, NOTICE_FIELDS, session=session,
    ).to_list(None)
    return await sms.record(
        db, patients, message_type, day["day_date"], day.get("venue_sms") or day["venue"], end_date,
        event_key=sms.edit_key(revision), session=session, now=now_utc(),
    )


async def edit_day(db: AsyncDatabase, kind: str, day: dict, changes: dict, background_tasks: Any) -> dict:
    """The Schedule edit of an OT Schedule Day or Specs collection day, against the day the admin loaded."""
    collection_name, day_field, message_type = DAY_KINDS[kind]
    collection = db[collection_name]
    extra_filter: Dict[str, Any] = {}
    if kind == "ot":
        if changes["seat_limit"] < day.get("seats_taken", 0):
            raise api_error(409, "SEAT_LIMIT_BELOW_ASSIGNED", f"Cannot set below {day.get('seats_taken', 0)} already-assigned seats")
        extra_filter = {"seats_taken": {"$lte": changes["seat_limit"]}}
    else:
        day = {**day, "end_date": day.get("end_date") or day["day_date"]}
    material = any(changes[key] != day.get(key) for key in ("day_date", "venue", "end_date") if key in changes)
    if material:
        changes = {**changes, "edit_revision": str(ObjectId())}

    async def write(session):
        changed = await collection.find_one_and_update(
            {"_id": day["_id"], "day_date": day["day_date"], "venue": day["venue"], **extra_filter},
            {"$set": changes}, return_document=True, session=session,
        )
        if not changed:
            raise api_error(409, "THE_DAY_CHANGED_RELOAD_AND_TRY_AGAIN", 'The day changed; reload and try again')
        if material:
            return changed, await _replace_tokens(db, day_field, changed, message_type, session)
        await db.deferred_slips.update_many(
            {day_field: day["_id"], "active": True}, {"$set": {"collection_venue_sms": changed.get("venue_sms")}},
            session=session,
        )
        return changed, []

    try:
        changed, intent_ids = await in_transaction(write)
    except DuplicateKeyError:
        raise day_exists()
    await sms.dispatch(background_tasks, db, intent_ids, now_utc())
    return changed


async def patients_to_phone(db: AsyncDatabase, now: Any) -> List[Dict[str, Any]]:
    """Patients of the active camp whose replaced Token has no SMS on its way and who were not phoned yet."""
    camp = await db.camps.find_one({"is_active": True})
    if not camp:
        return []
    tokens = await db.deferred_slips.find(
        {"active": True, "edit_revision": {"$exists": True}, "contacted_at": None},
    ).to_list(None)
    patients = {p["_id"]: p for p in await db.patients.find(
        {"_id": {"$in": [token["patient_id"] for token in tokens]}, "camp_id": camp["_id"]}, NOTICE_FIELDS,
    ).to_list(None)}
    states = await sms.notice_states(db, [
        (token["patient_id"], token["edit_revision"]) for token in tokens if token["patient_id"] in patients
    ], now)
    notices = []
    for token in tokens:
        patient = patients.get(token["patient_id"])
        if not patient:
            continue
        status = states[(token["patient_id"], token["edit_revision"])]
        if status in SENT_OR_SENDING:
            continue
        notices.append({
            "slip_id": str(token["_id"]), "item_type": token["item_type"],
            "reg_no": patient.get("reg_no"), "full_name": patient.get("full_name"),
            "phone": patient.get("phone_normalized") or patient.get("phone"),
            "collection_date": token["collection_date"], "collection_end_date": token.get("collection_end_date"),
            "collection_venue": token["collection_venue"], "sms_status": status,
        })
    notices.sort(key=lambda n: (n["collection_date"], n["reg_no"] or 0))
    return notices


async def mark_contacted(db: AsyncDatabase, token_id: ObjectId, actor_id: str, now: Any) -> None:
    res = await db.deferred_slips.update_one(
        {"_id": token_id, "active": True, "edit_revision": {"$exists": True}},
        {"$set": {"contacted_at": now, "contacted_by": actor_id}},
    )
    if not res.matched_count:
        raise api_error(404, "NOTICE_NOT_FOUND", 'Notice not found')
