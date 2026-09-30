# ADR 0101: One module owns the Print verdict

**Carries ADR 0010, ADR 0092 and ADR 0093.** ADR 0021 and ADR 0090 (`arrival.py` is the only writer of the Arrival fields) are unchanged.

## Context

- "May this patient be printed now?" was written six times, and the copies had drifted:
  - `_print_refusal` in `routes_desk.py`
  - the atomic filter that records `printed_at`, which left out the arrived rule
  - No-card print's Doctor-seen refusal
  - `PatientRow` in `Desk.js`
  - `ArrivedCard` in `ScanOutcome.js`, which ignored the Print window
  - `status()` in `Lookalikes.js`
- The Print window and the Operating day lived in `routes_camps.py` as `effective_printing`. About eight callers reloaded the camp days and compared ids themselves, so route modules imported route modules.
- The `PRINT_WINDOW_CLOSED`, `NEEDS_DOOR_SCAN` and `ALREADY_SEEN` errors were written out again in `routes_desk.py` and `arrival.py`.
- Issue #110 (slice 4) asks for one owner of the print rules, with the desk rendering the server's answer.

## Decision

`backend/printing.py` owns:

- **The Print window and the Operating day.** `resolve(camp, days)` is the old `effective_printing`, moved unchanged and pure. `load(db, camp)` reads the camp's days once and returns them with the state. `operates(state, day)` is the Operating day test, and `require_open(state)` raises `PRINT_WINDOW_CLOSED`.
- **The Print verdict.**
  - `refusal(patient, state, sheet_stamp)` holds the refusal order: `ALREADY_SEEN`, then `NOT_ARRIVED`, then no refusal at all for a printed patient (a Reprint), then `PRINT_WINDOW_CLOSED`, then `NEEDS_DOOR_SCAN`.
  - `verdict(patient, state)` gives the desk `{allowed, code, stage}`. `stage` is seen, printed, arrived or booked, in that order of precedence.
  - The desk Print action arrives an unarrived booking that has a No-card print, so `verdict` skips the arrival rule for one and maps `NOT_ARRIVED` to `NEEDS_DOOR_SCAN`. It never returns `NOT_ARRIVED`, and it reads its facts by truthiness, so `verdict(ser_patient(p)) == verdict(p)`.
  - `require_not_seen(patient)` is No-card print's Doctor-seen refusal.
- **The matching atomic filter.** `first_print_filter(patient_id)` is the verdict's rules about the patient document as a query. It includes `arrived_at`, so "the verdict and the write agree" is enforced by a test over every combination of status, arrival, print and hold, rather than by remembering. The Print window is camp state and cannot be in the filter (ADR 0093 accepts a window that closes between the check and the write).
- **The Sheet stamp.** `sign_sheet(patient, state)` mints only while the window is open. Freshness is checked inside `refusal`, and a Sheet stamp still skips the closed window and never the hold (ADR 0093). A stamp with a non-ASCII signature is now "not fresh" instead of a server error.
- **The four error messages**, from one table: `error(code)`. Codes, statuses and texts do not change.

Route modules call the module and stop importing each other for it. `ser_patient(p, printing_state)` attaches `registration.print` on the payloads that reach `PatientRow`, `ArrivedCard` and `Lookalikes`, computed once per request:

- `/desk/lookup` (after the patient is found), `/desk/scan` (the arrived outcome), `/desk/scan/confirm`, `/desk/no-card` (both returns)
- staff `/register` (created, replayed and overwritten, and the Lookalike rows)
- `/patients/search` (one read for all rows, none when there are no results)

`/desk/arrive`, `/desk/print`, the mismatch and ambiguous rows and `/self-register` are unchanged. `ser_day` takes the state instead of a boolean.

The desk renders `registration.print` and derives nothing. `ArrivedCard` now respects the Print window and the identity hold. The Reprint offer (typed find only) stays a desk rule in `deskSession.js`.

## Consequences

- A verdict is a snapshot. The desk already learns `printing_open` and `operating_day_id` from its polled camp state. When either changes, `deskSession` drops `found` and `searchResults` (`printingChanged`), so no row shows Print while the window is closed and none stays "closed" after it opens. It does not touch `seq`, so a Paper check that is open is still recorded. It bumps a separate `findSeq` instead, which every lookup and search reply must match, so a reply already in flight at the flip is dropped rather than bringing back a verdict from the old window. The server re-checks every print with the same codes and messages.
- Lookup on a hit and search with results add one indexed `camp_days` read per request, never one per patient. The other payloads add none. Check p95 against the perf baseline after deploy.
- The desk has no fallback for a missing `print`: a fallback would be a second copy of the rule. The payload tests are the guard.
- Follow-up: slice 2's Queue stage (ADR 0099) will own the Doctor-seen predicate and the stage ladder. Once both land, `printing.require_not_seen` and the seen and stage tests should import it. Do not build a second one. `lock_resolution._refusal` and `overwrite` restate "printed or seen" as the Aadhaar-overwrite guard; that is a different rule and is left alone.
- The `print_override` writers stay in `routes_camps.toggle_print_window`, and `resolve` is the only reader. Move the writer in here if a second one ever appears.
- `CARD_IN_HAND` and `checked_manual_note` moved from `routes_registration.py` to `lock_resolution.py`, beside `is_manual` and `is_scanned`, so `routes_desk.py` no longer imports a route module.

## Rejected alternatives

- **Send only `printing_open` and keep a JavaScript twin of the rules (`canPrint(patient, window)`), with tests that hold the twin and the Python in step.** That is the status quo with a shared helper. The two copies had already drifted (`ArrivedCard` ignored the window), and it leaves the atomic filter and No-card print's Doctor-seen check as separate hand-written copies.
- **A per-row `GET /desk/print-verdict` endpoint.** It adds a round trip per row on a desk that already reads the row.
