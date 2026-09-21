# SNP backend production review

Reviewed snapshot: `Piyushmanyata/SNP` main `0e1c9feb8211820f241df0b05e22f55bbba4c91f` (2026-09-19). Review scope: clinical lifecycle, desk, camps, reports, staff/authentication, templates, SMS/reminders, indexes, and deployment. No application files were changed. No server, browser, production endpoint, or SMS provider was contacted.

## Evidence and limits

Findings below come from current source, not previous audit reports. Three behaviors were reproduced by executing the actual AST-extracted source functions against in-memory collection fakes: a stale draft overwrites a newer draft; replaying a correction revision after patient commit gives `409 operation_conflict`; an arbitrarily old pending SMS claim cannot be reclaimed. These are focused logic experiments, not Mongo concurrency or device tests. Source test files became available during review; the existing completion and issue recovery tests are substantial, but corresponding correction/undo crash cases are absent. System Python lacked FastAPI at review time; the root agent is installing the repository environment and owns full test execution.

Priority meanings: P1 = resolve before relying on the affected production workflow; P2 = operational correctness or meaningful optimization; P3 = follow-up hardening. No measured latency, live data corruption, or delivered-message failure is claimed.

## Confirmed findings and executor tasks

### B01 — P1 — Stale clinical drafts silently overwrite newer edits

Evidence: `backend/models.py:142` declares `expected_draft_version`; `backend/routes_clinical.py:299-311` never uses it. `_upsert_transcription`, lines 246-287, rereads the current version and compares that freshly read version instead of the version the operator edited. Its CAS protects overlapping database writes, but not two sequential saves from stale screens.

Reproduction: operators A and B load draft version 1. A saves new BP/remarks, producing version 2. B submits the version-1 form after A's request completes. B gets success, version 3, and A's changes disappear. The source-function experiment produced versions 2 then 3 and retained `stale operator B`.

Fix: require and validate the caller's expected draft version, use it in the update predicate, and return a structured 409 with current version on mismatch. Define initial creation as version 0 and use the unique patient/transcription index to make the losing first save conflict. Return the current version on lookup and preserve the operator's unsaved form on conflict. Confirm completion policy when another operator has a newer draft.

Tests: sequential stale saves; simultaneous first saves; concurrent saves from the same version; retry of the same operation; locked completion; no mutation on conflict. Retain existing completion-versus-draft race tests.

### B02 — P1 — Correction and undo cannot recover after partially committed writes

Evidence: correction commits `patients.committed_revision_id` and generation at `backend/routes_clinical.py:985-989`, then writes transcription, audit, and operation at 990-1009. On retry, `prepare_revision` receives the now-current revision as predecessor (981-984) and compares it against the originally stored predecessor (`backend/clinical_state.py:237-262`), returning `operation_conflict`. The actual source-function experiment confirmed that conflict. Undo clears the committed revision at `routes_clinical.py:391`, before superseding the previous operation, unlocking transcription, and recording its result (394-415). A retry after that commit but before operation persistence reaches `not_completed` at 388-389.

Impact: a transient database error or restart can leave the canonical revision and displayed transcription inconsistent, or leave an undone patient with a locked draft. The response suggests failure but a durable partial state change occurred. Completion already has recovery handling at 343-364; its existing regression test is `backend/tests/test_clinical_operation_safety.py:231-254`.

Fix: persist an operation intent and immutable predecessor/expected generation before mutation. Make correction/undo finalization replayable from their own committed state and never increment generation twice. Make the audit insert unique by operation/revision. Keep operation identity separate from the latest mutable patient state. Standalone Mongo is currently deployed, so do not introduce transaction-dependent code without explicitly changing deployment to a replica set.

Tests: inject failures after patient commit, transcription update, prior-operation superseding, audit persistence, and result persistence. Retry identical request and assert one generation change, one audit entry, matching transcription/canonical revision, correct lock state, and identical result. Changed payload under the same operation ID remains 409.

### B03 — P1 — Interrupted fulfilment can strand a patient or leak OT capacity

Evidence: `backend/clinical_state.py:346-365` persists issue authorization without a lease/recovery deadline. Another operation is refused while `issue_auth_op` is present (355-356); corrections are also blocked by `routes_clinical.py:937-938`. Recovery exists only when the exact operation is replayed (`routes_clinical.py:703-746`). Separately `_consume_seat` increments OT capacity at 464-469 before slip/fulfilment persistence at 589-602 and 782-799. The reservation has no operation marker; a process death bypasses exception rollback. Slip records do not contain the operation ID (866-883).

Reproduction: terminate the worker after OT seat increment but before fulfilment save. Replay the same request after the two-minute transcription lock expires. There is no stored fulfilment to recover and a second seat may be consumed. If the original operation ID is lost on browser reload, a new issue/correction remains blocked indefinitely. Ordinary caught exceptions and completed-issue cleanup are already handled; this finding is specifically about restart/cancellation windows and recovery without the original browser state.

Fix: persist recoverable operation state, make seat acquisition/release idempotent by operation ID, and add a reconciler/operator recovery path for interrupted issues. Never simply clear the authorization lease without reconciling reservations/fulfilment. Fence state transitions against late workers. Persist client operation IDs through reload.

Tests: kill/restart after each durable step; retry same ID; retry from another device with a recovery action; last-seat contention; no duplicate seat, active slip, or physical-issue record; never release another patient's seat.

### B04 — P1 — SMS can disappear permanently, and provider error JSON is accepted as success

Evidence: clinical SMS is only queued in process memory via `BackgroundTasks` before the operation is marked committed (`backend/routes_clinical.py:834-849`). A committed replay returns without requeuing SMS (707-711). Registration also uses background tasks (`backend/routes_registration.py:470-471,517-518`). `backend/sms.py:45-57` refuses any existing ledger status except `failed`, including indefinitely old `pending` records; the source-function experiment confirmed an old pending row cannot be reclaimed. The daily cron counts only `failed`, so pending does not make a run incomplete (`backend/routes_reminders.py:91-94`). `backend/msg91.py:48-50` returns a string from any HTTP-200 JSON body, without checking success or requiring a provider request ID; `sms.py:113-118` then records it as sent.

Reproduction: restart after the HTTP response/committed operation but before background execution; restart after pending ledger insert but before network send; return an HTTP-200 body containing an error `message` or an empty object from the provider fake. The former cases can lose a notification; the latter is recorded as sent. The provider's precise success/error schema must be checked against its official current contract before implementing validation. The root agent confirmed that project documents deliberately treat pending provider state as uncertain to avoid duplicate sends. Preserving that state is intentional, not itself a bug; the gap is durable enqueue/reconciliation and visibility, including distinguishing unsent pending from unknown provider acceptance. Do not automatically resend every stale pending row.

Fix: durable SMS outbox enqueued with a recoverable business operation, worker claim leases, bounded retries/backoff, explicit pending/accepted/failed/unknown states, and admin retry visibility. Distinguish provider acceptance from handset delivery. Unknown acceptance after a network timeout needs reconciliation/idempotency policy; blindly retrying can duplicate messages. Validate the provider response before recording acceptance. Do not require every one of six template IDs just to send an independently configured message type (`msg91.py:17-20`), unless readiness intentionally blocks all SMS and makes that visible.

Tests: process-failure windows; provider HTTP/JSON failures; unknown acceptance; retry without duplicate acceptance; registration/token retry in addition to D-1 reminders; missing one template; pending ages visible and counted.

### B05 — P1 — Door confirmation can mutate a registration from the wrong camp

Evidence: `backend/routes_desk.py:249-263` checks the active camp's print window, then loads the target registration using only `_id`; it never checks `patient.camp_id == active_camp._id` before `_apply_overwrite`. The overwrite happens before `_stamp_arrival` checks the target's own camp. Thus the request can fail after changing a different camp's manual registration. Other desk ID-based writes and clinical `_require_printed_patient` likewise do not consistently constrain live writes to the active camp (desk 266-275, 334-355; clinical 234-243).

Reproduction: active camp A with open printing, manual patient in camp B, `POST /api/desk/scan/confirm` using B's patient ID and a valid card. Patient B is changed before any later target-camp failure. No tampered role is necessary; a stale screen is sufficient.

Fix: scope the selection and atomic overwrite predicate to the intended camp and validate the entire transition before mutation. Define explicit historical-read/reprint behavior separately; do not accidentally forbid legitimate historical clinical history. Return a helpful `camp_changed` conflict for an operator whose screen predates activation changes.

Tests: A/B cross-camp IDs; activation between read and save; foreign-camp manual confirmation leaves every field unchanged; historical reads retain intended access.

### B06 — P2 — Reminder batches silently omit records beyond 10,000 and do sequential network work

Evidence: `backend/routes_reminders.py:48` truncates camp patients to 10,000 per day and line 60 truncates all matching slips of a type to 10,000. There is no continuation cursor. `_send_each` sends serially (30-38); `_token_targets` additionally makes a patient query and sometimes a schedule query per slip (64-74). `backend/reminder_worker.py:31` allows 120 seconds for the whole run while each provider request can take 20 seconds (`msg91.py:48`). For example, 1,000 sends averaging 0.2 seconds need 200 seconds even before database work; this is an illustrative bound, not a measurement.

Fix: cursor/chunk-based target enumeration without silent truncation, batch join/lookups, bounded provider concurrency respecting actual rate limits, and durable jobs. The cron endpoint should enqueue/claim a run and return promptly; worker progress must survive restarts. Index patient camp-day access after measuring with real Mongo explain plans (no camp_day_id index is currently created in `db.py:125-159`).

Tests: 10,001 and 15,000 same-day patients, 10,001 slips, invalid phones, shared phone with distinct patients, a deliberately slow provider, restart mid-run, overlapping schedules, and no missing tail records.

### B07 — P2 — Schedule edits leave issued tokens and messages inconsistent

Evidence: specs day edits overwrite venue/window at `backend/routes_clinical.py:1132-1136`, while slips snapshot those values at 874-878 and specs reminders reuse those snapshots (`backend/routes_reminders.py:70-78`). OT reminder venue reads the current schedule (71-74) while existing slips retain the earlier venue. Deduplication uses only patient/type/date (`sms.py:45-49`), so a same-date time/venue change cannot produce a new notification through the same token-send path. `get_slip` also attaches current surgery-eye/vitals to an older OT slip (`routes_clinical.py:903-906`) without a corresponding slip version change.

Fix: explicitly version schedules and issued slips. Once people are booked, either prevent a material edit until the admin reviews its affected patients, or run a durable reschedule operation that invalidates old slips, issues updated versions, records who changed what, and queues updated notices. Preserve the reviewed prescription revision on issued clinical documents. Clinical corrections to already issued/scheduled instructions need explicit re-review semantics.

Tests: edit after booking, same-date venue/time changes, cancellation, replay, old token display, and consistent printed/SMS/admin information. Validate intended clinical-correction policy with the project owner before changing it.

### B08 — P2 — Leaderboard query count grows with staff count; export buffers the entire camp

Evidence: `backend/routes_reports.py:45-75` performs `2V + 4L` sequential count queries for V volunteers and L leads, in addition to collection reads. Fifty volunteers and five leads cause 120 count queries per request. CSV export loads patients, revisions, transcriptions, fulfilments into memory and renders them all on the async request loop (`routes_reports.py:187-206`); `StreamingResponse(iter([buf.getvalue()]))` streams one already-built string, not bounded row chunks. Fulfilment data has an independent 100,000-record cap, so sufficiently large camps can lose line data before reaching the patient cap.

Fix: use grouped aggregations for credit totals, preserve the stored `registrar_team_lead_id` attribution, and join staff metadata in a bounded number of calls. Stream exports in deterministic patient batches with projected fields and cancellation/backpressure; keep CSV-formula escaping. Use keyset pagination and verify index coverage. Benchmark at the actual intended 15,000 patients/50 concurrent users rather than promising a latency number from source alone.

Tests: score parity including self-registration and team changes; constant query count as staff grow; missing/deactivated staff; export row/line totals, formula safety, bounded memory, and normal registration latency during export.

### B09 — P2 — Admin setup has incomplete concurrency and deletion guarantees

Evidence: camp setup idempotency does `find_one` followed by `insert_one` without catching a unique-key race (`backend/routes_camps.py:93-105`), despite the unique setup-request index (`backend/db.py:117-120`). A reused setup ID silently reuses the old camp even when the submitted identity differs. Camp activation first deactivates all camps and then activates one (218-220), exposing an empty-active interval and leaving no active camp if interrupted. Camp/day deletion checks references and then deletes in separate operations (235-238,328-330), allowing an admitted concurrent registration to reference a deleted record. Camp-day capacity is freely reduced at 250-251, unlike the guarded OT capacity update (`routes_clinical.py:1066-1078`).

Fix: store/compare setup request identity and recover duplicate-key races; make active-camp switching a serialized/recoverable operation or use one atomic active-camp pointer. Prefer archive/closed states for camps/days with live workflows; recheck admission against lifecycle state and prevent deletion races. Decide whether registration capacity is planning-only before applying OT-style hard-cap semantics: existing ADR naming indicates that distinction may be intentional.

Tests: same setup ID same/different payload concurrently; restart mid-activation; registration racing archive/delete; shrinking planned capacity with existing registrations; clear structured conflict responses instead of 500s.

### B10 — P2 — Readiness and backup configuration do not prove recoverability

Evidence: production Docker health checks `/api/health` (`docker-compose.prod.yml:49-54`), which unconditionally returns success (`backend/routes_reports.py:355-357`), while a real database readiness endpoint exists at 360-370. Hourly archives are held in a volume on the same deployment host (`docker-compose.prod.yml:103-124`; `ops/backup.sh:4-13`); failed backups only write stderr and no restore validation is performed by this setup. Database deployment is standalone Mongo.

Executor gate: use readiness for release/traffic health, retain liveness for process checks, and verify fresh migrations/indexes as part of release. Add monitored backup age/failure state and an independently stored copy if losing this VPS must not lose patient data. Restore to a disposable database and verify patient/clinical/ledger counts and essential relationships; record achieved RPO/RTO. These are configuration/operational gaps, not evidence that the actual VPS has failed or lacks any separate backup outside this repository. Coordinate deployment with the root agent; this reviewer has no VPS authorization role.

### B11 — P3 — Invalid scanner identifiers can produce server errors

Evidence: `backend/routes_desk.py:27-28` converts any all-digit input to an integer and queries Mongo without a bound. The clinical equivalent checks signed-64-bit range at `routes_clinical.py:173`, but still parses unbounded digit text before that check. `parse_patient_identifier` does not bound length (`backend/helpers.py:143-153`). A very long number can raise Python's integer-string conversion error; an ordinary 20-digit out-of-range number can fail BSON integer encoding at desk lookup.

Fix/tests: centralize identifier parsing and length/range validation before integer conversion; accept current valid UUID/registration formats; return 400/404 consistently for long digits, Unicode numerals, malformed URLs, and oversized inputs. Do not log raw scanner payloads.

## Workflow coverage and preserved safeguards

| Workflow | Source reviewed / safeguards to preserve | Main follow-up |
|---|---|---|
| Login, PIN change, reset, disable/enable | `routes_auth.py`, `security.py`, `routes_staff.py`: atomic attempt counting, bcrypt offloaded to thread, PIN-change requirement, database session-version checks, ownership controls for team leads | Default staff/reset PIN is shared `1234`; replace with unique expiring onboarding credentials if project policy permits. Logout currently clears cookies only (`routes_auth.py:117-122`); define shared-device revocation policy. |
| Camp setup, activate, dates, print window | `routes_camps.py`: admin role gates, unique active-camp index, date schema validation, time-limited print override | B09; preserve planning-seat policy. |
| Door lookup, Aadhaar confirmation, arrival | `routes_desk.py`: duplicate/manual resolution, atomic arrival stamp, no arrival capacity debit | B05, B11. Registration/scanner proof itself reviewed by another agent. |
| Prescription preview/print and identity exception | `routes_desk.py:279-397`: arrival required, print-window checks, already-seen block, admin identity-exception reason | Keep print preview free of writes. Physical print success cannot be inferred from a button/API alone; preserve safe reprint behavior. |
| Draft, complete, correction, undo | `clinical_state.py`, `routes_clinical.py`: immutable revisions, generation comparisons, per-transcription write claim, completion validation, undo forbidden after issuing | B01-B03. Do not remove existing safeguards to simplify UX. |
| Medicine / fixed specs / made specs / hospital | `routes_clinical.py`: whole prescription review, prescribed-line enforcement, per-medicine outcomes, fixed-power validation, mutually exclusive optical/surgery lines, atomic OT seat increment | B03, B07. Actual made-specs collection and completed surgery statuses are not represented by the current matrix (420-428); treat adding those as a scope decision, not a defect assumed from naming. |
| Clinical history, corrections, slips | `routes_clinical.py:893-1042`: role restrictions, batched history lookup | B02, B07; distinguish current status from historical issued facts. |
| Sponsor logos | `routes_templates.py`: admin write, MIME allowlist, strict base64, 2 MB/image cap, max six processed | Add unique camp_id template index for racing initial upserts; consider object/static asset delivery and true image decoding before accepting a logo. Lower priority than lifecycle fixes. |
| Board, KPIs, leaderboard, CSV | `routes_reports.py`: board uses some parallel/aggregate queries, CSV escaping, admin export | B08. Board transcription backlog (`seen_today - transcription_count`, 265-267) is normally zero under completion-only seen semantics; label a meaningful operational queue. No-camp KPI shape differs from active shape (22 versus 25-30); make stable. |
| Confirmation, token, D-1 SMS | `sms.py`, `msg91.py`, reminders: per-patient dedupe, invalid-phone exclusion, canceled-slip filtering, cron secret | B04, B06, B07. |
| Deployment/startup/backup | production Compose, backend Dockerfile, nginx/Caddy, init_indexes | B10. Preserve no exposed Mongo port, non-root backend, required production secrets, secure cookies, API no-store, TLS and compressed static responses. |

## Implementation order

1. Fix B01, B02, and B05 with focused regression tests; they are localized correctness repairs.
2. Introduce recoverable clinical operation finalization/reservations for B03 before claiming restart-safe fulfilment.
3. Implement provider response validation immediately; design a durable outbox and scalable reminder batches together for B04/B06.
4. Version material schedule changes, optimize aggregated reporting/streamed export, and close admin setup races.
5. Run real Mongo fault/race tests, realistic load profiling, release readiness checks, and a restore drill. Browser/device scanner verification remains a separate task, and the root agent owns release/CI/VPS actions.
