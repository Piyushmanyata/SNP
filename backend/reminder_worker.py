import json
import logging
import os
import signal
from datetime import datetime, timedelta, timezone
from http.client import HTTPException
from threading import Event
from urllib.error import URLError
from urllib.request import Request, urlopen


IST = timezone(timedelta(hours=5, minutes=30), "Asia/Kolkata")
SLOTS = (10, 20)
logger = logging.getLogger("snp.reminders")


def _post(url: str, secret: str) -> dict:
    request = Request(url, data=b"", headers={"X-Cron-Secret": secret}, method="POST")
    with urlopen(request, timeout=120) as response:
        result = json.load(response)
    if not isinstance(result, dict):
        raise ValueError("Reminder delivery incomplete")
    return result


def _due_slot(now: datetime, completed: set) -> int | None:
    for hour in SLOTS:
        slot = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if now >= slot and (now.date(), hour) not in completed:
            return hour
    return None


def _next_slot(now: datetime, completed: set) -> datetime:
    for hour in SLOTS:
        slot = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if now < slot or (now.date(), hour) not in completed and now < slot:
            if now < slot:
                return slot
    tomorrow = (now + timedelta(days=1)).replace(hour=SLOTS[0], minute=0, second=0, microsecond=0)
    return tomorrow


def run_worker(api_url: str, secret: str, stopped: Event) -> None:
    if not secret:
        raise ValueError("CRON_SECRET must be configured")
    root = api_url.rsplit("/", 1)[0]
    completed: set = set()
    retry_delay = 60
    last_pulse = None
    while not stopped.is_set():
        now = datetime.now(IST)
        if last_pulse is None or now - last_pulse >= timedelta(seconds=60):
            try:
                _post(f"{root}/heartbeat", secret)
                _post(f"{root}/outbox", secret)
            except (URLError, OSError, ValueError, HTTPException) as error:
                logger.warning("Reminder pulse failed (%s); retry in %s seconds", type(error).__name__, retry_delay)
                stopped.wait(min(60, retry_delay))
                continue
            last_pulse = now
        slot = _due_slot(now, completed)
        if slot is None:
            nxt = _next_slot(now, completed)
            stopped.wait(min(60, max(0, (nxt - now).total_seconds())))
            continue
        try:
            result = _post(api_url, secret)
            if result.get("complete") is False:
                if result.get("waiting"):
                    stopped.wait(60)
                continue
            if result.get("ok") is not True:
                raise ValueError("Reminder delivery incomplete")
            if result.get("reason") == "msg91_unconfigured":
                raise ValueError("SMS provider is not configured")
        except (URLError, OSError, ValueError, HTTPException) as error:
            logger.warning("Reminder run failed (%s); retry in %s seconds", type(error).__name__, retry_delay)
            stopped.wait(retry_delay)
            retry_delay = min(300, retry_delay * 2)
            continue
        completed.add((now.date(), slot))
        retry_delay = 60
        logger.info("Reminder run completed for %s %s:00", now.date(), slot)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    secret = os.environ.get("CRON_SECRET", "")
    if not secret:
        raise SystemExit("CRON_SECRET must be configured")
    stopped = Event()
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    signal.signal(signal.SIGINT, lambda *_: stopped.set())
    run_worker(os.environ.get("REMINDER_API_URL", "http://backend:8000/api/cron/reminders"), secret, stopped)


if __name__ == "__main__":
    main()
