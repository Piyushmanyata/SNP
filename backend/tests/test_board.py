"""Camp-day board counts and mock query operators."""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "snp_test")
os.environ.setdefault("AADHAAR_HASH_PEPPER", "test-pepper")

from bson import ObjectId

import helpers
import routes_reports
from routes_reports import camp_day_board
from test_adversarial_challenger import MockCollection, MockDB
from test_camp_lifecycle import TODAY, _mock, _seed_camp

NOW = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)
ADMIN = {"_id": ObjectId(), "role": "admin"}


class TestMockOperators:
    def test_gte(self):
        c = MockCollection("t", MockDB())
        assert c._matches({"n": 5}, {"n": {"$gte": 5}})
        assert c._matches({"n": 6}, {"n": {"$gte": 5}})
        assert not c._matches({"n": 4}, {"n": {"$gte": 5}})
        assert not c._matches({}, {"n": {"$gte": 5}})

    def test_in(self):
        c = MockCollection("t", MockDB())
        assert c._matches({"t": "a"}, {"t": {"$in": ["a", "b"]}})
        assert not c._matches({"t": "c"}, {"t": {"$in": ["a", "b"]}})

    def test_ne(self):
        c = MockCollection("t", MockDB())
        assert c._matches({"t": "a"}, {"t": {"$ne": "b"}})
        assert not c._matches({"t": "b"}, {"t": {"$ne": "b"}})


def _walk_strings(obj):
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.append(str(k))
            out.extend(_walk_strings(v))
    elif isinstance(obj, list):
        for i in obj:
            out.extend(_walk_strings(i))
    elif obj is not None:
        out.append(str(obj))
    return out


class TestCampDayBoard:
    def test_two_desks_one_quiet_backlog_lines_and_no_patient_names(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            monkeypatch.setattr(routes_reports, "get_db", lambda: mock_db)
            monkeypatch.setattr(routes_reports, "today_ist_str", lambda: TODAY)
            monkeypatch.setattr(routes_reports, "now_utc", lambda: NOW)
            monkeypatch.setattr(helpers, "today_ist_str", lambda: TODAY)
            monkeypatch.setattr(helpers, "now_utc", lambda: NOW)
            camp_id, (day_id,) = await _seed_camp(mock_db)
            desk_busy = ObjectId()
            desk_quiet = ObjectId()
            await mock_db.users.insert_one({
                "_id": desk_busy, "name": "Desk 1", "role": "volunteer", "disabled_at": None,
            })
            await mock_db.users.insert_one({
                "_id": desk_quiet, "name": "Desk 2", "role": "volunteer", "disabled_at": None,
            })
            p_seen = ObjectId()
            p_tx = ObjectId()
            await mock_db.patients.insert_one({
                "_id": p_seen, "camp_id": camp_id, "full_name": "Sunita Devi",
                "arrived_by": str(desk_busy), "arrived_at": NOW - timedelta(minutes=10),
                "seen_at": NOW - timedelta(minutes=5),
            })
            await mock_db.patients.insert_one({
                "_id": p_tx, "camp_id": camp_id, "full_name": "Ramesh Kumar",
                "arrived_by": str(desk_quiet), "arrived_at": NOW - timedelta(minutes=40),
                "seen_at": NOW - timedelta(minutes=30),
            })
            await mock_db.transcriptions.insert_one({
                "_id": ObjectId(), "patient_id": p_tx,
            })
            await mock_db.fulfilments.insert_one({
                "item_type": "medicine", "created_at": NOW - timedelta(minutes=2),
            })
            await mock_db.fulfilments.insert_one({
                "item_type": "ot", "created_at": NOW - timedelta(minutes=3),
            })
            await mock_db.ot_schedule_days.insert_one({
                "camp_id": camp_id, "day_date": "2026-09-02", "seat_limit": 10, "seats_taken": 3,
            })
            await mock_db.specs_collection_days.insert_one({
                "camp_id": camp_id, "day_date": "2026-09-05", "seat_limit": 8, "seats_taken": 8,
            })
            await mock_db.reminder_ledger.insert_one({
                "status": "failed", "created_at": NOW - timedelta(minutes=1),
            })
            out = await camp_day_board(actor=ADMIN)
            by_name = {d["name"]: d for d in out["desks"]}
            assert by_name["Desk 1"]["last_15m"] == 1
            assert by_name["Desk 1"]["quiet"] is False
            assert by_name["Desk 2"]["last_15m"] == 0
            assert by_name["Desk 2"]["last_60m"] == 1
            assert by_name["Desk 2"]["quiet"] is True
            assert out["transcription_backlog"] == 1
            assert out["lines"] == {"medicine": 1, "specs_fixed": 0, "specs_made": 0, "ot": 1}
            assert out["next_ot_day"]["seats_left"] == 7
            assert out["next_specs_day"]["seats_left"] == 0
            assert out["sms_failed_today"] == 1
            blob = " ".join(_walk_strings(out))
            assert "Sunita" not in blob
            assert "Ramesh" not in blob
        asyncio.run(run())
