# ADR 0100: What was prescribed is read from the committed revision

**Carries ADR 0065, ADR 0067, ADR 0068 and ADR 0088.**

## Context

- A patient's prescription lives in two places. `prescription_revisions` holds every committed version and the patient's `committed_revision_id` names the current one. `transcriptions` holds the wizard's draft plus a mirror of the last commit, written in the same transaction as every completion and correction (ADR 0065).
- Readers picked one or the other by habit. The Camp records export read the transcription by `patient_id` and never checked `locked` or `committed_revision_id`. After Undo completion the mirror still holds the last committed content until the draft is edited, and after the edit it holds the edit. A patient who was never completed but had a saved draft did the same. The export printed a draft as prescribed.
- Five handlers in `routes_clinical.py` (lookup, the two reads in Fulfilment issue, the slip, the correction) and the export each hand-wrote the same revision read. The in-transaction spectacles-line guard read the transcription while every other guard in that operation read the revision.
- Issue #110 (slice 3) asks for one place that answers "what was prescribed".

## Decision

- `backend/committed_prescription.py` has two functions:
  - `of_patient(db, patient, session=None)` returns the revision named by the patient's `committed_revision_id`, or `None`. `session` is passed to the read, so Fulfilment issue reads inside its transaction.
  - `of_patients(db, patients)` is the batch form: one `find` with `$in` over the distinct committed ids, returning `{patient _id: revision}` for committed patients only. It keys each patient through that patient's own `committed_revision_id`, not through the revision's `patient_id`. No committed id means no query.
- **A patient with no committed revision has no prescription.** A committed id whose revision document is missing reads the same. Nothing falls back to the transcription, and the module never reads it.
- Moved onto the module: the lookup, both Fulfilment issue reads, the slip, the correction and the history reads in `routes_clinical.py`, and the batch read in the export.
- The Camp records export takes diagnosis, BP, blood sugar, the seven measurement columns, medicines prescribed and not given, and the prescribed fixed powers from the revision, blank when there is none. The Hospital outcome already read the revision. Column set and order are unchanged.
- **The export stays bounded (ADR 0067):** batches of 200, one `$in` per collection, three queries per batch. Its transcription query is projected to `_id` and `patient_id` and only maps a patient to the transcription that keys their fulfilments, so draft content is not transferred. The server still reads the document, because the `patient_id` index does not cover `_id`.
- The in-transaction spectacles-line guard `_assert_specs_prescription` reads the revision that `require_fresh_review` returns for the session read. The pre-transaction guards, the payload hash and the medicine-status derivation stay as ADR 0088 has them.
- `GET /api/clinical/history/{person_id}` gains `committed_revision` on each visit, serialised or `null`. The `transcription` key stays for contract compatibility. The history modal reads Dx from the revision.
- **The transcription stays the wizard's draft, and its mirror write stays in `_upsert_transcription` inside the clinical transaction (ADR 0065).** While a revision exists the mirror equals it and `locked` is true. Undo completion clears both together. A test pins this, which is why the fulfilment station, the read-only prescription and the correction modal keep reading `data.transcription`: they show it only while locked.
- **`fulfilments.patient_seen_at` is kept.** It is a timestamp, not prescription content. The board counts its seven fulfilment buckets on the covered index `{camp_id, item_type, status, patient_seen_at}` without loading a patient (ADR 0068). It cannot drift: `seen_at` is written only by completion, undo and registration, undo is refused once any fulfilment exists, and a correction never changes it. A test pins the correction half.

## Consequences

- One rule, stated once, in a module of two functions. The value is the leverage across seven call sites and the deleted divergent reads, not its size.
- **The one intended behaviour change:** after Undo completion, and for a patient who was never completed, the Camp records export shows blank prescription columns instead of the draft. An admin who diffs an export taken mid-camp against a later one will see previously filled cells go blank for those patients.
- A patient with a committed revision exports exactly what they did before, because the mirror is written with identical content in the same transaction.
- The history endpoint returns one revision per visit, up to 100 a call, and costs one more query (four, not three). The query is skipped when no listed patient is committed.
- The export benchmark dataset (`benchmark_dataset.py`) now puts diagnosis and BP on the revision rows, so a reader that fell back to the transcription would write blank cells and show up in the budget.
- A future change that drops the mirror also drops the `transcription` key from history and points the frontend's locked readers at `committed_revision`. That is out of scope here.
- Tests (`test_committed_prescription.py`):
  - the export is blank after undo and a later draft edit, and for a never-committed draft
  - the export shows the revision, not a mirror that was changed by hand
  - a 250-patient export reads each patient's own revision in one query per batch
  - `of_patient` and `of_patients` return only committed patients, keyed correctly, with no query when none is committed
  - history reports `committed_revision`
  - the mirror equals the revision and `locked` tracks the commit through complete, correct and undo

## Rejected alternatives

- **Keep reading the transcription in the export but gate it on `locked` or on `committed_revision_id`.** It fixes the two cases the tests show with fewer changed lines. It leaves two authorities for one fact: the next reader has to remember the gate, and the export would still trust a copy whose equality with the revision rests on a convention.
- **A revision lookup per exported row.** It breaks the bounded export of ADR 0067.
- **Delete the mirror now.** The frontend's locked readers and the correction modal still depend on it; that removal is its own change.
