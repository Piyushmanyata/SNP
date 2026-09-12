# Clinical concurrency and recovery audit

Date: 2026-09-12

## Context

Undo checked issue history without holding the prescription write claim. An issue could finish between that check and undo's patient update, leaving issued medicine attached to a registration marked unseen. Corrections addressed only by patient ID also skipped the claim. Completion did not participate in the claim and could commit the patient before a transcription or operation-ledger failure made the request impossible to retry.

The correction compatibility payload accepted arbitrary values in `changes`. It processed these values before schema validation, so a non-list medicine payload raised an internal error. The unused legacy fulfilment cleanup function also retained destructive deletion and seat-release logic with no callers.

## Decision

Completion, undo, corrections and issuing share the existing Mongo transcription write claim. Completion ensures the transcription exists before committing the patient and rechecks the registration under the claim. A matching retry can finish transcription and operation-ledger persistence after the patient commit without incrementing the clinical generation again. The saved revision still verifies the patient and original request content. A different current revision cannot be overwritten by recovery.

Undo holds the claim while checking issue history and committing its change. Patient-only corrections resolve the existing transcription before claiming it. Correction values are validated with the completion request model before catalogue resolution and clinical validation. Missing or null diagnosis and medicine lists in legacy saved revisions default to empty lists before requested changes are applied. Requested malformed values still return a client error before any prescription state changes. The unused cleanup function is removed; active fulfilment finalization remains the seat-release authority.

This reuses the existing conditional-write protocol rather than adding a second lock or requiring a replica-set transaction deployment. The fulfilment HTTP handler keeps FastAPI's required `BackgroundTasks` type; direct tests explicitly select synchronous delivery when needed.

## Consequences and verification

Six regression cases cover the undo/issue interleaving, patient-only correction lock bypass, completion lock bypass, interrupted completion transcription persistence, interrupted completion ledger persistence and malformed correction content. Existing clinical matrix, scheduling, fulfilment and production-backend tests check related workflows. Production clinical modules also pass the configured mypy check.

The existing two-minute claim lease still does not make multi-document writes transactional. Abrupt failure during a correction or undo, an expired lease held by a stalled worker, or a disconnected Mongo write whose outcome is unknown can require reconciliation. This change specifically repairs interrupted completion retries and ordinary concurrent workflow mutations; it does not claim crash-proof transactions or measured VPS latency improvement.
