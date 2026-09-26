from datetime import timedelta
from uuid import uuid4
from xml.etree.ElementTree import Element, tostring

import pytest
from bson import ObjectId
from fastapi import HTTPException

from models import RegisterBody, ScanBody, ScanConfirmBody
from routes_desk import scan, scan_confirm
from routes_registration import desk_register
from seed import ACTOR, NOW, TODAY, Request, bearer, day, http, recorder, register, run_camp, seed_camp, user_doc


def card(name, uid, dob, gender="F", street="12 Station Road Sikar"):
    return tostring(Element("PrintLetterBarcodeData", name=name, gender=gender, dob=dob, uid=uid, street=street), encoding="unicode")


async def _refused(day_id, **fields):
    with pytest.raises(HTTPException) as exc:
        await register(day_id, **fields)
    return exc.value


def test_a_manual_entry_needs_only_a_reason_and_is_always_rechecked(monkeypatch):
    async def body(database, client):
        _camp_id, (day_id,) = await seed_camp(database, days=(day(1),))
        volunteer = (await database.users.insert_one(user_doc("Desk", "volunteer"))).inserted_id
        headers = bearer(volunteer, "Desk", "volunteer")
        payload = {"full_name": "Manual Patient", "age": 44, "phone": "9876500011", "camp_day_id": str(day_id)}
        refused = await client.post("/api/register", json=payload, headers=headers)
        assert refused.status_code == 400
        assert refused.json()["detail"]["code"] == "MANUAL_ENTRY_NOT_ALLOWED"
        saved = await client.post("/api/register", json={**payload, "manual_reason": "card left at home"}, headers=headers)
        assert saved.status_code == 200, saved.text
        stored = await database.patients.find_one({})
        assert stored["manual_entry"] is True and stored["identity_recheck_required"] is True
        assert "failed_scan_attempts" not in stored

    http(monkeypatch, body)


def test_a_door_scan_never_arrives_someone_else(monkeypatch):
    async def run(database):
        _camp_id, (day_id,) = await seed_camp(database)
        first = await register(day_id, full_name="Asha Rani", aadhaar_scanned=True, aadhaar_last4="4411", dob="1960-01-01", gender="F")
        full_date = await scan(ScanBody(payload=card("Asha Rani", "999900004411", "1960-05-12")), actor=ACTOR)
        other_year = await scan(ScanBody(payload=card("Asha Rani", "666600004411", "1962-01-01")), actor=ACTOR)
        same_dob = await scan(ScanBody(payload=card("Kamla Devi", "888800004411", "1960-01-01")), actor=ACTOR)
        assert full_date["outcome"] == "mismatch_review"
        assert other_year["outcome"] == "no_match"
        assert same_dob["outcome"] == "no_match"
        assert (await database.patients.find_one({"_id": ObjectId(first["id"])}))["arrived_at"] is None
        own = await scan(ScanBody(payload=card("Asha Rani", "777700004411", "1960-01-01")), actor=ACTOR)
        assert own["outcome"] == "arrived" and own["registration"]["id"] == first["id"]

    run_camp(monkeypatch, run)


def test_different_people_sharing_last4_and_a_year_only_birth_date_both_register(monkeypatch):
    async def run(database):
        _camp_id, (day_id,) = await seed_camp(database, days=(day(1),))
        await register(day_id, full_name="Asha Rani", aadhaar_scanned=True, aadhaar_last4="4411", dob="1960-01-01")
        second = await register(day_id, full_name="Kamla Devi", phone="9876500012", aadhaar_scanned=True, aadhaar_last4="4411", dob="1960-01-01")
        assert second["full_name"] == "Kamla Devi"
        assert await database.patients.count_documents({}) == 2

    run_camp(monkeypatch, run)


def test_namesakes_sharing_last4_with_different_birth_years_both_register(monkeypatch):
    async def run(database):
        _camp_id, (day_id,) = await seed_camp(database, days=(day(1),))
        first = await register(day_id, full_name="Asha Rani", aadhaar_scanned=True, aadhaar_last4="4411", dob="1960-03-02", gender="F")
        second = await register(day_id, full_name="Asha Rani", phone="9876500012", aadhaar_scanned=True, aadhaar_last4="4411", dob="1971-08-19", gender="F")
        assert second["id"] != first["id"]
        assert await database.patients.count_documents({}) == 2

    run_camp(monkeypatch, run)


def test_a_typed_birth_date_never_proves_a_different_person(monkeypatch):
    async def run(database):
        _camp_id, (day_id,) = await seed_camp(database, days=(day(1),))
        scanned = await register(day_id, full_name="Asha Rani", aadhaar_scanned=True, aadhaar_last4="4411", dob="1980-05-12", gender="F")
        refused = await _refused(day_id, full_name="Asha Rani", age=scanned["age"], aadhaar_last4="4411", dob="1980-12-05")
        assert refused.detail["code"] == "DUPLICATE_IN_CAMP"
        assert refused.detail["registration"]["id"] == scanned["id"]

    run_camp(monkeypatch, run)


def test_a_namesake_card_is_never_confirmed_onto_another_registration(monkeypatch):
    async def run(database):
        _camp_id, (day_id,) = await seed_camp(database)
        first = await register(day_id, full_name="Asha Rani", aadhaar_scanned=True, aadhaar_last4="4411", dob="1960-03-02", gender="F")
        namesake = card("Asha Rani", "999900004411", "1960-11-23")
        assert (await scan(ScanBody(payload=namesake), actor=ACTOR))["outcome"] == "no_match"
        with pytest.raises(HTTPException) as exc:
            await scan_confirm(ScanConfirmBody(patient_id=first["id"], payload=namesake), actor=ACTOR)
        assert exc.value.detail["code"] == "STALE_CANDIDATE"
        assert (await database.patients.find_one({"_id": ObjectId(first["id"])}))["arrived_at"] is None

    run_camp(monkeypatch, run)


def test_a_card_that_differs_from_a_manual_entry_goes_through_review_at_the_desk(monkeypatch):
    async def run(database):
        _camp_id, (day_id,) = await seed_camp(database, days=(day(1),))
        manual = await register(day_id, full_name="Sunita Devi", age=30, aadhaar_last4="1234")
        fields = dict(full_name="Sunita Devi", aadhaar_scanned=True, aadhaar_last4="1234", dob="1975-06-14", gender="F")
        refused = await _refused(day_id, **fields)
        assert refused.status_code == 409
        assert refused.detail["code"] == "MISMATCH_REVIEW_REQUIRED"
        assert refused.detail["registration"]["id"] == manual["id"]
        assert {d["field"] for d in refused.detail["diff"]} == {"age"}
        assert refused.detail["card"]["dob"] == "1975-06-14"
        assert (await database.patients.find_one({}))["aadhaar_scanned"] is not True

        request_id = str(uuid4())
        confirmed = await register(day_id, **fields, review_confirmed_id=manual["id"], registration_request_id=request_id)
        assert confirmed["id"] == manual["id"] and confirmed["aadhaar_scanned"] is True
        replayed = await register(day_id, **fields, review_confirmed_id=manual["id"], registration_request_id=request_id)
        assert replayed["id"] == manual["id"]

    run_camp(monkeypatch, run)


def test_a_printed_manual_entry_is_never_overwritten(monkeypatch):
    async def run(database):
        _camp_id, (day_id,) = await seed_camp(database)
        manual = await register(day_id, full_name="Sunita Devi", age=51, aadhaar_last4="1234")
        await database.patients.update_one({"_id": ObjectId(manual["id"])}, {"$set": {"arrived_at": NOW, "printed_at": NOW}})
        refused = await _refused(day_id, full_name="Sunita Devi", aadhaar_scanned=True, aadhaar_last4="1234", dob="1975-06-14", gender="F")
        assert refused.detail["code"] == "ALREADY_PRINTED"
        with pytest.raises(HTTPException) as exc:
            await scan(ScanBody(payload=card("Sunita Devi", "123456781234", "1975-06-14")), actor=ACTOR)
        assert exc.value.detail["code"] == "ALREADY_PRINTED"
        assert (await database.patients.find_one({}))["aadhaar_scanned"] is not True

    run_camp(monkeypatch, run)


def test_a_walk_in_after_midnight_on_a_late_camp_day_registers_without_sms(monkeypatch):
    sent = recorder(monkeypatch)

    async def run(database):
        camp_id, (day_id,) = await seed_camp(database, days=(TODAY,))
        await database.camp_days.update_one({"_id": day_id}, {"$set": {"seat_limit": 1, "booked": 1}})
        await database.camps.update_one({"_id": camp_id}, {"$set": {"print_override": {
            "mode": "enable", "day_id": str(day_id), "expires_at": NOW + timedelta(days=1),
        }}})
        walk_in = await register(day_id, full_name="Late Walk In", aadhaar_scanned=True, aadhaar_last4="5566", dob="1970-02-02")
        assert walk_in["reg_no"]
        assert sent == []

    run_camp(monkeypatch, run, ist=f"{day(1)}T00:30")


def test_a_past_day_that_is_not_the_operating_day_takes_no_bookings(monkeypatch):
    async def run(database):
        _camp_id, (past, _today) = await seed_camp(database, days=(day(-1), TODAY))
        refused = await _refused(past, full_name="Too Late", aadhaar_scanned=True, aadhaar_last4="5566", dob="1970-02-02")
        assert refused.status_code == 409 and refused.detail["code"] == "DAY_PASSED"
        with pytest.raises(HTTPException) as exc:
            await desk_register(RegisterBody(
                full_name="Too Late Manual", age=40, phone="9876500013", camp_day_id=str(past), manual_reason="no card",
            ), Request(), actor=ACTOR, background_tasks=None)
        assert exc.value.detail["code"] == "DAY_PASSED"
        assert await database.patients.count_documents({}) == 0

    run_camp(monkeypatch, run)


def test_confirming_review_of_a_scanned_registration_arrives_it_and_keeps_its_card(monkeypatch):
    async def run(database):
        _camp_id, (day_id,) = await seed_camp(database)
        booked = await register(day_id, full_name="Asha Rani", aadhaar_scanned=True, aadhaar_last4="4411", dob="1960-01-01", gender="F")
        other_card = card("Asha Rani", "999900004411", "1960-05-12")
        review = await scan(ScanBody(payload=other_card), actor=ACTOR)
        assert review["outcome"] == "mismatch_review" and review["registration"]["id"] == booked["id"]
        confirmed = await scan_confirm(ScanConfirmBody(patient_id=booked["id"], payload=other_card), actor=ACTOR)
        assert confirmed["outcome"] == "arrived"
        stored = await database.patients.find_one({"_id": ObjectId(booked["id"])})
        assert stored["arrived_at"] and stored["dob"] == "1960-01-01"

    run_camp(monkeypatch, run)
