# Daily reminder worker

## Decision

Run `python reminder_worker.py` as a separate container using the backend image. Use the standard library and the existing reminder endpoint and SMS ledger instead of adding a scheduler dependency or another persistent job store.

Set the same `CRON_SECRET` as the API. `REMINDER_API_URL` defaults to `http://backend:8000/api/cron/reminders`. The URL includes the endpoint path. Keep the worker on the application's private Docker network; it needs no published port. Configure container restart and a stop grace period of at least 130 seconds.

The worker posts at or after 10:00 and again at or after 20:00 Asia/Kolkata (UTC+05:30). Starting after a slot runs that slot immediately. It also posts `/api/cron/heartbeat` and `/api/cron/outbox` at least every 60 seconds. The outbox sends `queued` rows older than 30 seconds and `failed` rows whose `retry_after` has passed. `pending` rows older than five minutes become `uncertain` and are not sent again. It waits in interruptible intervals of no more than 60 seconds, so host clock corrections are observed. It does not attempt historical catch-up: the sweep endpoint always selects tomorrow's appointments using its own IST clock.

Each HTTP request has a 120-second timeout. A reply with `complete: false` is called again immediately, unless it is `waiting`, which waits 60 seconds. Transport errors, unsuccessful HTTP responses, invalid JSON, a finished pass with `ok: false`, and an unconfigured SMS provider retry after 60, 120, 240 and then at most 300 seconds. `ok` is false only for failures in that pass. An abandoned row does not keep `ok` false. A successful slot resets the delay. One sweep call is limited to 60 seconds and resumes from the cursor on `sms_controls` `_id: "reminder_lease"`. A second call while that lease is held does not run. Sent rows are skipped (ADR 0045). A failed row is retried only once its last attempt is at least 10 minutes old, and it is abandoned after three attempts or when its patient or slip is gone.

SIGTERM and SIGINT interrupt waiting; an in-flight HTTP request finishes or times out. Logs contain completion dates, exception class names and retry delays. They do not contain the cron secret, request headers, response bodies or exception messages.

## Delivery limits

The application ledger prevents routine duplicate sends and makes successful runs repeatable. A provider request that was accepted remotely but timed out locally can still be ambiguous; this worker does not provide a stronger exactly-once delivery guarantee than the existing SMS provider integration. It also cannot send appointments created after today's successful run until the worker restarts or another run is requested.

## Validation

`python -m pytest tests/test_reminder_worker.py -q` exercises the real worker loop with controlled clock and HTTP boundaries. Coverage includes the 09:59/10:00 IST transition, one successful run per day, UTC clock conversion, late startup, restart replay, network/HTTP/truncated-response failures, partial sends, missing provider configuration, secret-free logs, shutdown during waiting and absent cron credentials.

For the separate live HTTP regression suite, set `SNP_LIVE_API` to the service origin without `/api`; the fixture appends that prefix. `requests` must be installed. Make `/app/memory/test_credentials.md` available in the test container (read-only mount is sufficient), containing the name/PIN matching the isolated database's seeded administrator. Without these prerequisites, fixtures intentionally skip. The existing suite also skips its history case if the self-registered patient's response lacks `person_id`; treat that as an unverified path, not a pass.

Use a disposable Compose project/database for the live suite: it creates staff, changes the active camp and print window, and shares ordered state across tests. Do not parallelize `tests/backend_test.py`. Run from `backend` with `python -m pytest tests -q -ra` once the API is healthy and test dependencies are installed, and inspect the final skip count. The production backend image copies application Python files only, so tests and the credentials file must be mounted or run from the checkout.
