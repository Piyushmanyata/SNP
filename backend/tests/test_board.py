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
from test_adversarial_challenger import MockCollection, MockCursor, MockDB
from test_camp_lifecycle import TODAY, _mock as _camp_mock, _seed_camp

NOW = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)
ADMIN = {"_id": ObjectId(), "role": "admin"}


def _value(document, expression):
    if isinstance(expression, dict):
        return {key: _value(document, value) for key, value in expression.items()}
    return document.get(expression[1:]) if isinstance(expression, str) and expression.startswith("$") else expression


async def _aggregate(collection, pipeline):
    collection.db.query_count += 1
    documents = collection.docs
    for stage in pipeline:
        if "$match" in stage:
            documents = [doc for doc in documents if collection._matches(doc, stage["$match"])]
        elif "$group" in stage:
            spec = stage["$group"]
            groups = {}
            for document in documents:
                group_id = _value(document, spec["_id"])
                key = tuple(group_id.items()) if isinstance(group_id, dict) else group_id
                row = groups.setdefault(key, {"_id": group_id})
                for name, accumulator in spec.items():
                    if name == "_id":
                        continue
                    operator, expression = next(iter(accumulator.items()))
                    value = _value(document, expression)
                    if operator == "$sum":
                        row[name] = row.get(name, 0) + value
                    elif operator == "$max":
                        if value is not None and (row.get(name) is None or value > row[name]):
                            row[name] = value
                    else:
                        raise NotImplementedError(operator)
            documents = list(groups.values())
        else:
            raise NotImplementedError(stage)
    return MockCursor(documents)


async def _distinct(collection, field, query):
    collection.db.query_count += 1
    return list({document[field] for document in collection.docs if field in document and collection._matches(document, query)})


def _mock(monkeypatch):
    database = _camp_mock(monkeypatch)
    find_one = MockCollection.find_one

    async def sorted_find_one(collection, query, sort=None):
        if sort is None:
            return await find_one(collection, query)
        cursor = collection.find(query)
        for field, direction in reversed(sort):
            cursor = cursor.sort(field, direction)
        rows = await cursor.to_list(1)
        return rows[0] if rows else None

    monkeypatch.setattr(MockCollection, "find_one", sorted_find_one)
    monkeypatch.setattr(MockCollection, "aggregate", _aggregate)
    monkeypatch.setattr(MockCollection, "distinct", _distinct, raising=False)
    return database


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
    def test_next_schedule_is_earliest_valid_day_beyond_two_hundred_records(self, monkeypatch):
        async def run():
            database = _mock(monkeypatch)
            monkeypatch.setattr(routes_reports, "get_db", lambda: database)
            monkeypatch.setattr(routes_reports, "today_ist_str", lambda: TODAY)
            monkeypatch.setattr(routes_reports, "now_utc", lambda: NOW)
            camp_id, _ = await _seed_camp(database)
            today = datetime.fromisoformat(TODAY)
            tomorrow = (today + timedelta(days=1)).date().isoformat()
            for collection in (database.ot_schedule_days, database.specs_collection_days):
                collection.docs = [{
                    "camp_id": camp_id,
                    "day_date": (today + timedelta(days=i + 2)).date().isoformat(),
                    "start_time": "10:00", "end_time": "17:00",
                } for i in range(200)]
                collection.docs.extend([
                    {"camp_id": camp_id, "day_date": tomorrow, "start_time": "10:00", "end_time": "17:00"},
                    {"camp_id": camp_id, "day_date": (today - timedelta(days=1)).date().isoformat()},
                    {"camp_id": ObjectId(), "day_date": TODAY, "start_time": "10:00", "end_time": "17:00"},
                ])
            database.specs_collection_days.docs.extend([
                {"camp_id": camp_id, "day_date": TODAY, "start_time": "09:00"},
                {"camp_id": camp_id, "day_date": TODAY, "start_time": "", "end_time": "17:00"},
            ])
            result = await camp_day_board(actor=ADMIN)
            assert result["next_ot"]["day_date"] == tomorrow
            assert result["next_specs"]["day_date"] == tomorrow
        asyncio.run(run())

    def test_counts_do_not_truncate_after_twenty_thousand_arrivals(self, monkeypatch):
        async def run():
            database = _mock(monkeypatch)
            monkeypatch.setattr(routes_reports, "get_db", lambda: database)
            monkeypatch.setattr(routes_reports, "today_ist_str", lambda: TODAY)
            monkeypatch.setattr(routes_reports, "now_utc", lambda: NOW)
            camp_id, _ = await _seed_camp(database)
            database.patients.docs = [{"_id": ObjectId(), "camp_id": camp_id, "arrived_at": NOW}
                                      for _ in range(20001)]
            result = await camp_day_board(actor=ADMIN)
            assert result["stages"]["arrived"] == 20001
            assert result["stages"]["awaiting_print"] == 20001
        asyncio.run(run())

    def test_scoped_kpis_quiet_activity_and_no_patient_names(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            monkeypatch.setattr(routes_reports, "get_db", lambda: mock_db)
            monkeypatch.setattr(routes_reports, "today_ist_str", lambda: TODAY)
            monkeypatch.setattr(routes_reports, "now_utc", lambda: NOW)
            monkeypatch.setattr(helpers, "today_ist_str", lambda: TODAY)
            monkeypatch.setattr(helpers, "now_utc", lambda: NOW)
            camp_id, (day_id,) = await _seed_camp(mock_db)
            other = ObjectId()
            await mock_db.camps.insert_one({"_id": other, "name": "Other Camp", "is_active": False})
            desk_busy = ObjectId()
            desk_quiet = ObjectId()
            idle = ObjectId()
            await mock_db.users.insert_one({
                "_id": desk_busy, "name": "Vol 1", "role": "volunteer", "disabled_at": None,
            })
            await mock_db.users.insert_one({
                "_id": desk_quiet, "name": "Vol 2", "role": "volunteer", "disabled_at": None,
            })
            await mock_db.users.insert_one({
                "_id": idle, "name": "Off Duty", "role": "volunteer", "disabled_at": None,
            })
            p_seen = ObjectId()
            p_tx = ObjectId()
            await mock_db.patients.insert_one({
                "_id": p_seen, "camp_id": camp_id, "full_name": "Sunita Devi",
                "arrived_by": str(desk_busy), "arrived_at": NOW - timedelta(minutes=10),
                "printed_at": NOW - timedelta(minutes=8),
                "seen_at": NOW - timedelta(minutes=5),
            })
            await mock_db.patients.insert_one({
                "_id": p_tx, "camp_id": camp_id, "full_name": "Ramesh Kumar",
                "arrived_by": str(desk_quiet), "arrived_at": NOW - timedelta(minutes=40),
                "printed_at": NOW - timedelta(minutes=35),
                "seen_at": NOW - timedelta(minutes=30),
            })
            await mock_db.patients.insert_one({
                "camp_id": other, "full_name": "Other Patient",
                "arrived_by": str(desk_busy), "arrived_at": NOW - timedelta(minutes=2),
                "seen_at": NOW - timedelta(minutes=1),
            })
            tx = ObjectId()
            await mock_db.transcriptions.insert_one({
                "_id": tx, "patient_id": p_tx, "camp_id": camp_id,
            })
            await mock_db.fulfilments.insert_one({
                "transcription_id": tx, "item_type": "medicine", "status": "fulfilled",
                "created_at": NOW - timedelta(minutes=2),
            })
            await mock_db.fulfilments.insert_one({
                "transcription_id": tx, "item_type": "ot", "status": "deferred",
                "created_at": NOW - timedelta(minutes=3),
            })
            await mock_db.ot_schedule_days.insert_one({
                "camp_id": camp_id, "day_date": "2026-09-02", "venue": "OT Hall",
                "seat_limit": 10, "seats_taken": 3,
            })
            await mock_db.specs_collection_days.insert_one({
                "camp_id": camp_id, "day_date": "2026-09-05", "venue": "Optical",
                "start_time": "10:00", "end_time": "17:00",
            })
            await mock_db.reminder_ledger.insert_one({
                "status": "failed", "created_at": NOW - timedelta(minutes=1),
                "patient_id": p_seen,
            })
            await mock_db.reminder_ledger.insert_one({
                "status": "failed", "created_at": NOW - timedelta(minutes=1),
                "patient_id": ObjectId(),
            })
            await mock_db.reminder_ledger.insert_one({
                "status": "abandoned", "created_at": NOW - timedelta(minutes=1),
                "patient_id": p_seen,
            })
            for row in (
                {"status": "rejected"},
                {"status": "sent", "delivery": "failed", "dlt_failure": True},
                {"status": "sent", "delivery": "delivered"},
                {"status": "uncertain"},
                {"status": "paused"},
            ):
                await mock_db.reminder_ledger.insert_one({**row, "created_at": NOW - timedelta(minutes=1), "patient_id": p_tx})
            await mock_db.sms_controls.insert_one({"_id": "registration", "paused": True})
            await mock_db.sms_controls.insert_one({"_id": "camp", "paused": False})
            out = await camp_day_board(actor=ADMIN)
            assert out["state"] == "current"
            assert out["as_of"]
            assert out["camp"]["name"] == "Sikar Camp"
            assert out["day"]["day_date"] == TODAY
            assert out["stages"]["arrived"] == 2
            assert out["stages"]["seen"] == 2
            assert out["stages"]["transcription_backlog"] == 1
            by_name = {d["name"]: d for d in out["activity"]}
            assert set(by_name) == {"Vol 1", "Vol 2"}
            assert by_name["Vol 1"]["quiet"] is False
            assert by_name["Vol 2"]["quiet"] is True
            assert out["quiet_count"] == 1
            assert out["fulfilment"]["medicine"]["fulfilled"] == 1
            assert out["fulfilment"]["ot"]["deferred"] == 1
            assert out["next_ot"]["seats_left"] == 7
            assert out["next_ot"]["venue"] == "OT Hall"
            assert out["next_specs"]["start_time"] == "10:00"
            assert "seats_left" not in out["next_specs"]
            assert out["sms_failures"] == 4
            assert out["sms_not_sent"] == 1
            assert out["sms_paused"] == ["registration"]
            blob = " ".join(_walk_strings(out))
            assert "Sunita" not in blob
            assert "Ramesh" not in blob
            assert "Other Patient" not in blob
        asyncio.run(run())

    def test_query_count_stays_flat_as_volunteers_grow(self, monkeypatch):
        async def run():
            mock_db = _mock(monkeypatch)
            monkeypatch.setattr(routes_reports, "get_db", lambda: mock_db)
            monkeypatch.setattr(routes_reports, "today_ist_str", lambda: TODAY)
            monkeypatch.setattr(routes_reports, "now_utc", lambda: NOW)
            monkeypatch.setattr(helpers, "today_ist_str", lambda: TODAY)
            camp_id, _days = await _seed_camp(mock_db)

            async def seed(n):
                mock_db.users.docs.clear()
                mock_db.patients.docs = [d for d in mock_db.patients.docs if d.get("camp_id") != camp_id or d.get("reg_no")]
                for i in range(n):
                    uid = ObjectId()
                    await mock_db.users.insert_one({
                        "_id": uid, "name": f"V{i}", "role": "volunteer", "disabled_at": None,
                    })
                    await mock_db.patients.insert_one({
                        "camp_id": camp_id, "arrived_by": str(uid),
                        "arrived_at": NOW - timedelta(minutes=2),
                    })

            await seed(5)
            mock_db.query_count = 0
            await camp_day_board(actor=ADMIN)
            small = mock_db.query_count
            await seed(25)
            mock_db.query_count = 0
            await camp_day_board(actor=ADMIN)
            large = mock_db.query_count
            assert large <= small + 2
            assert large < 25
        asyncio.run(run())
