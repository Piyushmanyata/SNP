"""Lock resolution through its interface: a pure classifier, the candidate search and the one overwrite writer."""

import pytest
from bson import ObjectId
from fastapi import HTTPException

import lock_resolution
from lock_resolution import classify
from seed import patient_doc, run_camp, seed_camp

PERSON = {"_id": ObjectId()}
CARD = {"full_name": "Sunita Devi", "age": 51, "gender": "F", "dob": "1975-06-14", "aadhaar_last4": "1234", "address": "Sikar"}
MANUAL = {"_id": ObjectId(), "manual_entry": True, "full_name": "Sunita Devi", "age": 51, "gender": "F"}


def _scanned(**fields):
    return {"_id": ObjectId(), "aadhaar_scanned": True, "person_id": ObjectId(), **fields}


def test_the_card_holders_own_scanned_registration_is_own():
    own = _scanned(person_id=PERSON["_id"])
    outcome = classify(CARD, [_scanned(), own], PERSON)
    assert (outcome.kind, outcome.registration) == ("own", own)


def test_a_scanned_registration_of_another_person_goes_to_review_even_with_no_diff():
    other = _scanned(full_name="Sunita Devi")
    outcome = classify(CARD, [other], PERSON)
    assert (outcome.kind, outcome.registration, outcome.diff) == ("scanned_elsewhere", other, [])


def test_two_manual_entries_are_ambiguous():
    second = {**MANUAL, "_id": ObjectId()}
    outcome = classify(CARD, [MANUAL, second], None)
    assert (outcome.kind, outcome.registrations) == ("ambiguous", [MANUAL, second])


@pytest.mark.parametrize("stored", [
    {"full_name": "sunita  devi"},
    {"full_name": "Devi Sunita"},
    {"age": 52},
    {"age": 50},
    {"gender": "female"},
    {"dob": " 1975-06-14 "},
    {"aadhaar_last4": "1234"},
    {"address": "Somewhere else entirely"},
    {"dob": ""},
    {"aadhaar_last4": None},
])
def test_one_manual_entry_with_only_trivial_differences_is_overwritten(stored):
    manual = {**MANUAL, **stored}
    outcome = classify(CARD, [manual], None)
    assert (outcome.kind, outcome.registration, outcome.diff) == ("overwrite", manual, [])


@pytest.mark.parametrize("stored,field", [
    ({"full_name": "Sunita Kumari"}, "full_name"),
    ({"age": 53}, "age"),
    ({"gender": "M"}, "gender"),
    ({"dob": "1975-06-15"}, "dob"),
    ({"aadhaar_last4": "9999"}, "aadhaar_last4"),
])
def test_one_manual_entry_with_a_material_difference_goes_to_review(stored, field):
    outcome = classify(CARD, [{**MANUAL, **stored}], None)
    assert outcome.kind == "review"
    assert [d["field"] for d in outcome.diff] == [field]


def test_no_candidates_is_none():
    assert classify(CARD, [], PERSON).kind == "none"


def test_any_candidate_of_a_typed_entry_is_a_duplicate():
    assert classify(CARD, [MANUAL], None, scanned=False).kind == "duplicate"
    assert classify(CARD, [], None, scanned=False).kind == "none"


def test_namesakes_born_apart_are_not_candidates(monkeypatch):
    async def run(db):
        camp_id, _ = await seed_camp(db)
        await db.patients.insert_many([
            patient_doc(camp_id=camp_id, aadhaar_scanned=True, person_id=ObjectId(), full_name="Sunita Devi",
                        full_name_normalized="sunita devi", aadhaar_last4="1234", dob="1990-02-02"),
            patient_doc(camp_id=camp_id, aadhaar_scanned=True, person_id=ObjectId(), full_name="Sunita Devi",
                        full_name_normalized="sunita devi", aadhaar_last4="1234", dob="1975-01-01"),
        ])
        scanned = await lock_resolution.find_candidates(db, camp_id, CARD, None, scanned=True)
        typed = await lock_resolution.find_candidates(db, camp_id, CARD, None, scanned=False)
        assert [c["dob"] for c in scanned] == ["1975-01-01"]
        assert len(typed) == 2

    run_camp(monkeypatch, run)


async def _manual(db, **fields):
    camp_id, _ = await seed_camp(db)
    patient = patient_doc(camp_id=camp_id, manual_entry=True, aadhaar_scanned=False, person_id=None,
                          printed_at=None, full_name="Sunita", **fields)
    await db.patients.insert_one(patient)
    return patient


def test_the_overwrite_writes_the_card_the_person_and_extra_fields(monkeypatch):
    async def run(db):
        patient = await _manual(db)
        person, _ = await lock_resolution.resolve_person(db, CARD)
        updated = await lock_resolution.overwrite(db, patient, CARD, person, {"registration_request_id": "req-1"})
        assert {key: updated[key] for key in CARD} == CARD
        assert (updated["full_name_normalized"], updated["person_id"], updated["aadhaar_scanned"]) == (
            "sunita devi", person["_id"], True)
        assert (updated["manual_entry"], updated["manual_exception"], updated["identity_recheck_required"]) == (
            False, None, False)
        assert updated["registration_request_id"] == "req-1"

    run_camp(monkeypatch, run)


@pytest.mark.parametrize("state,code", [
    ({"printed_at": "2026-10-05"}, "ALREADY_PRINTED"),
    ({"queue_status": "seen"}, "ALREADY_PRINTED"),
    ({"aadhaar_scanned": True}, "NOT_A_MANUAL_ENTRY"),
])
def test_the_overwrite_is_refused_after_print_seen_or_a_scan(monkeypatch, state, code):
    async def run(db):
        patient = await _manual(db)
        await db.patients.update_one({"_id": patient["_id"]}, {"$set": state})
        with pytest.raises(HTTPException) as exc:
            await lock_resolution.overwrite(db, patient, CARD, None)
        assert exc.value.detail["code"] == code

    run_camp(monkeypatch, run)


def test_an_overwrite_that_would_collide_with_another_registration_is_a_duplicate(monkeypatch):
    async def run(db):
        patient = await _manual(db)
        person, _ = await lock_resolution.resolve_person(db, CARD)
        holder = patient_doc(camp_id=patient["camp_id"], person_id=person["_id"], aadhaar_scanned=True)
        await db.patients.insert_one(holder)
        with pytest.raises(HTTPException) as exc:
            await lock_resolution.overwrite(db, patient, CARD, person)
        assert exc.value.detail["code"] == "DUPLICATE_IN_CAMP"
        assert exc.value.detail["registration"]["id"] == str(holder["_id"])

    run_camp(monkeypatch, run)


def test_finding_a_person_never_creates_one(monkeypatch):
    async def run(db):
        assert await lock_resolution.find_person(db, CARD) is None
        assert await db.persons.count_documents({}) == 0
        person, created = await lock_resolution.resolve_person(db, CARD)
        assert created is True
        assert (await lock_resolution.find_person(db, CARD))["_id"] == person["_id"]
        assert (await lock_resolution.resolve_person(db, CARD))[1] is False

    run_camp(monkeypatch, run)
