"""Lock resolution: which of the camp's registrations a decoded Aadhaar card belongs to, and the one Aadhaar overwrite."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from db import next_seq
from helpers import OVERWRITTEN_FIELDS, api_error, material_diff, normalize_name, normalize_phone, now_utc, person_key
from serializers import ser_patient


@dataclass
class Outcome:
    """own, scanned_elsewhere, ambiguous, overwrite, review, none, or duplicate for a typed (unscanned) entry."""
    kind: str
    registrations: List[dict] = field(default_factory=list)
    diff: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def registration(self) -> dict:
        return self.registrations[0]


def is_manual(patient: dict) -> bool:
    return bool(patient.get("manual_entry") or patient.get("manual_exception"))


def is_scanned(patient: dict) -> bool:
    return bool(patient.get("aadhaar_scanned") or patient.get("person_id"))


CARD_IN_HAND = ("card_unreadable", "scanner_down")


def checked_manual_note(reason: Optional[str], note: Optional[str]) -> Optional[str]:
    if not reason:
        raise api_error(400, "MANUAL_ENTRY_NOT_ALLOWED", 'Scan the Aadhaar card, or choose why it cannot be scanned.')
    if reason != "other":
        return None
    note = (note or "").strip()
    if not note:
        raise api_error(400, "MANUAL_NOTE_REQUIRED", 'Write why the card cannot be scanned.')
    return note


def duplicate_in_camp(row: dict) -> HTTPException:
    return api_error(409, "DUPLICATE_IN_CAMP", 'Already registered in this camp', registration=ser_patient(row))


def _born_apart(a: Optional[str], b: Optional[str]) -> bool:
    if not a or not b or a == b:
        return False
    return a[:4] != b[:4] or not (a.endswith("-01-01") or b.endswith("-01-01"))


def _key(card: dict) -> str:
    return person_key(card["aadhaar_last4"], card["full_name"], card.get("dob") or "", card.get("gender") or "")


async def find_person(db: AsyncDatabase, card: dict) -> Optional[dict]:
    """The Person this card belongs to, if one exists. Looking never creates one."""
    if not (card.get("aadhaar_last4") and card.get("full_name")):
        return None
    return await db.persons.find_one({"aadhaar_key": _key(card)})


async def resolve_person(db: AsyncDatabase, card: dict) -> tuple[Dict[str, Any], bool]:
    """Finds or creates the Person for a card with its last-4 and DOB. Returns (person, created)."""
    key = _key(card)
    person = await db.persons.find_one({"aadhaar_key": key})
    if person:
        return person, False
    doc = {
        "aadhaar_key": key,
        "person_no": await next_seq("person_no"),
        "name_verbatim": card["full_name"],
        "dob": card.get("dob"),
        "gender": card.get("gender"),
        "last4": card["aadhaar_last4"],
        "locked": True,
        "created_at": now_utc(),
    }
    try:
        res = await db.persons.insert_one(doc)
    except DuplicateKeyError:
        person = await db.persons.find_one({"aadhaar_key": key})
        if person:
            return person, False
        raise
    doc["_id"] = res.inserted_id
    return doc, True


async def find_candidates(
    db: AsyncDatabase, camp_id: Any, card: dict, person: Optional[dict], *, scanned: bool, phone: Optional[str] = None,
) -> List[dict]:
    """The camp's registrations that match the card by the Duplicate in camp keys, minus namesakes born apart (ADR 0083)."""
    queries: List[dict] = []
    if person:
        queries.append({"person_id": person["_id"]})
    norm = normalize_name(card.get("full_name") or "")
    phone = normalize_phone(phone)
    if norm and card.get("age") is not None and phone:
        queries.append({"full_name_normalized": norm, "age": card["age"], "phone_normalized": phone})
    candidates: List[dict] = []
    for query in queries:
        candidates += await db.patients.find({"camp_id": camp_id, **query}).to_list(20)
    tokens = sorted(norm.split())
    if card.get("aadhaar_last4") and tokens:
        candidates += [
            d for d in await db.patients.find({"camp_id": camp_id, "aadhaar_last4": card["aadhaar_last4"]}).to_list(50)
            if sorted((d.get("full_name_normalized") or "").split()) == tokens
        ]
    hits = []
    seen = set()
    for d in candidates:
        if d["_id"] in seen:
            continue
        seen.add(d["_id"])
        own = person and d.get("person_id") == person["_id"]
        if scanned and is_scanned(d) and not own and _born_apart(d.get("dob"), card.get("dob")):
            continue
        hits.append(d)
    return hits


def classify(card: dict, candidates: List[dict], person: Optional[dict], *, scanned: bool = True) -> Outcome:
    if not scanned:
        return Outcome("duplicate", candidates) if candidates else Outcome("none")
    scanned_rows = [c for c in candidates if is_scanned(c)]
    own = next((c for c in scanned_rows if person and c.get("person_id") == person["_id"]), None)
    if own:
        return Outcome("own", [own])
    if scanned_rows:
        return Outcome("scanned_elsewhere", scanned_rows, material_diff(card, scanned_rows[0]))
    manual = [c for c in candidates if is_manual(c)]
    if len(manual) > 1:
        return Outcome("ambiguous", manual)
    if len(manual) == 1:
        diff = material_diff(card, manual[0])
        return Outcome("review" if diff else "overwrite", manual, diff)
    return Outcome("none")


async def _refusal(db: AsyncDatabase, patient_id: Any) -> HTTPException:
    current = await db.patients.find_one({"_id": patient_id}) or {}
    if current.get("printed_at") or current.get("queue_status") == "seen":
        return api_error(409, "ALREADY_PRINTED", "This patient's prescription is already printed. Their details cannot change now.")
    return api_error(409, "NOT_A_MANUAL_ENTRY", 'This registration already has Aadhaar on file. Scan again.')


async def overwrite(
    db: AsyncDatabase, patient: dict, card: dict, person: Optional[dict], extra_fields: Optional[Dict[str, Any]] = None,
) -> dict:
    """The Aadhaar overwrite of a Manual entry that has not been printed or seen. Returns the updated registration."""
    try:
        updated = await db.patients.find_one_and_update(
            {"_id": patient["_id"], "aadhaar_scanned": {"$ne": True}, "person_id": None,
             "printed_at": None, "queue_status": {"$ne": "seen"}},
            {"$set": {
                **(extra_fields or {}),
                **{name: card.get(name) for name in OVERWRITTEN_FIELDS},
                "full_name_normalized": normalize_name(card.get("full_name") or ""),
                "aadhaar_scanned": True,
                "person_id": person["_id"] if person else None,
                "manual_entry": False,
                "manual_exception": None,
                "identity_recheck_required": False,
            }},
            return_document=True,
        )
    except DuplicateKeyError:
        if person:
            existing = await db.patients.find_one({"person_id": person["_id"], "camp_id": patient["camp_id"]})
            if existing:
                raise duplicate_in_camp(existing)
        raise
    if not updated:
        raise await _refusal(db, patient["_id"])
    return updated
