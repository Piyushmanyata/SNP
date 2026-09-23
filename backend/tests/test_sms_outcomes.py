import io
import json
import os
import sys
from contextlib import nullcontext
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "snp_test")

import asyncio

import pytest
from bson import ObjectId

import msg91
import reminder_worker
import routes_reminders
from test_adversarial_challenger import setup_mock_db
from test_reminder_worker import IST, Clock
from test_reminders import (
    HOUSEHOLD,
    TOMORROW,
    _calls,
    _client,
    _post,
    _seed_camp_household,
)

WORKER_URL = "http://backend:8000/api/cron/reminders"


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _provider(monkeypatch, body, requests=None):
    payload = body if isinstance(body, bytes) else json.dumps(body).encode()

    def _open(request, timeout=None):
        if requests is not None:
            requests.append(request)
        return _FakeResponse(payload)

    monkeypatch.setattr(msg91.urllib.request, "urlopen", _open)


class TestProviderAcceptance:
    def test_http_200_provider_error_body_stays_unsent(self, monkeypatch):
        mock_db = setup_mock_db(monkeypatch)
        asyncio.run(_seed_camp_household(mock_db, n_patients=1))
        client = _client(monkeypatch, mock_db)
        _provider(monkeypatch, {"type": "error", "message": "template not approved"})

        body = _post(client).json()

        assert body["sent"] == 0
        assert body["failed"] == 1
        assert body["ok"] is False
        row = mock_db.reminder_ledger.docs[0]
        assert row["status"] == "failed"
        assert row["provider_id"] is None

    def test_success_body_records_the_request_id(self, monkeypatch):
        mock_db = setup_mock_db(monkeypatch)
        asyncio.run(_seed_camp_household(mock_db, n_patients=1))
        client = _client(monkeypatch, mock_db)
        requests = []
        _provider(monkeypatch, {"type": "success", "message": "3a4b5c6d7e"}, requests)

        body = _post(client).json()

        assert body == {"ok": True, "sent": 1, "failed": 0, "complete": True,
                        "event_date": TOMORROW, "send_date": "2026-09-01"}
        row = mock_db.reminder_ledger.docs[0]
        assert row["status"] == "sent"
        assert row["provider_id"] == "3a4b5c6d7e"
        assert len(requests) == 1

    @pytest.mark.parametrize("body", [
        {},
        {"type": "success"},
        {"type": "success", "message": ""},
        {"type": "success", "message": "   "},
        {"request_id": "abc"},
        ["success"],
        b"not json at all",
    ])
    def test_malformed_or_missing_identifier_fails_safely(self, monkeypatch, body):
        mock_db = setup_mock_db(monkeypatch)
        asyncio.run(_seed_camp_household(mock_db, n_patients=1))
        client = _client(monkeypatch, mock_db)
        _provider(monkeypatch, body)

        result = _post(client).json()

        assert result["sent"] == 0
        assert result["failed"] == 1
        row = mock_db.reminder_ledger.docs[0]
        assert row["status"] == "failed"
        assert row["provider_id"] is None

    def test_request_id_field_is_accepted_when_the_type_is_success(self, monkeypatch):
        mock_db = setup_mock_db(monkeypatch)
        asyncio.run(_seed_camp_household(mock_db, n_patients=1))
        client = _client(monkeypatch, mock_db)
        _provider(monkeypatch, {"type": "success", "request_id": "rq-77"})

        assert _post(client).json()["sent"] == 1
        assert mock_db.reminder_ledger.docs[0]["provider_id"] == "rq-77"

    def test_an_uncertain_acceptance_is_never_resent(self, monkeypatch):
        mock_db = setup_mock_db(monkeypatch)
        asyncio.run(_seed_camp_household(mock_db, n_patients=1))
        client = _client(monkeypatch, mock_db)
        requests = []
        _provider(monkeypatch, {"type": "success", "message": "req-1"}, requests)
        ledger = mock_db.reminder_ledger
        original = ledger.update_one

        async def unreachable(query, update, upsert=False):
            raise RuntimeError("ledger unreachable")

        monkeypatch.setattr(ledger, "update_one", unreachable)
        first = _post(client).json()
        monkeypatch.setattr(ledger, "update_one", original)

        assert first["sent"] == 1
        assert len(requests) == 1
        assert ledger.docs[0]["status"] == "pending"

        second = _post(client).json()

        assert second["sent"] == 0
        assert len(requests) == 1
        assert ledger.docs[0]["status"] == "pending"
        assert len(ledger.docs) == 1


class TestBoundedDispatch:
    def test_repeated_cron_runs_are_idempotent_across_page_boundaries(self, monkeypatch):
        mock_db = setup_mock_db(monkeypatch)
        asyncio.run(_seed_camp_household(mock_db, n_patients=9))
        monkeypatch.setattr(routes_reminders, "PAGE_SIZE", 2)
        captured = _calls(monkeypatch)
        client = _client(monkeypatch, mock_db)

        assert _post(client).json()["sent"] == 9
        assert _post(client).json()["sent"] == 0

        assert sorted(c["reg_no"] for c in captured) == list(range(1000, 1009))
        assert len(mock_db.reminder_ledger.docs) == 9

    def test_a_run_is_bounded_and_reports_its_own_incompleteness(self, monkeypatch):
        mock_db = setup_mock_db(monkeypatch)
        asyncio.run(_seed_camp_household(mock_db, n_patients=5))
        monkeypatch.setattr(routes_reminders, "PAGE_SIZE", 2)
        monkeypatch.setattr(routes_reminders, "SEND_LIMIT", 2)
        captured = _calls(monkeypatch)
        client = _client(monkeypatch, mock_db)

        runs = [_post(client).json()]
        while not runs[-1]["complete"]:
            runs.append(_post(client).json())

        assert [r["sent"] for r in runs] == [2, 2, 1]
        assert [r["complete"] for r in runs] == [False, False, True]
        assert len(captured) == 5
        assert len(mock_db.reminder_ledger.docs) == 5

    def test_a_recipient_beyond_position_ten_thousand_is_processed(self, monkeypatch):
        mock_db = setup_mock_db(monkeypatch)
        camp_id = ObjectId()
        day_id = ObjectId()
        mock_db.camps.docs.append({
            "_id": camp_id, "name": "Big Camp", "venue": "Hall A", "is_active": True, "camp_number": 162,
        })
        mock_db.camp_days.docs.append({"_id": day_id, "camp_id": camp_id, "day_date": TOMORROW})
        for i in range(10_050):
            mock_db.patients.docs.append({
                "_id": ObjectId(), "camp_id": camp_id, "camp_day_id": day_id,
                "reg_no": i, "phone": None, "phone_normalized": None,
            })
        last = mock_db.patients.docs[-1]
        last["phone"] = last["phone_normalized"] = HOUSEHOLD
        captured = _calls(monkeypatch)
        client = _client(monkeypatch, mock_db)

        body = _post(client).json()

        assert body["sent"] == 1
        assert body["complete"] is True
        assert [c["reg_no"] for c in captured] == [10_049]

    def test_the_send_budget_carries_across_message_types(self, monkeypatch):
        mock_db = setup_mock_db(monkeypatch)

        async def seed():
            camp_id, _day_id, ids = await _seed_camp_household(mock_db, n_patients=2)
            for pid in ids:
                await mock_db.deferred_slips.insert_one({
                    "patient_id": pid, "item_type": "ot", "active": True, "cancelled": False,
                    "collection_date": TOMORROW, "collection_venue": "OT Theatre", "version": 1,
                })

        asyncio.run(seed())
        monkeypatch.setattr(routes_reminders, "SEND_LIMIT", 3)
        captured = _calls(monkeypatch)
        client = _client(monkeypatch, mock_db)

        first = _post(client).json()
        assert first == {"ok": True, "sent": 3, "failed": 0, "complete": False,
                         "event_date": TOMORROW, "send_date": "2026-09-01"}
        assert [c["type"] for c in captured] == ["camp", "camp", "ot"]

        second = _post(client).json()
        assert second["sent"] == 1
        assert second["complete"] is True
        assert [c["type"] for c in captured] == ["camp", "camp", "ot", "ot"]
        assert len(mock_db.reminder_ledger.docs) == 4

    def test_failed_sends_consume_the_budget_and_the_next_run_reaches_later_recipients(self, monkeypatch):
        mock_db = setup_mock_db(monkeypatch)
        asyncio.run(_seed_camp_household(mock_db, n_patients=4))
        monkeypatch.setattr(routes_reminders, "SEND_LIMIT", 2)
        calls = []

        def fake_send(message_type, mobile, variables):
            calls.append(variables["reg_no"])
            if len(calls) <= 2:
                raise RuntimeError("carrier down")
            return f"id-{len(calls)}"

        monkeypatch.setattr(msg91, "send_dlt_sms", fake_send)
        monkeypatch.setattr(routes_reminders.sms.msg91, "send_dlt_sms", fake_send)
        monkeypatch.setattr(msg91, "configured", lambda: True)
        monkeypatch.setattr(routes_reminders.msg91, "configured", lambda: True)
        monkeypatch.setattr(routes_reminders.sms.msg91, "configured", lambda: True)
        client = _client(monkeypatch, mock_db)

        first = _post(client).json()
        second = _post(client).json()

        assert first["sent"] == 0
        assert first["complete"] is False
        assert second["sent"] == 2
        assert second["complete"] is True
        assert calls == [1000, 1001, 1002, 1003]

    def test_provider_unconfigured_stays_visibly_skipped(self, monkeypatch):
        mock_db = setup_mock_db(monkeypatch)
        asyncio.run(_seed_camp_household(mock_db, n_patients=2))
        client = _client(monkeypatch, mock_db, msg91_on=False)

        assert _post(client).json() == {
            "ok": True, "sent": 0, "complete": True, "reason": "msg91_unconfigured",
        }
        assert mock_db.reminder_ledger.docs == []


def _flaky_provider(monkeypatch, failures):
    calls = []

    def fake_send(message_type, mobile, variables):
        calls.append({"type": message_type, **variables})
        if len(calls) <= failures:
            raise RuntimeError("carrier down")
        return f"id-{len(calls)}"

    monkeypatch.setattr(msg91, "send_dlt_sms", fake_send)
    monkeypatch.setattr(msg91, "configured", lambda: True)
    return calls


async def _numbered_camp(mock_db):
    camp_id = ObjectId()
    await mock_db.camps.insert_one({"_id": camp_id, "name": "C", "venue": "Hall A", "camp_number": 162})
    return camp_id


def _later(mock_db):
    for row in mock_db.reminder_ledger.docs:
        row["created_at"] -= routes_reminders.sms.RETRY_AFTER + timedelta(minutes=1)


class TestFailedRemindersRetryOnALaterRun:
    def test_a_failure_is_retried_only_after_the_retry_interval(self, monkeypatch):
        mock_db = setup_mock_db(monkeypatch)
        asyncio.run(_seed_camp_household(mock_db, n_patients=1))
        calls = _flaky_provider(monkeypatch, failures=1)
        client = _client(monkeypatch, mock_db)

        first = _post(client).json()
        assert (first["sent"], first["failed"], first["ok"]) == (0, 1, False)
        assert _post(client).json()["sent"] == 0
        assert len(calls) == 1

        _later(mock_db)
        third = _post(client).json()
        assert (third["sent"], third["failed"], third["ok"]) == (1, 0, True)
        assert len(calls) == 2

    def test_three_spaced_failures_are_abandoned_and_stay_reported(self, monkeypatch):
        mock_db = setup_mock_db(monkeypatch)
        asyncio.run(_seed_camp_household(mock_db, n_patients=1))
        calls = _flaky_provider(monkeypatch, failures=99)
        client = _client(monkeypatch, mock_db)

        for _ in range(4):
            result = _post(client).json()
            _later(mock_db)

        assert len(calls) == 3
        assert mock_db.reminder_ledger.docs[0]["status"] == "abandoned"
        assert (result["failed"], result["ok"]) == (1, False)

    def test_a_retry_skips_a_surgery_cancelled_after_the_failure(self, monkeypatch):
        mock_db = setup_mock_db(monkeypatch)

        async def seed():
            pid = ObjectId()
            await mock_db.patients.insert_one({
                "_id": pid, "camp_id": await _numbered_camp(mock_db), "camp_day_id": ObjectId(), "reg_no": 7,
                "phone": HOUSEHOLD, "phone_normalized": HOUSEHOLD,
            })
            await mock_db.deferred_slips.insert_one({
                "patient_id": pid, "item_type": "ot", "active": True, "cancelled": False,
                "collection_date": TOMORROW, "collection_venue": "OT Theatre", "version": 1,
            })

        asyncio.run(seed())
        calls = _flaky_provider(monkeypatch, failures=1)
        client = _client(monkeypatch, mock_db)
        _post(client)
        slip = mock_db.deferred_slips.docs[0]
        slip["active"], slip["cancelled"] = False, True
        _later(mock_db)

        _post(client)

        assert len(calls) == 1

    def test_a_specs_retry_keeps_its_collection_window(self, monkeypatch):
        mock_db = setup_mock_db(monkeypatch)

        async def seed():
            pid = ObjectId()
            await mock_db.patients.insert_one({
                "_id": pid, "camp_id": await _numbered_camp(mock_db), "camp_day_id": ObjectId(), "reg_no": 42,
                "phone": HOUSEHOLD, "phone_normalized": HOUSEHOLD,
            })
            await mock_db.deferred_slips.insert_one({
                "patient_id": pid, "item_type": "specs_made", "active": True, "cancelled": False,
                "collection_date": TOMORROW, "collection_venue": "Token Hall",
                "collection_start_time": "10:00", "collection_end_time": "17:00", "version": 1,
            })

        asyncio.run(seed())
        calls = _flaky_provider(monkeypatch, failures=1)
        client = _client(monkeypatch, mock_db)
        _post(client)
        _later(mock_db)

        _post(client)

        assert [(c["date"], c["end_date"]) for c in calls] == [
            ("02-09-2026", "02-09-2026"),
        ] * 2


class TestWorkerFollowsThrough:
    def test_worker_keeps_going_until_the_run_reports_complete(self, monkeypatch):
        clock = Clock(datetime(2026, 9, 5, 10, tzinfo=IST))
        replies = [
            {"ok": True, "sent": 200, "failed": 0, "complete": False},
            {"ok": True, "sent": 40, "failed": 0, "complete": True},
        ]
        attempts = []
        monkeypatch.setattr(reminder_worker, "datetime",
                            SimpleNamespace(now=lambda tz: clock.current.astimezone(tz)))

        def post(request, timeout):
            body = replies[len(attempts)]
            attempts.append(clock.current)
            clock.stopped = len(attempts) == len(replies)
            return nullcontext(io.BytesIO(json.dumps(body).encode()))

        monkeypatch.setattr(reminder_worker, "urlopen", post)
        reminder_worker.run_worker(WORKER_URL, "test-secret", clock)

        assert len(attempts) == 2
        assert clock.waits == []
