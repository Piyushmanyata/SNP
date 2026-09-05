# 0027. Clinical completion before seen

## Context

Camp workflow previously required volunteers to mark patients seen before clinical transcription, awarded points on arrival, treated camera permission denial as a manual-entry unlock, and stored printing as a boolean on each camp day.

## Decision

- Only `clinical_desk_operator` accounts may draft, complete, correct, undo or issue. Admin is not a clinical bypass.
- Clinical lookup is allowed after arrival and print, before seen. Independent desk mark-seen cannot confer seen or points.
- Completing a whole prescription (including explicit no-fulfilment) commits an immutable revision, seen status and point eligibility together. Drafts do not.
- Printing availability is derived on the server from the IST calendar date plus a camp-scoped override that expires at the next IST midnight.
- Camera permission denial shows enablement guidance and Retry. Manual demographic entry unlocks after three completed unreadable scan sessions, not on stall or denial.
- Staff points equal currently completed doctor-seen registrations credited to the original registrar. Self-registration earns none.

Rejected: keeping volunteer mark-seen; permission-denial manual fallback; arrival-point scoring; a scheduler job for midnight print expiry; replica-set transactions.

## Consequence

Existing tests that required seen before transcription, treated admin as a clinical operator, or scored arrivals were rewritten. Indexes for prescription revisions and clinical operations are created at backend startup.
