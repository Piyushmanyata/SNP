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

import asyncio

from bson import ObjectId
from fastapi.testclient import TestClient

import db as db_module
import helpers
import msg91
import routes_reminders
import server as server_mod
import sms
from sms import (
    CAMP_REMINDER,
    OT_REMINDER,
    OT_TOKEN,
    REGISTRATION_CONFIRMATION,
    SPECS_REMINDER,
    SPECS_TOKEN,
)
from test_adversarial_challenger import setup_mock_db

TODAY = "2026-09-01"
TOMORROW = "2026-09-02"
SECRET = "cron-test-secret"
HOUSEHOLD = "9876500001"

TEMPLATE_ENV = {
    "MSG91_TEMPLATE_REGISTRATION": "tmpl-registration",
    "MSG91_TEMPLATE_CAMP": "tmpl-camp",
    "MSG91_TEMPLATE_OT_TOKEN": "tmpl-ot-token",
    "MSG91_TEMPLATE_OT": "tmpl-ot",
    "MSG91_TEMPLATE_SPECS_TOKEN": "tmpl-specs-token",
    "MSG91_TEMPLATE_SPECS": "tmpl-specs",
}


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
        for name, value in TEMPLATE_ENV.items():
            monkeypatch.setenv(name, value)
    else:
        monkeypatch.delenv("MSG91_AUTH_KEY", raising=False)
        for name in TEMPLATE_ENV:
            monkeypatch.delenv(name, raising=False)
    server_mod.app.router.on_startup.clear()
    return TestClient(server_mod.app, raise_server_exceptions=True)


def _calls(monkeypatch):
    captured = []

    def fake_send(message_type, mobile, reg_no, event_date, venue):
        captured.append({
            "type": message_type, "mobile": mobile, "reg_no": reg_no,
            "date": event_date, "venue": venue,
        })
        return f"id-{len(captured)}"

    monkeypatch.setattr(msg91, "send_dlt_sms", fake_send)
    monkeypatch.setattr(sms.msg91, "send_dlt_sms", fake_send)
    monkeypatch.setattr(sms.msg91, "configured", lambda: True)
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


class TestMessageCopy:
    def test_six_approved_devanagari_strings(self):
        assert REGISTRATION_CONFIRMATION == "SNP नेत्र शिविर पंजीकरण हुआ। क्रमांक {reg_no}, दिनांक {date}, स्थान {venue}।"
        assert CAMP_REMINDER == "कल SNP नेत्र शिविर। क्रमांक {reg_no}, दिनांक {date}, स्थान {venue}। समय पर पहुँचें।"
        assert OT_TOKEN == "SNP ऑपरेशन नियत। क्रमांक {reg_no}, दिनांक {date}, स्थान {venue}। टोकन साथ लाएँ।"
        assert OT_REMINDER == "कल SNP ऑपरेशन। क्रमांक {reg_no}, दिनांक {date}, स्थान {venue}। टोकन साथ लाएँ।"
        assert SPECS_TOKEN == "SNP चश्मा वितरण नियत। क्रमांक {reg_no}, दिनांक {date}, स्थान {venue}। टोकन साथ लाएँ।"
        assert SPECS_REMINDER == "कल SNP से चश्मा लें। क्रमांक {reg_no}, दिनांक {date}, स्थान {venue}। टोकन साथ लाएँ।"

    def test_every_message_fits_two_ucs2_segments(self):
        rendered = [
            copy.format(reg_no=999999, date="2026-09-02", venue="Sikar Bhawan Kolkata")
            for copy in sms.MESSAGE_COPY.values()
        ]
        assert all(len(text) <= 134 for text in rendered), [len(t) for t in rendered]


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

    def test_household_of_four_sends_four_camp_reminders(self, monkeypatch):
        mock_db = setup_mock_db(monkeypatch)
        asyncio.run(_seed_camp_household(mock_db, n_patients=4, phone=HOUSEHOLD, venue="Hall A"))
        captured = _calls(monkeypatch)
        client = _client(monkeypatch, mock_db)
        r = _post(client)
        assert r.status_code == 200, r.text
        assert r.json()["sent"] == 4
        assert [c["mobile"] for c in captured] == [HOUSEHOLD] * 4
        assert sorted(c["reg_no"] for c in captured) == [1000, 1001, 1002, 1003]
        assert {c["type"] for c in captured} == {"camp"}
        assert {c["date"] for c in captured} == {TOMORROW}
        assert len(mock_db.reminder_ledger.docs) == 4

    def test_camp_reminder_ledger_row_carries_reg_no_copy(self, monkeypatch):
        mock_db = setup_mock_db(monkeypatch)
        asyncio.run(_seed_camp_household(mock_db, n_patients=1, phone=HOUSEHOLD, venue="Hall A"))
        _calls(monkeypatch)
        client = _client(monkeypatch, mock_db)
        assert _post(client).status_code == 200
        row = mock_db.reminder_ledger.docs[0]
        assert row["message_type"] == "camp"
        assert row["event_date"] == TOMORROW
        assert row["number"] == HOUSEHOLD
        assert row["status"] == "sent"
        assert row["provider_id"] == "id-1"
        assert row["copy"] == CAMP_REMINDER.format(reg_no=1000, date=TOMORROW, venue="Hall A")

    def test_same_patient_camp_and_ot_sends_two(self, monkeypatch):
        mock_db = setup_mock_db(monkeypatch)

        async def seed():
            camp_id, _day_id, ids = await _seed_camp_household(mock_db, n_patients=1, phone=HOUSEHOLD, venue="Hall A")
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
        assert {(c["type"], c["venue"]) for c in captured} == {("camp", "Hall A"), ("ot", "OT Theatre")}

    def test_cancelled_token_excluded_from_ot_and_specs(self, monkeypatch):
        mock_db = setup_mock_db(monkeypatch)

        async def seed():
            camp_id = ObjectId()
            pid = ObjectId()
            await mock_db.camps.insert_one({"_id": camp_id, "name": "C", "venue": "Hall A"})
            await mock_db.patients.insert_one({
                "_id": pid, "camp_id": camp_id, "camp_day_id": ObjectId(), "reg_no": 7,
                "phone": HOUSEHOLD, "phone_normalized": HOUSEHOLD,
            })
            await mock_db.deferred_slips.insert_one({
                "patient_id": pid, "item_type": "ot", "active": False, "cancelled": True,
                "collection_date": TOMORROW, "collection_venue": "OT Theatre", "version": 1,
            })
            await mock_db.deferred_slips.insert_one({
                "patient_id": pid, "item_type": "specs_made", "active": False, "cancelled": True,
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

        async def seed():
            camp_id = ObjectId()
            day_id = ObjectId()
            await mock_db.camps.insert_one({"_id": camp_id, "name": "C", "venue": "Hall A"})
            await mock_db.camp_days.insert_one({"_id": day_id, "camp_id": camp_id, "day_date": TOMORROW})
            for reg_no, phone in ((1, None), (2, "9999999999"), (3, "123")):
                await mock_db.patients.insert_one({
                    "_id": ObjectId(), "camp_id": camp_id, "camp_day_id": day_id, "reg_no": reg_no,
                    "phone": phone, "phone_normalized": phone,
                })
        asyncio.run(seed())
        captured = _calls(monkeypatch)
        client = _client(monkeypatch, mock_db)
        r = _post(client)
        assert r.status_code == 200, r.text
        assert captured == []
        assert mock_db.reminder_ledger.docs == []

    def test_second_run_same_event_date_emits_nothing_extra(self, monkeypatch):
        mock_db = setup_mock_db(monkeypatch)
        asyncio.run(_seed_camp_household(mock_db, n_patients=4, phone=HOUSEHOLD, venue="Hall A"))
        captured = _calls(monkeypatch)
        client = _client(monkeypatch, mock_db)
        r1 = _post(client)
        r2 = _post(client)
        assert r1.json()["sent"] == 4
        assert r2.json()["sent"] == 0
        assert len(captured) == 4
        assert len(mock_db.reminder_ledger.docs) == 4

    def test_specs_reminder_uses_day_venue(self, monkeypatch):
        mock_db = setup_mock_db(monkeypatch)

        async def seed():
            pid = ObjectId()
            specs_day = ObjectId()
            await mock_db.patients.insert_one({
                "_id": pid, "camp_id": ObjectId(), "camp_day_id": ObjectId(), "reg_no": 42,
                "phone": HOUSEHOLD, "phone_normalized": HOUSEHOLD,
            })
            await mock_db.specs_collection_days.insert_one({
                "_id": specs_day, "day_date": TOMORROW, "venue": "Optical Desk",
                "seat_limit": 10, "seats_taken": 1, "camp_id": ObjectId(),
            })
            await mock_db.deferred_slips.insert_one({
                "patient_id": pid, "item_type": "specs_made", "active": True, "cancelled": False,
                "collection_date": TOMORROW, "collection_venue": "stale",
                "specs_collection_day_id": specs_day, "version": 1,
            })
        asyncio.run(seed())
        captured = _calls(monkeypatch)
        client = _client(monkeypatch, mock_db)
        r = _post(client)
        assert r.status_code == 200, r.text
        assert captured == [{
            "type": "specs", "mobile": HOUSEHOLD, "reg_no": 42,
            "date": TOMORROW, "venue": "Optical Desk",
        }]
        assert mock_db.reminder_ledger.docs[0]["copy"] == SPECS_REMINDER.format(
            reg_no=42, date=TOMORROW, venue="Optical Desk"
        )
