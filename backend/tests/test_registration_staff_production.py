import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from bson import ObjectId
from fastapi import HTTPException, Request
from pymongo.errors import DuplicateKeyError

import routes_registration
import routes_staff
import security
from models import CampBody, CampDayBody, CampSetupDay, CreateStaffBody, RegisterBody
from pydantic import ValidationError
from test_adversarial_challenger import setup_mock_db


def test_registrations_without_request_ids_do_not_collide(monkeypatch):
    async def run():
        db = setup_mock_db(monkeypatch)
        camp_id, day_id = ObjectId(), ObjectId()
        await db.camps.insert_one({"_id": camp_id, "is_active": True})
        await db.camp_days.insert_one({"_id": day_id, "camp_id": camp_id, "seat_limit": 10, "booked": 0})
        insert = db.patients.insert_one

        async def sparse_unique_insert(doc):
            if "registration_request_id" in doc and any(
                "registration_request_id" in row and row["registration_request_id"] == doc["registration_request_id"]
                for row in db.patients.docs
            ):
                raise DuplicateKeyError("registration_request_id_1")
            return await insert(doc)

        monkeypatch.setattr(db.patients, "insert_one", sparse_unique_insert)
        for name in ("First Patient", "Second Patient"):
            body = RegisterBody(full_name=name, age=40, phone="9876543210", camp_day_id=str(day_id))
            _, created = await routes_registration._create_registration(body, ObjectId(), False, None)
            assert created
        assert len(db.patients.docs) == 2
        assert db.camp_days.docs[0]["booked"] == 2

    asyncio.run(run())


def test_concurrent_person_creation_returns_the_winning_identity(monkeypatch):
    async def run():
        db = setup_mock_db(monkeypatch)
        winner_id = ObjectId()

        async def losing_insert(doc):
            db.persons.docs.append({**doc, "_id": winner_id})
            raise DuplicateKeyError("aadhaar_key_1")

        monkeypatch.setattr(db.persons, "insert_one", losing_insert)
        person, created = await routes_registration._resolve_person({
            "aadhaar_last4": "4321", "full_name": "Patient", "dob": "1980-01-01", "gender": "M",
        })
        assert person["_id"] == winner_id
        assert created is False

    asyncio.run(run())


def test_disabling_and_reenabling_staff_keeps_prior_sessions_revoked(monkeypatch):
    async def run():
        db = setup_mock_db(monkeypatch)
        monkeypatch.setattr(routes_staff, "get_db", lambda: db)
        monkeypatch.setattr(security, "get_db", lambda: db)
        monkeypatch.setenv("JWT_SECRET", "production-audit-test-secret-at-least-32")
        uid = ObjectId()
        await db.users.insert_one({"_id": uid, "name": "Staff", "role": "volunteer", "disabled_at": None})
        token = security.create_access_token(str(uid))
        actor = {"_id": ObjectId(), "role": "admin"}
        request = Request({"type": "http", "path": "/api/auth/me", "headers": [(b"authorization", f"Bearer {token}".encode())]})
        assert (await security.get_current_user(request))["_id"] == uid
        await routes_staff.disable_staff(str(uid), actor)
        await routes_staff.enable_staff(str(uid), actor)
        with pytest.raises(HTTPException) as exc:
            await security.get_current_user(request)
        assert exc.value.status_code == 401

    asyncio.run(run())


def test_concurrent_staff_creation_returns_a_name_conflict(monkeypatch):
    async def run():
        db = setup_mock_db(monkeypatch)
        monkeypatch.setattr(routes_staff, "get_db", lambda: db)
        monkeypatch.setattr(routes_staff, "hash_pin", lambda _: "hash")

        async def losing_insert(doc):
            raise DuplicateKeyError("name_normalized_1")

        monkeypatch.setattr(db.users, "insert_one", losing_insert)
        with pytest.raises(HTTPException) as exc:
            await routes_staff.create_staff(CreateStaffBody(name="Staff", role="volunteer"), {"_id": ObjectId(), "role": "admin"})
        assert exc.value.status_code == 409
        assert exc.value.detail == "Name already exists"

    asyncio.run(run())


@pytest.mark.parametrize("insert_conflict", [False, True])
def test_request_id_reuse_cannot_return_another_patients_record(monkeypatch, insert_conflict):
    async def run():
        db = setup_mock_db(monkeypatch)
        camp_id, day_id = ObjectId(), ObjectId()
        await db.camps.insert_one({"_id": camp_id, "is_active": True})
        await db.camp_days.insert_one({"_id": day_id, "camp_id": camp_id})
        existing = {
            "_id": ObjectId(), "camp_id": camp_id, "camp_day_id": day_id, "full_name": "Another Patient",
            "registration_request_id": "reused-request", "aadhaar_last4": "1234", "dob": "1970-01-01",
            "phone": "9876543210", "address": "Private address", "patient_qr": "private-token",
        }
        await db.patients.insert_one(existing)
        body = RegisterBody(
            full_name="New Patient", camp_day_id=str(day_id), phone="9876543210",
            registration_request_id="reused-request", aadhaar_scanned=True, aadhaar_last4="5678", dob="1980-01-01",
        )

        async def collision(doc):
            raise DuplicateKeyError("registration_request_id_1")

        with pytest.raises(HTTPException) as exc:
            if insert_conflict:
                monkeypatch.setattr(db.patients, "insert_one", collision)
                await routes_registration._insert_patient_document(db, {}, body, None, camp_id)
            else:
                await routes_registration._create_registration(body, None, True, None)
        assert exc.value.status_code == 409
        assert "private" not in str(exc.value.detail).lower()
        assert "registration" not in exc.value.detail

    asyncio.run(run())


def test_public_duplicate_errors_exclude_patient_records(monkeypatch):
    async def run():
        monkeypatch.setattr(routes_registration, "decode_aadhaar", lambda _: {"outcome": "card", "data": {"full_name": "Patient"}})

        async def duplicate(*args):
            raise HTTPException(status_code=409, detail={
                "code": "DUPLICATE_IN_CAMP", "message": "Already registered in this camp",
                "registration": {"phone": "9876543210", "address": "Private address", "patient_qr": "private-token"},
            })

        monkeypatch.setattr(routes_registration, "_create_registration", duplicate)
        body = RegisterBody(full_name="Patient", camp_day_id=str(ObjectId()))
        request = Request({"type": "http", "client": ("audit-client", 1234), "headers": []})
        with pytest.raises(HTTPException) as exc:
            await routes_registration.self_register(body, request, background_tasks=None)
        assert exc.value.status_code == 409
        assert exc.value.detail == {"code": "DUPLICATE_IN_CAMP", "message": "Already registered in this camp"}

    asyncio.run(run())


@pytest.mark.parametrize("date_value", ["2026-02-30", "not-a-date", "2026-13-01"])
@pytest.mark.parametrize("model,field,extra", [
    (CampBody, "camp_date", {"name": "Camp", "venue": "Hall"}),
    (CampDayBody, "day_date", {"camp_id": str(ObjectId()), "seat_limit": 10}),
    (CampSetupDay, "day_date", {"seat_limit": 10}),
])
def test_camp_dates_reject_impossible_or_malformed_values(date_value, model, field, extra):
    with pytest.raises(ValidationError):
        model(**extra, **{field: date_value})


def test_camp_dates_keep_the_database_string_contract():
    body = CampBody(name="Camp", venue="Hall", camp_date="2028-02-29", days=[{"day_date": "2028-02-29", "seat_limit": 10}])
    assert body.camp_date == "2028-02-29"
    assert body.days[0].day_date == "2028-02-29"


def test_scanned_retry_preserves_the_original_booking_after_arrival_moves_the_day():
    camp_id, booked_day_id = ObjectId(), ObjectId()
    existing = {
        "_id": ObjectId(), "camp_id": camp_id, "camp_day_id": ObjectId(), "booked_camp_day_id": booked_day_id,
        "full_name": "Patient", "aadhaar_last4": "1234", "dob": "1980-01-01", "reg_no": 12,
    }
    body = RegisterBody(
        full_name="Patient", camp_day_id=str(booked_day_id), aadhaar_scanned=True,
        aadhaar_last4="1234", dob="1980-01-01",
    )
    patient, created = routes_registration._replay_registration(existing, body, camp_id)
    assert patient["reg_no"] == 12
    assert created is False
