import asyncio
import threading

import pytest
from bson import ObjectId
from fastapi import HTTPException, Request
from pymongo.asynchronous.collection import AsyncCollection

import helpers
import routes_registration
import routes_staff
import security
from conftest import run_db
from models import CampBody, CampDayBody, CampSetupDay, CreateStaffBody, RegisterBody
from pydantic import ValidationError
from seed import ADMIN, patient_doc, run_camp, seed_camp, user_doc


def test_registrations_without_request_ids_do_not_collide(monkeypatch):
    async def run(database):
        camp_id, (day_id,) = await seed_camp(database)
        for name in ("First Patient", "Second Patient"):
            body = RegisterBody(full_name=name, age=40, phone="9876543210", camp_day_id=str(day_id))
            _, created = await routes_registration._create_registration(body, ObjectId(), False, None)
            assert created
        assert await database.patients.count_documents({"camp_id": camp_id}) == 2
        assert (await database.camp_days.find_one({"_id": day_id}))["booked"] == 2

    run_camp(monkeypatch, run)


def test_concurrent_person_creation_returns_the_winning_identity(monkeypatch):
    winner_id = ObjectId()
    real_next_seq = routes_registration.next_seq

    async def run(database):
        async def rival_inserts_first(name):
            await database.persons.insert_one({
                "_id": winner_id, "aadhaar_key": helpers.person_key("4321", "Patient", "1980-01-01", "M"),
                "person_no": await real_next_seq(name),
            })
            return await real_next_seq(name)

        monkeypatch.setattr(routes_registration, "next_seq", rival_inserts_first)
        person, created = await routes_registration._resolve_person({
            "aadhaar_last4": "4321", "full_name": "Patient", "dob": "1980-01-01", "gender": "M",
        })
        assert person["_id"] == winner_id
        assert created is False
        assert await database.persons.count_documents({}) == 1

    run_db(run)


def test_disabling_and_reenabling_staff_keeps_prior_sessions_revoked(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "production-audit-test-secret-at-least-32")

    async def run(database):
        uid = ObjectId()
        await database.users.insert_one(user_doc("Staff", _id=uid))
        token = security.create_access_token(str(uid))
        request = Request({"type": "http", "path": "/api/auth/me", "headers": [(b"authorization", f"Bearer {token}".encode())]})
        assert (await security.get_current_user(request))["_id"] == uid
        await routes_staff.disable_staff(str(uid), ADMIN)
        await routes_staff.enable_staff(str(uid), ADMIN)
        with pytest.raises(HTTPException) as exc:
            await security.get_current_user(request)
        assert exc.value.status_code == 401

    run_db(run)


def test_deleting_staff_hides_roster_and_allows_name_reuse_without_losing_history(monkeypatch):
    monkeypatch.setattr(routes_staff, "hash_pin", lambda _: "hash")

    async def run(database):
        staff_id, patient_id = ObjectId(), ObjectId()
        await database.users.insert_one(user_doc("Vol One", _id=staff_id, phone="9876500001"))
        await database.patients.insert_one(patient_doc(_id=patient_id, created_by=str(staff_id)))

        await routes_staff.delete_staff(str(staff_id), ADMIN)

        original = await database.users.find_one({"_id": staff_id})
        assert original["name"] == "Vol One"
        assert original["deleted_at"] is not None
        assert original["disabled_at"] is not None
        assert (await database.patients.find_one({"_id": patient_id}))["created_by"] == str(staff_id)
        assert all(row["id"] != str(staff_id) for row in (await routes_staff.list_staff(ADMIN))["staff"])
        replacement = await routes_staff.create_staff(CreateStaffBody(name="Vol One", role="volunteer"), ADMIN)
        assert replacement["staff"]["id"] != str(staff_id)

    run_db(run)


def test_team_lead_deletion_requires_reassigning_volunteers():
    async def run(database):
        old_lead_id, new_lead_id, volunteer_id, patient_id = ObjectId(), ObjectId(), ObjectId(), ObjectId()
        await database.users.insert_many([
            user_doc("Old Lead", "team_lead", _id=old_lead_id),
            user_doc("New Lead", "team_lead", _id=new_lead_id),
            user_doc("Volunteer", _id=volunteer_id, team_lead_id=str(old_lead_id)),
        ])
        await database.patients.insert_one(patient_doc(_id=patient_id, registrar_team_lead_id=str(old_lead_id)))

        with pytest.raises(HTTPException) as blocked:
            await routes_staff.delete_staff(str(old_lead_id), ADMIN)
        assert blocked.value.status_code == 409

        await routes_staff.reassign_volunteer(
            str(volunteer_id), routes_staff.PatchStaffTeamLeadBody(team_lead_id=str(new_lead_id)), ADMIN,
        )
        await routes_staff.delete_staff(str(old_lead_id), ADMIN)

        assert (await database.users.find_one({"_id": volunteer_id}))["team_lead_id"] == str(new_lead_id)
        assert (await database.patients.find_one({"_id": patient_id}))["registrar_team_lead_id"] == str(old_lead_id)

    run_db(run)


def test_delete_staff_rejects_invalid_id():
    async def run(database):
        with pytest.raises(HTTPException) as rejected:
            await routes_staff.delete_staff("not-an-id", ADMIN)
        assert rejected.value.status_code == 400

    run_db(run)


def _pair_users_calls(monkeypatch, method, pairs):
    real = getattr(AsyncCollection, method)
    barrier = asyncio.Barrier(2)

    async def paired(self, *args, **kwargs):
        result = await real(self, *args, **kwargs)
        if self.name == "users" and pairs(*args):
            await barrier.wait()
        return result

    monkeypatch.setattr(AsyncCollection, method, paired)


def test_concurrent_admin_deletes_leave_an_enabled_admin(monkeypatch):
    first_id, second_id = ObjectId(), ObjectId()

    async def run(database):
        await database.users.insert_many([
            user_doc("First Admin", "admin", _id=first_id, deleted_at=None),
            user_doc("Second Admin", "admin", _id=second_id, deleted_at=None),
        ])
        _pair_users_calls(monkeypatch, "count_documents", lambda query: True)
        _pair_users_calls(
            monkeypatch, "update_one", lambda query, update: update.get("$set", {}).get("deleted_at") is not None,
        )
        async with asyncio.timeout(10):
            await asyncio.gather(
                routes_staff.delete_staff(str(second_id), {"_id": first_id, "role": "admin"}),
                routes_staff.delete_staff(str(first_id), {"_id": second_id, "role": "admin"}),
                return_exceptions=True,
            )

        enabled = await database.users.find({"role": "admin", "disabled_at": None, "deleted_at": None}).to_list(None)
        assert len(enabled) >= 1

    run_db(run)


def test_concurrent_staff_creation_returns_a_name_conflict(monkeypatch):
    both_checked = threading.Barrier(2, timeout=10)

    def hash_after_both_name_checks(_pin):
        both_checked.wait()
        return "hash"

    monkeypatch.setattr(routes_staff, "hash_pin", hash_after_both_name_checks)

    async def run(database):
        results = await asyncio.gather(*[
            routes_staff.create_staff(CreateStaffBody(name="Staff", role="volunteer"), ADMIN) for _ in range(2)
        ], return_exceptions=True)
        conflicts = [r for r in results if isinstance(r, HTTPException)]
        assert len(conflicts) == 1
        assert conflicts[0].status_code == 409
        assert conflicts[0].detail == "Name already exists"
        assert await database.users.count_documents({"name_normalized": "staff"}) == 1

    run_db(run)


@pytest.mark.parametrize("insert_conflict", [False, True])
def test_request_id_reuse_cannot_return_another_patients_record(monkeypatch, insert_conflict):
    async def run(database):
        camp_id, (day_id,) = await seed_camp(database)
        await database.patients.insert_one(patient_doc(
            camp_id=camp_id, camp_day_id=day_id, full_name="Another Patient",
            registration_request_id="reused-request", aadhaar_last4="1234", dob="1970-01-01",
            phone="9876543210", address="Private address", patient_qr="private-token",
        ))
        body = RegisterBody(
            full_name="New Patient", camp_day_id=str(day_id), phone="9876543210",
            registration_request_id="reused-request", aadhaar_scanned=True, aadhaar_last4="5678", dob="1980-01-01",
        )

        with pytest.raises(HTTPException) as exc:
            if insert_conflict:
                await routes_registration._insert_patient_document(
                    database, patient_doc(registration_request_id="reused-request"), body, None, camp_id,
                )
            else:
                await routes_registration._create_registration(body, None, True, None)
        assert exc.value.status_code == 409
        assert "private" not in str(exc.value.detail).lower()
        assert "registration" not in exc.value.detail
        assert await database.patients.count_documents({}) == 1

    run_camp(monkeypatch, run)


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
