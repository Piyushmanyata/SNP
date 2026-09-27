# ADR 0089: One module owns OT seats, Tokens and Schedule edits

**Carries ADR 0066.**

## Context

- The rule "one OT Schedule Day seat per active IOL surgery Token" was split. A helper took the seat. The Fulfilment handler released it with a raw decrement, next to an inline Token cancel and an inline Token SMS record.
- Deferral used a string-keyed config (`DEFERRAL_CONFIG`) that was looked up by attribute name on both the database and the request body.
- Schedule edits, Token replacement and the Patients to phone list lived in `routes_clinical.py`.
- Issue #88 (slice 4) asks for one Token module that owns all of these.

## Decision

`backend/tokens.py` (not `token.py`, which would shadow the standard-library module) owns:

- **`defer(line, patient, transcription, prior, day_id, session)`:**
  - IOL surgery takes a seat, only while `seats_taken < seat_limit`.
  - Re-issuing to the same day takes none.
  - A move to another day releases the old seat in the same session.
  - A full day is refused with `DAY_FULL`, or `NO_CLINICAL_DAY_AVAILABLE` when no later day has a seat.
  - Spectacles to be made takes no seat and moves the day's `booking_seq` on.
  - Every deferral issues the next Token version, closes older active versions, and records the Token SMS intent keyed by the Token.
- **`close(line, transcription_id, prior, session)`:** a non-deferred outcome closes the line's active Tokens. It gives back the OT seat if the prior outcome was deferred to an OT Schedule Day, guarded against going below zero.
- **`edit_day(kind, day, changes, background_tasks)`:** the OT Schedule Day and Specs collection day Schedule edit.
  - It refuses `SEAT_LIMIT_BELOW_ASSIGNED`, `THE_DAY_CHANGED_RELOAD_AND_TRY_AGAIN` and `DAY_EXISTS`.
  - A change to the date, venue or end date is material. It replaces every active Token and records one notice per patient keyed by the edit revision.
  - Any other change keeps the Tokens and syncs their SMS venue.
- **`patients_to_phone(now)` and `mark_contacted(token, actor, now)`.**

The deferral rules are explicit per line (`_book_ot_day`, `_book_specs_day`), not looked up by attribute name. The routes keep request-shape validation and day creation. Storage, codes and responses are unchanged.

## Consequences

- A seat bug has one place to look.
- Token tests (`test_tokens.py`) assert seat counts and Token states through the verbs, not Mongo update shapes. The route test that failed the seat release by matching its update shape is gone. The runner's rollback test (ADR 0088) covers atomicity.
- Chunking a very large Specs collection day edit, which #88 leaves out of scope, now has one place to land.

## Rejected alternatives

- **Keep the seat helper and move only the release.** It is smaller, but the take and release rules would still live apart from the Token versions that justify them.
- **Put the Token rules in the Clinical operation runner.** Schedule edits are not clinical operations, so the rules would split again.
