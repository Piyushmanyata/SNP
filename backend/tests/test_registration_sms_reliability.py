import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from bson import ObjectId
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

import routes_registration
import routes_desk
import routes_clinical
import sms
from models import RegisterBody
from test_adversarial_challenger import setup_mock_db


@pytest.mark.parametrize("entry", ["e6d9244e-8d6f-40c1-8753-5717cda5d38e", "SNP:E6D9244E-8D6F-40C1-8753-5717CDA5D38E"])
def test_legacy_patient_qr_resolves_at_desk_and_clinical_lookup(monkeypatch, entry):
    async def run():
        db = setup_mock_db(monkeypatch)
        patient_id = ObjectId()
        camp_id = ObjectId()
        await db.camps.insert_one({"_id": camp_id, "is_active": True})
        await db.patients.insert_one({
            "_id": patient_id, "camp_id": camp_id, "patient_qr": "e6d9244e-8d6f-40c1-8753-5717cda5d38e",
            "queue_status": "registered",
        })
        patient = await routes_desk._resolve(entry)
        assert patient and patient["_id"] == patient_id
        with pytest.raises(HTTPException) as exc:
            await routes_clinical.clinical_lookup(
                {"value": entry}, {"_id": ObjectId(), "role": "clinical_desk_operator"},
            )
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "not_arrived"

    asyncio.run(run())


def test_competing_arrivals_preserve_the_first_volunteer(monkeypatch):
    async def run():
        db = setup_mock_db(monkeypatch)
        camp_id = ObjectId()
        await db.camps.insert_one({"_id": camp_id})
        target = {"_id": ObjectId(), "camp_id": camp_id, "queue_status": "registered"}
        await db.patients.insert_one(target.copy())

        async def door_open(*args):
            return {}

        monkeypatch.setattr(routes_desk, "_require_door_open", door_open)
        first = await routes_desk._stamp_arrival(db, target, "first-volunteer")
        retry = await routes_desk._stamp_arrival(db, target, "second-volunteer")
        assert retry["arrived_by"] == "first-volunteer"
        assert retry["arrived_at"] == first["arrived_at"]

    asyncio.run(run())


@pytest.mark.parametrize("path", ["registration", "door"])
def test_stale_manual_identity_cannot_overwrite_a_completed_scan(monkeypatch, path):
    async def run():
        db = setup_mock_db(monkeypatch)
        camp_id = ObjectId()
        target = {"_id": ObjectId(), "camp_id": camp_id, "manual_entry": True, "full_name": "Patient"}
        await db.patients.insert_one(target.copy())
        first = RegisterBody(
            full_name="Patient", camp_day_id=str(ObjectId()), aadhaar_scanned=True,
            aadhaar_last4="1234", dob="1980-01-01", age=46, gender="M", address="Hall",
        )
        second = first.model_copy(update={"aadhaar_last4": "5678"})

        async def scan(body):
            if path == "door":
                return await routes_desk._apply_overwrite(db, target, body.model_dump())
            person, _ = await routes_registration._resolve_person(body.model_dump())
            return await routes_registration._overwrite_manual(db, target, body, person, body.age)

        await scan(first)
        with pytest.raises(HTTPException) as exc:
            await scan(second)
        assert exc.value.status_code == 409
        stored = await db.patients.find_one({"_id": target["_id"]})
        assert stored["aadhaar_last4"] == "1234"
        assert stored["aadhaar_scanned"] is True

    asyncio.run(run())


@pytest.mark.parametrize("key", ["patient_qr", "reg_no"])
def test_registration_retries_only_patient_code_collisions(monkeypatch, key):
    async def run():
        db = setup_mock_db(monkeypatch)
        camp_id, day_id = ObjectId(), ObjectId()
        await db.camps.insert_one({"_id": camp_id, "is_active": True})
        await db.camp_days.insert_one({"_id": day_id, "camp_id": camp_id, "seat_limit": 10, "booked": 0})
        codes = iter(["AAAAAAAA", "BBBBBBBB"])
        monkeypatch.setattr(routes_registration, "new_patient_code", lambda: next(codes))
        insert = db.patients.insert_one
        attempts = []

        async def collide_once(doc):
            attempts.append(doc["patient_qr"])
            if len(attempts) == 1:
                raise DuplicateKeyError("duplicate", details={"keyPattern": {key: 1}})
            return await insert(doc)

        monkeypatch.setattr(db.patients, "insert_one", collide_once)
        body = RegisterBody(full_name="Patient", age=40, camp_day_id=str(day_id))
        if key == "patient_qr":
            patient, created = await routes_registration._create_registration(body, None, False, None)
            assert created and patient["patient_qr"] == "BBBBBBBB"
            assert attempts == ["AAAAAAAA", "BBBBBBBB"]
            assert db.camp_days.docs[0]["booked"] == 1
            assert len(db.patients.docs) == 1
        else:
            with pytest.raises(DuplicateKeyError):
                await routes_registration._create_registration(body, None, False, None)
            assert attempts == ["AAAAAAAA"]
            assert db.camp_days.docs[0]["booked"] == 0

    asyncio.run(run())


@pytest.mark.parametrize("provider_succeeds", [True, False])
def test_sms_ledger_failure_does_not_escape_or_resend_an_accepted_message(monkeypatch, provider_succeeds):
    async def run():
        db = setup_mock_db(monkeypatch)
        monkeypatch.setattr(sms.msg91, "configured", lambda: True)
        calls = []

        def send(*args):
            calls.append(args)
            if not provider_succeeds:
                raise RuntimeError("provider unavailable")
            return "accepted"

        async def unavailable(*args, **kwargs):
            raise RuntimeError("ledger unavailable")

        monkeypatch.setattr(sms.msg91, "send_dlt_sms", send)
        monkeypatch.setattr(db.reminder_ledger, "update_one", unavailable)
        patient = {"_id": ObjectId(), "phone": "9876543210", "reg_no": 42}
        assert await sms.send_patient_sms(db, patient, "registration", "2026-09-12", "Hall") is provider_succeeds
        assert not await sms.send_patient_sms(db, patient, "registration", "2026-09-12", "Hall")
        assert len(calls) == 1
        assert db.reminder_ledger.docs[0]["status"] == "pending"

    asyncio.run(run())


def test_accepted_sms_is_not_marked_failed_when_receipt_persistence_fails(monkeypatch):
    async def run():
        db = setup_mock_db(monkeypatch)
        monkeypatch.setattr(sms.msg91, "configured", lambda: True)
        calls = []
        monkeypatch.setattr(sms.msg91, "send_dlt_sms", lambda *args: calls.append(args) or "accepted")
        update = db.reminder_ledger.update_one

        async def lose_receipt(query, change):
            if change["$set"]["status"] == "sent":
                raise RuntimeError("receipt write failed")
            return await update(query, change)

        monkeypatch.setattr(db.reminder_ledger, "update_one", lose_receipt)
        patient = {"_id": ObjectId(), "phone": "9876543210", "reg_no": 42}
        assert await sms.send_patient_sms(db, patient, "registration", "2026-09-12", "Hall")
        assert not await sms.send_patient_sms(db, patient, "registration", "2026-09-12", "Hall")
        assert len(calls) == 1

    asyncio.run(run())
