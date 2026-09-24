# Clinical operation safety

Date: 2026-09-24 (ADR 0065). Replaces the claim and compensation design of 2026-09-05.

## Writes

`complete`, `undo`, `correction` and `fulfilment` each run in one MongoDB transaction through `db.in_transaction`. The callback:

1. `$inc`s `patients.clinical_seq`, so a second writer on the same patient conflicts and the driver retries it on fresh state;
2. replays a committed operation with the same id, if one exists;
3. re-checks every gate (printed, completed, generation, draft version, review, seats);
4. writes the seat, Token, fulfilment, revision and patient changes;
5. inserts the `clinical_operations` row with the result.

Every read and write in the callback passes `session=`. The callback has no side effects outside MongoDB, because the driver may run it more than once.

## Replay

`clinical_operations.operation_id` is unique.

| Request | Result |
|---|---|
| Same id, same kind and hash | The stored result |
| Same id, different kind or hash | 409 `operation_conflict` |
| Replayed completion after an undo | 409 `OPERATION_SUPERSEDED` |

An operation id that loses a duplicate-key race replays the winner's stored row.

## Tokens and SMS

Scheduling OT or Spectacles to be made inserts a `queued` `reminder_ledger` row keyed by the new Token's id in the same transaction. After commit, a background task claims it (`queued` → `pending`) and calls the provider. A→B→A sends three messages.

## Drafts

A draft save requires an unlocked transcription and the draft version the request read. A draft that loses a race with completion or another draft gets `409 draft_version_conflict`.

## Corrections

Corrections apply explicitly supplied fields, so clearing a line, medicine list or measurement is applied. A correction refuses with 409 `surgery_scheduled` or `SPECS_SCHEDULED` while that line has an active Token. Record `cancelled` or `declined` first.

## Verification

- `tests/test_clinical_transactions.py`: an error after the seat `$inc` and a failed SMS intent leave nothing behind; concurrent lines and duplicate issues; replay after undo; `SPECS_SCHEDULED`.
- `tests/test_clinical_operation_safety.py`: foreign and changed replays, and injected failures at each write.
- `tests/test_clinical_draft_concurrency.py`: draft races.
