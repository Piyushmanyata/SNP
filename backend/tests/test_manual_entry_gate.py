import asyncio

import pytest
from fastapi import HTTPException

import routes_registration
from models import IdentityCheckBody, RegisterBody, ScanConfirmBody
from routes_desk import record_identity_check, scan_confirm
from test_camp_lifecycle import ACTOR, CARD, TODAY, _Request, _mock, _seed_camp


def test_unscanned_staff_registration_needs_three_camera_attempts_and_a_reason(monkeypatch):
    async def run():
        mock_db = _mock(monkeypatch)
        _camp_id, (day_id,) = await _seed_camp(mock_db)
        body = RegisterBody(
            full_name="Sunita Devi", age=51, phone="9876500001", camp_day_id=str(day_id),
        )
        with pytest.raises(HTTPException) as exc:
            await routes_registration.desk_register_strict(
                body, _Request(), actor=ACTOR, background_tasks=None,
            )
        assert exc.value.status_code == 400
        assert exc.value.detail["code"] == "MANUAL_ENTRY_NOT_ALLOWED"
        assert mock_db.patients.docs == []

        body.failed_scan_attempts = 2
        body.manual_reason = "camera would not start"
        with pytest.raises(HTTPException) as exc:
            await routes_registration.desk_register_strict(
                body, _Request(), actor=ACTOR, background_tasks=None,
            )
        assert exc.value.detail["code"] == "MANUAL_ENTRY_NOT_ALLOWED"

        body.failed_scan_attempts = 3
        opened = await routes_registration.desk_register_strict(
            body, _Request(), actor=ACTOR, background_tasks=None,
        )
        assert opened["created"] is True
        assert opened["registration"]["manual_entry"] is True
        stored = mock_db.patients.docs[0]
        assert stored["manual_reason"] == "camera would not start"
        assert stored["failed_scan_attempts"] == 3
        assert stored["manual_at_door"] is False

    asyncio.run(run())


def test_door_manual_entry_stays_shut_until_an_admin_opens_the_gate(monkeypatch):
    async def run():
        mock_db = _mock(monkeypatch)
        camp_id, (day_id,) = await _seed_camp(mock_db)
        body = RegisterBody(
            full_name="Door Patient", age=40, phone="9876500002", camp_day_id=str(day_id),
            failed_scan_attempts=3, manual_reason="scanners are down", at_door=True,
            registration_request_id="door-1",
        )
        with pytest.raises(HTTPException) as exc:
            await routes_registration.desk_register_strict(
                body, _Request(), actor=ACTOR, background_tasks=None,
            )
        assert exc.value.status_code == 403
        assert exc.value.detail["code"] == "DOOR_MANUAL_SHUT"
        assert mock_db.patients.docs == []

        await mock_db.camps.update_one({"_id": camp_id}, {"$set": {"door_manual_date": TODAY}})
        opened = await routes_registration.desk_register_strict(
            body, _Request(), actor=ACTOR, background_tasks=None,
        )
        assert opened["created"] is True
        assert mock_db.patients.docs[0]["manual_at_door"] is True

    asyncio.run(run())


def test_scan_confirm_rejects_a_wrong_camp_or_stale_candidate(monkeypatch):
    async def run():
        from bson import ObjectId

        mock_db = _mock(monkeypatch)
        camp_id, (day_id,) = await _seed_camp(mock_db)
        body = RegisterBody(
            full_name="Other Person", age=44, phone="9876500003", camp_day_id=str(day_id),
            failed_scan_attempts=3, manual_reason="camera would not start", manual_entry=True,
        )
        created = await routes_registration.desk_register_strict(
            body, _Request(), actor=ACTOR, background_tasks=None,
        )
        patient_id = created["registration"]["id"]
        foreign = ObjectId()
        await mock_db.patients.update_one(
            {"_id": ObjectId(patient_id)}, {"$set": {"camp_id": foreign}},
        )
        with pytest.raises(HTTPException) as exc:
            await scan_confirm(ScanConfirmBody(patient_id=patient_id, payload=CARD), actor=ACTOR)
        assert exc.value.detail["code"] == "WRONG_CAMP"
        stored = await mock_db.patients.find_one({"_id": ObjectId(patient_id)})
        assert stored["camp_id"] == foreign
        assert stored.get("arrived_at") is None

        await mock_db.patients.update_one(
            {"_id": ObjectId(patient_id)}, {"$set": {"camp_id": camp_id}},
        )
        writes = []
        original_update = mock_db.patients.find_one_and_update

        async def recording_update(*args, **kwargs):
            writes.append(args)
            return await original_update(*args, **kwargs)

        monkeypatch.setattr(mock_db.patients, "find_one_and_update", recording_update)
        with pytest.raises(HTTPException) as exc:
            await scan_confirm(ScanConfirmBody(patient_id=patient_id, payload=CARD), actor=ACTOR)
        assert exc.value.detail["code"] == "STALE_CANDIDATE"
        stored = await mock_db.patients.find_one({"_id": ObjectId(patient_id)})
        assert stored.get("aadhaar_scanned") is not True
        assert stored["full_name"] == "Other Person"
        assert writes == []
        assert mock_db.persons.docs == []

    asyncio.run(run())


def test_scan_confirm_reports_a_card_holder_already_in_the_camp(monkeypatch):
    async def run():
        mock_db = _mock(monkeypatch)
        _camp_id, (day_id,) = await _seed_camp(mock_db)
        holder = await routes_registration.desk_register_strict(
            RegisterBody(full_name="Sunita Devi", phone="9876500004", camp_day_id=str(day_id),
                         aadhaar_scanned=True, qr_payload=CARD),
            _Request(), actor=ACTOR, background_tasks=None,
        )
        other = await routes_registration.desk_register_strict(
            RegisterBody(full_name="Other Person", age=44, phone="9876500005", camp_day_id=str(day_id),
                         failed_scan_attempts=3, manual_reason="camera would not start"),
            _Request(), actor=ACTOR, background_tasks=None,
        )
        with pytest.raises(HTTPException) as exc:
            await scan_confirm(
                ScanConfirmBody(patient_id=other["registration"]["id"], payload=CARD), actor=ACTOR,
            )
        assert exc.value.detail["code"] == "DUPLICATE_IN_CAMP"
        assert exc.value.detail["registration"]["id"] == holder["registration"]["id"]

    asyncio.run(run())


def test_an_unscanned_staff_registration_is_a_manual_entry_whatever_the_client_claims(monkeypatch):
    async def run():
        mock_db = _mock(monkeypatch)
        _camp_id, (day_id,) = await _seed_camp(mock_db)
        body = RegisterBody(
            full_name="Typed Patient", age=60, phone="9876500006", camp_day_id=str(day_id),
            failed_scan_attempts=3, manual_reason="card QR is scratched",
            manual_entry=False, manual_exception=False,
        )
        created = await routes_registration.desk_register_strict(
            body, _Request(), actor=ACTOR, background_tasks=None,
        )
        assert created["registration"]["manual_entry"] is True
        stored = mock_db.patients.docs[0]
        assert stored["manual_entry"] is True
        assert stored["identity_recheck_required"] is True

        checked = await record_identity_check(
            IdentityCheckBody(patient_id=created["registration"]["id"], reason="Voter ID seen"),
            actor={**ACTOR, "role": "admin"},
        )
        assert checked["registration"]["identity_recheck_required"] is False
        assert checked["registration"]["identity_checked"] is True

    asyncio.run(run())
