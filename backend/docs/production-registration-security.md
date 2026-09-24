# Registration and staff production contract

## Decision: bind registration retries to the original patient

Request IDs are client supplied. Reusing one previously returned the stored patient before checking the submitted identity or camp, including from the public registration endpoint.

Both the ordinary retry path and the database uniqueness-conflict path now require the same camp, original booked day, normalized name, and scanned Aadhaar last four digits and date of birth. A mismatch returns `409 REGISTRATION_REQUEST_CONFLICT` without a patient record. Arrival may change the operating day; retries still compare the original booking. Trusting the request ID alone was rejected because it is an idempotency key, not proof of patient identity.

Public registration errors expose only a code and message. Authenticated desk duplicate handling retains patient details needed to resolve registrations.

## Decision: use database constraints and existing session versions

- A missing registration request ID is omitted from the patient document. MongoDB's sparse unique index allows multiple missing fields but treats explicit null as an indexed value; retaining null would reject the second registration without an ID.
- Concurrent Aadhaar person creation uses the winning row after an Aadhaar-key uniqueness conflict. Unrelated uniqueness errors still propagate.
- Concurrent staff creation returns `409 Name already exists` after the unique name index rejects the losing insert.
- Disabling staff increments `session_version`. Reenabling the account permits fresh login but cannot revive tokens issued before disabling. No separate revocation store is needed.

## Camp dates

Camp dates and setup-day dates must be real calendar dates in `YYYY-MM-DD` format. Pydantic validates inputs before persistence while retaining strings for MongoDB ordering, print-day comparisons, and existing API consumers. Converting stored fields to date objects was rejected because it would change these contracts.

## Decision: retry only patient-code uniqueness collisions

Eight-character patient codes retain their unique MongoDB index. When MongoDB identifies that exact index key in a duplicate-key error, registration generates another code and retries, up to three insertion attempts. The registration number and reserved camp seat are reused. Request replays and Aadhaar duplicates retain their existing handling; unrelated database errors propagate and release the seat. Retrying arbitrary uniqueness errors was rejected because it would hide conflicting identities or broken counters.

## Decision: claim a manual identity atomically

Both registration and door scans attach Aadhaar only while the stored patient remains unscanned and has no linked person. The same conditional database write returns the updated row, eliminating a second read. A competing scan receives `409 NOT_A_MANUAL_ENTRY` and must scan again. Checking the previously fetched patient alone was rejected because a second card could replace the first card's completed identity update.

Arrival also uses a conditional write so a competing volunteer cannot replace the original arrival timestamp or attribution. Successful arrival returns the updated row without another query.

## Decision: preserve existing printed UUID codes

Before short codes, patient QR values were lowercase UUIDs. The shared identifier parser now canonicalizes UUID input with Python's UUID parser and continues uppercasing short codes. This restores existing printed slips at both desk and clinical lookup without modifying stored identifiers or reprinting slips. Uppercasing every token was rejected because MongoDB identifier matches are case sensitive.

## Decision: keep accepted SMS messages out of the retry queue

A provider success followed by a failed ledger write leaves the claim pending and reports the accepted send. It does not mark that message failed, so a later worker run cannot send it twice. Known provider failures remain retryable when their failed status can be persisted. Errors recording a failed send are logged and contained so they cannot fail a committed registration or clinical operation. Blindly retrying pending claims was rejected because provider acceptance is uncertain after a process or database failure; unresolved pending claims require provider reconciliation.

## Verification

`python -m pytest backend/tests/test_registration_staff_production.py backend/tests/test_auth_pin.py backend/tests/test_registration_invariants.py backend/tests/test_hardening.py backend/tests/test_camp_operations_matrix.py -q`

Regression cases exercise sparse-index null collisions, uniqueness races, account disable/enable token revocation, public error privacy, mismatched request replays, an arrival-day change followed by a valid retry, and invalid versus valid leap dates. Each test runs against its own real MongoDB database; races are forced into a fixed order with barriers. Production-stack verification is separate.

`python -m pytest backend/tests/test_registration_sms_reliability.py backend/tests/test_reminders.py -q` also covers generated-code collisions, unrelated unique-index failures, database failures during SMS bookkeeping, and prevention of repeat sends after provider acceptance.

The reliability regressions additionally exercise competing Aadhaar scans, competing arrival stamps, and legacy UUID lookups. Backend static checking preserves the optional timestamp contract, validates cookie policy choices, and requires FastAPI's injected background-task argument explicitly; direct function tests pass `None` to exercise synchronous notification handling.
