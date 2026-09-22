"""Specs collection days are date/venue/time windows with no capacity."""
import asyncio
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "snp_test")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("AADHAAR_HASH_PEPPER", "test-pepper")
os.environ.setdefault("COOKIE_SECURE", "false")

from bson import ObjectId
from fastapi.testclient import TestClient

import db as db_module
import helpers
import routes_auth
import routes_clinical
import routes_desk
import routes_registration
import routes_reports
import routes_staff
import security
import server as server_mod
from helpers import IST
from routes_clinical import record_fulfilment
from security import hash_pin
from test_adversarial_challenger import setup_mock_db
from test_camp_lifecycle import RX, _fulfil, _recorder, _seen_patient_with_transcription


def _async_noop():
    async def _inner(*_a, **_k):
        return None
    return _inner


def _patch_db(monkeypatch, mock_db):
    for mod in (
        db_module, routes_staff, routes_auth, routes_clinical, routes_reports,
        routes_desk, routes_registration, security,
    ):
        monkeypatch.setattr(mod, "get_db", lambda: mock_db)
    return mock_db


def _client(monkeypatch, mock_db):
    monkeypatch.setattr(server_mod, "init_indexes", _async_noop())
    monkeypatch.setattr(server_mod, "seed_admin", _async_noop())
    _patch_db(monkeypatch, mock_db)
    server_mod.app.router.on_startup.clear()
    return TestClient(server_mod.app, raise_server_exceptions=True)


def _auth(user_id, name, role):
    token = security.create_access_token(str(user_id), name, role)
    return {"Authorization": f"Bearer {token}"}


async def _admin(mock_db):
    admin_id = ObjectId()
    await mock_db.users.insert_one({
        "_id": admin_id, "name": "admin", "name_normalized": "admin",
        "pin_hash": hash_pin("2468"), "role": "admin", "disabled_at": None,
    })
    return admin_id


async def _active_camp(mock_db, name="Sikar Camp"):
    camp_id = ObjectId()
    await mock_db.camps.insert_one({
        "_id": camp_id, "name": name, "venue": "Sikar Bhawan", "is_active": True,
    })
    return camp_id


def _future_date():
    return (datetime.now(IST) + timedelta(days=7)).strftime("%Y-%m-%d")


def test_specs_create_update_list_window_contract(monkeypatch):
    async def run():
        mock_db = setup_mock_db(monkeypatch)
        admin_id = await _admin(mock_db)
        camp_id = await _active_camp(mock_db)
        client = _client(monkeypatch, mock_db)
        headers = _auth(admin_id, "admin", "admin")
        day = _future_date()

        missing = client.post("/api/clinical/specs-days", json={
            "camp_id": str(camp_id), "day_date": day, "venue": "Optical",
        }, headers=headers)
        assert missing.status_code == 400

        inverted = client.post("/api/clinical/specs-days", json={
            "camp_id": str(camp_id), "day_date": day, "venue": "  Optical Desk  ",
            "start_time": "14:00", "end_time": "14:00",
        }, headers=headers)
        assert inverted.status_code == 400

        created = client.post("/api/clinical/specs-days", json={
            "camp_id": str(camp_id), "day_date": day, "venue": "  Optical Desk  ",
            "start_time": "10:00", "end_time": "12:30",
            "seat_limit": 12,
        }, headers=headers)
        assert created.status_code == 200
        row = created.json()["specs_day"]
        assert row["venue"] == "Optical Desk"
        assert row["start_time"] == "10:00"
        assert row["end_time"] == "12:30"
        assert row["day_date"] == day
        assert "seat_limit" not in row
        assert "seats_taken" not in row
        assert "seats_free" not in row
        stored = await mock_db.specs_collection_days.find_one({"_id": ObjectId(row["id"])})
        assert "seat_limit" not in stored
        assert "seats_taken" not in stored

        updated = client.post("/api/clinical/specs-days", json={
            "camp_id": str(camp_id), "day_date": day, "venue": "New Optical",
            "start_time": "11:00", "end_time": "13:00",
        }, headers=headers)
        assert updated.status_code == 200
        assert updated.json()["specs_day"]["id"] == row["id"]
        assert updated.json()["specs_day"]["venue"] == "New Optical"
        assert updated.json()["specs_day"]["start_time"] == "11:00"
        listed = client.get("/api/clinical/specs-days", headers=headers)
        assert listed.status_code == 200
        days = listed.json()["specs_days"]
        assert len(days) == 1
        assert "seat_limit" not in days[0]
        assert days[0]["end_time"] == "13:00"
    asyncio.run(run())


def test_specs_rejects_inactive_past_malformed_and_same_day_ended_window(monkeypatch):
    async def run():
        mock_db = setup_mock_db(monkeypatch)
        admin_id = await _admin(mock_db)
        camp_id = await _active_camp(mock_db)
        other = ObjectId()
        await mock_db.camps.insert_one({
            "_id": other, "name": "Other", "venue": "X", "is_active": False,
        })
        client = _client(monkeypatch, mock_db)
        headers = _auth(admin_id, "admin", "admin")
        future = _future_date()

        inactive = client.post("/api/clinical/specs-days", json={
            "camp_id": str(other), "day_date": future, "venue": "Hall",
            "start_time": "09:00", "end_time": "11:00",
        }, headers=headers)
        assert inactive.status_code == 400

        malformed = client.post("/api/clinical/specs-days", json={
            "camp_id": "not-an-id", "day_date": future, "venue": "Hall",
            "start_time": "09:00", "end_time": "11:00",
        }, headers=headers)
        assert malformed.status_code == 400

        yesterday = (datetime.now(IST) - timedelta(days=1)).strftime("%Y-%m-%d")
        past = client.post("/api/clinical/specs-days", json={
            "camp_id": str(camp_id), "day_date": yesterday, "venue": "Hall",
            "start_time": "09:00", "end_time": "11:00",
        }, headers=headers)
        assert past.status_code == 400

        today = datetime.now(IST).strftime("%Y-%m-%d")
        now = datetime.now(IST).replace(second=0, microsecond=0)
        ended = (now - timedelta(minutes=1)).strftime("%H:%M")
        earlier = (now - timedelta(hours=1)).strftime("%H:%M")
        if earlier < ended:
            same_day = client.post("/api/clinical/specs-days", json={
                "camp_id": str(camp_id), "day_date": today, "venue": "Hall",
                "start_time": earlier, "end_time": ended,
            }, headers=headers)
            assert same_day.status_code == 400
    asyncio.run(run())


def test_many_specs_assignments_do_not_refuse_or_mutate_seats(monkeypatch):
    async def run():
        mock_db = setup_mock_db(monkeypatch)
        _patch_db(monkeypatch, mock_db)
        camp_id, _pid, trans_a = await _seen_patient_with_transcription(mock_db, RX)
        trans_b = ObjectId()
        p_b = ObjectId()
        await mock_db.patients.insert_one({
            "_id": p_b, "camp_id": camp_id, "camp_day_id": ObjectId(), "reg_no": 502,
            "queue_status": "seen", "arrived_at": helpers.now_utc(),
            "printed_at": helpers.now_utc(), "seen_at": helpers.now_utc(),
        })
        await mock_db.transcriptions.insert_one({
            "_id": trans_b, "patient_id": p_b, "camp_id": camp_id,
            "locked": False, "specs_measurements": RX,
        })
        day_id = ObjectId()
        await mock_db.specs_collection_days.insert_one({
            "_id": day_id, "camp_id": camp_id, "day_date": _future_date(),
            "venue": "Optical Desk", "start_time": "09:00", "end_time": "17:00",
        })
        actor = {"_id": ObjectId(), "role": "clinical_desk_operator"}
        rev_b = ObjectId()
        await mock_db.patients.update_one({"_id": p_b}, {"$set": {
            "committed_revision_id": rev_b, "clinical_generation": 1, "issue_auth_op": None,
        }})
        await mock_db.prescription_revisions.insert_one({
            "_id": rev_b, "patient_id": p_b,
            "prescribed_lines": ["specs_made"], "none_prescribed": False,
            "specs_measurements": RX,
        })
        first = await record_fulfilment(_fulfil(
            trans_a, mock_db.last_rev_id, item_type="specs_made", status="deferred",
            specs_collection_day_id=str(day_id), operation_id="op-a",
        ), actor=actor, background_tasks=None)
        second = await record_fulfilment(_fulfil(
            trans_b, rev_b, item_type="specs_made", status="deferred",
            specs_collection_day_id=str(day_id), operation_id="op-b",
        ), actor=actor, background_tasks=None)
        assert first["slip"]["collection_date"]
        assert second["slip"]["collection_date"]
        day = await mock_db.specs_collection_days.find_one({"_id": day_id})
        assert day.get("seats_taken") in (None, 0)
        assert "seats_taken" not in day or day["seats_taken"] == 0
    asyncio.run(run())


def test_clinical_specs_picker_rejects_ended_cross_camp_legacy_and_malformed(monkeypatch):
    async def run():
        mock_db = setup_mock_db(monkeypatch)
        _patch_db(monkeypatch, mock_db)
        camp_id, _pid, trans_id = await _seen_patient_with_transcription(mock_db, RX)
        other_camp = ObjectId()
        ended = ObjectId()
        legacy = ObjectId()
        valid = ObjectId()
        future = _future_date()
        yesterday = (datetime.now(IST) - timedelta(days=1)).strftime("%Y-%m-%d")
        await mock_db.specs_collection_days.insert_one({
            "_id": ended, "camp_id": camp_id, "day_date": yesterday,
            "venue": "Old Hall", "start_time": "09:00", "end_time": "10:00",
        })
        await mock_db.specs_collection_days.insert_one({
            "_id": legacy, "camp_id": camp_id, "day_date": future,
            "venue": "Needs Window",
        })
        afternoon = ObjectId()
        await mock_db.specs_collection_days.insert_one({
            "_id": afternoon, "camp_id": camp_id, "day_date": future,
            "venue": "Saved Before The Hours Rule", "start_time": "14:00", "end_time": "17:00",
        })
        assert routes_clinical.ser_specs_day(
            await mock_db.specs_collection_days.find_one({"_id": afternoon}),
        )["window_required"] is True
        await mock_db.specs_collection_days.insert_one({
            "_id": ObjectId(), "camp_id": other_camp, "day_date": future,
            "venue": "Other Camp", "start_time": "09:00", "end_time": "13:00",
        })
        await mock_db.specs_collection_days.insert_one({
            "_id": valid, "camp_id": camp_id, "day_date": future,
            "venue": "Optical Desk", "start_time": "09:00", "end_time": "17:00",
        })
        actor = {"_id": ObjectId(), "role": "clinical_desk_operator"}

        for bad_id in (str(ended), str(legacy), str(afternoon), "not-an-id"):
            with __import__("pytest").raises(__import__("fastapi").HTTPException) as exc:
                await record_fulfilment(_fulfil(
                    trans_id, mock_db.last_rev_id, item_type="specs_made", status="deferred",
                    specs_collection_day_id=bad_id, operation_id=str(bad_id),
                ), actor=actor, background_tasks=None)
            assert exc.value.status_code == 400

        other_day = await mock_db.specs_collection_days.find_one({"venue": "Other Camp"})
        with __import__("pytest").raises(__import__("fastapi").HTTPException) as exc:
            await record_fulfilment(_fulfil(
                trans_id, mock_db.last_rev_id, item_type="specs_made", status="deferred",
                specs_collection_day_id=str(other_day["_id"]), operation_id="op-other",
            ), actor=actor, background_tasks=None)
        assert exc.value.status_code == 400

        ok = await record_fulfilment(_fulfil(
            trans_id, mock_db.last_rev_id, item_type="specs_made", status="deferred",
            specs_collection_day_id=str(valid), operation_id="op-ok",
        ), actor=actor, background_tasks=None)
        assert ok["slip"]["collection_start_time"] == "09:00"
        assert ok["slip"]["collection_end_time"] == "17:00"
        assert ok["slip"]["collection_venue"] == "Optical Desk"
    asyncio.run(run())


def test_specs_token_snapshot_survives_later_schedule_edit(monkeypatch):
    async def run():
        mock_db = setup_mock_db(monkeypatch)
        admin_id = await _admin(mock_db)
        camp_id, _pid, trans_id = await _seen_patient_with_transcription(mock_db, RX)
        await mock_db.camps.insert_one({
            "_id": camp_id, "name": "Sikar Camp", "venue": "Sikar Bhawan", "is_active": True,
        })
        client = _client(monkeypatch, mock_db)
        headers = _auth(admin_id, "admin", "admin")
        day = _future_date()
        created = client.post("/api/clinical/specs-days", json={
            "camp_id": str(camp_id), "day_date": day, "venue": "Optical Desk",
            "start_time": "10:00", "end_time": "12:00",
        }, headers=headers)
        day_id = created.json()["specs_day"]["id"]
        out = await record_fulfilment(_fulfil(
            trans_id, mock_db.last_rev_id, item_type="specs_made", status="deferred",
            specs_collection_day_id=day_id, operation_id="op-snap",
        ), actor={"_id": ObjectId(), "role": "clinical_desk_operator"}, background_tasks=None)
        assert out["slip"]["collection_start_time"] == "10:00"
        assert out["slip"]["collection_end_time"] == "12:00"
        client.post("/api/clinical/specs-days", json={
            "camp_id": str(camp_id), "day_date": day, "venue": "Moved Hall",
            "start_time": "14:00", "end_time": "16:00",
        }, headers=headers)
        slip = await mock_db.deferred_slips.find_one({"_id": ObjectId(out["slip"]["id"])})
        assert slip["collection_venue"] == "Optical Desk"
        assert slip["collection_start_time"] == "10:00"
        assert slip["collection_end_time"] == "12:00"
        reprint = client.get(f"/api/clinical/slip/{out['slip']['id']}", headers=_auth(
            ObjectId(), "Op", "clinical_desk_operator",
        ))
        assert reprint.status_code in (200, 401, 403)
        if reprint.status_code == 200:
            assert reprint.json()["slip"]["collection_start_time"] == "10:00"
            assert reprint.json()["slip"]["collection_venue"] == "Optical Desk"
    asyncio.run(run())


def test_specs_window_spans_days_from_a_morning_start_to_an_evening_end(monkeypatch):
    async def run():
        mock_db = setup_mock_db(monkeypatch)
        admin_id = await _admin(mock_db)
        camp_id = await _active_camp(mock_db)
        client = _client(monkeypatch, mock_db)
        headers = _auth(admin_id, "admin", "admin")
        start = _future_date()
        until = (datetime.now(IST) + timedelta(days=14)).strftime("%Y-%m-%d")

        def post(**overrides):
            return client.post("/api/clinical/specs-days", json={
                "camp_id": str(camp_id), "day_date": start, "end_date": until,
                "venue": "SNP कार्यालय, देवघर", "start_time": "10:00", "end_time": "17:00", **overrides,
            }, headers=headers)

        before_start = (datetime.now(IST) + timedelta(days=6)).strftime("%Y-%m-%d")
        assert post(end_date=before_start).status_code == 400
        assert post(end_date="14-09-2026").status_code == 400
        assert post(start_time="13:00").status_code == 400
        assert post(end_time="11:30").status_code == 400
        created = post()
        assert created.status_code == 200, created.text
        assert created.json()["specs_day"]["end_date"] == until
        single = post(day_date=until, end_date=None)
        assert single.status_code == 200, single.text
        assert single.json()["specs_day"]["end_date"] == until
    asyncio.run(run())


def test_started_window_stays_selectable_and_token_sms_states_the_range(monkeypatch):
    async def run():
        mock_db = setup_mock_db(monkeypatch)
        _patch_db(monkeypatch, mock_db)
        sent = _recorder(monkeypatch)
        camp_id, _pid, trans_id = await _seen_patient_with_transcription(mock_db, RX)
        await mock_db.camps.insert_one({
            "_id": camp_id, "name": "Sikar Camp", "venue": "Sikar Bhawan", "is_active": True, "camp_number": 162,
        })
        yesterday = (datetime.now(IST) - timedelta(days=1)).strftime("%Y-%m-%d")
        until = _future_date()
        day_id = ObjectId()
        await mock_db.specs_collection_days.insert_one({
            "_id": day_id, "camp_id": camp_id, "day_date": yesterday, "end_date": until,
            "venue": "SNP कार्यालय, देवघर", "start_time": "10:00", "end_time": "17:00",
        })
        out = await record_fulfilment(_fulfil(
            trans_id, mock_db.last_rev_id, item_type="specs_made", status="deferred",
            specs_collection_day_id=str(day_id), operation_id="op-range",
        ), actor={"_id": ObjectId(), "role": "clinical_desk_operator"}, background_tasks=None)
        assert out["slip"]["collection_date"] == yesterday
        assert out["slip"]["collection_end_date"] == until
        assert sent == [{
            "type": "specs_token", "mobile": "9876500001", "reg_no": 501, "camp_no": "162",
            "date": helpers.display_date(yesterday), "end_date": helpers.display_date(until),
            "start_time": "10:00", "end_time": "05:00", "venue": "SNP कार्यालय, देवघर",
        }]
    asyncio.run(run())
