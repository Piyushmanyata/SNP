# Clinical operation safety

Date: 2026-09-24 (ADR 0065). Replaces the claim and compensation design of 2026-09-05.

## Writes

`complete`, `undo`, `correction` and `fulfilment` each run through `clinical_operation.run` (ADR 0088), in one MongoDB transaction via `db.in_transaction`. Each handler supplies its payload, supersede rule and apply step. An operation id is required for all four. The runner:

1. `$inc`s `patients.clinical_seq`, so a second writer on the same patient conflicts and the driver retries it on fresh state;
2. replays a committed operation with the same id, if one exists;
3. calls the apply step, which re-checks every gate with the pure guards in `clinical_state.py` (printed, completed, generation, draft version, review, seats);
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
| Replayed undo after a new completion | 409 `OPERATION_SUPERSEDED` |

An operation id that loses a duplicate-key race replays the winner's stored row. A completion retry skips the retired-catalogue check, so it still replays after a medicine or power is retired.

## Desk side

`frontend/src/components/clinical/useClinicalCommand.js` sends all four writes. It keeps one operation id per unchanged payload, so a retry after a dropped connection replays. A changed payload, a success, a patient change, a reload or `reset()` gets a new id. The expected (or, for issue, reviewed) generation is the patient's clinical generation, falling back to 0.

`STALE_GENERATION`, `DRAFT_VERSION_CONFLICT`, `OPERATION_SUPERSEDED`, `STALE_REVIEW` and `OPERATION_CONFLICT` show the Reload banner. Any other refusal is shown as an error and keeps the id. Draft save uses the same classification.

## Tokens and SMS

`tokens.defer` (ADR 0089) records a `queued` `reminder_ledger` row keyed by the new Token's id in the same transaction when it schedules OT or Spectacles to be made. After commit, a background task claims it (`queued` → `pending`) and calls the provider. A→B→A sends three messages.

## Drafts

A draft save requires an unlocked transcription and the draft version the request read. A draft that loses a race with completion or another draft gets `409 draft_version_conflict`.

## Corrections

Corrections apply explicitly supplied fields, so clearing a line, medicine list or measurement is applied. A correction refuses with 409 `surgery_scheduled` or `SPECS_SCHEDULED` while that line has an active Token. Record `cancelled` or `declined` first. Inside the same transaction, the correction hands each existing Fulfilment line to `fulfilment_line.correct`, which re-derives an issued medicine or Fixed-power specs line against the corrected revision and marks what it changed as corrected after issue (ADR 0097, ADR 0098). A fulfilment issue reads the same module: `fulfilment_line.check_issue` derives the medicine status from the committed revision before the transaction, because the payload hash covers it, and `fulfilment_line.issue` decides inside the transaction what the line becomes over a prior one.

## Verification

- `tests/test_clinical_transactions.py`: an error after the seat `$inc` and a failed SMS intent leave nothing behind; concurrent lines and duplicate issues; replay after undo; `SPECS_SCHEDULED`.
- `tests/test_clinical_operation_safety.py`: foreign and changed replays, and injected failures at each write.
- `tests/test_clinical_draft_concurrency.py`: draft races.
- `tests/test_fulfilment_line.py`: the Fulfilment line rules with no database, including a correction followed by a re-issue.
