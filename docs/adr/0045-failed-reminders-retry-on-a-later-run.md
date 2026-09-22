# ADR 0045: A failed reminder is retried on a later run, from the current targets

**Amends ADR 0013.**

## Context

The production-experience specification (R10) says a known SMS failure "is retried on a later run and abandoned after three attempts". The implementation did not meet that. It made a second pass, `_retry_failed`, straight after the first pass in the same request. That second pass read the failed ledger rows rather than the day's targets. This had three effects:

- Attempts 1 and 2 were seconds apart. The worker's next call, about 60 seconds later, made attempt 3. A carrier outage of about three minutes therefore abandoned every reminder for the next day.
- Once a reminder was abandoned, the board and the cron response no longer counted it, because both counted only `failed` rows. The worker then logged "Reminder run completed".
- The retry resent to a stored ledger row. The surgery or specs slip behind that row might have been cancelled or moved in the meantime. The retry also dropped the specs collection window, because the ledger row does not store it.

## Decision

- **There is no second pass.** Each run makes one pass over tomorrow's current targets, as derived from camp days and active slips. Eligibility, venue and window are therefore always current.
- **Failed rows wait before a retry.** A `failed` row is retried only when its last attempt is older than `RETRY_AFTER` (10 minutes). Until then it is skipped, and it does not consume the run's send budget. After three attempts the row is `abandoned`.
- **Abandoned rows still count as failures.** The cron response's `failed` count and the camp-day board's SMS failures both include `abandoned` rows. `ok` stays false, so the worker keeps backing off and logging the failure instead of reporting a completed run.
- **A concurrent claim is skipped, not failed.** If two overlapping runs both try to insert the same ledger row, the unique index rejects one of them. That rejection is now treated as skipped, so it neither consumes budget nor is logged as a send failure.

The per-event sends (the registration confirmation, the OT token and the specs token) keep their immediate retry. They are sent once, at the moment of the event, and have no later run.

## Consequences

Three failed attempts now take at least 20 minutes of carrier failure rather than about three. A target that was cancelled after a failure is simply no longer a target, so nothing is resent to it. When the carrier is down, a day's worker keeps retrying every five minutes until midnight IST. Each retry skips every row that is not due.

## Rejected alternatives

- **Keep the same-run retry and raise the attempt limit.** This still burns attempts seconds apart, and it still resends to stale ledger rows.
- **Filter the ledger-driven retry for cancelled slips.** This duplicates target derivation in a second place, and it still has no specs window to send.
- **Stop counting abandoned rows so the worker can finish.** This is exactly the silent loss the board is meant to prevent.
