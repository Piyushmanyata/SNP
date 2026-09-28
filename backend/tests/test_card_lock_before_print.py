from uuid import uuid4

import pytest
from bson import ObjectId

from seed import CARD, TODAY, TOMORROW, asgi_client, bearer, run_camp, seed_camp, user_doc

CARD_LAST4 = "1234"


async def _desk(database, days=None):
    _camp_id, day_ids = await seed_camp(database, **({"days": days} if days else {}))
    user_id = ObjectId()
    await database.users.insert_one(user_doc("Ramesh", _id=user_id))
    return day_ids, bearer(user_id, "Ramesh", "volunteer")


def _scanned(day_id, **fields):
    return {
        "full_name": "Sunita Devi", "phone": "9876500001", "camp_day_id": str(day_id),
        "aadhaar_scanned": True, "qr_payload": CARD, **fields,
    }


async def _no_card(client, headers, patient_id, reason="no_card", **fields):
    return await client.post("/api/desk/no-card", json={"patient_id": patient_id, "reason": reason, **fields}, headers=headers)


def test_a_scanned_booking_arrives_only_after_a_no_card_print(monkeypatch):
    async def run(database):
        (day_id,), headers = await _desk(database)
        async with asgi_client() as client:
            reg = (await client.post("/api/register", json=_scanned(day_id), headers=headers)).json()["registration"]
            held = await client.post(f"/api/desk/arrive/{reg['id']}", headers=headers)
            assert held.status_code == 409, held.text
            assert held.json()["detail"]["code"] == "NEEDS_DOOR_SCAN"
            assert (await database.patients.find_one({}))["arrived_at"] is None

            assert (await _no_card(client, headers, reg["id"])).status_code == 200
            arrived = await client.post(f"/api/desk/arrive/{reg['id']}", headers=headers)
            assert arrived.status_code == 200, arrived.text
            assert arrived.json()["registration"]["arrived_at"]
            assert arrived.json()["prescription"]["reg_no"] == reg["reg_no"]

    run_camp(monkeypatch, run)


@pytest.mark.parametrize("reason, fields", [
    ("no_card", {}),
    ("card_unreadable", {"aadhaar_last4": CARD_LAST4}),
    ("scanner_down", {"aadhaar_last4": CARD_LAST4}),
    ("other", {"note": "Card left at home"}),
])
def test_a_scanned_booking_takes_a_no_card_print_with_each_reason(monkeypatch, reason, fields):
    async def run(database):
        (day_id,), headers = await _desk(database)
        async with asgi_client() as client:
            reg = (await client.post("/api/register", json=_scanned(day_id), headers=headers)).json()["registration"]
            r = await _no_card(client, headers, reg["id"], reason, **fields)
        assert r.status_code == 200, r.text
        assert r.json()["registration"]["no_card_print"] is True
        stored = await database.patients.find_one({})
        assert stored["no_card_print"]["reason"] == reason
        assert stored["no_card_print"]["note"] == fields.get("note")

    run_camp(monkeypatch, run)


@pytest.mark.parametrize("reason", ["card_unreadable", "scanner_down"])
@pytest.mark.parametrize("last4, status, code", [
    (None, 400, "AADHAAR_LAST4_REQUIRED"),
    ("9999", 409, "NO_CARD_LAST4_MISMATCH"),
])
def test_a_card_in_hand_must_match_the_booking_s_last_4(monkeypatch, reason, last4, status, code):
    async def run(database):
        (day_id,), headers = await _desk(database)
        async with asgi_client() as client:
            reg = (await client.post("/api/register", json=_scanned(day_id), headers=headers)).json()["registration"]
            r = await _no_card(client, headers, reg["id"], reason, **({"aadhaar_last4": last4} if last4 else {}))
            assert r.status_code == status, r.text
            assert r.json()["detail"]["code"] == code
            assert "no_card_print" not in await database.patients.find_one({})
            assert (await client.post(f"/api/desk/arrive/{reg['id']}", headers=headers)).status_code == 409

    run_camp(monkeypatch, run)


def test_a_no_card_print_never_marks_the_card_scanned(monkeypatch):
    async def run(database):
        (day_id,), headers = await _desk(database)
        async with asgi_client() as client:
            reg = (await client.post("/api/register", json={
                "full_name": "Kamla Bai", "age": 62, "gender": "F", "phone": "9876500011",
                "camp_day_id": str(day_id), "manual_reason": "card_unreadable", "aadhaar_last4": "4321",
            }, headers=headers)).json()["registration"]
            r = await _no_card(client, headers, reg["id"], "card_unreadable", aadhaar_last4="0000")
            assert r.status_code == 200, r.text
            await client.post(f"/api/desk/arrive/{reg['id']}", headers=headers)
        stored = await database.patients.find_one({})
        assert stored["arrived_at"]
        assert stored["aadhaar_scanned"] is False
        assert stored["person_id"] is None
        assert stored["identity_recheck_required"] is False

    run_camp(monkeypatch, run)


def test_a_no_card_print_is_refused_once_the_doctor_has_seen_the_patient(monkeypatch):
    async def run(database):
        (day_id,), headers = await _desk(database)
        async with asgi_client() as client:
            reg = (await client.post("/api/register", json=_scanned(day_id), headers=headers)).json()["registration"]
            await database.patients.update_one({}, {"$set": {"queue_status": "seen", "arrived_at": None}})
            r = await _no_card(client, headers, reg["id"])
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["code"] == "ALREADY_SEEN"
        assert "no_card_print" not in await database.patients.find_one({})

    run_camp(monkeypatch, run)


def test_a_scanned_door_walk_in_arrives_in_the_request_that_registers_it(monkeypatch):
    async def run(database):
        (day_id,), headers = await _desk(database)
        body = _scanned(day_id, at_door=True, registration_request_id=str(uuid4()))
        async with asgi_client() as client:
            first = await client.post("/api/register", json=body, headers=headers)
            assert first.status_code == 200, first.text
            reg = first.json()["registration"]
            assert reg["arrived_at"]
            assert reg["queue_status"] == "arrived"
            replay = await client.post("/api/register", json=body, headers=headers)
            assert replay.status_code == 200, replay.text
            assert replay.json()["registration"]["arrived_at"] == reg["arrived_at"]
            printed = await client.post(f"/api/desk/print/{reg['id']}", headers=headers)
            assert printed.status_code == 200, printed.text
        assert await database.patients.count_documents({}) == 1

    run_camp(monkeypatch, run)


def test_a_scanned_door_walk_in_is_for_the_operating_day_only(monkeypatch):
    async def run(database):
        (_today, tomorrow), headers = await _desk(database, days=(TODAY, TOMORROW))
        async with asgi_client() as client:
            r = await client.post("/api/register", json=_scanned(tomorrow, at_door=True), headers=headers)
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["code"] == "NOT_OPERATING_DAY"
        assert await database.patients.count_documents({}) == 0

    run_camp(monkeypatch, run)


def test_a_self_registration_never_arrives_at_the_door(monkeypatch):
    async def run(database):
        (day_id,), _headers = await _desk(database)
        async with asgi_client() as client:
            r = await client.post("/api/self-register", json=_scanned(day_id, at_door=True))
        assert r.status_code == 200, r.text
        assert (await database.patients.find_one({}))["arrived_at"] is None

    run_camp(monkeypatch, run)
