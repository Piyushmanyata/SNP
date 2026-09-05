# Admin consolidation, Specs collection windows, Camp-day board, and reliability hardening

## Problem Statement

SNP Camps currently exposes overlapping and contradictory workflows, and several operational numbers cannot be trusted during a camp. The Admin dashboard still contains a deprecated Volunteer Roster even though authenticated Volunteers and Team Leads replaced roster attribution. It also embeds Staff management while the dedicated Team page provides substantially the same account-management workflow. The two surfaces have already diverged: only the Admin copy can edit an Operator line, the Team form retains hidden values after creation, and Operator line labels are duplicated.

Spectacles to be made is modelled as a capacity-limited Specs collection day. The required operating model is different: a Specs collection day has a date, venue, and required start/end time window, with no seat limit. Capacity fields, full-day refusals, seat consumption and release, “free seats” labels, Tokens, reminders, exports, and Camp-day board data all currently encode the wrong rule. A selected Specs collection day is also accepted by identifier alone, allowing a stale, past, or another camp's day to be assigned.

The Camp-day board mixes active-camp counts with global activity. Registration activity is not scoped to the active camp, Fulfilment and SMS counts can include other camps, and every enabled Volunteer is presented as a Registration desk and marked quiet even when they are not working that day. Every 15-second refresh performs a number of database operations that grows with the number of Volunteers, materializes very large row sets, and can overlap with the previous request. An older response can therefore replace newer data. Several operational KPIs sit below the activity table, Print Prescription is missing from the stage view, and the page does not communicate its camp, camp day, last refresh, loading, stale, or no-day state. Quiet state is communicated by colour alone.

The audit also confirmed the following defects outside the four reported areas:

1. **P0 — forged self-registration:** the public registration endpoint trusts a client-supplied `aadhaar_scanned` boolean and client-supplied demographics; a caller can create a registration without a successful Decode.
2. **P0 — unsafe bootstrap credential:** a new or migrated Admin can receive the repository-known PIN `1234`, and the seeded Admin is explicitly exempted from mandatory PIN change. Mandatory PIN change is not enforced as an API authorization boundary.
3. **P0 — over-broad credentialed CORS:** authenticated cookies are permitted for every RFC1918 and loopback web origin, so an unrelated LAN origin can be authorized to read or mutate the API.
4. **P0 — Camp-day capacity race:** registration checks the current booking count and inserts later; concurrent requests can both pass the check and exceed the seat limit.
5. **P0 — booking/Arrival day disagreement:** capacity uses the immutable booked day, while public occupancy and Camp-day deletion use the mutable Arrival day. Moving an Arrival can make the original booking appear to release a seat and can allow its day to be deleted.
6. **P0 — non-atomic deferred fulfilment:** schedule reservation, Token creation, prior-record cleanup, and Fulfilment replacement are separate writes. A failure can leak an OT seat, leave an orphan Token, remove the prior record, or create duplicate Fulfilment records. Cross-camp schedule identifiers are not rejected.
7. **P1 — false Print Prescription transition:** opening the print page posts the print mutation and stamps `printed_at` before the operator explicitly asks to print.
8. **P1 — SMS attempts cannot recover:** any existing pending or failed ledger entry permanently blocks another claim, while missing provider configuration or invalid data can fail before any actionable ledger entry exists.
9. **P1 — unsafe and slow Camp records export:** untrusted values can be interpreted as spreadsheet formulas, and each exported patient causes sequential transcription and Fulfilment queries.
10. **P1 — corrections bypass the clinical schema:** correction values are accepted as arbitrary data. Unknown fields can create an audit entry with no applied change, while allowed fields can receive invalid types or values.
11. **P2 — inaccurate privacy copy:** the scanner says Decode occurs on-device even though the raw QR payload is sent to the SNP backend. The no-UIDAI-call and last-four-only-storage statements are distinct and remain valid.
12. **P2 — accessibility regression:** Diagnosis controls have a 36-pixel minimum height instead of the required 44-by-44-pixel touch target. Board quiet state also lacks a visible textual status.
13. **P2 — known validation and noise backlog:** gender and OT eye remain loose strings, public routes can make a cosmetic authenticated bootstrap request, and Registration desk phone errors are only caught after submission.
14. **P1 — broken verification gate:** the legacy live-API regression suite still sends retired email/password payloads, depends on ordered global state, and partially runs against whatever answers on localhost while credential-dependent setup is skipped. The audited full run produced ten failures and 99 skips instead of a trustworthy result.

## Solution

Deliver the work as one specification with independently reviewable milestones, in this order:

1. Consolidate account management on the Team page and retire the obsolete Roster surface and runtime plumbing.
2. Replace Specs capacity with a required date/venue/time-window model while leaving OT capacity unchanged.
3. Make deferred Fulfilment selection camp-safe and failure-safe.
4. Replace the Camp-day board response with camp-scoped stage, Fulfilment, schedule, failure, and activity KPIs; render every KPI before the activity table.
5. Harden public registration, bootstrap authentication, CORS, Camp-day capacity, printing, SMS retry, corrections, CSV export, privacy copy, and touch targets.
6. Update the domain glossary, PRD, operational documentation, and ADRs that the new rules supersede.

The result is successful when there is one role-aware Team management surface, no active Roster workflow, every new Spectacles-to-be-made Token carries a valid Specs collection window without capacity, every Board number is scoped to one active camp and current camp day, and the added security/data-integrity regressions are covered at the highest existing API or page seam.

## User Stories

1. As an Admin, I want one Staff and Team management surface, so that I do not have to decide which duplicate screen is authoritative.
2. As an Admin, I want to create Admins, Team Leads, Volunteers, and Clinical Desk Operators from the Team page, so that all account provisioning remains available after the duplicate Admin tab is removed.
3. As an Admin, I want to assign a Volunteer to a Team Lead, so that Team ownership and Leaderboard attribution are explicit.
4. As an Admin, I want to set and change a Clinical Desk Operator's default Operator line, so that consolidation does not remove an existing capability.
5. As an Admin, I want to enable, disable, and reset the PIN of eligible accounts from the Team page, so that all account lifecycle actions live together.
6. As a Team Lead, I want the Team page to show only my Volunteers and permitted actions, so that I cannot view or manage another Team.
7. As a Team Lead, I want to create and reset only Volunteers assigned to me, so that delegation stays within my Team.
8. As an account manager, I want a completed form to reset every role-specific value, so that a subsequent account does not inherit a hidden Team Lead or Operator line.
9. As an Admin, I do not want a Roster tab or Roster API, so that the product reflects authenticated Volunteer identity from ADR 0025.
10. As an auditor, I want new actions attributed only to the authenticated user, so that no no-op Roster identity can appear in current records.
11. As an auditor, I want historical Roster fields retained as inert legacy data until a deliberate retention decision, so that consolidation does not silently destroy evidence.
12. As an Admin, I want to create one Specs collection day for an active camp using a date, venue, start time, and end time, so that patients receive a precise collection window.
13. As an Admin, I want the end time to be later than the start time, so that an impossible window cannot be saved.
14. As an Admin, I want blank, malformed, past, or inactive-camp Specs collection days rejected, so that unusable appointments never reach a Token.
15. As an Admin, I want to update the venue and window for a camp/date intentionally, so that a correction is explicit and does not create an accidental duplicate.
16. As an Admin, I do not want to enter or view a Specs seat limit, so that the screen matches unlimited collection capacity.
17. As a Spectacles-to-be-made operator, I want to choose only a current or future Specs collection day belonging to the patient's camp, so that I cannot issue a stale or cross-camp Token.
18. As a Spectacles-to-be-made operator, I want every available day shown with date, venue, and time window, so that I can tell the patient exactly when to attend.
19. As a Spectacles-to-be-made operator, I want an empty-schedule message that says no day is scheduled, so that an empty list is not falsely described as full.
20. As a patient, I want the Specs Token to print the collection date, venue, start time, and end time, so that I know when to collect my spectacles.
21. As a patient, I want Specs Token and reminder SMS copy to include the same time window, so that the paper and message do not disagree.
22. As an Admin, I want OT Schedule Day seat limits and atomic reservation to remain intact, so that removing Specs capacity cannot overbook surgery.
23. As a clinical operator, I want a failed defer or replacement attempt to leave the previous Fulfilment, Token, and OT seat unchanged, so that retrying is safe.
24. As a clinical operator, I want concurrent saves for the same patient and Fulfilment line to produce one current record and one active Token, so that duplicate clicks cannot split state.
25. As a Team Lead, I want all Camp-day board KPIs displayed before the Registration activity table, so that the operational state is visible without scanning the page.
26. As a Team Lead, I want to see the active camp, current camp day, and data timestamp, so that I know which operation the numbers describe.
27. As a Team Lead, I want to see Arrived, Awaiting Print, Awaiting Seen, Seen, and Transcription backlog counts, so that the required desk sequence is measurable.
28. As a Team Lead, I want Fulfilment counts split by line and meaningful status, so that “Medicine given” and “Out of stock,” or “OT done” and “OT scheduled,” are not collapsed.
29. As a Team Lead, I want to see the count of quiet active Volunteers and their last Arrival time, so that I can investigate a stopped Registration position.
30. As a Team Lead, I want the Registration activity table to describe Volunteers rather than pretend accounts are physical desks, so that the label matches the data model.
31. As a Team Lead, I want disabled or off-duty Volunteers without activity today omitted from quiet warnings, so that the Board does not manufacture alerts.
32. As a Team Lead, I want active-camp SMS failures surfaced at the top, so that communications problems are actionable.
33. As a Team Lead, I want the next OT Schedule Day's date, venue, and remaining seats at the top, so that surgical capacity stays visible.
34. As a Team Lead, I want the next Specs collection day's date, venue, and time window at the top, so that collection planning no longer implies seats.
35. As a Team Lead, I want explicit loading, no-active-camp, no-camp-day, current, and stale/error states, so that blank or old numbers are never mistaken for live data.
36. As a Team Lead, I want refreshes to stop while the page is hidden and never overlap, so that the Board does not waste field bandwidth or regress to an older snapshot.
37. As a keyboard or assistive-technology user, I want quiet state expressed in text and tables to retain clear headers and responsive overflow, so that the Board is understandable without colour or a wide screen.
38. As a patient using self-registration, I want the registration request to Decode my submitted QR and derive its demographics on the server, so that forged “scanned” claims cannot consume seats.
39. As an operator, I want the scanner's privacy copy to accurately say that the SNP backend performs Decode without calling UIDAI and stores only the last four digits, so that consent is truthful.
40. As a system owner, I want a bootstrap Admin secret supplied outside the repository and a mandatory first PIN change enforced by the API, so that a known default cannot control a fresh deployment.
41. As a system owner, I want credentialed API access limited to explicitly configured frontend origins, so that an unrelated LAN website cannot use an authenticated session.
42. As a patient, I want concurrent bookings for the last Camp-day seat to allow exactly one registration, so that capacity remains a hard booking limit.
43. As an Admin, I want public occupancy and Camp-day deletion protection to use the immutable booked day, so that an Arrival on another day does not rewrite planning history.
44. As a desk operator, I want opening a print preview to leave the patient unprinted until I explicitly press Print Prescription, so that the Mark Seen gate reflects an intentional print attempt.
45. As an operator, I want transient SMS failures and abandoned pending attempts to be safely retryable, so that a temporary provider problem does not become permanent.
46. As a patient, I want a Specs reminder to use the date, venue, and time window printed on my active Token, so that a later schedule edit cannot make the message disagree with the paper.
47. As an Admin, I want exported text to open as data rather than spreadsheet formulas, so that a patient-supplied value cannot execute in a spreadsheet.
48. As an Admin, I want Camp records export work to remain bounded as patient count grows, so that a large camp does not issue multiple sequential database queries per row.
49. As a Doctor's Rx operator, I want a Correction rejected when its field or value violates the transcription schema, so that audited corrections cannot corrupt clinical data.
50. As a Doctor's Rx operator, I want an empty reason or a correction that changes nothing rejected, so that the audit trail records real changes.
51. As a touch user, I want every Diagnosis choice to be at least 44 by 44 pixels, so that the Clinical Desk remains usable in field conditions.
52. As a developer, I want public pages to avoid an expected unauthorized bootstrap request, so that console and monitoring noise represents real faults.
53. As a Registration desk Volunteer, I want immediate phone validation and clear inline feedback, so that predictable errors are corrected before a request.
54. As a data owner, I want gender and OT eye accepted only from their defined domain values, so that reporting does not accumulate spelling variants.
55. As a developer, I want live-API tests to use the current Name/PIN contracts, isolated fixtures, and an explicit opt-in target, so that the complete local suite is deterministic and failures identify product behavior rather than missing shared setup.

## Implementation Decisions

- **Canonical Team surface:** keep the dedicated, role-aware Team page for Admins and Team Leads. Remove Staff and Roster tabs from the Admin dashboard. The Admin dashboard may link to Team management but must not embed a second implementation.
- **Capability parity before deletion:** move Operator-line editing into the Team page, reuse the shared Operator-line vocabulary, and reset name, phone, role, Team Lead, and Operator line after successful creation. Do not create another shared form abstraction unless a third consumer appears.
- **Roster retirement:** stop registering the Roster router, delete the bulk/list/enable/disable contract and request model, remove no-op Roster dependencies from Registration, Desk, Clinical, serializers, Leaderboards, and tests, and stop creating the Roster index on new databases. Do not bulk-delete historical Roster documents or legacy attribution fields in this change; stop reading and writing them.
- **Authenticated attribution:** current Leaderboards and audit projections use authenticated `created_by` and `arrived_by` user identifiers only. Team Lead scores remain the sum of their Volunteers' scores.
- **Specs collection day contract:** accept and return `camp_id`, ISO local `day_date`, trimmed `venue`, local `start_time`, and local `end_time`. Times use strict `HH:MM` values interpreted in Asia/Kolkata and require `start_time < end_time`. Do not accept or return `seat_limit`, `seats_taken`, or `seats_free` for Specs.
- **One Specs window per camp/date:** preserve the existing unique camp/date identity. Re-submitting the same active-camp date updates its venue and time window. Multiple windows on the same date require a separate domain decision and are out of scope.
- **Legacy Specs days:** never invent a time window. Existing rows without both times are visible to Admin as “window required,” are not selectable by Clinical, and become valid when the Admin explicitly saves the window. Historical capacity fields remain inert in MongoDB but are no longer written, serialized, or interpreted. Existing historical Tokens without a time remain printable without fabricated data.
- **Schedule validity:** creating or updating a Specs collection day requires the active camp and a window whose end instant is later than the current IST instant, including on the current date. Selecting either a Specs collection day or OT Schedule Day requires that it belongs to the patient's camp and has not ended or passed; the exact end boundary is rejected. Invalid object identifiers are client errors, not server errors.
- **Specs deferral:** Spectacles to be made fetches and validates the selected Specs collection day but never consumes or releases capacity. Existing “full,” “none free,” and seat-refund branches are removed only for Specs. OT keeps its current capacity rule.
- **Token snapshot:** a newly issued Specs Token and Fulfilment snapshot the selected date, venue, start time, and end time. Reprinting remains stable even if an Admin later edits the schedule. Specs Token and reminder message contracts include both times, and reminders read the active Token snapshot rather than the mutable schedule. Any required DLT template/configuration change ships with the feature.
- **Deferred write invariant:** add a unique current-Fulfilment invariant for patient transcription plus item type and a one-active-Token invariant. Validate camp, day, status, and clinical prerequisites before mutation. Because the deployed MongoDB topology has no multi-document transactions, use a durable idempotent operation state with a reservation identifier and reconciliation for OT reservation, Fulfilment replacement, and Token activation. The prior record remains current until the new operation is finalized; retries resume the same operation, and startup/on-demand reconciliation completes or rolls back abandoned operations. Specs replacement, which has no capacity mutation, stores its Token snapshot with the current Fulfilment in one atomic document update.
- **Board snapshot contract:** return `as_of`, active camp, current camp day, stage counts, Fulfilment counts by line/status, active Registration activity, quiet count, active-camp SMS failures, next OT Schedule Day, and next Specs collection day. Return explicit no-camp and no-current-day states with zeroed counts and no fabricated quiet rows.
- **Board stage definitions:** `Arrived` means Arrival stamped within the current camp day; `Awaiting Print` means Arrived with no `printed_at`; `Awaiting Seen` means printed with no `seen_at`; `Seen` means Seen within the day; `Transcription backlog` means Seen within the day with no transcription. The counts preserve the Registration → Print Prescription → Mark Seen → Clinical Fulfilment invariant.
- **Board scoping:** every count is restricted to the active camp and current IST day. Fulfilment and SMS failures are scoped by resolving their existing transcription/patient identifiers in bounded bulk queries; do not duplicate camp identity merely for the Board. A second camp's records must never affect the snapshot.
- **Board activity semantics:** aggregate Arrival activity by authenticated Volunteer for the active camp. Show Volunteers with activity today; mark one quiet only after prior activity today and no Arrival in the last 15 minutes. Label the section “Registration activity” and the identity column “Volunteer” because there is no physical-desk entity.
- **Board query budget:** replace per-Volunteer counts and 100,000-row materialization with aggregation/bulk reads whose database round trips are bounded independently of Volunteer count. Add compound indexes that match active-camp time-range, current-Fulfilment, and SMS-failure queries. Verify the query budget in tests instead of setting an arbitrary patient-count ceiling.
- **Board refresh:** keep the 15-second cadence, allow only one request in flight, ignore or abort obsolete responses, pause while the document is hidden, refresh immediately on visibility return, retain the last good snapshot on failure, and visibly mark it stale with its `as_of` time.
- **Board presentation:** place stage, Fulfilment, quiet, SMS, OT, and Specs KPI cards before the activity table in DOM and visual order. Use readable labels, status-specific counts, a compact responsive grid, visible text for warnings, table header scopes/caption, and horizontal overflow where required.
- **Self-registration proof:** self-registration submits the raw QR payload and the server calls the existing bounded Decode implementation inside the registration request, deriving identity fields from the Decode result. Ignore client claims that a scan occurred and do not accept client-authored Aadhaar demographics. This deliberately avoids a second signed-token protocol while preserving the existing public Decode preview and registration idempotency.
- **Bootstrap and mandatory PIN change:** require the initial Admin PIN from deployment configuration, never fall back to a repository-known production value, and mark the account for change. Until `must_change_pin` is false, the API permits only identity lookup, PIN change, and logout. Existing delegated-account default PIN behavior may remain only with the same server-side restriction. Update the accepted Name/PIN ADR for this exception.
- **Credentialed origins:** replace the broad RFC1918 credentialed origin rule with the minimum explicit origins from deployment configuration. Local/LAN setup must name its actual frontend origin. Reopen the LAN-origin ADR and document the secure setup; do not rely on wildcard-like private-network matching.
- **Atomic Camp-day capacity:** maintain a booking counter or equivalent atomic reservation on the Camp-day document and use a conditional single-document update before insert. Release a reservation on failed insert or deletion, make idempotent retries neutral, and prove the last-seat race. Continue allowing Arrival above capacity as the existing domain rule requires.
- **Booked day as planning identity:** public occupancy, remaining seats, and Camp-day deletion protection use `booked_camp_day_id`. Arrival may update the attended `camp_day_id` without releasing, moving, or hiding the booking.
- **Print transition:** loading a preview is read-only. An explicit Print Prescription action performs the server transition and then opens the browser print dialog. The system records an intentional print attempt; it does not claim that browsers can prove paper physically printed or distinguish dialog cancellation reliably.
- **SMS retry state:** reuse the existing patient, message type, event date, status, creation time, and error fields. Add only the attempt count and retry/lease timestamps required to atomically reclaim failed or stale-pending entries; never resend a sent entry. Provider-not-configured and invalid-data outcomes must be visible rather than silently disappearing.
- **Safe bounded export:** sanitize every untrusted spreadsheet cell that begins with a formula-trigger character while preserving ordinary values. Fetch patients, camp days, transcriptions, and Fulfilments in bounded bulk operations or one aggregation, then stream rows without sequential per-patient queries.
- **Typed corrections:** replace arbitrary change values with a discriminated, allow-listed correction contract that reuses transcription validation for each supported field. Reject unknown fields, invalid enums/shapes, blank reasons, and no-op changes before mutation. Store the append-only correction entry and its resulting transcription field update in the same transcription document with one atomic update; retain legacy correction rows as readable history.
- **Truthful privacy and accessibility:** replace “Offline decode/on-device” with accurate server-Decode copy while retaining “no UIDAI call” and “only last four stored.” Raise Diagnosis choices and any affected Board controls to the 44-by-44-pixel minimum; do not use colour as the only state signal.
- **Small backlog fixes:** constrain gender and OT eye to domain enums, suppress authenticated bootstrap on public routes, and add client-side Registration phone validation while preserving server validation.
- **Deterministic test boundary:** migrate valuable live-API scenarios to the current Name/PIN and response contracts, replace order-dependent shared state with fixtures, and gate the entire live-API suite behind an explicit configured target. Ordinary local test discovery must not contact an arbitrary localhost service or run anonymous fragments after authenticated setup is skipped. Delete scenarios already covered at the faster route seam rather than maintaining duplicate contracts.
- **Documentation:** update the glossary definitions for Specs collection day, Token, Specs Token SMS, Specs reminder, and Camp-day board; remove active Roster language; update the PRD. Add an ADR that supersedes the Specs-capacity portion of ADR 0014 while preserving Camp-day and OT capacity. Amend or supersede ADR 0006 for explicit credentialed origins and ADR 0025 for secure Admin bootstrap and server-enforced first PIN change.

## Testing Decisions

- Tests assert externally observable behavior at the highest existing seam: async FastAPI route tests against the repository's Mongo-compatible fake, and React page/component tests with mocked API responses and fake timers. Internal helper call order is not a contract.
- Extend the Admin dashboard page seam to prove Staff and Roster tabs/content are absent and Team management is linked once.
- Add a dedicated Team page suite covering Admin role options, Team Lead scoping, Operator-line editing, account lifecycle actions, errors, busy state, and complete form reset.
- Replace legacy Roster behavior tests with attribution tests that prove new Registration, Arrival, Print, Clinical, Leaderboard, and export behavior uses authenticated user IDs and exposes no Roster endpoint.
- Test Specs collection create/update/list with required date, trimmed venue, strict times, `start < end`, `end_at > now` at the exact same-day boundary, active-camp ownership, past dates, malformed identifiers, incomplete legacy rows, and responses containing no capacity fields.
- Test multiple patients assigned to one Specs collection day without any capacity refusal or counter mutation; retain OT last-seat and seat-release tests unchanged.
- Test the Clinical picker for zero days, incomplete legacy days, valid windows, ended windows, cross-camp identifiers, and date/venue/time rendering.
- Test new Specs Tokens, reprints, reminder payloads, and Camp records export snapshots for date, venue, start time, and end time, including graceful historical records with no time and an edit-after-issuance case proving the reminder still matches the Token snapshot.
- Add concurrency and injected-failure tests proving one current Fulfilment, one active Token, no cross-camp assignment, no leaked OT seat, and preservation of the prior record after a failed replacement.
- Extend the Board backend seam with a second camp and boundary timestamps to prove every stage, Fulfilment, Volunteer, schedule, and SMS count is active-camp/current-day scoped.
- Test Board stage boundaries: Arrived/unprinted, printed/unseen, Seen/untranscribed, transcribed, and each Fulfilment status. No patient name or other PHI may appear in the response.
- Instrument the Board fake database to prove the request count is bounded as Volunteer count grows and that supporting indexes are declared.
- Extend the Board page seam for KPI-first DOM order, camp/day/as-of context, status-specific labels, next OT capacity, next Specs window, explicit loading/no-camp/no-day/stale states, visible quiet text, and responsive table semantics.
- Use fake timers and controllable promises to prove polling pauses while hidden, never overlaps, rejects stale responses, resumes immediately, and cleans up on unmount.
- Test forged public self-registration with an invalid/non-Aadhaar payload, a valid decoded payload, repeated/idempotent submission, and Duplicate-in-camp behavior. Failed cases create no Person, patient, or capacity reservation, and client-authored demographic fields cannot override decoded values.
- Test fresh and migrated Admin bootstrap with missing configuration, mandatory change, direct API attempts before change, successful change, and absence of a usable repository-known credential.
- Test CORS preflights and credentialed requests for each explicit allowed origin plus unrelated public, RFC1918, loopback, scheme, host, and port variants.
- Add a simultaneous last-seat registration test proving exactly one success, one `CAMP_DAY_FULL`, a neutral idempotent retry, and reservation rollback after insert failure.
- Test a patient booked for one day and arriving on another: occupancy and capacity stay on the booked day, attendance stays on the Arrival day, and the booked day remains deletion-protected.
- Test that preview loading never changes `printed_at`, explicit Print Prescription changes it once, and Mark Seen remains blocked before the explicit action.
- Test SMS sent, transient failure, retry, stale pending recovery, concurrent retry, unconfigured provider, invalid number, and active-camp Board failure visibility.
- Test CSV values beginning with `=`, `+`, `-`, `@`, tab, and carriage return, plus quotes/newlines; verify ordinary values remain unchanged and database query count is bounded.
- Test every supported Correction field with valid and invalid values, unknown fields, blank reason, no-op value, and atomic audit/transcription behavior.
- Test privacy copy against the server-Decode architecture and assert all interactive Clinical and Board targets retain at least the 44-pixel minimum class/contract.
- Test ordinary backend discovery with no live target and the explicitly enabled live-API target separately; neither may depend on test order or obsolete credentials, and skips are reviewed rather than treated as coverage.
- Retain targeted regression coverage for Duplicate in camp, Arrival, Print window, Mark Seen, clinical locking, Specs-line mutual exclusion, OT capacity, Leaderboards, and no-PHI Board output.
- Run frontend lint/tests/build and the complete backend suite after implementation. A partial pass is not completion.

## Out of Scope

- Enforcing an Operator line as a server-side permission. ADR 0020 deliberately defines it as a posting with a session override, not an authorization boundary.
- Removing OT Schedule Day seats, Camp-day booking capacity, or the rule that Arrival is never rejected for capacity.
- Supporting multiple Specs collection windows on the same camp/date.
- Proving that paper physically emerged from a printer or distinguishing print-dialog cancellation; the product can prove only an explicit print attempt.
- Replacing the browser scanning stack, adding a native app, calling UIDAI, or implementing real UIDAI Secure QR cryptographic verification. Re-decoding inside self-registration proves successful SNP Decode, not government authenticity beyond the current decoder.
- Adding patient names, drill-down actions, alerts, push notifications, charts, forecasts, or historical analytics to the read-only Camp-day board.
- Deleting historical Roster data or rewriting legacy attribution by matching names.
- Changing Team Lead score rules, Clinical Fulfilment line definitions, the two-specs-line mutual exclusion, or the active-camp model.
- Refactoring the retired root Next.js/Supabase application.

## Further Notes

- Assumption: one Specs collection day remains unique per active camp and date; the required time window describes that day rather than introducing multiple sessions.
- This specification intentionally contradicts the Specs-capacity portion of ADR 0014 and the broad credentialed LAN-origin decision in ADR 0006. Those decisions must be superseded in the same implementation. It implements ADR 0025's Roster retirement and preserves ADR 0020's Operator-line semantics.
- Existing API route tests and React page tests are the selected seams. They cover the user-visible contracts without introducing a new end-to-end harness.
- Audit baseline: frontend lint, production build, 23 suites, and 147 tests pass. Backend discovery reports 211 passed, 99 skipped, and ten failed because the legacy live-API suite is stale and only partially gated; this specification does not misreport that run as green.
- The production build also emits Node deprecation warning `DEP0176` from the current React Scripts toolchain. A toolchain migration is not included because the build succeeds and no product failure is evidenced; track it separately before a Node upgrade turns it into an error.
- The security choices follow [MDN credentialed-CORS guidance](https://developer.mozilla.org/en-US/docs/Web/Security/Practical_implementation_guides/CORS), [OWASP CSV Injection guidance](https://owasp.org/www-community/attacks/CSV_Injection), and [MongoDB single-document atomicity](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/).
- “Every bug” is bounded to reproducible or directly evidenced defects in the active React/FastAPI/MongoDB stack. Speculative redesigns and the retired application are intentionally excluded.
