# ADR 0088: One runner for every Clinical operation

**Carries ADR 0065.**

## Context

- Completion, undo, Fulfilment issue and correction each repeated the same steps inside their own handler: refuse a missing id, hash, look up a recorded operation, claim the patient by incrementing `clinical_seq`, look up again inside the transaction, write, record the operation, commit, recover a unique-index collision, and dispatch SMS intents after commit.
- Each kind carried its own supersede-on-replay rule inline. Completion read the `clinical_operations` collection directly. Issue and correction minted an operation id when none was sent, which silently disabled replay.
- The prescription guards were inline `if` blocks, so they could only be tested through MongoDB.
- Issue #88 (slice 3) asks for one runner, with each kind supplying only its payload, its supersede rule and an apply step.

## Decision

- `backend/clinical_operation.py` has `run(db, Operation, background_tasks)` and `is_replay(db, operation_id)`. An `Operation` is:
  - kind
  - operation id
  - patient id
  - the hashed payload
  - `apply(patient, session) -> (result, sms_intent_ids)`
  - an optional `is_superseded(patient, stored_result) -> message or None`
- `run`, in order:
  1. Refuse a missing id with `OPERATION_ID_IS_REQUIRED` (400).
  2. Hash the kind and payload.
  3. Replay a matching record, or refuse a different kind or hash with `OPERATION_CONFLICT`. Refuse a superseded replay with `OPERATION_SUPERSEDED`.
  4. Open the transaction and claim the patient.
  5. Look up the operation again, then apply.
  6. Record the operation and commit.
  7. Recover the winner after a unique-index collision.
  8. Dispatch SMS intents only after a successful commit, never on replay.
- The prescription guards are pure functions in `clinical_state.py`. Each raises the existing refusal with the existing code:
  - `require_printed`, `require_not_completed`, `require_generation`, `require_unchanged` and `require_draft_version`
  - `require_undoable`
  - `require_fresh_review` and `require_line_prescribed`
  - `require_specs_exclusive` and `require_correction_allowed`
- The one-call `commit_completion`, `commit_undo` and `commit_correction` wrappers are gone. Apply steps call `commit(db, patient, fields, session)`.
- **Deliberate fix (issue #88, fix 4):** issue and correction now require an operation id, as completion and undo already did. The desk always sends one (#88 slice 7).
- **Fulfilment issue hashes the medicine status it derives from the committed revision.** So its handler reads the revision before the transaction and runs `require_fresh_review` and `require_line_prescribed` on that read, keeping today's refusal order. Its apply step runs the same pure guards again on the claimed state. The rule lives once, with two call points.

## Consequences

- A fifth clinical write needs a payload, a supersede rule and an apply step. Replay, claim, transaction and dispatch come with the runner.
- Runner tests (`test_clinical_operation.py`) cover:
  - a failure inside apply rolls everything back, and the retry applies once
  - payload and kind conflicts
  - supersede
  - two concurrent writers
  - dispatch only after commit
- Guard tests (`test_prescription_guards.py`) need no database.
- Route rollback tests inject failures at the storage seam (`intercept`) instead of patching route helpers by name.

## Rejected alternatives

- **A decorator around each handler.** Less code, but the claim and the replay lookup need the patient id and payload before the handler's body runs, so every handler would still build them in its own way.
- **Keep minting an operation id for issue and correction.** It keeps old clients working, but a minted id can never replay, and the desk has sent one on every write since #88 slice 7.
