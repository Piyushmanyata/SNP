"""Arrival through its interface: stamped once, onto the Operating day, only while the door is open."""

import asyncio

import pytest
from fastapi import HTTPException

import arrival
import helpers
from seed import TODAY, TOMORROW, patient_doc, run_camp, seed_camp

OPEN = {"printing_open": True}


async def _booked(db, days=(TODAY,), **fields):
    camp_id, day_ids = await seed_camp(db, days=days)
    patient = patient_doc(camp_id=camp_id, camp_day_id=day_ids[-1], queue_status="registered", **fields)
    await db.patients.insert_one(patient)
    return patient, day_ids


def test_arrival_is_stamped_once_under_a_race(monkeypatch):
    async def run(db):
        patient, _ = await _booked(db)
        first, second = await asyncio.gather(
            arrival.stamp(db, patient, "door-1", OPEN), arrival.stamp(db, patient, "door-2", OPEN),
        )
        assert first["arrived_by"] == second["arrived_by"]
        assert first["arrived_at"] == second["arrived_at"]
        stored = await db.patients.find_one({"_id": patient["_id"]})
        assert (stored["arrived_by"], stored["queue_status"]) == (first["arrived_by"], "arrived")

    run_camp(monkeypatch, run)


def test_a_second_stamp_changes_nothing(monkeypatch):
    async def run(db):
        patient, _ = await _booked(db)
        first = await arrival.stamp(db, patient, "door-1", OPEN)
        again = await arrival.stamp(db, first, "door-2", {"printing_open": False})
        assert again == first

    run_camp(monkeypatch, run)


def test_arrival_moves_the_patient_onto_the_operating_day(monkeypatch):
    async def run(db):
        patient, (today_id, tomorrow_id) = await _booked(db, days=(TODAY, TOMORROW))
        arrived = await arrival.stamp(db, patient, "door-1", {"printing_open": True, "operating_day_id": str(today_id)})
        assert (arrived["camp_day_id"], arrived["camp_day_changed_from"]) == (today_id, TOMORROW)
        assert patient["camp_day_id"] == tomorrow_id

    run_camp(monkeypatch, run)


def test_arrival_on_the_booked_day_records_no_move(monkeypatch):
    async def run(db):
        patient, (today_id,) = await _booked(db)
        arrived = await arrival.stamp(db, patient, "door-1", {"printing_open": True, "operating_day_id": str(today_id)})
        assert arrived["camp_day_id"] == today_id
        assert "camp_day_changed_from" not in arrived

    run_camp(monkeypatch, run)


def test_a_closed_print_window_refuses_arrival(monkeypatch):
    async def run(db):
        patient, _ = await _booked(db)
        with pytest.raises(HTTPException) as exc:
            await arrival.stamp(db, patient, "door-1", {"printing_open": False})
        assert exc.value.detail["code"] == "PRINT_WINDOW_CLOSED"
        assert (await db.patients.find_one({"_id": patient["_id"]})).get("arrived_at") is None

    run_camp(monkeypatch, run)


def test_a_vanished_registration_is_not_found(monkeypatch):
    async def run(db):
        patient, _ = await _booked(db)
        await db.patients.delete_one({"_id": patient["_id"]})
        with pytest.raises(HTTPException) as exc:
            await arrival.stamp(db, patient, "door-1", OPEN)
        assert exc.value.detail["code"] == "REGISTRATION_NOT_FOUND"

    run_camp(monkeypatch, run)


@pytest.mark.parametrize("patient,ok", [
    ({}, False), ({"aadhaar_scanned": True}, True), ({"no_card_print": True}, True), ({"arrived_at": "x"}, True),
])
def test_only_a_lock_a_no_card_print_or_an_arrival_is_arrivable(patient, ok):
    if ok:
        arrival.require_arrivable(patient)
    else:
        with pytest.raises(HTTPException) as exc:
            arrival.require_arrivable(patient)
        assert exc.value.detail["code"] == "NEEDS_DOOR_SCAN"


def test_a_manual_entry_at_the_door_has_the_same_arrival_fields_as_a_door_lock(monkeypatch):
    async def run(db):
        patient, _ = await _booked(db)
        locked = await arrival.stamp(db, patient, "door-1", OPEN)
        created = arrival.fields_at_creation("door-1", helpers.now_utc())
        stamped = {key: locked.get(key) for key in created}
        assert {**stamped, "arrived_at": helpers.as_utc(stamped["arrived_at"])} == created

    run_camp(monkeypatch, run)


def test_a_registration_that_did_not_arrive_has_empty_arrival_fields():
    assert arrival.fields_at_creation(None, helpers.now_utc()) == {
        "arrived_at": None, "arrived_by": None, "camp_day_changed_from": None,
    }
