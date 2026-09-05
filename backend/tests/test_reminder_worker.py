import io
import json
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from http.client import IncompleteRead
from types import SimpleNamespace
from urllib.error import HTTPError, URLError

import pytest
import reminder_worker


IST = timezone(timedelta(hours=5, minutes=30))


class Clock:
    def __init__(self, now):
        self.current = now
        self.stopped = False
        self.waits = []

    def is_set(self):
        return self.stopped

    def wait(self, seconds):
        self.waits.append(seconds)
        self.current += timedelta(seconds=seconds)
        return self.stopped


def test_worker_waits_until_ten_ist_and_runs_once_each_day(monkeypatch):
    clock = Clock(datetime(2026, 9, 5, 9, 59, tzinfo=IST))
    requests = []
    monkeypatch.setattr(reminder_worker, "datetime", SimpleNamespace(now=lambda tz: clock.current.astimezone(tz)))

    def post(request, timeout):
        requests.append((clock.current, request, timeout))
        clock.stopped = len(requests) == 2
        return nullcontext(io.BytesIO(json.dumps({"ok": True, "sent": 3}).encode()))

    monkeypatch.setattr(reminder_worker, "urlopen", post)
    reminder_worker.run_worker("http://backend:8000/api/cron/reminders", "test-secret", clock)

    assert [item[0] for item in requests] == [
        datetime(2026, 9, 5, 10, tzinfo=IST),
        datetime(2026, 9, 6, 10, tzinfo=IST),
    ]
    assert requests[0][1].get_method() == "POST"
    assert requests[0][1].full_url == "http://backend:8000/api/cron/reminders"
    assert requests[0][1].get_header("X-cron-secret") == "test-secret"


@pytest.mark.parametrize("failure", [
    URLError("test-secret network issue"),
    HTTPError("http://backend:8000/api/cron/reminders", 503, "test-secret provider failure", None, None),
    IncompleteRead(b"test-secret"),
    {"ok": False, "failed": 1, "message": "test-secret"},
    {"ok": True, "sent": 0, "reason": "msg91_unconfigured"},
])
def test_worker_retries_transient_and_partial_failures_without_logging_secrets(monkeypatch, caplog, failure):
    clock = Clock(datetime(2026, 9, 5, 10, tzinfo=IST))
    attempts = []
    monkeypatch.setattr(reminder_worker, "datetime", SimpleNamespace(now=lambda tz: clock.current.astimezone(tz)))

    def post(request, timeout):
        attempts.append(clock.current)
        if len(attempts) <= 2:
            if isinstance(failure, Exception):
                raise failure
            return nullcontext(io.BytesIO(json.dumps(failure).encode()))
        clock.stopped = True
        return nullcontext(io.BytesIO(b'{"ok": true}'))

    monkeypatch.setattr(reminder_worker, "urlopen", post)
    reminder_worker.run_worker("http://backend:8000/api/cron/reminders", "test-secret", clock)

    assert [attempt.minute for attempt in attempts] == [0, 1, 3]
    assert clock.waits == [60, 120]
    assert "test-secret" not in caplog.text


def test_worker_runs_immediately_after_late_start_and_each_restart(monkeypatch):
    clock = Clock(datetime(2026, 9, 5, 5, tzinfo=timezone.utc))
    attempts = []
    monkeypatch.setattr(reminder_worker, "datetime", SimpleNamespace(now=lambda tz: clock.current.astimezone(tz)))

    def post(request, timeout):
        attempts.append(request.full_url)
        clock.stopped = True
        return nullcontext(io.BytesIO(b'{"ok": true}'))

    monkeypatch.setattr(reminder_worker, "urlopen", post)
    reminder_worker.run_worker("http://backend:8000/api/cron/reminders", "test-secret", clock)
    clock.stopped = False
    reminder_worker.run_worker("http://backend:8000/api/cron/reminders", "test-secret", clock)

    assert len(attempts) == 2
    assert clock.waits == []


def test_worker_can_stop_while_waiting_without_sending(monkeypatch):
    clock = Clock(datetime(2026, 9, 5, 9, tzinfo=IST))
    monkeypatch.setattr(reminder_worker, "datetime", SimpleNamespace(now=lambda tz: clock.current.astimezone(tz)))

    def wait(seconds):
        assert seconds <= 60
        clock.stopped = True

    def post(*args, **kwargs):
        pytest.fail("Shutdown must not send reminders")

    monkeypatch.setattr(clock, "wait", wait)
    monkeypatch.setattr(reminder_worker, "urlopen", post)
    reminder_worker.run_worker("http://backend:8000/api/cron/reminders", "test-secret", clock)


def test_worker_requires_a_cron_secret_before_network_access():
    with pytest.raises(ValueError, match="CRON_SECRET must be configured"):
        reminder_worker.run_worker("http://backend:8000/api/cron/reminders", "", Clock(datetime.now(IST)))
