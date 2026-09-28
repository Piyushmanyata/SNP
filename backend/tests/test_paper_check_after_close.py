from datetime import timedelta

import pytest
from bson import ObjectId

from conftest import advance_clock
from seed import asgi_client, bearer, run_camp, seed_camp, user_doc


async def _desk(database, client):
    _camp_id, (day_id,) = await seed_camp(database)
    volunteer, admin = ObjectId(), ObjectId()
    await database.users.insert_many([user_doc("Ramesh", _id=volunteer), user_doc("Admin", role="admin", _id=admin)])
    headers = bearer(volunteer, "Ramesh", "volunteer")
    patients = []
    for name, phone in (("Kamla Bai", "9876500011"), ("Ram Kumar", "9876500012")):
        r = await client.post("/api/register", json={
            "full_name": name, "age": 62, "gender": "F", "phone": phone, "camp_day_id": str(day_id),
            "manual_reason": "no_card", "at_door": True,
        }, headers=headers)
        assert r.status_code == 200, r.text
        patients.append(r.json()["registration"])

    async def close_window():
        r = await client.patch(
            f"/api/camps/days/{day_id}/print-window", json={"mode": "disable"}, headers=bearer(admin, "Admin", "admin"),
        )
        assert r.status_code == 200, r.text

    return headers, patients, close_window


async def _fetch(client, headers, patient):
    r = await client.get(f"/api/desk/print/{patient['id']}", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["prescription"]["sheet_stamp"]


async def _record(client, headers, patient, stamp):
    return await client.post(f"/api/desk/print/{patient['id']}", json={"sheet_stamp": stamp}, headers=headers)


def test_a_sheet_fetched_while_open_is_recorded_after_the_window_closes(monkeypatch):
    async def run(database):
        async with asgi_client() as client:
            headers, (patient, _other), close_window = await _desk(database, client)
            stamp = await _fetch(client, headers, patient)
            await close_window()
            r = await _record(client, headers, patient, stamp)
        assert r.status_code == 200, r.text
        assert r.json()["registration"]["printed_at"]
        assert (await database.patients.find_one({"_id": ObjectId(patient["id"])}))["printed_at"]

    run_camp(monkeypatch, run)


@pytest.mark.parametrize("stamp_for", ["missing", "tampered", "other patient", "garbage"])
def test_a_paper_check_after_close_without_a_good_stamp_is_refused(monkeypatch, stamp_for):
    async def run(database):
        async with asgi_client() as client:
            headers, (patient, other), close_window = await _desk(database, client)
            stamp = await _fetch(client, headers, patient)
            others = await _fetch(client, headers, other)
            await close_window()
            sent = {
                "missing": None,
                "tampered": stamp[:-1] + ("0" if stamp[-1] != "0" else "1"),
                "other patient": others,
                "garbage": "not-a-stamp",
            }[stamp_for]
            r = await _record(client, headers, patient, sent)
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["code"] == "PRINT_WINDOW_CLOSED"
        assert (await database.patients.find_one({"_id": ObjectId(patient["id"])}))["printed_at"] is None

    run_camp(monkeypatch, run)


def test_no_sheet_is_fetched_after_the_window_closes(monkeypatch):
    async def run(database):
        async with asgi_client() as client:
            headers, (patient, _other), close_window = await _desk(database, client)
            await close_window()
            r = await client.get(f"/api/desk/print/{patient['id']}", headers=headers)
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["code"] == "PRINT_WINDOW_CLOSED"

    run_camp(monkeypatch, run)


def test_a_sheet_fetched_on_an_earlier_day_is_refused(monkeypatch):
    async def run(database):
        async with asgi_client() as client:
            headers, (patient, _other), _close_window = await _desk(database, client)
            stamp = await _fetch(client, headers, patient)
            advance_clock(timedelta(days=1))
            r = await _record(client, headers, patient, stamp)
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["code"] == "PRINT_WINDOW_CLOSED"

    run_camp(monkeypatch, run)


@pytest.mark.parametrize("change, code", [
    ({"queue_status": "seen"}, "ALREADY_SEEN"),
    ({"identity_recheck_required": True}, "NEEDS_DOOR_SCAN"),
])
def test_a_good_stamp_still_obeys_the_other_refusals(monkeypatch, change, code):
    async def run(database):
        async with asgi_client() as client:
            headers, (patient, _other), close_window = await _desk(database, client)
            stamp = await _fetch(client, headers, patient)
            await close_window()
            await database.patients.update_one({"_id": ObjectId(patient["id"])}, {"$set": change})
            r = await _record(client, headers, patient, stamp)
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["code"] == code

    run_camp(monkeypatch, run)


def test_a_printed_sheet_carries_no_stamp(monkeypatch):
    async def run(database):
        async with asgi_client() as client:
            headers, (patient, _other), _close_window = await _desk(database, client)
            stamp = await _fetch(client, headers, patient)
            assert (await _record(client, headers, patient, stamp)).status_code == 200
            reprint = await client.get(f"/api/desk/print/{patient['id']}", headers=headers)
        assert reprint.status_code == 200, reprint.text
        assert "sheet_stamp" not in reprint.json()["prescription"]

    run_camp(monkeypatch, run)
