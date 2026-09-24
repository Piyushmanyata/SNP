# ADR 0065: Each clinical write is one transaction

Issue #50, slice S7. Supersedes the claim, issue-authorization and compensation design in `backend/docs/clinical-operation-safety.md` (2026-09-05).

## Context

- Completion, undo, correction and fulfilment each write several documents: an OT or specs seat, a Token, a fulfilment, a revision, the patient and an operation record. They ran without transactions, so correctness depended on hand-written parts:
  - a two-minute write claim on the transcription;
  - a pending `issue_authorization` sub-document on the patient;
  - `except` blocks that gave a seat back and restored the old Token;
  - `released_issues.<hash>` markers on OT days, kept forever so cleanup could run twice.
- A crash between two writes still left a taken seat or a Token with no fulfilment. The contract told the operator to "reconcile" by hand.
- ADR 0060 made MongoDB a replica set in every environment, so multi-document transactions are available.

## Decision

- **One transaction per write.** `db.in_transaction(callback)` runs `session.with_transaction`. Every read and write in the callback passes `session=`.
- **Writers on one patient conflict.** The callback first `$inc`s `patients.clinical_seq`. Two writers on one patient hit a write conflict; the driver retries the loser, which re-validates on fresh state.
- **The operation record commits with the work.** `clinical_operations` gets `{operation_id, kind, payload_hash, patient_id, result}` inside the transaction. Replay rules:
  - same id and hash → the stored result;
  - same id, different kind or hash → 409 `operation_conflict`;
  - a replayed completion whose revision is no longer the committed one (it was undone) → 409 `OPERATION_SUPERSEDED`.
  - a replayed undo after the patient was completed again → 409 `OPERATION_SUPERSEDED`.
- **The callback only touches the database**, because the driver may run it more than once. A Token's SMS is a `queued` `reminder_ledger` row, keyed by the Token's id, inserted in the transaction. After commit a background task sends it. The provider is never called inside a transaction.
- **Deleted:** the write-only `corrections` collection (revisions already hold the reason, author and predecessor), the write claim, `clinical_write_token`, `issue_authorization`, `issue_auth_op`, `released_issues`, `_ensure_transcription_locked`, `line_review`, the compensation blocks and the fulfilment `current` flag.

Also in S7:
- A correction that removes or changes Spectacles to be made while its Token is active returns 409 `SPECS_SCHEDULED`. The operator first records `cancelled`, which closes the Token.
- A line that is not prescribed stores no content.
- Retired medicines and powers cannot be newly prescribed or issued.
- "Every day is full" counts only today and later.
- `GET /clinical/corrections/{id}` is deleted; History shows corrections.

## Consequences

- An error or crash at any point leaves no seat, Token, fulfilment, revision or operation record. Issue story 19's reconciliation pass is not needed: `test_clinical_transactions.py` raises after the seat `$inc` and finds nothing changed.
- A Token never exists without its SMS intent. A→B→A sends three messages, one per Token.
- Two lines issued at once for one patient both commit; one of them retries.
- MongoDB must run as a replica set everywhere, tests included (ADR 0060, ADR 0061).

## Rejected alternatives

- **Keep the claims and compensation, add a reconciliation job.** It repairs damage after the fact and still shows a patient a Token with no booking in between.
- **A lock collection keyed by patient.** A transaction already serialises writers on the patient document, and a lock needs its own expiry and cleanup.
- **Call the SMS provider inside the transaction.** A retried callback would send twice, and a slow provider would hold the transaction open.
