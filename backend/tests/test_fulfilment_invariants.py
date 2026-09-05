"""Deferred Fulfilment keeps one current record; a failed write leaves prior state."""
import asyncio
import os
import sys
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

import routes_clinical
from routes_clinical import record_fulfilment
from test_camp_lifecycle import RX, _fulfil, _mock, _seen_patient_with_transcription


def test_failed_ot_replace_leaves_prior_fulfilment_and_seat(monkeypatch):
    async def run():
        mock_db = _mock(monkeypatch)
        camp_id, _pid, trans_id = await _seen_patient_with_transcription(mock_db, RX)
        day_a, day_b = ObjectId(), ObjectId()
        await mock_db.ot_schedule_days.insert_one({
            "_id": day_a, "camp_id": camp_id, "day_date": "2026-10-02",
            "venue": "OT A", "seat_limit": 1, "seats_taken": 0,
        })
        await mock_db.ot_schedule_days.insert_one({
            "_id": day_b, "camp_id": camp_id, "day_date": "2026-10-03",
            "venue": "OT B", "seat_limit": 1, "seats_taken": 0,
        })
        actor = {"_id": ObjectId(), "role": "clinical_desk_operator"}
        first = await record_fulfilment(_fulfil(
            trans_id, mock_db.last_rev_id, item_type="ot", status="deferred",
            ot_schedule_day_id=str(day_a),
        ), actor=actor)
        prior_id = first["fulfilment"]["id"]
        assert (await mock_db.ot_schedule_days.find_one({"_id": day_a}))["seats_taken"] == 1

        async def boom(*_a, **_k):
            raise RuntimeError("injected write failure")

        monkeypatch.setattr(routes_clinical, "persist_fulfilment", boom)
        try:
            await record_fulfilment(_fulfil(
                trans_id, mock_db.last_rev_id, item_type="ot", status="deferred",
                ot_schedule_day_id=str(day_b), operation_id="op-replace",
            ), actor=actor)
            raise AssertionError("expected failure")
        except RuntimeError:
            pass
        still = await mock_db.fulfilments.find_one({"_id": ObjectId(prior_id)})
        assert still["ot_schedule_day_id"] == day_a
        assert (await mock_db.ot_schedule_days.find_one({"_id": day_a}))["seats_taken"] == 1
        assert (await mock_db.ot_schedule_days.find_one({"_id": day_b}))["seats_taken"] == 0
        current = await mock_db.fulfilments.find({"transcription_id": trans_id, "item_type": "ot"}).to_list(10)
        assert len(current) == 1
        active_slips = await mock_db.deferred_slips.find({"transcription_id": trans_id, "active": True}).to_list(10)
        assert len(active_slips) == 1
        assert active_slips[0]["ot_schedule_day_id"] == day_a
    asyncio.run(run())


def test_overlapping_ot_assignments_never_consume_two_seats(monkeypatch):
    async def run():
        mock_db = _mock(monkeypatch)
        camp_id, _, trans_id = await _seen_patient_with_transcription(mock_db, RX)
        day_id = ObjectId()
        await mock_db.ot_schedule_days.insert_one({
            "_id": day_id, "camp_id": camp_id, "day_date": "2026-10-02",
            "venue": "Hospital", "seat_limit": 10, "seats_taken": 0,
        })
        actor = {"_id": ObjectId(), "role": "clinical_desk_operator"}
        body = _fulfil(trans_id, mock_db.last_rev_id, item_type="ot", status="deferred",
                       ot_schedule_day_id=str(day_id), operation_id="op-overlap")
        original = routes_clinical._process_deferral

        async def delayed(*args, **kwargs):
            await asyncio.sleep(0.02)
            return await original(*args, **kwargs)

        monkeypatch.setattr(routes_clinical, "_process_deferral", delayed)
        results = await asyncio.gather(record_fulfilment(body, actor=actor),
                                       record_fulfilment(body, actor=actor), return_exceptions=True)
        assert sum(isinstance(result, dict) for result in results) >= 1
        day = await mock_db.ot_schedule_days.find_one({"_id": day_id})
        assert day["seats_taken"] == 1
        assert await mock_db.fulfilments.count_documents({"transcription_id": trans_id}) == 1
    asyncio.run(run())


def test_concurrent_same_line_leaves_one_current_specs_record(monkeypatch):
    async def run():
        mock_db = _mock(monkeypatch)
        camp_id, _pid, trans_id = await _seen_patient_with_transcription(mock_db, RX)
        day = ObjectId()
        await mock_db.specs_collection_days.insert_one({
            "_id": day, "camp_id": camp_id, "day_date": "2026-10-20",
            "venue": "Optical", "start_time": "09:00", "end_time": "17:00",
        })
        actor = {"_id": ObjectId(), "role": "clinical_desk_operator"}
        body = _fulfil(trans_id, mock_db.last_rev_id, item_type="specs_made", status="deferred",
                       specs_collection_day_id=str(day), operation_id="op-specs")
        await record_fulfilment(body, actor=actor)
        await record_fulfilment(body, actor=actor)
        rows = await mock_db.fulfilments.find(
            {"transcription_id": trans_id, "item_type": "specs_made"},
        ).to_list(20)
        assert len(rows) == 1
        assert rows[0].get("current") is True
        slips = [s for s in mock_db.deferred_slips.docs if s.get("active")]
        assert len(slips) == 1
    asyncio.run(run())
