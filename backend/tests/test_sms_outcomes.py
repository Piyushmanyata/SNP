import io
import json
import os
import sys
from contextlib import nullcontext
from datetime import datetime
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
        mock_db.camps.docs.append({"_id": camp_id, "name": "Big Camp", "venue": "Hall A", "is_active": True})
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

    def test_provider_unconfigured_stays_visibly_skipped(self, monkeypatch):
        mock_db = setup_mock_db(monkeypatch)
        asyncio.run(_seed_camp_household(mock_db, n_patients=2))
        client = _client(monkeypatch, mock_db, msg91_on=False)

        assert _post(client).json() == {
            "ok": True, "sent": 0, "complete": True, "reason": "msg91_unconfigured",
        }
        assert mock_db.reminder_ledger.docs == []


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
