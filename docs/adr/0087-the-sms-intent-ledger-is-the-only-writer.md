# ADR 0087: The SMS intent ledger is the only writer, and it is told the time

## Context

- SMS intents changed status in two modules. `sms.py` claimed, sent and settled them. `routes_reminders.py` also wrote them: it retired stale pending rows, requeued failed rows, abandoned rows whose patient or Token was gone, and ran the Canary rule. It reached into the private `sms._pause` for that.
- The timeouts were inline literals in both modules: the 30 s resend, the 5 min uncertain, the 5 min throttle backoff and the 10 min Canary wait.
- The queued row shape was built in three places. The Patients to phone list found its notices by rebuilding the `edit:<revision>` string convention.
- Tests simulated time passing by rewriting `created_at` on ledger rows.
- Issue #88 (slice 2) asks that one module own every SMS intent transition, with `now` passed in.

## Decision

- `sms.py` is the SMS intent ledger. It is the only code that inserts or updates `reminder_ledger` rows and the SMS pause documents in `sms_controls`. The only other `sms_controls` document, the reminder lease, stays with the reminders routes because it is reminder policy.
- The ledger's verbs:
  - `record`, `record_and_send`, `send_queued` and `dispatch`
  - `sweep` (the outbox pass), `due_retries` and `abandon_if_gone`
  - `canary` and `pause_after_rejection`
  - `record_delivery_report`, `paused`, `resume`, `controls` and `paused_types`
  - `recorded`, `used`, `status_counts`, `ledger_groups` and `notice_states`
  - `token_key` and `edit_key`
- Every verb that depends on time takes `now`. Route handlers and the reminder worker pass `now_utc()` at the edge, read at each call. The D-1 sweep reads the clock per call, not once at its start. A single timestamp for the whole sweep would let a Resume that lands mid-sweep miss the Canary it sends, and a second Canary would go out.
- The time rules are named once in the ledger:
  - `QUEUED_RESEND_AFTER` 30 s
  - `PENDING_UNCERTAIN_AFTER` 5 min
  - `RETRY_AFTER` 10 min
  - `THROTTLE_BACKOFF` 5 min
  - `CANARY_WAIT` 10 min
  - `MAX_ATTEMPTS` 3
  - `REGISTRATION_DAILY_CAP` 6
- The reminders routes keep reminder policy only: which patients get a reminder, the lease, paging, the send limit, and asking `canary` whether to send one, hold or open the batch.
- Storage, statuses and indexes are unchanged. No migration.

## Consequences

- One search finds every SMS intent transition.
- Ledger tests (`test_sms_ledger.py`) pass `now` directly: resend after 30 s, uncertain after 5 min, retry after 10 min, throttle backoff after 5 min, three attempts, Canary states.
- Route tests advance the frozen clock with `advance_clock` instead of rewriting rows.

## Rejected alternatives

- **Keep the outbox and Canary in the reminders routes.** It is a smaller change, but two modules would still write intents, so a new timeout could be missed in one of them.
- **Read the clock inside the ledger.** Fewer parameters, but tests could only move time by rewriting rows or patching the clock module-wide.
