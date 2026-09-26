import pytest
from bson import ObjectId
from fastapi import HTTPException

from conftest import CommandLog
from models import NoCardBody, RegisterBody, ScanConfirmBody
from routes_desk import record_no_card_print, scan_confirm
from routes_registration import desk_register
from seed import ACTOR, CARD, Request, run_camp, seed_camp


async def _desk_register(body):
    return await desk_register(body, Request(), actor=ACTOR, background_tasks=None)


def test_scan_confirm_rejects_a_wrong_camp_or_stale_candidate(monkeypatch):
    log = CommandLog()

    async def run(database):
        camp_id, (day_id,) = await seed_camp(database)
        body = RegisterBody(
            full_name="Other Person", age=44, gender="M", phone="9876500003", camp_day_id=str(day_id),
            manual_reason="no_card",
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
            RegisterBody(full_name="Other Person", age=44, gender="M", phone="9876500005", camp_day_id=str(day_id),
                         manual_reason="no_card"),
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
            full_name="Typed Patient", age=60, gender="F", phone="9876500006", camp_day_id=str(day_id),
            manual_reason="no_card", manual_entry=False, manual_exception=False,
        )
        created = await _desk_register(body)
        assert created["registration"]["manual_entry"] is True
        stored = await database.patients.find_one({})
        assert stored["manual_entry"] is True
        assert stored["identity_recheck_required"] is True

        released = await record_no_card_print(
            NoCardBody(patient_id=created["registration"]["id"], reason="no_card"), actor=ACTOR,
        )
        assert released["registration"]["identity_recheck_required"] is False
        assert released["registration"]["no_card_print"] is True

    run_camp(monkeypatch, run)
