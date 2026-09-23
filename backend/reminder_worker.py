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
logger = logging.getLogger("snp.reminders")


def run_worker(api_url: str, secret: str, stopped: Event) -> None:
    if not secret:
        raise ValueError("CRON_SECRET must be configured")
    completed_date = None
    retry_delay = 60
    while not stopped.is_set():
        now = datetime.now(IST)
        scheduled = now.replace(hour=10, minute=0, second=0, microsecond=0)
        if completed_date == now.date():
            scheduled += timedelta(days=1)
        if now < scheduled:
            stopped.wait(min(60, (scheduled - now).total_seconds()))
            continue
        try:
            request = Request(api_url, data=b"", headers={"X-Cron-Secret": secret}, method="POST")
            with urlopen(request, timeout=120) as response:
                result = json.load(response)
            if not isinstance(result, dict) or result.get("ok") is not True:
                raise ValueError("Reminder delivery incomplete")
            if result.get("reason") == "msg91_unconfigured":
                raise ValueError("SMS provider is not configured")
            if result.get("complete") is False:
                logger.info("Reminder batch delivered %s; more remain", result.get("sent"))
                if result.get("waiting"):
                    stopped.wait(60)
                continue
        except (URLError, OSError, ValueError, HTTPException) as error:
            logger.warning("Reminder run failed (%s); retry in %s seconds", type(error).__name__, retry_delay)
            stopped.wait(retry_delay)
            retry_delay = min(300, retry_delay * 2)
            continue
        completed_date = now.date()
        retry_delay = 60
        logger.info("Reminder run completed for %s", completed_date)


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
