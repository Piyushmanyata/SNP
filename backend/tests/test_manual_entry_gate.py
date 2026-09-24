import pytest
from bson import ObjectId
from fastapi import HTTPException

from conftest import CommandLog
from models import IdentityCheckBody, RegisterBody, ScanConfirmBody
from routes_desk import record_identity_check, scan_confirm
from routes_registration import desk_register
from seed import ACTOR, CARD, TODAY, Request, run_camp, seed_camp


async def _desk_register(body):
    return await desk_register(body, Request(), actor=ACTOR, background_tasks=None)


def test_unscanned_staff_registration_needs_a_reason(monkeypatch):
    async def run(database):
        _camp_id, (day_id,) = await seed_camp(database)
        body = RegisterBody(
            full_name="Sunita Devi", age=51, phone="9876500001", camp_day_id=str(day_id),
        )
        with pytest.raises(HTTPException) as exc:
            await _desk_register(body)
        assert exc.value.status_code == 400
        assert exc.value.detail["code"] == "MANUAL_ENTRY_NOT_ALLOWED"
        assert await database.patients.count_documents({}) == 0

        body.manual_reason = "   "
        with pytest.raises(HTTPException) as exc:
            await _desk_register(body)
        assert exc.value.detail["code"] == "MANUAL_ENTRY_NOT_ALLOWED"

        body.manual_reason = "camera would not start"
        opened = await _desk_register(body)
        assert opened["created"] is True
        assert opened["registration"]["manual_entry"] is True
        stored = await database.patients.find_one({})
        assert stored["manual_reason"] == "camera would not start"
        assert stored["manual_at_door"] is False

    run_camp(monkeypatch, run)


def test_door_manual_entry_stays_shut_until_an_admin_opens_the_gate(monkeypatch):
    async def run(database):
        camp_id, (day_id,) = await seed_camp(database)
        body = RegisterBody(
            full_name="Door Patient", age=40, phone="9876500002", camp_day_id=str(day_id),
            manual_reason="scanners are down", at_door=True,
            registration_request_id="7b3f2a10-4c5d-4e6f-8a9b-0c1d2e3f4a5b",
        )
        with pytest.raises(HTTPException) as exc:
            await _desk_register(body)
        assert exc.value.status_code == 403
        assert exc.value.detail["code"] == "DOOR_MANUAL_SHUT"
        assert await database.patients.count_documents({}) == 0

        await database.camps.update_one({"_id": camp_id}, {"$set": {"door_manual_date": TODAY}})
        opened = await _desk_register(body)
        assert opened["created"] is True
        assert (await database.patients.find_one({}))["manual_at_door"] is True

    run_camp(monkeypatch, run)


def test_scan_confirm_rejects_a_wrong_camp_or_stale_candidate(monkeypatch):
    log = CommandLog()

    async def run(database):
        camp_id, (day_id,) = await seed_camp(database)
        body = RegisterBody(
            full_name="Other Person", age=44, phone="9876500003", camp_day_id=str(day_id),
            manual_reason="camera would not start", manual_entry=True,
        )
        created = await _desk_register(body)
        patient_id = created["registration"]["id"]
        foreign = ObjectId()
        await database.patients.update_one({"_id": ObjectId(patient_id)}, {"$set": {"camp_id": foreign}})
        with pytest.raises(HTTPException) as exc:
            await scan_confirm(ScanConfirmBody(patient_id=patient_id, payload=CARD), actor=ACTOR)
        assert exc.value.detail["code"] == "WRONG_CAMP"
        stored = await database.patients.find_one({"_id": ObjectId(patient_id)})
        assert stored["camp_id"] == foreign
        assert stored.get("arrived_at") is None

        await database.patients.update_one({"_id": ObjectId(patient_id)}, {"$set": {"camp_id": camp_id}})
        log.commands.clear()
        with pytest.raises(HTTPException) as exc:
            await scan_confirm(ScanConfirmBody(patient_id=patient_id, payload=CARD), actor=ACTOR)
        assert exc.value.detail["code"] == "STALE_CANDIDATE"
        assert [name for name, target in log.commands if target == "patients" and name in ("findAndModify", "update")] == []
        stored = await database.patients.find_one({"_id": ObjectId(patient_id)})
        assert stored.get("aadhaar_scanned") is not True
        assert stored["full_name"] == "Other Person"
        assert await database.persons.count_documents({}) == 0

    run_camp(monkeypatch, run, listener=log)


def test_scan_confirm_reports_a_card_holder_already_in_the_camp(monkeypatch):
    async def run(database):
        _camp_id, (day_id,) = await seed_camp(database)
        holder = await _desk_register(
            RegisterBody(full_name="Sunita Devi", phone="9876500004", camp_day_id=str(day_id),
                         aadhaar_scanned=True, qr_payload=CARD),
        )
        other = await _desk_register(
            RegisterBody(full_name="Other Person", age=44, phone="9876500005", camp_day_id=str(day_id),
                         manual_reason="camera would not start"),
        )
        with pytest.raises(HTTPException) as exc:
            await scan_confirm(
                ScanConfirmBody(patient_id=other["registration"]["id"], payload=CARD), actor=ACTOR,
            )
        assert exc.value.detail["code"] == "DUPLICATE_IN_CAMP"
        assert exc.value.detail["registration"]["id"] == holder["registration"]["id"]

    run_camp(monkeypatch, run)


def test_an_unscanned_staff_registration_is_a_manual_entry_whatever_the_client_claims(monkeypatch):
    async def run(database):
        _camp_id, (day_id,) = await seed_camp(database)
        body = RegisterBody(
            full_name="Typed Patient", age=60, phone="9876500006", camp_day_id=str(day_id),
            manual_reason="card QR is scratched",
            manual_entry=False, manual_exception=False,
        )
        created = await _desk_register(body)
        assert created["registration"]["manual_entry"] is True
        stored = await database.patients.find_one({})
        assert stored["manual_entry"] is True
        assert stored["identity_recheck_required"] is True

        checked = await record_identity_check(
            IdentityCheckBody(patient_id=created["registration"]["id"], reason="Voter ID seen"),
            actor={**ACTOR, "role": "admin"},
        )
        assert checked["registration"]["identity_recheck_required"] is False
        assert checked["registration"]["identity_checked"] is True

    run_camp(monkeypatch, run)
