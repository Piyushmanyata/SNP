"""Tokens through their verbs: seats, Token versions, Schedule edits and the Patients to phone list."""

from datetime import timedelta

import pytest
from bson import ObjectId
from fastapi import HTTPException

import sms
import tokens
from conftest import advance_clock
from db import in_transaction
import helpers
from seed import day, patient_doc, recorder, run_camp, seed_camp


async def _camp(db, seat_limit=2, days=(1, 2)):
    camp_id, _ = await seed_camp(db, venue="Hall A")
    ot_days = []
    for offset in days:
        ot_days.append((await db.ot_schedule_days.insert_one({
            "camp_id": camp_id, "day_date": day(offset), "venue": f"OT {offset}", "seat_limit": seat_limit, "seats_taken": 0,
        })).inserted_id)
    return camp_id, ot_days


async def _patient(db, camp_id):
    patient = patient_doc(camp_id=camp_id, phone="9876500001", phone_normalized="9876500001")
    await db.patients.insert_one(patient)
    transcription = {"_id": ObjectId(), "patient_id": patient["_id"]}
    await db.transcriptions.insert_one(transcription)
    return patient, transcription


async def _defer(db, patient, transcription, day_id, prior=None, line="ot"):
    return await in_transaction(lambda session: tokens.defer(db, line, patient, transcription, prior, str(day_id), session))


async def _close(db, transcription, prior):
    await in_transaction(lambda session: tokens.close(db, "ot", transcription["_id"], prior, session))


async def _seats(db, day_id):
    return (await db.ot_schedule_days.find_one({"_id": day_id}))["seats_taken"]


def _deferred(day_id):
    return {"status": "deferred", "ot_schedule_day_id": day_id}


def test_a_deferral_takes_a_seat_and_reissuing_to_the_same_day_takes_none(monkeypatch):
    async def run(db):
        camp_id, (first, _second) = await _camp(db)
        patient, transcription = await _patient(db, camp_id)
        token, _ids = await _defer(db, patient, transcription, first)
        assert (token["version"], token["active"], await _seats(db, first)) == (1, True, 1)
        again, _ids = await _defer(db, patient, transcription, first, _deferred(first))
        assert (again["version"], await _seats(db, first)) == (2, 1)
        assert await db.deferred_slips.count_documents({"active": True}) == 1

    run_camp(monkeypatch, run)


def test_moving_to_another_day_releases_the_old_seat_and_takes_the_new_one(monkeypatch):
    async def run(db):
        camp_id, (first, second) = await _camp(db)
        patient, transcription = await _patient(db, camp_id)
        await _defer(db, patient, transcription, first)
        await _defer(db, patient, transcription, second, _deferred(first))
        assert (await _seats(db, first), await _seats(db, second)) == (0, 1)

    run_camp(monkeypatch, run)


def test_surgery_declined_releases_the_seat_and_closes_the_token(monkeypatch):
    async def run(db):
        camp_id, (first, _second) = await _camp(db)
        patient, transcription = await _patient(db, camp_id)
        await _defer(db, patient, transcription, first)
        await _close(db, transcription, _deferred(first))
        assert await _seats(db, first) == 0
        assert await db.deferred_slips.count_documents({"active": True}) == 0
        await _close(db, transcription, _deferred(first))
        assert await _seats(db, first) == 0

    run_camp(monkeypatch, run)


@pytest.mark.parametrize("later_free,code", [(True, "DAY_FULL"), (False, "NO_CLINICAL_DAY_AVAILABLE")])
def test_a_full_day_is_refused(monkeypatch, later_free, code):
    async def run(db):
        camp_id, (first, second) = await _camp(db, seat_limit=1)
        if not later_free:
            await db.ot_schedule_days.update_one({"_id": second}, {"$set": {"seats_taken": 1}})
        taken, _ = await _patient(db, camp_id)
        await _defer(db, taken, {"_id": ObjectId(), "patient_id": taken["_id"]}, first)
        patient, transcription = await _patient(db, camp_id)
        with pytest.raises(HTTPException) as exc:
            await _defer(db, patient, transcription, first)
        assert exc.value.detail["code"] == code
        assert await _seats(db, first) == 1

    run_camp(monkeypatch, run)


def test_spectacles_to_be_made_takes_no_seat_and_a_new_version_closes_the_previous(monkeypatch):
    async def run(db):
        camp_id, _ = await _camp(db, days=())
        specs_day = (await db.specs_collection_days.insert_one({
            "camp_id": camp_id, "day_date": day(3), "end_date": day(5), "venue": "Optician",
        })).inserted_id
        patient, transcription = await _patient(db, camp_id)
        first, _ = await _defer(db, patient, transcription, specs_day, line="specs_made")
        second, _ = await _defer(db, patient, transcription, specs_day, line="specs_made")
        assert (first["collection_end_date"], first["ot_schedule_day_id"], second["version"]) == (day(5), None, 2)
        assert [t["version"] for t in await db.deferred_slips.find({"active": True}).to_list(None)] == [2]
        assert (await db.specs_collection_days.find_one({"_id": specs_day}))["booking_seq"] == 2

    run_camp(monkeypatch, run)


def test_a_deferral_records_its_token_sms_and_the_intent_goes_after_commit(monkeypatch):
    sent = recorder()

    async def run(db):
        camp_id, (first, _second) = await _camp(db)
        patient, transcription = await _patient(db, camp_id)
        token, ids = await _defer(db, patient, transcription, first)
        row = await db.reminder_ledger.find_one({"_id": ids[0]})
        assert (row["message_type"], row["event_key"], row["status"]) == ("ot_token", str(token["_id"]), "queued")
        assert sent == []

    run_camp(monkeypatch, run)


async def _deferred_on(db, camp_id, day_id):
    patient, transcription = await _patient(db, camp_id)
    token, _ = await _defer(db, patient, transcription, day_id)
    await db.fulfilments.insert_one({
        "transcription_id": transcription["_id"], "item_type": "ot", "status": "deferred", "slip_id": token["_id"],
    })
    return patient, token


class NeverRun:
    def add_task(self, *_args):
        pass


def _ot_changes(day_doc, **changes):
    return {"day_date": day_doc["day_date"], "seat_limit": day_doc["seat_limit"], "venue": day_doc["venue"],
            "venue_sms": day_doc.get("venue_sms"), **changes}


def test_a_venue_change_replaces_every_active_token_and_queues_one_notice_each(monkeypatch):
    recorder()

    async def run(db):
        camp_id, (first, _second) = await _camp(db)
        await _deferred_on(db, camp_id, first)
        await _deferred_on(db, camp_id, first)
        loaded = await db.ot_schedule_days.find_one({"_id": first})
        await tokens.edit_day(db, "ot", loaded, _ot_changes(loaded, venue="New Hospital"), None)
        active = await db.deferred_slips.find({"active": True}).to_list(None)
        assert [t["collection_venue"] for t in active] == ["New Hospital"] * 2
        assert all(t.get("replaces") and t.get("edit_revision") for t in active)
        fulfilments = await db.fulfilments.find({}).to_list(None)
        assert {f["slip_id"] for f in fulfilments} == {t["_id"] for t in active}
        assert await db.reminder_ledger.count_documents({"message_type": "ot_change"}) == 2

    run_camp(monkeypatch, run)


def test_a_seat_limit_or_sms_name_change_replaces_nothing_but_follows_the_sms_venue(monkeypatch):
    async def run(db):
        camp_id, (first, _second) = await _camp(db)
        _patient_doc, token = await _deferred_on(db, camp_id, first)
        loaded = await db.ot_schedule_days.find_one({"_id": first})
        await tokens.edit_day(db, "ot", loaded, _ot_changes(loaded, seat_limit=5, venue_sms="Hosp"), None)
        [active] = await db.deferred_slips.find({"active": True}).to_list(None)
        assert (active["_id"], active["collection_venue_sms"]) == (token["_id"], "Hosp")
        assert await db.reminder_ledger.count_documents({"message_type": "ot_change"}) == 0

    run_camp(monkeypatch, run)


def test_a_seat_limit_below_the_seats_taken_is_refused(monkeypatch):
    async def run(db):
        camp_id, (first, _second) = await _camp(db)
        await _deferred_on(db, camp_id, first)
        await _deferred_on(db, camp_id, first)
        loaded = await db.ot_schedule_days.find_one({"_id": first})
        with pytest.raises(HTTPException) as exc:
            await tokens.edit_day(db, "ot", loaded, _ot_changes(loaded, seat_limit=1), None)
        assert exc.value.detail["code"] == "SEAT_LIMIT_BELOW_ASSIGNED"

    run_camp(monkeypatch, run)


def test_patients_to_phone_lists_unsent_and_stuck_notices_until_contacted(monkeypatch):
    async def run(db):
        camp_id, (first, _second) = await _camp(db)
        patient, _token = await _deferred_on(db, camp_id, first)
        loaded = await db.ot_schedule_days.find_one({"_id": first})
        await tokens.edit_day(db, "ot", loaded, _ot_changes(loaded, venue="New Hospital"), None)
        [notice] = await tokens.patients_to_phone(db, helpers.now_utc())
        assert (notice["reg_no"], notice["sms_status"]) == (patient["reg_no"], "not_sent")
        await tokens.mark_contacted(db, ObjectId(notice["slip_id"]), "admin", helpers.now_utc())
        assert await tokens.patients_to_phone(db, helpers.now_utc()) == []

    run_camp(monkeypatch, run)


def test_a_queued_notice_is_listed_only_once_it_is_stuck(monkeypatch):
    recorder()

    async def run(db):
        camp_id, (first, _second) = await _camp(db)
        await _deferred_on(db, camp_id, first)
        loaded = await db.ot_schedule_days.find_one({"_id": first})
        await tokens.edit_day(db, "ot", loaded, _ot_changes(loaded, venue="New Hospital"), NeverRun())
        assert await tokens.patients_to_phone(db, helpers.now_utc()) == []
        advance_clock(timedelta(minutes=11))
        [notice] = await tokens.patients_to_phone(db, helpers.now_utc())
        assert notice["sms_status"] == "not_sent"

    run_camp(monkeypatch, run)


SMS_VENUE_EDITS = {
    "ot": (
        {"seat_limit": 5},
        {"venue_sms": "Hosp A"},
        {"venue_sms": None},
        {"day_date": day(4)},
        {"venue": "New Hospital, Near The Old Bus Stand", "venue_sms": "New Hospital"},
        {"venue": "Third Hospital, Near The Old Bus Stand"},
    ),
    "specs": (
        {"venue_sms": "Optic A"},
        {"venue_sms": None},
        {"day_date": day(4)},
        {"end_date": day(9)},
        {"venue": "New Optician, Near The Old Bus Stand", "venue_sms": "New Optician"},
        {"venue": "Third Optician, Near The Old Bus Stand"},
    ),
}


def _edit_fields(kind, day_doc, **changes):
    fields = ("day_date", "seat_limit", "venue", "venue_sms") if kind == "ot" else ("day_date", "end_date", "venue", "venue_sms")
    return {**{key: day_doc.get(key) for key in fields}, **changes}


@pytest.mark.parametrize("kind", ["ot", "specs"])
def test_every_edit_path_leaves_each_active_token_reading_its_days_sms_venue(monkeypatch, kind):
    recorder()

    async def run(db):
        camp_id, (first, _second) = await _camp(db)
        if kind == "ot":
            day_id, collection, line = first, db.ot_schedule_days, "ot"
        else:
            day_id = (await db.specs_collection_days.insert_one({
                "camp_id": camp_id, "day_date": day(3), "end_date": day(5), "venue": "Optician Hall, Near The Old Bus Stand",
            })).inserted_id
            collection, line = db.specs_collection_days, "specs_made"
        await collection.update_one({"_id": day_id}, {"$set": {"venue_sms": "Start Short"}})

        async def assert_tokens_read_their_day(count):
            day_doc = await collection.find_one({"_id": day_id})
            active = await db.deferred_slips.find({"active": True}).to_list(None)
            assert len(active) == count
            for token in active:
                assert sms.sms_venue(token) == sms.sms_venue(day_doc)
                assert token.get("collection_venue_sms") == day_doc.get("venue_sms")

        for _ in range(2):
            patient, transcription = await _patient(db, camp_id)
            await _defer(db, patient, transcription, day_id, line=line)
        await assert_tokens_read_their_day(2)
        for step in SMS_VENUE_EDITS[kind]:
            loaded = await collection.find_one({"_id": day_id})
            await tokens.edit_day(db, kind, loaded, _edit_fields(kind, loaded, **step), None)
            await assert_tokens_read_their_day(2)
        patient, transcription = await _patient(db, camp_id)
        await _defer(db, patient, transcription, day_id, line=line)
        await assert_tokens_read_their_day(3)

    run_camp(monkeypatch, run)
