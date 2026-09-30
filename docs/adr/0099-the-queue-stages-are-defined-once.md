# ADR 0099: The queue stages are defined once

**Carries ADR 0067, ADR 0088 and ADR 0090.**

## Context

- A patient's stage between the door and the doctor was written out in four places:
  - the Pending list and the KPIs in `routes_reports.py`, one as `_pending_query` and one as an inline `queue_status: "seen"` filter
  - the Camp-day board's aggregation in `camp_day_board`, with its unpacking and the same number assigned twice as `awaiting_seen` and `transcription_backlog`
  - the stage names again in `_empty_board`
  - `test_query_plans.py`, which pasted the filters and a two-accumulator copy of the board pipeline, so a change to the real rule could leave the index proof testing something else
- Completion and undo wrote the queue-stage fields (`queue_status`, `seen_at`, `seen_by`) as literals in `routes_clinical.py`. Pending is "arrived with a print", so the value undo writes decides whether an undone patient re-enters Pending. Nothing tied the two together.
- ADR 0067 defined the Transcription backlog as "today's arrived patients". Issue #89 made it camp-wide: the backlog, Pending and awaiting seen are one set, over every camp day. The code already did this; the ADR wording did not.
- Issue #110 (slice 2) asks for each queue stage to be defined once.

## Decision

`backend/queue_stage.py` is the only place that says who is in which stage. It has no database handle and no clock: every function is pure and returns plain dicts or lists, and the routes keep the I/O.

- **Filters**, each taking the camp id:
  - `awaiting_print`: status `arrived` with `printed_at` null or missing
  - `pending`: status `arrived` with `printed_at` of BSON type `date`. This is also the Transcription backlog and Awaiting seen: one camp-wide set. It uses `$type: "date"`, never `$ne: null`, which fetched every patient. With `PENDING_SORT` the index `(camp_id, queue_status, printed_at, arrived_at)` serves the filter and the sort: no SORT stage and no FETCH.
  - `doctor_seen`: status `seen`, camp-wide (the `/kpis` "seen")
  - Awaiting print and Pending are disjoint, and together they are exactly the `arrived` status.
- **`PENDING_SORT`**: `printed_at` ascending, longest since print first. It has no tie-breaker on equal `printed_at`, as before.
- **`seen_fields(actor_id, now)` and `unseen_fields()`**: the queue-stage part of the `$set` for completion and undo. They are exact inverses with the same key set (`queue_status`, `seen_at`, `seen_by`), so undo returns the patient to Arrived and a printed patient is Pending again. `clinical_state.commit` (ADR 0088) stays the only writer of clinical fields: `committed_revision_id` is not here, because a correction commit writes it alone. The routes write `{"committed_revision_id": ..., **queue_stage.seen_fields(...)}`. `now` is passed in, so tests that freeze the clock in `routes_clinical` still work.
- **`board_pipeline(camp_id, day_start)` and `board_stages(rows)`**: the board's one `$group` over the `arrived` status, and its decoding into `awaiting_print`, `awaiting_seen`, `transcription_backlog` and their `earlier_days` (arrived before the IST day start). Awaiting seen and the Transcription backlog are the same number by construction. `board_stages([])` is the all-zero shape `_empty_board` uses. The board's `arrived` and `seen` counts are the Operating day's arrivals and seen-today, which are not stages, and stay in the route. Its `stages` JSON keeps the same keys and numbers; only the key order changes.
- `/kpis`, `/pending`, the Camp-day board, `_empty_board` and `test_query_plans.py` import these definitions. The query-plan test now plans the real pipeline, with all four accumulators, and passes the sort as `dict(queue_stage.PENDING_SORT)`.
- The rule is written twice, as a filter and as aggregation expressions (`$gt` and `$lte` against null), because the board must stay one covered aggregate. A parity test in `test_queue_stage.py` runs both over null, missing and date `printed_at` and requires equal counts, so they cannot drift.
- ADR 0067's "today's arrived patients" backlog wording is superseded by the camp-wide set above.
- The Arrival move stays inside `arrival.py` (ADR 0090). A contract test pins that a registration built by `arrival.fields_at_creation` or stamped by `arrival.stamp` lands in Awaiting print, without importing a constant into `arrival.py`.
- The read-side `"seen"` guards of printing and issue (`routes_desk`, `lock_resolution`, `clinical_state.require_fresh_review`) stay as they are. They are print and issue guards, owned by the Printing slice (#110 slice 4).

## Consequences

- A change to what Pending means is one edit in `queue_stage.py`, and the board, the KPIs and the query-plan test follow.
- `test_queue_stage.py` covers, through the interface and against real MongoDB:
  - each filter over registered, arrived (null, missing and dated print, today and an earlier camp day), seen and another camp's patients
  - the partition of `arrived`
  - the board parity and the earlier-day split
  - the all-zero shape
  - a printed patient leaving Pending when seen and returning on undo
  - the sort
  - the Arrival contract
- `awaiting_print(camp_id)` has no production caller, because the board uses the aggregate. It stays as the named definition of the stage and as the oracle for the parity test.
- The clinical name search (`printed_at` not null across all statuses) is a name-index plan for the search handler, not a queue stage, and is not touched.
- No HTTP status, field or count changes.

## Rejected alternatives

- **Derive the board from the filters, with four `count_documents` calls.** The definition would be one dict, but one `$group` over the arrived set becomes four scans, polled by every lead every 15 seconds, and it drops the covered aggregate ADR 0067 chose. The earlier-day counts could not use `arrived_at` as a tight bound after a `$type` range.
- **A shared `QueueStage` enum or constants imported by `arrival.py` and the guards.** It names strings without concentrating a rule, and gives `arrival.py` a dependency it does not need (ADR 0090).
- **Put `committed_revision_id` in `seen_fields` and `unseen_fields`.** `queue_stage` would then own a clinical field that a correction commit writes alone (ADR 0088).
