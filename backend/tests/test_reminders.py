import os
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "snp_test")
os.environ.setdefault("ADMIN_EMAIL", "admin@snpcamps.org")
os.environ.setdefault("ADMIN_PASSWORD", "TestPass@12345")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("AADHAAR_HASH_PEPPER", "test-pepper")

from bson import ObjectId
from fastapi.testclient import TestClient

import db as db_module
import helpers
import msg91
import routes_reminders
import server as server_mod
from routes_reminders import CAMP_REMINDER, OT_REMINDER, SPECS_REMINDER
from test_adversarial_challenger import MockDB, setup_mock_db

TODAY = "2026-09-01"
TOMORROW = "2026-09-02"
SECRET = "cron-test-secret"
HOUSEHOLD = "9876500001"


def _async_noop():
    async def _inner(*_a, **_k):
        return None
    return _inner


def _client(monkeypatch, mock_db, *, msg91_on=True, secret=SECRET):
    monkeypatch.setattr(server_mod, "init_indexes", _async_noop())
    monkeypatch.setattr(server_mod, "seed_admin", _async_noop())
    monkeypatch.setattr(helpers, "today_ist_str", lambda: TODAY)
    monkeypatch.setattr(helpers, "tomorrow_ist_str", lambda: TOMORROW)
    monkeypatch.setattr(routes_reminders, "helpers", helpers)
    monkeypatch.setattr(db_module, "get_db", lambda: mock_db)
    monkeypatch.setattr(routes_reminders, "get_db", lambda: mock_db)
    monkeypatch.setenv("CRON_SECRET", secret)
    if msg91_on:
        monkeypatch.setenv("MSG91_AUTH_KEY", "auth")
        monkeypatch.setenv("MSG91_TEMPLATE_CAMP", "tmpl-camp")
        monkeypatch.setenv("MSG91_TEMPLATE_OT", "tmpl-ot")
        monkeypatch.setenv("MSG91_TEMPLATE_SPECS", "tmpl-specs")
    else:
        monkeypatch.delenv("MSG91_AUTH_KEY", raising=False)
        monkeypatch.delenv("MSG91_TEMPLATE_CAMP", raising=False)
        monkeypatch.delenv("MSG91_TEMPLATE_OT", raising=False)
        monkeypatch.delenv("MSG91_TEMPLATE_SPECS", raising=False)
    server_mod.app.router.on_startup.clear()
    return TestClient(server_mod.app, raise_server_exceptions=True)


def _calls(monkeypatch):
    captured = []

    def fake_send(reminder_type, mobile, venue):
        captured.append({"type": reminder_type, "mobile": mobile, "venue": venue})
        return f"id-{len(captured)}"

    monkeypatch.setattr(msg91, "send_dlt_sms", fake_send)
    monkeypatch.setattr(routes_reminders.msg91, "send_dlt_sms", fake_send)
    monkeypatch.setattr(routes_reminders.msg91, "configured", lambda: True)
    return captured


async def _seed_camp_household(mock_db, n_patients=4, phone=HOUSEHOLD, venue="Hall A"):
    camp_id = ObjectId()
    day_id = ObjectId()
    await mock_db.camps.insert_one({"_id": camp_id, "name": "Nadia Camp", "venue": venue, "is_active": True})
    await mock_db.camp_days.insert_one({
        "_id": day_id, "camp_id": camp_id, "day_date": TOMORROW, "seat_limit": 50,
    })
    ids = []
    for i in range(n_patients):
        pid = ObjectId()
        await mock_db.patients.insert_one({
            "_id": pid,
            "camp_id": camp_id,
            "camp_day_id": day_id,
            "phone": phone,
            "phone_normalized": phone,
            "full_name": f"P{i}",
            "reg_no": 1000 + i,
        })
        ids.append(pid)
    return camp_id, day_id, ids


def _post(client, secret=SECRET):
    return client.post("/api/cron/reminders", headers={"X-Cron-Secret": secret})


class TestReminderCopy:
    def test_approved_devanagari_strings(self):
        assert CAMP_REMINDER == "कल SNP नेत्र शिविर है। स्थान: {venue}। कृपया समय पर पहुँचें।"
        assert OT_REMINDER == "कल SNP ऑपरेशन के लिए {venue} पहुँचें। अपना टोकन साथ लाएँ।"
        assert SPECS_REMINDER == "कल SNP से चश्मा लेने {venue} पहुँचें। अपना टोकन साथ लाएँ।"


class TestReminderCronHttp:
    def test_wrong_secret_refused(self, monkeypatch):
        mock_db = setup_mock_db(monkeypatch)
        client = _client(monkeypatch, mock_db)
        r = _post(client, secret="nope")
        assert r.status_code == 401

    def test_missing_secret_refused(self, monkeypatch):
        mock_db = setup_mock_db(monkeypatch)
        client = _client(monkeypatch, mock_db)
        r = client.post("/api/cron/reminders")
        assert r.status_code == 401

    def test_msg91_unset_does_not_500(self, monkeypatch):
        mock_db = setup_mock_db(monkeypatch)
        client = _client(monkeypatch, mock_db, msg91_on=False)
        r = _post(client)
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True
        assert r.json()["sent"] == 0

    def test_household_of_four_sends_one_camp_reminder(self, monkeypatch):
        mock_db = setup_mock_db(monkeypatch)
        import asyncio
        asyncio.run(_seed_camp_household(mock_db, n_patients=4, phone=HOUSEHOLD, venue="Hall A"))
        captured = _calls(monkeypatch)
        client = _client(monkeypatch, mock_db)
        r = _post(client)
        assert r.status_code == 200, r.text
        assert r.json()["sent"] == 1
        assert captured == [{"type": "camp", "mobile": HOUSEHOLD, "venue": "Hall A"}]
        rows = mock_db.reminder_ledger.docs
        assert len(rows) == 1
        assert rows[0]["number"] == HOUSEHOLD
        assert rows[0]["reminder_type"] == "camp"
        assert rows[0]["event_date"] == TOMORROW
        assert rows[0]["send_date"] == TODAY
        assert rows[0]["status"] == "sent"
        assert rows[0]["provider_id"] == "id-1"
        assert rows[0]["copy"] == CAMP_REMINDER.format(venue="Hall A")

    def test_same_number_camp_and_ot_sends_two(self, monkeypatch):
        mock_db = setup_mock_db(monkeypatch)
        import asyncio

        async def seed():
            camp_id, day_id, ids = await _seed_camp_household(mock_db, n_patients=1, phone=HOUSEHOLD, venue="Hall A")
            ot_day = ObjectId()
            await mock_db.ot_schedule_days.insert_one({
                "_id": ot_day, "camp_id": camp_id, "day_date": TOMORROW,
                "venue": "OT Theatre", "seat_limit": 5, "seats_taken": 1,
            })
            await mock_db.deferred_slips.insert_one({
                "patient_id": ids[0], "item_type": "ot", "active": True, "cancelled": False,
                "collection_date": TOMORROW, "collection_venue": "stale",
                "ot_schedule_day_id": ot_day, "version": 1,
            })
        asyncio.run(seed())
        captured = _calls(monkeypatch)
        client = _client(monkeypatch, mock_db)
        r = _post(client)
        assert r.status_code == 200, r.text
        assert r.json()["sent"] == 2
        types = {(c["type"], c["venue"]) for c in captured}
        assert types == {("camp", "Hall A"), ("ot", "OT Theatre")}

    def test_cancelled_token_excluded_from_ot_and_specs(self, monkeypatch):
        mock_db = setup_mock_db(monkeypatch)
        import asyncio

        async def seed():
            camp_id = ObjectId()
            pid = ObjectId()
            await mock_db.camps.insert_one({"_id": camp_id, "name": "C", "venue": "Hall A"})
            await mock_db.patients.insert_one({
                "_id": pid, "camp_id": camp_id, "camp_day_id": ObjectId(),
                "phone": HOUSEHOLD, "phone_normalized": HOUSEHOLD,
            })
            await mock_db.deferred_slips.insert_one({
                "patient_id": pid, "item_type": "ot", "active": False, "cancelled": True,
                "collection_date": TOMORROW, "collection_venue": "OT Theatre", "version": 1,
            })
            await mock_db.deferred_slips.insert_one({
                "patient_id": pid, "item_type": "specs", "active": False, "cancelled": True,
                "collection_date": TOMORROW, "collection_venue": "Optical", "version": 1,
            })
        asyncio.run(seed())
        captured = _calls(monkeypatch)
        client = _client(monkeypatch, mock_db)
        r = _post(client)
        assert r.status_code == 200, r.text
        assert captured == []
        assert r.json()["sent"] == 0

    def test_missing_and_invalid_numbers_skipped(self, monkeypatch):
        mock_db = setup_mock_db(monkeypatch)
        import asyncio

        async def seed():
            camp_id = ObjectId()
            day_id = ObjectId()
            await mock_db.camps.insert_one({"_id": camp_id, "name": "C", "venue": "Hall A"})
            await mock_db.camp_days.insert_one({"_id": day_id, "camp_id": camp_id, "day_date": TOMORROW})
            await mock_db.patients.insert_one({
                "_id": ObjectId(), "camp_id": camp_id, "camp_day_id": day_id,
                "phone": None, "phone_normalized": None,
            })
            await mock_db.patients.insert_one({
                "_id": ObjectId(), "camp_id": camp_id, "camp_day_id": day_id,
                "phone": "9999999999", "phone_normalized": "9999999999",
            })
            await mock_db.patients.insert_one({
                "_id": ObjectId(), "camp_id": camp_id, "camp_day_id": day_id,
                "phone": "123", "phone_normalized": "123",
            })
        asyncio.run(seed())
        captured = _calls(monkeypatch)
        client = _client(monkeypatch, mock_db)
        r = _post(client)
        assert r.status_code == 200, r.text
        assert captured == []
        assert mock_db.reminder_ledger.docs == []

    def test_second_run_same_ist_day_emits_nothing_extra(self, monkeypatch):
        mock_db = setup_mock_db(monkeypatch)
        import asyncio
        asyncio.run(_seed_camp_household(mock_db, n_patients=4, phone=HOUSEHOLD, venue="Hall A"))
        captured = _calls(monkeypatch)
        client = _client(monkeypatch, mock_db)
        r1 = _post(client)
        r2 = _post(client)
        assert r1.status_code == 200 and r2.status_code == 200
        assert r1.json()["sent"] == 1
        assert r2.json()["sent"] == 0
        assert captured == [{"type": "camp", "mobile": HOUSEHOLD, "venue": "Hall A"}]
        assert len(mock_db.reminder_ledger.docs) == 1

    def test_specs_reminder_uses_day_venue(self, monkeypatch):
        mock_db = setup_mock_db(monkeypatch)
        import asyncio

        async def seed():
            pid = ObjectId()
            specs_day = ObjectId()
            await mock_db.patients.insert_one({
                "_id": pid, "camp_id": ObjectId(), "camp_day_id": ObjectId(),
                "phone": HOUSEHOLD, "phone_normalized": HOUSEHOLD,
            })
            await mock_db.specs_collection_days.insert_one({
                "_id": specs_day, "day_date": TOMORROW, "venue": "Optical Desk",
                "seat_limit": 10, "seats_taken": 1, "camp_id": ObjectId(),
            })
            await mock_db.deferred_slips.insert_one({
                "patient_id": pid, "item_type": "specs", "active": True, "cancelled": False,
                "collection_date": TOMORROW, "collection_venue": "stale",
                "specs_collection_day_id": specs_day, "version": 1,
            })
        asyncio.run(seed())
        captured = _calls(monkeypatch)
        client = _client(monkeypatch, mock_db)
        r = _post(client)
        assert r.status_code == 200, r.text
        assert captured == [{"type": "specs", "mobile": HOUSEHOLD, "venue": "Optical Desk"}]
        assert mock_db.reminder_ledger.docs[0]["copy"] == SPECS_REMINDER.format(venue="Optical Desk")
