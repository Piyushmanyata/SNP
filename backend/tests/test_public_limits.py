import asyncio
from xml.etree.ElementTree import Element, tostring

import pytest
from bson import ObjectId
from fastapi import HTTPException
from pymongo.asynchronous.collection import AsyncCollection

import aadhaar_extract
import routes_auth
import routes_registration
from conftest import CommandLog
from helpers import normalize_name, normalize_phone
from models import RegisterBody
from models import ScanBody
from routes_desk import arrive, preview_prescription, scan
from routes_registration import desk_register
from seed import ACTOR, ADMIN, CARD, NOW, TODAY, Request, asgi_client, bearer, day, http, recorder, register, run_camp, seed_camp, user_doc


def card(name, uid, dob="1970-02-02", gender="F", street="Sikar"):
    return tostring(Element("PrintLetterBarcodeData", name=name, gender=gender, dob=dob, uid=uid, street=street), encoding="unicode")


@pytest.mark.parametrize("raw, canonical", [
    ("9876543210", "9876543210"),
    ("+91 98765 43210", "9876543210"),
    ("+91-98765-43210", "9876543210"),
    ("098765 43210", "9876543210"),
    ("919876543210", "9876543210"),
    ("98765432101", None),
    ("1234567890", None),
    ("0091 98765 43210", None),
    ("98765", None),
])
def test_the_household_phone_rule_keeps_the_ten_local_digits_or_refuses(raw, canonical):
    assert normalize_phone(raw) == canonical


def test_names_keep_every_script_and_compare_after_nfc():
    assert normalize_name("  સુનીતા   દેવી ") == "સુનીતા દેવી"
    assert normalize_name("சுனிதா") == "சுனிதா"
    assert normalize_name("José") == normalize_name("José") == "josé"
    assert normalize_name("R. K. Singh-Rao") == "r k singhrao"


LONG = "x" * 16001


@pytest.mark.parametrize("path, payload", [
    ("/api/aadhaar/decode", {"payload": LONG}),
    ("/api/self-register", {"full_name": "A", "camp_day_id": "x", "qr_payload": LONG}),
    ("/api/self-register", {"full_name": "A" * 101, "camp_day_id": "x"}),
    ("/api/self-register", {"full_name": "A", "camp_day_id": "x", "address": "a" * 301}),
    ("/api/self-register", {"full_name": "A", "camp_day_id": "x", "phone": "9" * 21}),
    ("/api/self-register", {"full_name": "A", "camp_day_id": "x", "gender": "X"}),
    ("/api/self-register", {"full_name": "A", "camp_day_id": "x", "registration_request_id": "door-1"}),
    ("/api/self-register", {"full_name": "A", "camp_day_id": "x", "manual_reason": "r" * 201}),
])
def test_public_bodies_are_bounded(monkeypatch, path, payload):
    async def body(database, client):
        response = await client.post(path, json=payload)
        assert response.status_code == 422, response.text

    http(monkeypatch, body)


def test_staff_bodies_are_bounded(monkeypatch):
    async def body(database, client):
        admin = (await database.users.insert_one(user_doc("Admin", "admin"))).inserted_id
        headers = bearer(admin, "Admin", "admin")
        for path, payload in [
            ("/api/desk/scan", {"payload": LONG}),
            ("/api/desk/scan/confirm", {"patient_id": str(ObjectId()), "payload": LONG}),
            ("/api/camps", {"name": "C" * 81, "venue": "Hall", "camp_date": TODAY}),
            ("/api/staff", {"name": "S" * 81, "role": "volunteer"}),
            ("/api/desk/no-card", {"patient_id": str(ObjectId()), "reason": "other", "note": "n" * 201}),
        ]:
            response = await client.post(path, json=payload, headers=headers)
            assert response.status_code == 422, (path, response.text)

    http(monkeypatch, body)


def test_staff_decode_is_never_limited_but_anonymous_decode_is(monkeypatch):
    routes_registration._decode_rl.clear()

    async def body(database, client):
        staff = (await database.users.insert_one(user_doc("Desk", "volunteer"))).inserted_id
        for _ in range(61):
            assert (await client.post("/api/aadhaar/decode", json={"payload": CARD}, headers=bearer(staff, "Desk", "volunteer"))).status_code == 200
        for _ in range(60):
            assert (await client.post("/api/aadhaar/decode", json={"payload": CARD})).status_code == 200
        assert (await client.post("/api/aadhaar/decode", json={"payload": CARD})).status_code == 429

    http(monkeypatch, body)


def test_self_register_limits_one_network_and_one_household(monkeypatch):
    sent = recorder(monkeypatch)
    routes_registration._rl.clear()

    async def body(database, client):
        _camp_id, (day_id,) = await seed_camp(database, days=(day(1),))
        for i in range(6):
            ok = await client.post("/api/self-register", json={
                "full_name": "x", "phone": "9876500020", "camp_day_id": str(day_id),
                "qr_payload": card(f"Member {'abcdefg'[i]}", f"55556666{1000 + i}"),
            })
            assert ok.status_code == 200, ok.text
        seventh = await client.post("/api/self-register", json={
            "full_name": "x", "phone": "+91 98765 00020", "camp_day_id": str(day_id),
            "qr_payload": card("Member Seven", "555566661007"),
        })
        assert seventh.status_code == 409 and seventh.json()["detail"]["code"] == "HOUSEHOLD_LIMIT"
        assert await database.patients.count_documents({}) == 6
        assert len(sent) == 6
        for i in range(24):
            await client.post("/api/self-register", json={"full_name": "x", "camp_day_id": str(day_id), "qr_payload": "not a card"})
        assert (await client.post("/api/self-register", json={"full_name": "x", "camp_day_id": str(day_id), "qr_payload": "no"})).status_code == 429

    http(monkeypatch, body)


def test_a_number_gets_at_most_six_registration_sms_a_day(monkeypatch):
    sent = recorder(monkeypatch)

    async def run(database):
        _camp_id, (day_id,) = await seed_camp(database, days=(day(1),))
        for i in range(7):
            await register(day_id, full_name=f"Family {'abcdefg'[i]}", phone="9876500030", aadhaar_scanned=True,
                           aadhaar_last4=f"{4000 + i}", dob="1970-02-02")
        assert len(sent) == 6
        capped = await database.reminder_ledger.find_one({"status": "skipped"})
        assert capped["reason"] == "daily_cap" and capped["message_type"] == "registration"

    run_camp(monkeypatch, run)


def test_a_stalled_upload_does_not_make_a_second_upload_busy(monkeypatch):
    async def fake_worker(document, password):
        return {"outcome": "card", "bytes": len(document)}

    monkeypatch.setattr(aadhaar_extract, "run_worker", fake_worker)

    class Stalled:
        client = type("C", (), {"host": "198.51.100.5"})()
        headers = {}

        async def stream(self):
            yield b"\xff\xd8\xff"
            await asyncio.sleep(3600)

    class Quick:
        client = type("C", (), {"host": "198.51.100.6"})()
        headers = {}

        async def stream(self):
            yield b"\xff\xd8\xff" + b"0" * 10

        async def receive(self):
            await asyncio.sleep(3600)

    async def main():
        stalled = asyncio.create_task(aadhaar_extract.extract_document(Stalled()))
        await asyncio.sleep(0.05)
        result = await asyncio.wait_for(aadhaar_extract.extract_document(Quick()), 5)
        stalled.cancel()
        return result

    assert asyncio.run(main())["outcome"] == "card"


def test_a_year_only_birth_date_is_stored_as_the_first_of_january(monkeypatch):
    async def run(database):
        _camp_id, (day_id,) = await seed_camp(database, days=(day(1),))
        saved = await register(day_id, full_name="Year Only", age=None, dob="1970", manual_reason="no_card")
        assert saved["dob"] == "1970-01-01"

    run_camp(monkeypatch, run)


def test_arrival_needs_a_scan_or_a_no_card_print_for_a_typed_pre_registration(monkeypatch):
    async def run(database):
        _camp_id, (day_id,) = await seed_camp(database)
        manual = await register(day_id, full_name="Phone Booking", age=40, manual_reason="no_card")
        with pytest.raises(HTTPException) as exc:
            await arrive(manual["id"], actor=ACTOR)
        assert exc.value.status_code == 409 and exc.value.detail["code"] == "NEEDS_DOOR_SCAN"
        await database.patients.update_one({"_id": ObjectId(manual["id"])}, {"$set": {"no_card_print": {"reason": "no_card"}}})
        assert (await arrive(manual["id"], actor=ACTOR))["registration"]["arrived_at"]

        at_door = await desk_register(RegisterBody(
            full_name="Door Walk In", age=33, gender="M", phone="9876500031", camp_day_id=str(day_id),
            manual_reason="no_card", at_door=True,
        ), Request(), actor=ACTOR, background_tasks=None)
        assert at_door["registration"]["arrived_at"]

    run_camp(monkeypatch, run)


def test_a_prescription_preview_stays_in_the_active_camp(monkeypatch):
    async def run(database):
        _camp_id, (day_id,) = await seed_camp(database)
        other_camp = ObjectId()
        patient = await register(day_id, full_name="Elsewhere", aadhaar_scanned=True, aadhaar_last4="7788", dob="1970-02-02")
        await database.patients.update_one({"_id": ObjectId(patient["id"])}, {"$set": {"camp_id": other_camp, "arrived_at": NOW}})
        with pytest.raises(HTTPException) as exc:
            await preview_prescription(patient["id"], actor=ADMIN)
        assert exc.value.detail["code"] == "WRONG_CAMP"

    run_camp(monkeypatch, run)


def test_a_racing_camp_day_create_is_a_conflict_not_a_crash(monkeypatch):
    real = AsyncCollection.find_one
    raced = []

    async def racing(self, *args, **kwargs):
        if self.name == "camp_days" and not raced:
            raced.append(True)
            return None
        return await real(self, *args, **kwargs)

    async def body(database, client):
        admin = (await database.users.insert_one(user_doc("Admin", "admin"))).inserted_id
        camp_id, _days = await seed_camp(database, days=(day(3),))
        monkeypatch.setattr(AsyncCollection, "find_one", racing)
        response = await client.post("/api/camps/days", json={"camp_id": str(camp_id), "day_date": day(3), "seat_limit": 9}, headers=bearer(admin, "Admin", "admin"))
        assert response.status_code == 409, response.text

    http(monkeypatch, body)


def test_public_occupancy_reads_the_day_counters(monkeypatch):
    log = CommandLog()

    async def run(database):
        _camp_id, (day_id,) = await seed_camp(database, days=(day(1),))
        await database.camp_days.update_one({"_id": day_id}, {"$set": {"booked": 7}})
        log.commands.clear()
        async with asgi_client() as client:
            data = (await client.get("/api/camps/active/public")).json()
        assert data["total_registered"] == 7 and data["days"][0]["registered"] == 7
        assert [name for name, target in log.commands if target == "patients"] == []

    run_camp(monkeypatch, run, listener=log)


def test_public_occupancy_marks_the_camp_days_that_have_passed(monkeypatch):
    async def run(database):
        await seed_camp(database, days=(day(-1), TODAY, day(1)))
        async with asgi_client() as client:
            data = (await client.get("/api/camps/active/public")).json()
        assert [(d["day_date"], d["is_past"]) for d in data["days"]] == [(day(-1), True), (TODAY, False), (day(1), False)]

    run_camp(monkeypatch, run)


def test_login_answers_with_a_cookie_only_and_checks_unknown_names_in_constant_time(monkeypatch):
    checked = []
    real = routes_auth.verify_pin

    def counting(pin, hashed):
        checked.append(hashed)
        return real(pin, hashed)

    monkeypatch.setattr(routes_auth, "verify_pin", counting)

    async def body(database, client):
        from security import hash_pin
        await database.users.insert_one(user_doc("Known", pin_hash=hash_pin("2580"), must_change_pin=False))
        ok = await client.post("/api/auth/login", json={"name": "Known", "pin": "2580"})
        assert ok.status_code == 200 and "access_token" not in ok.json()
        assert "access_token" in ok.cookies
        changed = await client.post("/api/auth/change-pin", json={"current_pin": "2580", "new_pin": "3691"})
        assert changed.status_code == 200 and "access_token" not in changed.json()
        assert (await client.post("/api/auth/login", json={"name": "Nobody", "pin": "2580"})).status_code == 401
        assert len(checked) == 3

    http(monkeypatch, body)


def test_a_card_with_a_long_address_scans_and_registers(monkeypatch):
    async def run(database):
        _camp_id, (day_id,) = await seed_camp(database)
        payload = card("Long Address", "555566669999", street="S" * 400)
        at_door = await scan(ScanBody(payload=payload), actor=ACTOR)
        assert at_door["outcome"] == "no_match" and len(at_door["card"]["address"]) == 300
        saved = await register(day_id, full_name="Long Address", aadhaar_scanned=True, qr_payload=payload,
                               address=at_door["card"]["address"], aadhaar_last4="9999", dob="1970-02-02")
        assert len(saved["address"]) == 300

    run_camp(monkeypatch, run)


def test_the_door_types_entries_only_for_the_operating_day(monkeypatch):
    async def run(database):
        _camp_id, (_today, tomorrow) = await seed_camp(database, days=(TODAY, day(1)))
        with pytest.raises(HTTPException) as exc:
            await desk_register(RegisterBody(
                full_name="Door Tomorrow", age=33, gender="M", phone="9876500032", camp_day_id=str(tomorrow),
                manual_reason="no_card", at_door=True,
            ), Request(), actor=ACTOR, background_tasks=None)
        assert exc.value.status_code == 409 and exc.value.detail["code"] == "NOT_OPERATING_DAY"
        assert await database.patients.count_documents({}) == 0

    run_camp(monkeypatch, run)
