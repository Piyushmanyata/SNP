# ADR 0098: What a Fulfilment line becomes is one module

**Carries ADR 0088 and ADR 0097 (corrections after issue carry forward and flag; two files are numbered 0097).**

## Context

- Matching the medicine outcomes to the committed revision, deriving Partially fulfilled, the valid statuses per line, the re-issue rules and the correction carry-forward were spread over `routes_clinical.py` and `clinical_state.py`.
- PR 108's bug sat in the gap between `record_fulfilment.apply`, which decided what a re-issue keeps, and `_carry_forward`, which decided what a correction leaves open. Each read `given` on its own terms.
- The valid statuses per line lived in four places and had drifted: `routes_clinical._validate_fulfilment_matrix`, `routes_reports._empty_board`, `clinical_state.PRESCRIBED_LINE_KEYS` and `routes_staff.VALID_LINES`. The Camp-day board had no bucket for cancelled Spectacles to be made orders.
- Issue #110 (slice 1) asks for one module that owns the rules and a small interface that the routes call.

## Decision

- `backend/fulfilment_line.py` is a pure module: no database, no clock, no I/O. It has five names:
  - `STATUSES`, the one table of valid statuses per Fulfilment line item type.
  - `require_line(item_type)`, which refuses an unknown line with `INVALID_FULFILMENT_ITEM_STATUS` (400).
  - `check_issue(revision, item_type, status, outcomes)`, run before the transaction. It matches the medicine outcomes to the committed revision, derives the medicine status, and checks any other status against the table. It returns the status and the outcomes.
  - `issue(item_type, status, outcomes, powers, prior)`, run inside the transaction. It returns the fields a line becomes when issued over a prior line: kept removed medicines, the Corrected after issue mark, Settled outcomes and the Issued power.
  - `correct(line, before, after, *, by, at)`, run once per existing line inside the correction's transaction. It returns the `$set` patch, or `None` when the correction leaves the line alone. Spectacles to be made and Hospital lines always return `None`.
- Settled and open are defined once: an outcome with `given` not null is settled, and `given` null is open. `issue` and `correct` agree because they share the module.
- `routes_clinical.py` keeps the transaction, the Tokens, the stock-catalogue read for the Issued power (`resolve_issued_powers`), the identity, Token and slip columns of the line (`_build_fulfilment_doc`) and persistence.
- **Fulfilment issue still derives its medicine status before the transaction.** `record_fulfilment` sets `body.status` from `check_issue` before the Operation is built, because the payload hash covers it (ADR 0088). The order of refusals is unchanged: fresh review, unknown line, line not prescribed, Issued power, then outcomes and status.
- `clinical_state.PRESCRIBED_LINE_KEYS` is `tuple(STATUSES)`, `routes_staff.VALID_LINES` is `{"rx", *STATUSES}`, and the Camp-day board builds its buckets from the table. The board therefore also counts cancelled Spectacles to be made orders: `fulfilment.specs_made.cancelled` is an additive field, and the board issues one more count per poll.
- `_carry_forward` reads every Fulfilment line of the transcription and takes one timestamp for the whole correction, so every line the correction marks carries the same `at`.
- **Known second copy, on purpose.** `FulfilmentStation.js` `FULFILMENT_LINES` (actions, withdraw and status labels) lists the statuses per line as UI labels, and its reopened and settled derivations read `given: null` as the server's word for open. The server re-validates every status against `STATUSES`, so a stale client is refused, not trusted. Both move when the client's prescription source changes (slice 3, ADR 0100).
- **Literal status reads outside the table remain by design.** They read meaning, not validity: `deferred` in `tokens.py` and `routes_reminders.py`, `deferred` and `declined` in `routes_reports._hospital_outcome` and `_line_statuses`, and `cancelled` in the Spectacles exclusivity filter.

## Consequences

- A new status is added in one place, shows on the board and passes validation.
- The rules are tested through five names with no database (`test_fulfilment_line.py`), including the seam PR 108 fixed: a correction, then a re-issue over the corrected line.
- Route-level tests pin the order of refusals: an unknown line is a 400 before the line-not-prescribed 409, and the Issued power is resolved before the status is checked.
- The Camp-day board response gains `fulfilment.specs_made.cancelled`. `Board.js` reads only the buckets it shows, each with a fallback of 0, so it is unaffected.

## Rejected alternatives

- **A module that also owns persistence** (`record(db, ...)` and `carry_forward(db, ...)`). The reads and writes belong inside the Clinical operation runner's transaction with the Tokens (ADR 0088, ADR 0089). It would need a database to test rules that are pure, and it would hide the pre-transaction and in-transaction split that the payload hash depends on.
- **Keep the rules in `clinical_state` as loose functions that the routes sequence.** That is the arrangement that produced the PR 108 gap.
- **Give the board an explicit omit list instead of the full table.** It is a second list to drift.
