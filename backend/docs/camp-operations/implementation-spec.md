# Mobile camp operations and clinical completion specification

Status: ready for implementation. Correctness and simplicity document reviews completed; confirmed findings were fixed and rechecked with no remaining findings. This is a local specification, not evidence that the application has been changed or released.

## Problem Statement

Camp staff use phones of widely differing size, memory and speed. The current workflow exposes actions at the wrong time, duplicates camp-date setup, rewards arrival activity instead of completed consultations, and can force repeated prescription transcription. Camera permission errors and unreadable Aadhaar codes are not the same problem, but current fallback paths can treat them similarly. Clinical access currently depends on a seen mark that volunteers can perform, whereas the required workflow is the reverse: a clinical operator transcribes the doctor's prescription and completes it before the patient becomes seen or receives any fulfilment.

The implementation must make every required field and action usable on small, low-end phones, preserve correct patient and staff attribution, and enforce clinical prerequisites on the server. A desktop page that shrinks, a disabled button without API enforcement, or a successful mock-camera test does not satisfy this specification.

## Solution

Create a camp and its multiple operating dates in one setup flow. Enable printing automatically throughout each scheduled IST calendar day. Admins can temporarily enable printing for exactly one selected camp day or disable printing; the override expires at midnight IST. Printing availability determines the volunteer action: off means pre-registration; on means door scanning. Patient search is always available. There is no Camp paused state.

Volunteers and team leads register, check in and print. Only clinical desk operator accounts may transcribe, complete prescriptions, mark seen, correct clinical details or issue treatment. Admin accounts are not a clinical-role bypass. Doctor Rx is an optional position for a clinical operator, not a new role or compulsory queue. A clinical operator at any clinical position can enter the whole prescription. One explicit Save prescription & mark seen action commits completion and seen status together. Drafts confer neither points nor permission to issue anything.

Each issuing line must compare its relevant instructions with the physical paper prescription and explicitly confirm that review against the exact completed prescription revision before recording issue or allocating a token. Clinical operators may correct prescriptions with a reason. They may undo mistaken completion before any issue; issued history is never erased by resetting a visit.

Keep one registration and one clinical visit per patient per camp. Award the original staff registrar at most one currently valid point when the clinical prescription is completed. Credit stays with the registrar's team at registration. Self-registrations earn no staff point. Repeated scans cannot transfer attribution, reset care or multiply credit.

Use scan-first staff registration with three deliberate unsuccessful scan sessions before manual details unlock. A denied camera permission requires enablement guidance and retry, not a manual-entry shortcut. A genuine unavailable-device fallback remains available with a recorded reason. Manual registrations require camp-day identity rechecking; an admin may record an alternative check when Aadhaar is absent or unreadable, without claiming verified Aadhaar.

## User Stories

1. As an admin, I want to enter a camp's name, venue and all operating dates once, so that I do not repeat date setup.
2. As an admin, I want multiple dates to belong to one camp, so that attendance and prizes retain the agreed camp scope.
3. As an admin, I want each scheduled date to open printing automatically in IST, so that staff can start without waiting for me.
4. As an admin, I want to open exactly one selected camp day early, so that check-ins and prints have an unambiguous operating date.
5. As an admin, I want manual printing overrides to expire at midnight IST, so that a forgotten switch does not control later days.
6. As a volunteer, I want pre-registration when printing is off and door scanning when it is on, so that I see the appropriate action.
7. As a staff member, I want patient search in either printing state, so that switching state does not hide existing records.
8. As a staff member, I want an open page to refresh its printing state, so that a midnight boundary or admin change does not leave misleading controls.
9. As a volunteer, I want door scanning to register a new walk-in and check them in, so that I do not need the hidden pre-registration screen.
10. As a patient, I want a repeated scan to reopen my existing visit, so that my prescription and issued items are not reset.
11. As a volunteer, I want my signed-in identity clearly visible, so that I do not accidentally work under another person's account.
12. As a volunteer, I want to see Registered, Doctor seen and Points, so that I understand my own contribution.
13. As a team lead, I want my direct contribution shown separately from my team total, so that my own registrations count without double counting.
14. As a team lead, I want each volunteer's registrations and doctor-seen registrations visible, so that I can understand the team's results.
15. As a volunteer who changes teams, I want earlier registrations to retain their original team credit, so that reassignment does not rewrite prizes.
16. As an admin, I want transferred-member contributions identifiable in historical totals, so that the totals reconcile with current and former members.
17. As a self-registering patient, I want a mobile number required and clearly explained, so that camp messages have a contact destination.
18. As a household, I want to reuse a contact number for different patients, so that a shared phone is not mistaken for duplicate identity.
19. As a self-registering patient, I want later door scanning to preserve self-registration attribution, so that no staff member claims my registration.
20. As a patient, I want a Hindi reminder to bring Aadhaar, so that I arrive prepared for checking.
21. As a staff member, I want three visible, deliberate scan attempts, so that unreadable cards have a predictable recovery path.
22. As a staff member who denied camera permission, I want instructions to enable it and a Retry action, so that I can continue scanning.
23. As a staff member, I want permission denial, missing camera, busy camera, network failure and unreadable QR to have different messages, so that I take the correct recovery action.
24. As a staff member, I want valid USB or uploaded QR capture to remain usable, so that camera recovery does not disable other scanning methods.
25. As a manually registered patient, I want my record flagged for camp-day rechecking, so that staff know which details need confirmation.
26. As an admin, I want to record an alternative identity check and reason, so that a patient with no usable Aadhaar can continue without a false verified status.
27. As a clinical operator, I want to look up an arrived, printed patient before they are marked seen, so that I can transcribe the prescription first.
28. As a clinical operator beside a doctor, I want a Doctor Rx position, so that I can transcribe without issuing any item.
29. As a clinical operator at the first fulfilment desk, I want to enter the whole prescription when Doctor Rx is unstaffed, so that the patient is not sent through an unnecessary queue.
30. As a clinical operator, I want to save an incomplete draft, so that interruptions do not require retyping the entire prescription.
31. As a clinical operator, I want one explicit completion action, so that saving the complete prescription and marking seen cannot disagree.
32. As a clinical operator, I want completion errors to identify the missing information, so that I can correct the form without losing it.
33. As a volunteer or team lead, I want clinical actions excluded from my account, so that my role stays limited to registration, check-in and printing.
34. As an admin, I want clinical actions to require a clinical operator account even for me, so that role enforcement is consistent.
35. As an issuing operator, I want the saved prescription reused, so that I do not transcribe it again at every line.
36. As an issuing operator, I want to review the paper against the exact saved revision, so that I do not issue from an outdated transcription.
37. As a patient, I want medicine, spectacles and OT allocation blocked until transcription is complete, so that a draft cannot authorize fulfilment.
38. As a clinical operator, I want corrections recorded with author, time and reason, so that later staff can understand what changed.
39. As a clinical operator, I want stale review confirmation cleared after a prescription correction, so that the next issue is checked again.
40. As a clinical operator, I want to undo an erroneous completion before issue with a reason, so that the record and points become correct again.
41. As a patient, I want already-issued history preserved after correction, so that the system does not pretend an issue never happened.
42. As an operator, I want retries and double taps to return the existing result, so that weak networks do not duplicate records or allocations.
43. As an operator, I want visible Saving, Saved, Failed and Pending confirmation feedback, so that I know whether an action actually committed.
44. As a phone user, I want every field, error and action usable on a narrow screen, so that no necessary information is clipped or off-screen.
45. As a phone user with large text or an open keyboard, I want labels and actions to remain reachable, so that accessibility settings do not break the workflow.
46. As a low-end-phone user, I want scanning and forms to stay responsive, so that high memory or CPU use does not prevent camp work.
47. As an operator entering spectacle measurements, I want clear right-eye and left-eye sections on a phone, so that compact layout does not swap or hide values.
48. As a staff member returning from another tab or camera interruption, I want a safe resumed state, so that stale callbacks do not save the wrong patient.
49. As an admin, I want printable output and SMS retries to be distinguishable from new clinical allocations, so that operational recovery does not duplicate care.
50. As a camp organiser, I want automated validation at 1,000 patients per day and 50 active devices, so that performance claims have a repeatable basis.
51. As a camp organiser, I want a real phone, printer and SMS rehearsal before launch, so that simulated tests do not stand in for actual equipment.
52. As the implementing agent, I want ordered changes and explicit rejection cases, so that I cannot accidentally preserve an obsolete permission or lifecycle rule.

## Implementation Decisions

### 1. Authority, scope and implementation discipline

- Implement this specification in the authoritative React/Vite frontend and FastAPI/Motor/MongoDB backend only. Do not revive the retired Next.js/Supabase application or add a deployment platform.
- This specification supersedes older descriptions that permit any staff member to mark seen, allow permission-denial manual fallback, award arrival points, exclude a lead's direct points, or require seen before transcription.
- Preserve unrelated work already present in the working tree. Do not reset, discard, broadly format or replace unrelated changes. Do not wipe a database as a convenient way to pass a test. Use isolated synthetic test data.
- The deliverable is application behavior, tests and matching module/domain documentation. A UI-only change is insufficient. Do not publish an issue, deploy, purchase hosting or send messages to real patients as part of this spec.
- Use existing module boundaries and installed dependencies. Do not add a generic workflow engine, offline patient database, Redux-style state layer, drug catalogue or TypeScript conversion.
- Locate named modules and symbols by search before editing; follow every caller when changing a shared guard, serializer or clinical transition. Symbols below are navigation anchors, not permission to ignore other callers.
- Keep a numbered requirement-to-test checklist. An unimplemented acceptance case cannot be reported as passed.

### 2. Role and read-access contract

| Operation | Volunteer | Team lead | Clinical desk operator | Admin | Anonymous patient |
| --- | --- | --- | --- | --- | --- |
| Staff registration, check-in, printing | Allowed within existing scope and printing rules | Allowed within existing scope and printing rules | No new registration permissions in this change | Allowed within printing rules | No |
| Patient self-registration | Public flow only | Public flow only | Public flow only | Public flow only | Allowed with required mobile |
| Draft, complete, undo or correct clinical transcription | No | No | Allowed with clinical prerequisites | No | No |
| Mark doctor seen | No | No | Only through completion | No | No |
| Issue medicine/specs or allocate OT/specs token | No | No | Only after completion and paper review | No | No |
| Configure camp, schedule or printing override | No | No | No | Allowed | No |
| Record alternative identity check | No | No | No | Allowed with reason | No |
| Contribution reporting | Own totals | Own and credited-team totals | No expanded reporting access | Admin reports | No |

Clinical mutation guards must compare the exact clinical desk operator role. The current require_clinical helper includes admins; do not reuse that behavior unchanged. The independent desk mark_seen endpoint must not remain a route around transcription completion. Remove its frontend action and make direct calls incapable of conferring seen status, including calls by a clinical operator without a completed prescription.

Do not widen patient-data visibility to implement points. Volunteers and leads need registration identity and progress, not diagnosis or prescription contents. Frozen team attribution grants historical aggregate reporting, not unlimited access to a transferred volunteer's later patients. Preserve existing authentication, session expiry, rate limiting and public-response data minimization.

### 3. Camp dates, printing and registration mode

- Camp days are the authoritative schedule. The setup form collects metadata and all dates together. If an existing scalar camp_date is needed for compatibility, derive it from the schedule; never ask the admin to enter the date twice or use two independent schedules.
- Keep one active camp under the existing active-camp rule. Within it, at most one operating camp day is selected for check-in and printing at a time.
- Automatic mode: select the camp day whose day_date equals today's date in Asia/Kolkata; printing is enabled for that entire calendar date. With no matching day, printing is off.
- Manual enable: an admin must select a valid day belonging to the active camp. That day becomes the sole operating day, even when opened before its scheduled date. Record actual timestamps normally; do not fabricate the current date to match the selected day.
- Manual disable: printing is off. Pre-registration returns and door scanning is hidden, including on a scheduled date. There is no paused state.
- Both overrides expire at the next midnight IST measured from when the override is set. Expiry returns to automatic evaluation. An override must not survive camp switching or silently target a day in another camp.
- Compute effective availability on the server from date and a nullable override; do not depend on a browser timer or a scheduler successfully running at midnight. A stale stored printing_open boolean is not an independent authority.
- Return effective printing availability, operating-day identity, server time and override expiry in the existing camp-state projection. The public projection must not expose admin identity, reasons or patient information.
- Refresh authenticated mode on mount, focus, reconnect, mutation success and a lightweight periodic interval while visible. Suspend background polling when hidden. At a known midnight/expiry boundary, refresh immediately. Never keep a stale enabled scan/print action after the server rejects it.
- The backend checks the effective state at the actual check-in/print mutation. If a page is stale, reject without partial check-in or print marking, return a recoverable mode-changed result, and refresh the UI. Preserve the user's unsaved form in memory.
- This printing control governs door check-in and the registration/blank-prescription print workflow. Closing it does not revoke an already arrived/printed patient's clinical eligibility or block recovery/reprint of a token already allocated through valid clinical fulfilment. Do not introduce an unrelated clinical-closing gate.
- Pre-registration is available while printing is off; when printing is on, staff use the door-scanning flow. Apply the same policy to direct staff registration requests by distinguishing pre-registration from walk-in registration. Public self-registration remains a separate existing public flow; do not accidentally expose the staff door interface there.
- New walk-ins register and check in as one recoverable operation attributed to the authenticated registrar. Existing records reopen without changing created_by, team attribution or earlier clinical/fulfilment state. Search is always available, but does not bypass operation permissions.
- Preserve existing booking quotas at pre-registration and new walk-in registration. An already registered patient's arrival does not consume another booked place, release the original booking or acquire a new booking merely because the operating day differs. The current arrival path intentionally ignores booking capacity; do not introduce a new capacity rejection there. Show booked day and actual operating day distinctly, retain the booking, and record attendance against the selected operating day. A new walk-in still goes through the existing registration-quota checks before check-in; return that failure clearly without manufacturing an arrival.
- Camp setup must not announce success or enable activation while requested day records failed to save. A retry resumes the same camp setup rather than creating another camp. Reject duplicate dates and cross-camp day references. Do not silently delete a day containing registrations or clinical activity.
- Admins may edit today's or an upcoming camp day's date and seat limit. Bookings stay on the same day record when its date moves, and booked patients receive a new registration date SMS. A day with arrivals, printing or clinical activity cannot move. Lowering camp seats below current bookings keeps those bookings, shows the day as over capacity, and blocks further pre-registration until capacity is available again. The camp's displayed date follows the earliest scheduled day.
- Admins may edit today's or an upcoming OT day's date, hospital and seat limit. Moving its date keeps assigned patients on the same OT day, updates their active appointment slips and current fulfilment records, and sends a new OT token date SMS. A past or completed OT day cannot move. An OT seat limit cannot drop below assigned patients. A duplicate date within the same camp is rejected for either schedule.
- A day-date edit carries a persistent revision. Retrying the same date completes pending camp notifications or OT appointment updates and uses that revision as the SMS event key, so a delivered update is not sent twice.

### 4. Registration attribution and points

- Preserve created_by as the original authenticated staff registrar. Add a server-assigned registration-source distinction for self versus staff and a registration-time team-lead snapshot.
- For a volunteer, snapshot their assigned team lead at registration. For a lead's direct registration, snapshot that lead's own identity. For an unassigned staff registrar, retain personal credit and a null team; do not invent a team.
- A self-registration has no staff registrar or staff team credit. Client-supplied actor/team/source fields must not choose attribution.
- Registered is the count of valid registrations attributed to that person. Doctor seen is the subset with a currently committed completed prescription and valid seen state. Points equals that subset count, at most one per patient per camp.
- A team total equals the lead's direct credited registrations plus registrations credited to that team from volunteers, with no double counting. Show the lead's personal figures separately. Team reassignment never moves earlier credit.
- Derive scores from authoritative records using scoped grouped queries. Do not increment an independent point counter on each scan, completion, correction or retry.
- Undo before issue removes current clinical-completion eligibility and its point. Re-completion restores one point. Ordinary corrections preserve one point. Historical completion events do not sum into multiple points.
- Repeated scans, print reprints, multiple fulfilment lines and token reprints confer no additional points. Preserve identity uniqueness within a camp. A shared mobile number alone is not duplicate identity.
- Use existing duplicate prevention and an explicit conflict response. Automatic patient merging, credit reassignment and copying a prescription between patients are not part of this release.

### 5. Aadhaar and camera state contract

Treat idle, permission pending, permission denied, scanning, decoded, unreadable attempt, unavailable hardware, busy device and network/server failure as different states. Keep the typed reason through cameraHelpers, acquireCameraStream, useAadhaarCamera, AadhaarScanner and the parent registration flow; do not reduce it to a string too early and later guess its meaning.

| Event | Counts toward three attempts? | Demographic manual entry |
| --- | --- | --- |
| One completed, deliberately started scan session ends without readable QR | Once | Unlock only after three eligible sessions for this registration attempt |
| Explicit QR payload is decoded but rejected as invalid | Once per submitted attempt | Same three-attempt rule |
| Each camera frame fails to decode | No | Never unlock from frame count |
| Permission denied, dismissed or still unanswered | No | Do not unlock; guide enabling permission and retry |
| User cancels scan or closes modal | No | Do not unlock |
| API/network failure, device busy or insecure origin | No | Recover/retry; do not pretend the QR was unreadable |
| Camera genuinely unavailable | No | Eligible audited hardware fallback; preserve separate identity-recheck requirement |

- One camera scan session begins only after the camera is ready and runs for at most 20 seconds. Stop capture/decode scheduling when it succeeds, receives a terminal invalid-QR result, is canceled, or reaches that deadline. An unreadable/invalid terminal result counts at most once for that session; repeated frames or repeated rejected payloads in it cannot add attempts. Show the ended result and require an explicit Retry to start another session. The existing stall callback alone does not end scanning and must not be retained as an indefinite-session implementation.
- Permission waiting and camera initialization occur before the scan-session clock and do not consume attempts. If QR validation is pending over the network at the deadline, stop new capture and show validation pending/recovery; a timeout/network error is not an unreadable-card result. A deliberately submitted USB/image QR attempt likewise has exactly one terminal result, no automatic resubmissions and no counter increment on transport failure. Ignore late callbacks for an ended session.
- Permission denial stops camera-constraint retries immediately. Show short instructions for the detected platform's site and OS camera permissions, plus a generic fallback explanation when detection is uncertain. Retry must attempt camera acquisition again after user action. Do not invent an API that opens browser permission settings or change device settings automatically.
- A denied-permission state does not reset into an eligible hardware failure through a timeout, stale callback or generic error handler. Previous incomplete attempts, modal switching and changing capture modes must not accidentally unlock demographic entry. Scope/reset counters to the active patient-registration attempt, not the whole login session.
- USB/paste QR capture and QR image upload are scanning methods, not manual demographic entry. They may still work while camera permission is denied. Genuine completed attempts using them follow the same counting rule; switching tabs or submitting a network-failed request does not count.
- Require a fallback reason and record capture method for manual registrations. Recheck identity before camp-day check-in/printing completes. Successful admin-assisted alternative checking can release that hold while Aadhaar status remains unverified; record admin, time, evidence description and reason, without storing an unnecessary document image or full ID number.
- Browser permission state and hardware claims cannot be authenticated from client flags. This is a workflow control with auditing, not proof that a person physically made three honest attempts. Do not claim server-side anti-fraud guarantees from an attempt counter. Enforce registration permissions, input validation, attribution and recheck status independently on the backend.
- Distinguish QR decoded, cryptographic signature verified, and identity checked at camp. The current Aadhaar parser omits signature verification. Never label a decoded payload as signature-verified or treat a scanned client flag as trusted verification. Adding a verified label requires real verification and trusted fixtures; do not fabricate it to satisfy a test.
- Keep the installed software decoder fallback; native BarcodeDetector alone does not support every intended browser. Feature-detect rear camera, torch, zoom and native decoding rather than requiring them. Do not request microphone permission.
- Stop camera tracks and pending decoding work on success, cancel, navigation and unmount. Ignore stale callbacks after patient/route changes. Permit at most one active camera/decode session; do not load the decoder or start a camera on every dashboard render.
- Bound uploaded image/QR input sizes and decoder work. Never log Aadhaar payloads, photos, full identifiers or patient details in errors, analytics or performance measurements.

### 6. Whole prescription, completion and correction

Use the existing prescription content model and form as the base: diagnosis options/other diagnosis, blood sugar, BP, remarks, spectacle measurements and OT eye/procedure/notes. Preserve all existing clinical validation and right/left distinctions. Add a plainly labelled free-text medication/instruction field if the current fields cannot retain the paper's medicine instructions; do not invent a drug selection or dosage-recommendation system.

Completion requires the operator to confirm that all instructions on the paper have been copied. Include explicit prescribed-line selection using the existing medicine, specs_fixed, specs_made and ot keys, or an explicit no-fulfilment-prescribed choice. This selection describes the prescription, not an issued/not-required fulfilment record.

- Reject a completely blank prescription unless the operator explicitly records the doctor's no-treatment/no-fulfilment outcome. Do not use an empty object, the patient's existing seen flag or a single populated incidental field as proof of full transcription.
- Validate the fields required for every selected line using existing clinical rules. Copy only what the doctor wrote; never invent missing powers, dosages, laterality or surgery instructions. Unclear/incomplete paper instructions require clarification with the doctor and remain draft.
- Whole-prescription completion applies even when the operator selected Medicine or OT as their working position. Position can prioritize fields but must not omit other prescribed lines or hide their validation errors.
- Draft saving remains allowed without complete fields after the patient's arrival/print prerequisites. It does not set seen, commit a completed revision, issue anything, allocate seats or create prize eligibility.
- Completion is an explicit action distinct from Save draft. It requires arrival, a valid printing record, current clinical role, full-transcription confirmation and successful complete validation. It grants no fulfilment by itself.
- Clinical lookup and initial transcription must permit arrived, printed, not-yet-seen patients. Remove the circular requirement that they already be seen. Existing old tests requiring seen before transcription must be replaced, not preserved through a bypass.
- Keep Doctor Rx optional and within the existing clinical role. Add doctor_rx as an operator-position choice only. Never accept doctor_rx as an issued item type or add it to the four fulfilment lines.
- Corrections require a nonblank reason and retain actor/time and the prior completed content. A correction is a new completed revision; it must pass whole-prescription validation. Editing a draft after completion must not silently replace the committed prescription used by issuing desks.
- An operator can undo completion only before any actual issue or token allocation, and with no unresolved issue operation. Record reason and author, preserve audit history, clear current completion/seen eligibility, retain arrival/printing and retain the content as an editable draft. Do not erase issued activity to make undo possible.
- After an issue, allow reasoned corrections but no reset of the visit. Flag affected lines for review and clearly show the before/after details. Previously issued medicine or tokens remain historical facts. Do not automatically reissue, refund, cancel or contact the patient from a correction save.

### 7. Durable state and concurrency decisions

The deployment currently uses standalone MongoDB configuration. Do not introduce a transaction dependency that silently requires a replica set or deployment changes. Use MongoDB's single-document conditional-update guarantee for the clinical commit, with immutable completed revisions prepared before commit.

Introduce these explicit concepts; field names may follow the existing naming style, but their semantics are mandatory:

| Concept | Required semantics |
| --- | --- |
| Draft transcription | Mutable clinical workspace, version-checked; never an issue authority |
| Immutable prescription revision | Complete validated content, patient/camp identity, predecessor, author, timestamp, reason when applicable and operation identity; never overwritten |
| Patient clinical generation | Monotonically increasing version used in conditional transitions, including undo; prevents an old request succeeding after state changes back |
| Committed revision pointer | Stored on the patient and changed atomically with current seen state and clinical generation |
| Clinical operation identity | Binds a retry to actor, patient, operation kind and exact payload; reusing it for another request is rejected |
| Issue authorization | Durable patient-scoped record binding line, operation, reviewed revision/generation and reviewer before external fulfilment effects |

Completion procedure:

1. Authenticate and validate role, patient/camp, arrival/printing, expected clinical generation and the complete content. A new completion is allowed only when there is no current committed revision and no unresolved issue authorization. An already completed patient requires the correction operation and a reason; a different operation identity is not permission to complete over it.
2. Prepare or recover the immutable revision for the same operation identity. An orphan/prepared revision is not clinically completed and grants nothing.
3. In one conditional patient update, compare the expected generation, empty committed pointer and absence of unresolved issue authorization, set the committed revision pointer, set seen status/author/time and advance generation. Validate the arrival/printing prerequisites in this commit condition too. On conflict, return an already-completed or stale-state result as appropriate; do not overwrite another operator's work.
4. Only acknowledge completion after that commit. A response lost after commit is recovered by the same operation identity. A failed patient update leaves no seen status or score eligibility from the prepared revision.
5. All reads used for seen, points and fulfilment resolve the committed pointer. Never use the most recently written draft or merely any revision in the collection.

Undo advances generation even when the committed pointer becomes empty. Old completion retries after undo must return their recorded/superseded outcome without reactivating completion. Correction and undo require an existing current completion and no unresolved issue in their conditional update filters; undo additionally requires no prior actual issue/token allocation. A correction commits a new immutable revision and advances generation; preserve original completion history and do not add another point. A second completion using a new operation identity returns a conflict instead of acting as a reason-free correction.

The existing _clinical_write lease is not a cross-document transaction. Keep necessary existing coordination, but do not use the lease alone as proof that an issue and a concurrent correction cannot race.

Issue procedure:

1. Obtain an explicit paper-review confirmation for the currently displayed committed revision and generation. The request names patient, line, reviewed revision and a stable operation identity.
2. Atomically compare current patient generation/revision and record an in-flight issue authorization on the patient. This transition competes with correction and undo. If either changed the generation first, reject the stale review. A generic Boolean detached from a revision is insufficient.
3. While that authorization is unresolved, reject/ask retry for competing correction, undo or another issue for that patient. Include the absence of an unresolved issue in the atomic correction/undo/issue filters; a prior read followed by an unconditional update is not sufficient. Serialize this short commit per patient, not globally across patients. Do not leave an expiring lock as the only record of what was authorized.
4. Perform existing capacity/stock/fulfilment/token changes using stable operation identity and existing conditional unique-allocation safeguards. Every retry must recover the same allocation, not reserve another seat or issue another item.
5. Finalize the authorization with the resulting record identity, or safely release it only after proving no side effect committed. On uncertain failure, leave a recoverable pending state; retry reconciles by operation identity. Never clear an uncertain operation and start a second allocation.
6. A correction after finalized issue can create a new revision and flag the issued line; it preserves the revision actually reviewed for the earlier issue.

Add fault-injection tests before declaring this durable. If existing allocation helpers cannot recover a partially applied effect by operation identity, extend those helpers narrowly; do not conceal the gap with a try/except that returns success or a reset command.

### 8. Fulfilment and paper-review contract

- Every medicine issue, fixed-power specs issue, spectacles-to-be-made allocation and OT allocation requires a committed completed prescription, valid current seen state, the clinical role and explicit review of the physical paper for that line.
- A draft with a transcription_id must not unlock FulfilmentSection or satisfy the API. Reject fabricated/transferred transcription IDs, another patient's revision and another camp's resource IDs.
- The line must be prescribed. When no line is prescribed, completion can still mark seen and award the one registration point; it creates no fulfilment record.
- Display patient name and registration number with the relevant clinical values next to the review/issue action. Review is never prechecked, never inferred from opening the screen and never reused across patients or lines.
- Conservatively clear all unconsumed line-review confirmations whenever a new completed revision appears. This safely satisfies the requirement to recheck affected lines without requiring a fragile field-diff rules engine. Preserve consumed review evidence in issued records.
- Keep existing mutually exclusive fixed-power and made-spectacles outcomes, last-seat capacity protections, date/collection-window rules and replacement/correction safeguards. This task must not weaken them.
- Issuing and printing a token are different operations. Reprinting an existing token does not allocate another slot. Reprinting the blank registration prescription does not mark doctor seen. Reprint failures must be visible and recoverable.
- A prescription or record on screen does not prove a physical printer succeeded. Keep the existing print-record semantics explicit; do not relabel browser print-dialog opening as confirmed physical output.

### 9. API and module change map

Preserve existing route naming where possible, but make draft saving, completion, correction, undo and issue distinct server actions with these contracts. New routes are allowed; the following operations, not a particular URL spelling, are required.

| Operation | Required request information | Observable result |
| --- | --- | --- |
| Save draft | Patient, expected draft version, partial content, operation identity | Updated draft/version; no clinical completion side effects |
| Complete prescription | Patient, expected clinical generation, complete content, full-transcription confirmation, operation identity | Committed revision, seen state, new generation and current eligibility together |
| Correct prescription | Patient, expected generation, whole corrected content, nonblank reason, operation identity | New committed revision and review-invalidated state; earlier issue history retained |
| Undo completion | Patient, expected generation, reason, operation identity | Draft/unseen eligibility only if no issue or pending issue exists |
| Fulfil line | Patient/current transcription identity, line, reviewed revision and generation, paper-review confirmation, resource details, operation identity | Exactly one recoverable fulfilment/allocation result |
| Change printing override | Active camp, enable/disable/automatic, selected day for enable | Effective availability, operating day and server-calculated expiry |

Use the established structured-error style. Authentication failure must remain distinct from role denial. Return forbidden for disallowed roles; not-found for inaccessible/missing entities without leaking records; validation error for incomplete content; conflict for unmet lifecycle state, stale revision, existing allocation, pending operation or changed printing state. A rejected request must not partly confer seen/points or issue an item. Surface field errors and a safe refresh/retry path in the UI.

Primary modules/symbols to coordinate:

- Camp lifecycle and projections: create_camp, upsert_camp_day, active_camp, active_camp_public and toggle_print_window; their admin setup and registration consumers.
- Desk and registration: mark_seen, Desk.markSeen, staff/walk-in/self-registration handlers, arrival/print transitions and serializers. Eliminate obsolete seen actions and ensure printing-state gates are server-enforced.
- Clinical: clinical_lookup, create_transcription, _clinical_write, correction and fulfilment handlers, TranscriptionBody and FulfilmentBody, patient/revision serialization and unique indexes.
- Frontend clinical: Clinical.saveRx, PrescriptionForm, ClinicalLookupForm, FulfilmentSection, FulfilmentStation, CorrectionModal, ReadOnlyPrescription and operator-line selection. Coordinate eligibility changes rather than patching one button.
- Camera: cameraHelpers/acquireCameraStream, useAadhaarCamera, liveScanEngine, useAadhaarDecode, AadhaarScanner and all Desk/SelfRegister consumers. Remove both existing two-failure and one-stall unlock paths.
- Reporting and team screens: original-registrar grouping, frozen team attribution, self-registration exclusion and personal/team display separation.
- Mobile foundations: Layout, shared form/button/modal primitives, global styling, SpecsMeasurementsGrid and all registration/search/clinical screens; do not repair only the landing screen.
- SMS: existing confirmation/reminder generation and queue/retry paths. Add “कृपया शिविर के दिन अपना आधार कार्ड साथ लाएँ।” while preserving camp date, venue and registration reference. Test template output without sending real messages.

### 10. Deep phone UI/UX requirements

These requirements apply to volunteer/lead home, pre-registration, door scanning, search/results, patient details, print entry, team reporting, self-registration, clinical lookup, Doctor Rx, every fulfilment line, corrections and admin controls used on a phone.

- Support 320, 360, 390 and 430 CSS-pixel portrait widths, landscape and tablet widths. No page-level horizontal overflow, clipped labels, unreachable required fields, overlapping controls or hidden validation messages. At 200% text zoom, content must reflow and remain operable.
- Test long Hindi names, long clinical notes, multi-line labels and validation messages. Wrapping must preserve meaning and actions rather than truncate the only available identity or error text.
- Use a clear one-column mobile flow with the primary action visible early. Keep the camp/date, operating-day distinction when opened early, patient identity and signed-in staff identity understandable without relying on color alone.
- Buttons and touch controls have at least 44 by 44 CSS-pixel targets with separation. Do not put tiny icon-only edit/cancel actions beside a destructive or clinical action. Give icons accessible names.
- Labels remain visible after typing. Do not use placeholder-only fields. Use suitable telephone/numeric keyboards where appropriate, but preserve legitimate prescription signs, decimals and text; numerical-looking clinical data must not be silently rounded or stripped.
- The on-screen keyboard, browser chrome, safe-area inset and sticky action bar must not cover focused inputs, errors or buttons. Use normal document scrolling and CSS before custom viewport/scroll code. Avoid nested scroll traps. Modals can scroll within the available screen and always expose a usable close path.
- Spectacle measurements use clearly separated right-eye and left-eye groups on narrow screens. Show the meaning of each field, not only an abbreviated table header scrolled out of view. Retain signs, units, defaults and validation accurately. Wider screens may retain the existing grid.
- Full-prescription entry must be manageable on a phone: meaningful grouped sections, clear completion state and a visible error summary linking to invalid fields. Optional sections can collapse, but required/invalid sections open automatically. Selecting a station must never hide fields required to complete another prescribed line.
- Visual, keyboard-focus and screen-reader order must agree. Do not reorder clinical sections with CSS while leaving a confusing tab/reading sequence. Orientation and operator-position changes preserve entered values and right/left associations.
- Show Registered and Doctor seen as the two comparable measures. Points is a clearly labelled total derived from doctor-seen registrations. Use readable per-person rows/cards on phones rather than squeezing a desktop table into illegible columns.
- Pending save/issue feedback stays attached to the active patient and action. Disable duplicate submission while pending, but preserve an explicit recovery path on failure. Never show success before the server confirms the relevant commit.
- Returning from print, another tab, camera settings or an interrupted connection must restore a coherent screen. Re-fetch authorization-sensitive state and current revision; do not replace a dirty form silently or reuse another patient's async result.
- Keep patient drafts in component/session memory only unless existing approved secure storage already provides a suitable design. Do not add localStorage/IndexedDB patient caches or offline clinical writes for convenience. Logout and account changes clear patient content and camera state.
- Lazy-load scanner/WASM and infrequently used clinical/print modules when the existing routing supports it. Do not load a camera decoder for a user merely viewing contribution counts. Avoid duplicate decoder instances, continuous hidden-tab loops and per-frame React rendering.
- Use one in-flight decode attempt at a time, bounded work, cleanup and cancellation. Preserve the software decoder path on browsers without native detection. Optional camera capabilities must improve scanning without becoming prerequisites.
- On slow connections, keep existing content visible during refresh, show a clear connection/retry state and avoid blank-screen reload loops. Never treat network failure as an unreadable Aadhaar attempt.
- Accessibility tests include keyboard focus order, labelled controls, error association, focus restoration after modal close, status announcements and adequate contrast. Do not remove focus styles to make the page look cleaner.

### 11. Performance, recovery and release targets

- Accepted workload: 1,000 synthetic patients per camp day, multi-day data and 50 simultaneously active staff devices. Exercise registration, patient search, camp-state refresh, contribution reports, prescription completion and competing fulfilment requests rather than 50 idle sessions.
- Proposed engineering budgets for this implementation: under the recorded test environment, backend p95 patient lookup and ordinary mutations at or below 1 second, report p95 at or below 2 seconds, and no unexplained 5xx responses or duplicate/lost successful writes during a sustained 15-minute workload. Report hardware, dataset, action mix and latency distribution; do not claim a KVM size is sufficient from an unreported laptop run.
- On real low-end-phone rehearsal, target visible feedback within 100 ms of a tap, usable primary form content within 3 seconds on the recorded test connection, and a clear scan result/retry state within the bounded scan session. Camera initialization and decoding measurements must be reported separately; permission decision time is not decoder latency. These are measured targets, not existing results.
- Optimize the measured bottleneck. Existing per-person leaderboard count loops are a concrete candidate for grouped scoped queries; avoid speculative global caching of clinical or authorization-sensitive state. Retain pagination/limits and avoid fetching all patient records into a phone.
- Reuse existing resource-capacity, token, reminder and duplicate protections. Tests must cover lost responses, process interruption between durable steps and competing operators. Inability to recover a pending issue is a release blocker, not a reason to remove the guard.
- Before production, the camp team must rehearse at least a physical low-end Android phone, a midrange Android phone, a high-end Android phone, an older supported iPhone and a recent iPhone. Record exact model, OS, browser, network and result; include portrait/landscape, 200% text, open keyboard, denied permission then recovery, low light, glare, unreadable QR, photo/USB alternatives where applicable, tab suspension and interrupted saves.
- Rehearse the actual prescription/token printer and real SMS delivery using approved non-patient test contacts. Verify backup restoration and rollback using isolated synthetic records. Automated component tests cannot certify these devices/services.
- Repository rules prohibit agent browser/computer automation and dev servers. The agent must not bypass that restriction; use approved automated test seams and leave the actual equipment rehearsal explicitly assigned to the camp team. Do not call production-ready until both automated evidence and rehearsal sign-off exist.

### 12. Ordered implementation plan

1. Record the existing worktree baseline and resolve named module callers. Inventory current test seams and relevant endpoint contracts. Do not repeat broad exploration once the target is known.
2. Add failing backend behavior tests for clinical role denial, pre-seen clinical lookup, draft non-eligibility, whole-prescription completion, old desk-endpoint bypass and fulfilment without a completed/reviewed revision. Add failing component tests for permission-denial guidance and the corrected printing-mode UI.
3. Implement the strict clinical guard and coordinated lookup/draft/completion lifecycle with immutable revisions, patient generation and derived points. Do not temporarily ship a permissive fallback to make old tests pass.
4. Implement correction/undo and version-bound issue authorization/recovery. Preserve existing capacity and exclusivity invariants. Complete the fault-injection and concurrency tests before moving on.
5. Implement registrar/team snapshot reporting, self-registration exclusion and required mobile validation. Update fixtures to follow the clinical completion path; do not directly seed seen status to skip testing it.
6. Implement schedule-derived printing, selected-day overrides/expiry and a single camp setup experience. Update all registration/printing consumers and stale-state rejection handling together.
7. Implement camera error classification, permission guidance and consistent attempt counting across all staff capture paths. Keep public self-registration's existing scope distinct from staff-only manual-entry gating.
8. Perform the full phone UX pass across all named screens and shared primitives. Preserve functional tests while adding interaction cases for errors, modals, focus and patient/route changes.
9. Update reminder text and recovery feedback; verify print/token/retry semantics. Avoid adding unrelated queue-management products or dashboards.
10. Run the final automated gates, measure the agreed workload, obtain two adversarial reviews in parallel, fix confirmed findings and rerun affected checks. Deliver implementation evidence and an unambiguous rehearsal checklist/status.

## Testing Decisions

Use existing high-level API workflow tests as the primary business-rule seam and React component interaction tests as the UI seam. Use targeted decoder/clock tests only for behavior not reliably exposed at those seams. Tests should prove observable outcomes and rejected operations, not mirror implementation branches or assert private helper call order.

Reuse and update the camp lifecycle, desk scan-first, clinical route, fulfilment invariant, team delegation, Aadhaar scanner and Desk/Clinical component suites. Important existing anchors include test_arrival_then_print_then_seen, the obsolete test_transcription_requires_seen, test_concurrent_same_line_leaves_one_current_specs_record and test_dual_leaderboard_scoring. Rename/rewrite obsolete assertions to reflect this spec; do not weaken meaningful assertions or mock away the transition under test.

The required acceptance matrix is:

| ID | Scenario | Required observable outcome |
| --- | --- | --- |
| C01 | Clinical lookup after arrival/printing but before seen | Patient can be transcribed; no circular seen prerequisite |
| C02 | Volunteer, lead or admin directly requests completion/issue/correction | Forbidden; no clinical state, point or resource mutation |
| C03 | Any role calls old independent mark-seen action without completion | Cannot confer seen or points |
| C04 | Save incomplete draft | Content saved; unseen, zero new points, fulfilment blocked |
| C05 | Complete without arrival or printing | Conflict; no prepared revision becomes authoritative |
| C06 | Complete blank/incomplete whole prescription | Validation error with field guidance; no point or issue |
| C07 | Explicit complete prescription with no prescribed fulfilment | Seen and one eligible staff point; no issue records |
| C08 | Successful whole-Rx completion | Revision, seen and eligibility become authoritative together |
| C09 | Failure after preparing revision but before patient commit | Orphan grants nothing; retry safely finishes or reports conflict |
| C10 | Response lost after completion | Same operation returns/reconciles existing result; one point |
| C11 | Two operators complete/correct the same generation | One wins; other receives conflict without overwriting |
| C12 | Pre-issue undo with reason | Current completion and point revoked; content/history retained |
| C13 | Old completion retry after undo | Does not re-complete the patient or restore a point |
| C14 | Undo after issue or with an unresolved issue authorization | Rejected; history and resources preserved |
| C15 | Correction after issue with reason | New revision; previous issue/review history retained |
| C16 | New completion request against already completed patient, including during issue | Conflict; cannot replace content or bypass required correction reason |
| F01 | Issue with draft, absent completion or missing paper confirmation | Rejected, including token allocation |
| F02 | Issue using another patient's transcription/revision | Rejected without data leakage or allocation |
| F03 | Review revision A, then revision B is committed | Issue using A is rejected; UI review clears |
| F04 | Correction races issue authorization | Exactly one ordering wins; no issue silently accepts stale review |
| F05 | Process fails after authorization or resource effect | Retry recovers same operation; no duplicate seat/item/token |
| F06 | Double tap or retry same issue | One recoverable current result |
| F07 | Last OT/specs collection slot requested concurrently | No oversubscription; loser gets recoverable failure |
| F08 | Fixed-power and made-specs competing issue | Existing mutual-exclusion invariant remains true |
| F09 | Print/reprint existing prescription or token | No new seen status, point, stock issue or allocation |
| P01 | IST midnight starts/ends a scheduled date or gap date | Correct server-derived availability without a scheduled job |
| P02 | Manual off on scheduled day | Pre-registration/search available; door scan hidden and API blocked |
| P03 | Manual early open of one selected day | Check-ins/prints use selected day; actual timestamps unchanged |
| P04 | Override midnight expiry/camp switch | Automatic state resumes; no cross-camp override leakage |
| P05 | Stale open page submits scan/print after closing | Server rejects without partial mutation; form preserved and mode refreshed |
| P06 | New walk-in versus repeated existing scan | New registrar credit only once; existing credit/care retained |
| P07 | Camp setup partially fails | No false success/activation; retry resumes same camp |
| P08 | Already registered patient attends another/full operating day | Existing arrival behavior retained; no second booked seat or new arrival-capacity gate |
| S01 | Lead directly registers and patient completes Rx | Lead personal and team contribution each reconcile without double counting |
| S02 | Volunteer changes team after registration | Original team retains credit |
| S03 | Self-registration followed by staff check-in and completion | No staff point |
| S04 | Completion, correction, undo and re-completion sequence | Current point follows valid completion, never exceeds one |
| S05 | Shared household mobile | Different legitimate patients are not collapsed by phone alone |
| A01 | Denied camera permission | Enablement guidance/Retry; no manual unlock or attempt increment |
| A02 | Denial followed by stall, stale callback or mode/modal switch | No denial-based manual-entry bypass |
| A03 | Permission enabled after guidance and Retry | Camera can resume; stale error cleared appropriately |
| A04 | Three completed unreadable sessions | One count each; manual details available only at threshold |
| A05 | Repeated frames, cancel, pending permission or network failures | Do not consume eligible attempts |
| A06 | Valid USB/image QR while camera denied | Scanning alternative succeeds without being labelled manual entry |
| A07 | Unavailable hardware/manual registration | Reason recorded; camp-day recheck required |
| A08 | Admin alternative identity check | Hold released with evidence/reason; Aadhaar remains unverified |
| A09 | Patient switch/unmount/success during late decode | No wrong-patient callback or surviving camera loop |
| A10 | Raw decoded/client scanned flags | Cannot forge a signature-verified status or attribution |
| M01 | Self-registration missing/invalid mobile via UI and direct API | Rejected consistently without submitting an unusable contact |
| M02 | Confirmation/reminder rendering | Hindi Aadhaar reminder and existing date/venue/reference preserved |
| U01 | Narrow widths, landscape, large text and keyboard | All required controls/fields/errors reachable with no page overflow |
| U02 | Full Rx across several lines on a phone | Required fields are not hidden by selected operator position |
| U03 | Specs values and right/left sections | No lost signs/decimals, swapped eyes or missing labels |
| U04 | Modal open/close, validation failure and async status | Correct focus, labelled errors, usable close/retry paths |
| U05 | Weak network, tab return, logout and account change | No false success, stale mutation, exposed prior-patient draft or double submission |

Run focused tests red before implementation and green afterward. At the final gate run the complete frontend non-watch Jest suite, frontend ESLint and production build, plus backend syntax compilation, configured fatal-error lint and the complete backend test suite. Use the repository's existing scripts and supported Node/Python versions. The frontend currently has no dedicated TypeScript/typecheck script; do not report a typecheck pass that did not run or introduce a language migration to manufacture one. Record applicable checks and any absent static-typecheck command honestly.

The complete backend suite includes live HTTP tests; without its isolated API environment those tests skip. A run with those skipped is not a full pass. Use the existing isolated production-container test workflow with synthetic records, not a watch/dev server or a real camp database. Run the full suite serially when it shares state. Test environment failure must be reported rather than turned into skips or weakened assertions.

Run correctness and simplicity reviews as separate subagents in parallel, each limited to the repository's review budget. Review the actual final change against this spec. Fix confirmed findings or explicitly decline them with reasons, then rerun affected checks. Full validation evidence must distinguish software checks, load measurements and the separately required camp-team equipment rehearsal.

## Out of Scope

- Buying/configuring Hostinger, deployment, DNS changes, sending real SMS, or wiping an existing database.
- A second clinical visit per patient per camp, automatic patient merging, referral-based prize claims or moving old team credit.
- Shared clinical permissions for admin/volunteer/lead accounts, a standalone mark-seen shortcut or fulfilment from draft transcription.
- Automatic clinical decisions, inferred handwritten values, AI-prescribed medicines/doses, or treating a checkbox as independent proof of what the doctor did.
- New drug/inventory catalogues, a new compulsory Doctor Rx queue, extra fulfilment types, or changing existing medicine/specs/OT business rules unrelated to the new prerequisite.
- General offline patient storage, a new PWA/service worker, framework migration, new database infrastructure or a generic workflow engine.
- Claiming perfect scanning on every device, cryptographic verification from mere decoding, or production readiness from automated tests alone.
- Additional operational dashboards beyond the contribution/status/recovery information required above; later ideas need separate scope.

## Further Notes

The latest user decisions take precedence over earlier interview answers. In particular: clinical operators only; whole-prescription combined completion; denied permission gets guidance, not manual fallback; printing off restores pre-registration; overrides expire at midnight; one selected operating day; one visit and at most one point; self-registration earns no staff point.

The equipment rehearsal is an accepted launch prerequisite owned by the camp team. The agent can complete the software deliverable with passing automated evidence and a clearly pending rehearsal, but must not label the system production-ready before sign-off. The numerical latency budgets are proposed engineering targets attached to the accepted workload; publish actual measurements and identify any target missed.

Primary technical references for the decisions: [MongoDB single-document atomicity and conditional updates](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/), [MDN camera permissions and failure modes](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia), [MDN BarcodeDetector compatibility](https://developer.mozilla.org/en-US/docs/Web/API/BarcodeDetector), and [UIDAI Secure QR guidance](https://www.uidai.gov.in/images/Circular_regarding_dos_and_donts_of_the__tamper_proof_QR_code_scanning_by_residents__dated_22032023.pdf).

Completion report required from the implementing agent: requirements implemented, tests and counts actually run, unresolved failures, concurrency/retry evidence, measured phone/load results, document updates, reviewer findings and their disposition, and equipment-rehearsal status. Do not substitute a code diff summary for this evidence.
