import csv
import io

import pytest
from bson import ObjectId

from seed import TOMORROW, asgi_client, bearer, run_camp, seed_camp, user_doc


async def _desk(database, role="volunteer"):
    _camp_id, (day_id,) = await seed_camp(database)
    user_id = ObjectId()
    await database.users.insert_one(user_doc("Ramesh", role=role, _id=user_id))
    return day_id, bearer(user_id, "Ramesh", role)


def _typed(day_id, **fields):
    return {
        "full_name": "Kamla Bai", "age": 62, "gender": "F", "phone": "9876500011",
        "camp_day_id": str(day_id), "manual_reason": "no_card", **fields,
    }


def test_a_volunteer_types_a_patient_at_the_door_and_prints_at_once(monkeypatch):
    async def run(database):
        day_id, headers = await _desk(database)
        async with asgi_client() as client:
            r = await client.post("/api/register", json=_typed(day_id, at_door=True), headers=headers)
            assert r.status_code == 200, r.text
            reg = r.json()["registration"]
            assert reg["manual_entry"] is True
            assert reg["arrived_at"]
            printed = await client.post(f"/api/desk/print/{reg['id']}", headers=headers)
            assert printed.status_code == 200, printed.text
            assert printed.json()["registration"]["printed_at"]

    run_camp(monkeypatch, run)


@pytest.mark.parametrize("fields, status, code", [
    ({"manual_reason": "scanner unavailable"}, 422, None),
    ({"manual_reason": None}, 400, "MANUAL_ENTRY_NOT_ALLOWED"),
    ({"manual_reason": "other"}, 400, "MANUAL_NOTE_REQUIRED"),
    ({"manual_reason": "other", "manual_note": "   "}, 400, "MANUAL_NOTE_REQUIRED"),
    ({"manual_reason": "card_unreadable"}, 400, "AADHAAR_LAST4_REQUIRED"),
    ({"manual_reason": "scanner_down"}, 400, "AADHAAR_LAST4_REQUIRED"),
    ({"gender": None}, 400, "GENDER_REQUIRED"),
])
def test_a_manual_entry_is_refused_without_its_reason_and_fields(monkeypatch, fields, status, code):
    async def run(database):
        day_id, headers = await _desk(database)
        async with asgi_client() as client:
            r = await client.post("/api/register", json=_typed(day_id, **fields), headers=headers)
        assert r.status_code == status, r.text
        if code:
            assert r.json()["detail"]["code"] == code
        assert await database.patients.count_documents({}) == 0

    run_camp(monkeypatch, run)


@pytest.mark.parametrize("role", ["volunteer", "team_lead", "admin"])
def test_a_typed_pre_registration_prints_after_a_no_card_print(monkeypatch, role):
    async def run(database):
        day_id, headers = await _desk(database, role)
        async with asgi_client() as client:
            reg = (await client.post("/api/register", json=_typed(day_id), headers=headers)).json()["registration"]
            held = await client.post(f"/api/desk/arrive/{reg['id']}", headers=headers)
            assert held.status_code == 409
            assert held.json()["detail"]["code"] == "NEEDS_DOOR_SCAN"

            r = await client.post("/api/desk/no-card", json={"patient_id": reg["id"], "reason": "no_card"}, headers=headers)
            assert r.status_code == 200, r.text
            assert r.json()["registration"]["no_card_print"] is True
            assert (await client.post(f"/api/desk/arrive/{reg['id']}", headers=headers)).status_code == 200
            printed = await client.post(f"/api/desk/print/{reg['id']}", headers=headers)
            assert printed.status_code == 200, printed.text
        stored = await database.patients.find_one({})
        assert stored["no_card_print"]["reason"] == "no_card"
        assert stored["no_card_print"]["by"] == stored["created_by"]

    run_camp(monkeypatch, run)


def test_a_no_card_print_needs_a_reason_and_a_desk_role(monkeypatch):
    async def run(database):
        day_id, headers = await _desk(database)
        clinical_id = ObjectId()
        await database.users.insert_one(user_doc("Clin", role="clinical_desk_operator", _id=clinical_id))
        async with asgi_client() as client:
            reg = (await client.post("/api/register", json=_typed(day_id), headers=headers)).json()["registration"]
            refused = await client.post(
                "/api/desk/no-card", json={"patient_id": reg["id"], "reason": "no_card"},
                headers=bearer(clinical_id, "Clin", "clinical_desk_operator"),
            )
            assert refused.status_code == 403
            no_note = await client.post("/api/desk/no-card", json={"patient_id": reg["id"], "reason": "other"}, headers=headers)
            assert no_note.json()["detail"]["code"] == "MANUAL_NOTE_REQUIRED"
        assert (await database.patients.find_one({}))["identity_recheck_required"] is True

    run_camp(monkeypatch, run)


def test_a_no_card_print_is_refused_while_the_print_window_is_closed(monkeypatch):
    async def run(database):
        _camp_id, (tomorrow_id,) = await seed_camp(database, days=(TOMORROW,))
        user_id = ObjectId()
        await database.users.insert_one(user_doc("Ramesh", _id=user_id))
        headers = bearer(user_id, "Ramesh", "volunteer")
        async with asgi_client() as client:
            reg = (await client.post("/api/register", json=_typed(tomorrow_id), headers=headers)).json()["registration"]
            r = await client.post("/api/desk/no-card", json={"patient_id": reg["id"], "reason": "no_card"}, headers=headers)
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "PRINT_WINDOW_CLOSED"
        assert "no_card_print" not in await database.patients.find_one({})

    run_camp(monkeypatch, run)


def test_a_six_word_name_in_any_order_is_a_lookalike(monkeypatch):
    async def run(database):
        day_id, headers = await _desk(database)
        async with asgi_client() as client:
            await client.post("/api/register", json=_typed(day_id, full_name="Mohd Abdul Rahim Khan Pathan Saab"), headers=headers)
            r = await client.post(
                "/api/register", json=_typed(day_id, full_name="Saab Pathan Khan Rahim Abdul Mohd", phone="9876500022"),
                headers=headers,
            )
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["code"] == "LOOKALIKES"

    run_camp(monkeypatch, run)


def test_a_manual_entry_that_looks_like_a_seen_patient_shows_them_first(monkeypatch):
    async def run(database):
        day_id, headers = await _desk(database)
        async with asgi_client() as client:
            first = (await client.post(
                "/api/register", json=_typed(day_id, full_name="Ram Kumar", age=60, gender="M", at_door=True),
                headers=headers,
            )).json()["registration"]
            await database.patients.update_one({"_id": ObjectId(first["id"])}, {"$set": {"queue_status": "seen"}})
            again = _typed(day_id, full_name="kumar  RAM", age=64, gender="M", phone="9876500022", at_door=True)

            r = await client.post("/api/register", json=again, headers=headers)
            assert r.status_code == 409, r.text
            detail = r.json()["detail"]
            assert detail["code"] == "LOOKALIKES"
            assert [(p["id"], p["queue_status"]) for p in detail["registrations"]] == [(first["id"], "seen")]
            assert await database.patients.count_documents({}) == 1

            r = await client.post("/api/register", json={**again, "different_person": True}, headers=headers)
            assert r.status_code == 200, r.text
        stored = await database.patients.find_one({"_id": ObjectId(r.json()["registration"]["id"])})
        assert stored["lookalikes_overridden"] == [ObjectId(first["id"])]

    run_camp(monkeypatch, run)


def test_a_namesake_six_years_apart_is_not_a_lookalike(monkeypatch):
    async def run(database):
        day_id, headers = await _desk(database)
        async with asgi_client() as client:
            await client.post("/api/register", json=_typed(day_id, full_name="Ram Kumar", age=60), headers=headers)
            r = await client.post(
                "/api/register", json=_typed(day_id, full_name="Ram Kumar", age=66, phone="9876500022"), headers=headers,
            )
        assert r.status_code == 200, r.text
        assert (await database.patients.find_one({"age": 66})).get("lookalikes_overridden") == []

    run_camp(monkeypatch, run)


def test_the_camp_records_export_says_why_each_patient_was_typed(monkeypatch):
    async def run(database):
        day_id, headers = await _desk(database)
        async with asgi_client() as client:
            for fields in (
                {"full_name": "Kamla Bai", "manual_reason": "card_unreadable", "aadhaar_last4": "4321"},
                {"full_name": "Ram Kumar", "manual_reason": "other", "manual_note": "Card with her son", "phone": "9876500012"},
            ):
                assert (await client.post("/api/register", json=_typed(day_id, **fields), headers=headers)).status_code == 200
            admin_id = ObjectId()
            await database.users.insert_one(user_doc("Admin", role="admin", _id=admin_id))
            camp_id = (await database.camps.find_one({}))["_id"]
            export = await client.get(f"/api/exports/camp-records?camp_id={camp_id}", headers=bearer(admin_id, "Admin", "admin"))
        rows = {row["full_name"]: row for row in csv.DictReader(io.StringIO(export.text))}
        assert rows["Kamla Bai"]["manual_reason"] == "Card won't scan"
        assert rows["Ram Kumar"]["manual_reason"] == "Other: Card with her son"

    run_camp(monkeypatch, run)


@pytest.mark.parametrize("fields", [
    {"manual_reason": "no_card"},
    {"manual_reason": "card_unreadable", "aadhaar_last4": "4321"},
    {"manual_reason": "scanner_down", "aadhaar_last4": "4321"},
    {"manual_reason": "other", "manual_note": "Card left with son"},
])
def test_a_manual_entry_stores_its_reason_code_and_note(monkeypatch, fields):
    async def run(database):
        day_id, headers = await _desk(database)
        async with asgi_client() as client:
            r = await client.post("/api/register", json=_typed(day_id, **fields), headers=headers)
        assert r.status_code == 200, r.text
        stored = await database.patients.find_one({})
        assert stored["manual_reason"] == fields["manual_reason"]
        assert stored.get("manual_note") == fields.get("manual_note")

    run_camp(monkeypatch, run)
