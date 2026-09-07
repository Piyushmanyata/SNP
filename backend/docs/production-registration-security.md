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

## Verification

`python -m pytest backend/tests/test_registration_staff_production.py backend/tests/test_auth_pin.py backend/tests/test_adversarial_challenger.py::TestRegistrationDecomposedAndInvariants backend/tests/test_hardening.py backend/tests/test_camp_operations_matrix.py -q`

Regression cases exercise sparse-index null collisions, uniqueness races, account disable/enable token revocation, public error privacy, mismatched request replays, an arrival-day change followed by a valid retry, and invalid versus valid leap dates. Database race outcomes are injected into the existing in-memory test database; production-stack verification is separate.
