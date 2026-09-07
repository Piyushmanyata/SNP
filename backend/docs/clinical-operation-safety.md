# Clinical operation request identity

Date: 2026-09-05

## Context

An interrupted completion can leave an uncommitted revision. Previously, reusing its operation ID with another patient or changed content could commit the old revision. Fulfilment retries similarly returned a record by operation ID without checking the patient or requested outcome. A simultaneous retry could also release the first request's issue authorization.

## Decision

Revision reuse compares the patient, prescription content, selected lines, operation kind and predecessor against the original request. Fulfilments reserve their request identity in the existing uniquely indexed clinical operation ledger, and persist their operation ID, request digest and reviewed revision with the fulfilment write. A mismatched request returns `409 operation_conflict`. Existing records without a request digest also refuse replay; reload their current saved state before submitting a new operation.

One request owns the patient's pending issue authorization. A simultaneous duplicate receives a conflict and cannot clear that authorization. A matching retry after persistence first acquires the transcription claim, then resumes cleanup and releases only its own authorization. This retains Mongo conditional updates instead of adding a second lock or allowing duplicate requests to share ownership.

The operation ledger retains each successful issue's original response after the current fulfilment is replaced. Replaying an older issue returns its original response without reverting the newer outcome. Pending reservations cannot downgrade a committed ledger entry, and the ledger rejects operation ID collisions across request kinds.

Pending ledger snapshots are re-read after the request owns both the patient's issue authorization and the transcription claim. The current fulfilment is read under the same ownership. A request paused before acquiring ownership therefore observes a retry that has already completed and cannot overwrite an intervening newer issue.

The saved fulfilment includes its slip ID and previous OT schedule day so post-persistence cleanup can resume. Releasing the previous OT seat atomically records the operation's hashed key under that day's `released_issues` map together with the decrement. Repeated cleanup therefore cannot release another patient's seat. Slip cancellation is idempotent, and the existing SMS ledger handles repeated delivery attempts. These release markers are retained with the schedule day.

Corrections use Pydantic's explicitly supplied fields instead of truthiness to distinguish omitted fields from intentional empty or null values. Clearing a selected line, medicine list or measurement is therefore applied and validated. Correction request hashes include prescribed lines and the no-fulfilment selection.

Draft updates atomically require an unlocked transcription, no active clinical write claim, and the draft version observed by that request. A draft that loses a race with completion, fulfilment or another draft receives `409 stale_draft`; it cannot overwrite or unlock a completed prescription. The filter lives in the shared transcription writer instead of adding a second check before the write, which would leave the race open.

## Consequences and verification

Retries cannot silently attach another patient's revision or report another patient's fulfilment as successful. Recoverable exceptions after fulfilment persistence can be retried without duplicating allocation or release. Corrections can explicitly remove erroneous data while omitted fields retain their current values. These checks do not make multi-document Mongo operations transactional: interruption before the fulfilment is durably stored can still leave a newly reserved seat or slip requiring reconciliation, as documented in `production-clinical-contract.md`. Pending provider acceptance remains uncertain and is not blindly resent.

`tests/test_clinical_operation_safety.py` covers orphan revision collisions, changed and foreign fulfilment requests, duplicate in-flight issue ownership before and after persistence, explicit correction clears, and draft writes racing completion or an active clinical claim. It also covers old-operation replay after a newer outcome and cleanup failures both before and after OT seat release. The existing clinical matrix checks successful repeat requests, stale reviews and competing allocations.
