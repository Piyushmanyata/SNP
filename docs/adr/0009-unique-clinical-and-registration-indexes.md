# ADR 0009: Unique indexes for person-in-camp, transcription, and fulfilment

## Context

Desk and clinical invariants were enforced with find-then-insert. Concurrent Aadhaar registers could create two `reg_no`s for one person in a camp. Concurrent transcriptions and fulfilment rows could skip `queue_status == seen` races and overbook OT/specs seats. `patients (person_id, camp_id)` was a non-unique index.

## Decision

- Unique partial index on `patients (person_id, camp_id)` where `person_id` is an ObjectId (manual registrations may omit it). Drop the old non-unique index of the same keys first.
- Unique index on `transcriptions.patient_id`. A `DuplicateKeyError` on first insert falls through to the existing update path (lock check + `$set`).
- Fulfilment loads the patient and 409s unless `queue_status == seen`.

`init_indexes()` on API startup is how the remote database receives these indexes.

## Consequences

Startup fails if existing documents violate uniqueness; that is the signal to merge duplicates, not to skip the index. Manual registrations without `person_id` remain allowed.

## Rejected alternatives

- Unique `(person_id, camp_id)` without a partial filter — MongoDB would reject a second `person_id: null`.
- Application-only locking — not durable across processes; the repo already keeps invariants in unique indexes plus conditional writes.
- Unique `(transcription_id, item_type)` on fulfilments — seat consume happens before insert, so a unique-index loser would overbook worse than the current find-then-insert.
