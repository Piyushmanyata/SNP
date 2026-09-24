import io
import json
from contextlib import nullcontext
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from bson import ObjectId
from pymongo.asynchronous.collection import AsyncCollection

import msg91
import reminder_worker
import routes_reminders
from seed import TODAY, TOMORROW, patient_doc, recorder, seed_camp
from test_reminder_worker import IST, Clock
from test_reminders import (
    HOUSEHOLD,
    TOMORROW_SHOWN,
    _age_ledger,
    _ledger,
    _numbered_camp,
    _post,
    _run,
    _seed_camp_household,
)

WORKER_URL = "http://backend:8000/api/cron/reminders"


class _FakeResponse:
    def __init__(self, payload, status):
        self._payload = payload
        self.status = status

    def read(self):
        return self._payload


def _provider(monkeypatch, body, requests=None, *, status=200, fail_connect=None, fail_reply=None):
    payload = body if isinstance(body, bytes) else json.dumps(body).encode()

    class _Connection:
        def __init__(self, host, timeout=None):
            self.host = host

        def connect(self):
            if fail_connect:
                raise fail_connect

        def request(self, method, path, body=None, headers=None):
            if requests is not None:
                requests.append({"host": self.host, "path": path, "body": json.loads(body), "headers": headers})

        def getresponse(self):
            if fail_reply:
                raise fail_reply
            return _FakeResponse(payload, status)

        def close(self):
            pass

    monkeypatch.setattr(msg91.http.client, "HTTPSConnection", _Connection)


async def _later(database):
    await _age_ledger(database, routes_reminders.sms.RETRY_AFTER + timedelta(minutes=1))


class TestProviderAcceptance:
    def test_a_provider_refusal_is_recorded_and_never_repeated(self, monkeypatch):
        requests = []
        _provider(monkeypatch, {"type": "error", "message": "template not approved"}, requests, status=400)

        async def body(database, client):
            await _seed_camp_household(database, n_patients=1)

            first = (await _post(client)).json()
            await _age_ledger(database, routes_reminders.sms.RETRY_AFTER * 2)
            again = (await _post(client)).json()

            assert (first["sent"], first["failed"], first["ok"]) == (0, 0, True)
            assert again["sent"] == 0
            assert len(requests) == 1
            [row] = await _ledger(database)
            assert row["status"] == "rejected"
            assert row["error"] == "template not approved"
            assert row["provider_id"] is None

        _run(monkeypatch, body)

    def test_the_request_carries_the_flow_and_every_variable(self, monkeypatch):
        requests = []
        _provider(monkeypatch, {"type": "success", "message": "rq-1"}, requests)

        async def body(database, client):
            await _seed_camp_household(database, n_patients=1)

            await _post(client)

            [sent] = requests
            assert (sent["host"], sent["path"]) == ("control.msg91.com", "/api/v5/flow")
            assert sent["headers"]["authkey"] == "auth"
            assert sent["body"] == {
                "template_id": "tmpl-camp", "short_url": "0",
                "recipients": [{"mobiles": f"91{HOUSEHOLD}", "date": TOMORROW_SHOWN, "camp_no": "162",
                                "venue": "Hall A", "reg_no": "1000"}],
            }

        _run(monkeypatch, body)

    def test_a_connection_that_never_opened_is_retried_later(self, monkeypatch):
        _provider(monkeypatch, {"type": "success", "message": "rq-2"}, fail_connect=ConnectionRefusedError("refused"))

        async def body(database, client):
            await _seed_camp_household(database, n_patients=1)

            first = (await _post(client)).json()
            assert (first["sent"], first["failed"], first["ok"]) == (0, 1, False)
            assert (await _ledger(database))[0]["status"] == "failed"

            _provider(monkeypatch, {"type": "success", "message": "rq-2"})
            await _later(database)
            second = (await _post(client)).json()

            assert (second["sent"], second["failed"], second["ok"]) == (1, 0, True)
            assert (await _ledger(database))[0]["provider_id"] == "rq-2"

        _run(monkeypatch, body)

    @pytest.mark.parametrize("failure", [TimeoutError("read timed out"), ConnectionResetError("reset")])
    def test_a_reply_lost_after_sending_is_uncertain_and_never_resent(self, monkeypatch, failure):
        requests = []
        _provider(monkeypatch, {"type": "success", "message": "rq-3"}, requests, fail_reply=failure)

        async def body(database, client):
            await _seed_camp_household(database, n_patients=1)

            first = (await _post(client)).json()
            await _later(database)
            second = (await _post(client)).json()

            assert (first["sent"], first["failed"], first["ok"]) == (1, 0, True)
            assert second["sent"] == 0
            assert len(requests) == 1
            assert (await _ledger(database))[0]["status"] == "uncertain"

        _run(monkeypatch, body)

    def test_a_server_error_after_sending_is_uncertain(self, monkeypatch):
        _provider(monkeypatch, b"<html>bad gateway</html>", status=502)

        async def body(database, client):
            await _seed_camp_household(database, n_patients=1)

            await _post(client)

            [row] = await _ledger(database)
            assert row["status"] == "uncertain"
            assert "502" in row["error"]

        _run(monkeypatch, body)

    def test_success_body_records_the_request_id(self, monkeypatch):
        requests = []
        _provider(monkeypatch, {"type": "success", "message": "3a4b5c6d7e"}, requests)

        async def body(database, client):
            await _seed_camp_household(database, n_patients=1)

            result = (await _post(client)).json()

            assert result == {"ok": True, "sent": 1, "failed": 0, "complete": True, "waiting": False,
                              "event_date": TOMORROW, "send_date": TODAY}
            [row] = await _ledger(database)
            assert row["status"] == "sent"
            assert row["provider_id"] == "3a4b5c6d7e"
            assert len(requests) == 1

        _run(monkeypatch, body)

    @pytest.mark.parametrize("reply", [
        {},
        {"type": "success"},
        {"type": "success", "message": ""},
        {"type": "success", "message": "   "},
        {"request_id": "abc"},
        ["success"],
        b"not json at all",
    ])
    def test_an_unreadable_reply_is_uncertain_and_never_resent(self, monkeypatch, reply):
        requests = []
        _provider(monkeypatch, reply, requests)

        async def body(database, client):
            await _seed_camp_household(database, n_patients=1)

            result = (await _post(client)).json()
            await _later(database)
            await _post(client)

            assert (result["failed"], result["ok"]) == (0, True)
            assert len(requests) == 1
            [row] = await _ledger(database)
            assert row["status"] == "uncertain"
            assert row["provider_id"] is None

        _run(monkeypatch, body)

    def test_request_id_field_is_accepted_when_the_type_is_success(self, monkeypatch):
        _provider(monkeypatch, {"type": "success", "request_id": "rq-77"})

        async def body(database, client):
            await _seed_camp_household(database, n_patients=1)

            assert (await _post(client)).json()["sent"] == 1
            assert (await _ledger(database))[0]["provider_id"] == "rq-77"

        _run(monkeypatch, body)

    def test_an_uncertain_acceptance_is_never_resent(self, monkeypatch):
        requests = []
        _provider(monkeypatch, {"type": "success", "message": "req-1"}, requests)
        update_one = AsyncCollection.update_one

        async def unreachable(self, *args, **kwargs):
            if self.name == "reminder_ledger":
                raise RuntimeError("ledger unreachable")
            return await update_one(self, *args, **kwargs)

        async def body(database, client):
            await _seed_camp_household(database, n_patients=1)
            with monkeypatch.context() as broken:
                broken.setattr(AsyncCollection, "update_one", unreachable)
                first = (await _post(client)).json()

            assert first["sent"] == 1
            assert len(requests) == 1
            assert (await _ledger(database))[0]["status"] == "pending"

            second = (await _post(client)).json()

            assert second["sent"] == 0
            assert len(requests) == 1
            [row] = await _ledger(database)
            assert row["status"] == "pending"

        _run(monkeypatch, body)


class TestBoundedDispatch:
    def test_repeated_cron_runs_are_idempotent_across_page_boundaries(self, monkeypatch):
        monkeypatch.setattr(routes_reminders, "PAGE_SIZE", 2)
        captured = recorder(monkeypatch)

        async def body(database, client):
            await _seed_camp_household(database, n_patients=9)

            assert (await _post(client)).json()["sent"] == 9
            assert (await _post(client)).json()["sent"] == 0

            assert sorted(c["reg_no"] for c in captured) == list(range(1000, 1009))
            assert await database.reminder_ledger.count_documents({}) == 9

        _run(monkeypatch, body)

    def test_a_run_is_bounded_and_reports_its_own_incompleteness(self, monkeypatch):
        monkeypatch.setattr(routes_reminders, "PAGE_SIZE", 2)
        monkeypatch.setattr(routes_reminders, "SEND_LIMIT", 2)
        captured = recorder(monkeypatch)

        async def body(database, client):
            await _seed_camp_household(database, n_patients=5)

            runs = [(await _post(client)).json()]
            while not runs[-1]["complete"]:
                runs.append((await _post(client)).json())

            assert [r["sent"] for r in runs] == [2, 2, 1]
            assert [r["complete"] for r in runs] == [False, False, True]
            assert len(captured) == 5
            assert await database.reminder_ledger.count_documents({}) == 5

        _run(monkeypatch, body)

    def test_a_recipient_beyond_position_ten_thousand_is_processed(self, monkeypatch):
        captured = recorder(monkeypatch)

        async def body(database, client):
            camp_id, (day_id,) = await seed_camp(database, days=(TOMORROW,), name="Big Camp", venue="Hall A")
            patients = [
                patient_doc(camp_id=camp_id, camp_day_id=day_id, reg_no=i, patient_qr=f"big-{i}",
                            phone=None, phone_normalized=None)
                for i in range(10_050)
            ]
            patients[-1]["phone"] = patients[-1]["phone_normalized"] = HOUSEHOLD
            await database.patients.insert_many(patients)

            result = (await _post(client)).json()

            assert result["sent"] == 1
            assert result["complete"] is True
            assert [c["reg_no"] for c in captured] == [10_049]

        _run(monkeypatch, body)

    def test_the_send_budget_carries_across_message_types(self, monkeypatch):
        monkeypatch.setattr(routes_reminders, "SEND_LIMIT", 3)
        captured = recorder(monkeypatch)

        async def body(database, client):
            _camp_id, _day_id, ids = await _seed_camp_household(database, n_patients=2)
            await database.deferred_slips.insert_many([{
                "patient_id": pid, "item_type": "ot", "active": True, "cancelled": False,
                "collection_date": TOMORROW, "collection_venue": "OT Theatre", "version": 1,
            } for pid in ids])

            first = (await _post(client)).json()
            assert first == {"ok": True, "sent": 3, "failed": 0, "complete": False, "waiting": False,
                             "event_date": TOMORROW, "send_date": TODAY}
            assert [c["type"] for c in captured] == ["ot", "ot", "camp"]

            second = (await _post(client)).json()
            assert second["sent"] == 1
            assert second["complete"] is True
            assert [c["type"] for c in captured] == ["ot", "ot", "camp", "camp"]
            assert await database.reminder_ledger.count_documents({}) == 4

        _run(monkeypatch, body)

    def test_failed_sends_consume_the_budget_and_the_next_run_reaches_later_recipients(self, monkeypatch):
        monkeypatch.setattr(routes_reminders, "SEND_LIMIT", 2)
        calls = _flaky_provider(monkeypatch, failures=2)

        async def body(database, client):
            await _seed_camp_household(database, n_patients=4)

            first = (await _post(client)).json()
            second = (await _post(client)).json()

            assert first["sent"] == 0
            assert first["complete"] is False
            assert second["sent"] == 2
            assert second["complete"] is True
            assert [c["reg_no"] for c in calls] == [1000, 1001, 1002, 1003]

        _run(monkeypatch, body)

    def test_provider_unconfigured_stays_visibly_skipped(self, monkeypatch):
        async def body(database, client):
            await _seed_camp_household(database, n_patients=2)

            assert (await _post(client)).json() == {
                "ok": True, "sent": 0, "complete": True, "reason": "msg91_unconfigured",
            }
            assert await _ledger(database) == []

        _run(monkeypatch, body, msg91_on=False)


def _flaky_provider(monkeypatch, failures):
    calls = []

    def fake_send(message_type, mobile, variables):
        calls.append({"type": message_type, **variables})
        if len(calls) <= failures:
            raise msg91.Unsent("carrier down")
        return f"id-{len(calls)}"

    monkeypatch.setattr(msg91, "send_dlt_sms", fake_send)
    monkeypatch.setattr(msg91, "configured", lambda: True)
    return calls


class TestFailedRemindersRetryOnALaterRun:
    def test_a_failure_is_retried_only_after_the_retry_interval(self, monkeypatch):
        calls = _flaky_provider(monkeypatch, failures=1)

        async def body(database, client):
            await _seed_camp_household(database, n_patients=1)

            first = (await _post(client)).json()
            assert (first["sent"], first["failed"], first["ok"]) == (0, 1, False)
            assert (await _post(client)).json()["sent"] == 0
            assert len(calls) == 1

            await _later(database)
            third = (await _post(client)).json()
            assert (third["sent"], third["failed"], third["ok"]) == (1, 0, True)
            assert len(calls) == 2

        _run(monkeypatch, body)

    def test_three_spaced_failures_are_abandoned_and_the_day_can_finish(self, monkeypatch):
        calls = _flaky_provider(monkeypatch, failures=99)

        async def body(database, client):
            await _seed_camp_household(database, n_patients=1)

            results = []
            for _ in range(4):
                results.append((await _post(client)).json())
                await _later(database)

            assert len(calls) == 3
            assert (await _ledger(database))[0]["status"] == "abandoned"
            assert [(r["failed"], r["ok"]) for r in results] == [(1, False)] * 3 + [(0, True)]

        _run(monkeypatch, body)

    def test_a_retry_skips_a_surgery_cancelled_after_the_failure(self, monkeypatch):
        calls = _flaky_provider(monkeypatch, failures=1)

        async def body(database, client):
            pid = ObjectId()
            await database.patients.insert_one(patient_doc(
                _id=pid, camp_id=await _numbered_camp(database), camp_day_id=ObjectId(), reg_no=7,
                phone=HOUSEHOLD, phone_normalized=HOUSEHOLD,
            ))
            await database.deferred_slips.insert_one({
                "patient_id": pid, "item_type": "ot", "active": True, "cancelled": False,
                "collection_date": TOMORROW, "collection_venue": "OT Theatre", "version": 1,
            })
            await _post(client)
            await database.deferred_slips.update_one({"patient_id": pid}, {"$set": {"active": False, "cancelled": True}})
            await _later(database)

            await _post(client)

            assert len(calls) == 1

        _run(monkeypatch, body)

    def test_a_specs_retry_keeps_its_collection_window(self, monkeypatch):
        calls = _flaky_provider(monkeypatch, failures=1)

        async def body(database, client):
            pid = ObjectId()
            await database.patients.insert_one(patient_doc(
                _id=pid, camp_id=await _numbered_camp(database), camp_day_id=ObjectId(), reg_no=42,
                phone=HOUSEHOLD, phone_normalized=HOUSEHOLD,
            ))
            await database.deferred_slips.insert_one({
                "patient_id": pid, "item_type": "specs_made", "active": True, "cancelled": False,
                "collection_date": TOMORROW, "collection_venue": "Token Hall",
                "collection_start_time": "10:00", "collection_end_time": "17:00", "version": 1,
            })
            await _post(client)
            await _later(database)

            await _post(client)

            assert [(c["date"], c["end_date"]) for c in calls] == [(TOMORROW_SHOWN, TOMORROW_SHOWN)] * 2

        _run(monkeypatch, body)


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
            if not request.full_url.endswith("/reminders"):
                return nullcontext(io.BytesIO(b'{"ok": true, "complete": true}'))
            reply = replies[len(attempts)]
            attempts.append(clock.current)
            clock.stopped = len(attempts) == len(replies)
            return nullcontext(io.BytesIO(json.dumps(reply).encode()))

        monkeypatch.setattr(reminder_worker, "urlopen", post)
        reminder_worker.run_worker(WORKER_URL, "test-secret", clock)

        assert len(attempts) == 2
        assert clock.waits == []
