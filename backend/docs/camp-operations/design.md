# Mobile camp operations design

Status: supporting design record, 5 September 2026. The current actionable requirements are consolidated in [the implementation specification](implementation-spec.md), which takes precedence over earlier proposals here. These documents do not certify or change application behavior. Notes stay under backend/ to respect the repository's change boundary. The adjacent glossary records resolved terms for eventual reconciliation with the root glossary.

## Confirmed decision

A camp can span multiple dates (explicit user answer). Preserve Camp and Camp day as separate concepts. Proposed interface: create the camp and all its operating dates in one form, eliminating duplicate date entry and a separate setup step. The interface proposal remains open.

Each scheduled date automatically enables printing for the whole calendar day in IST (explicit user answer), rather than configured operating hours. Printing availability determines the volunteer action. On dates without an open printing window, pre-registration is available. Admin overrides can change printing availability and expire at midnight IST, when automatic scheduling resumes.

Award at most one prize point to the original registrar per patient per camp after confirmed doctor-seen status (explicit user answer). See [registration credit decision](adr/0001-registration-credit.md).

Only clinical desk operator accounts may complete prescriptions, mark doctor seen or issue treatment; admin accounts are not a clinical exception (confirmed). Use one Save prescription & mark seen completion action after transcribing the whole paper prescription and after arrival/printing. Draft saves grant no seen status or prize points. Volunteers and team leads facilitate registration, check-in and printing only. No medicine/specs/OT or other fulfilment may occur before completed transcription; each issuing desk separately checks the paper prescription.

Denied camera permission must show guidance for enabling permission and retry; it must not itself unlock manual entry or count as an unsuccessful scan (latest user correction). The previously accepted recorded hardware-unavailable fallback remains distinct. For unreadable cards, use three deliberate unsuccessful scan sessions, not frames; manual registrations require camp-day identity rechecking.

Keep team credit with the team at registration when a volunteer later changes teams (explicit user answer). Preserve the original registrar's personal credit too. Historical team reporting must be distinguishable from the current roster.

Allow only one clinical visit per patient per camp (explicit user answer, resolving the review finding). Subsequent scans reopen that visit without resetting arrival/printing/seen/prescription/fulfilment or granting another point. A new consultation must not be silently created on a later camp date. How to handle requests for an actual second consultation remains an operational exception to resolve.

Clinical operators can correct transcriptions at any time with a reason, including after issue (explicit user answer). Do not impose the rejected admin-only post-issue correction restriction. Recommend retaining issued-item history, recording the correcting actor/time/reason, and flagging affected desks for review; a correction must not silently erase or repeat fulfilment.

If a manually registered patient arrives without Aadhaar or it remains unreadable, use an admin-assisted alternative identity check with a recorded reason (explicit user answer). Permit onward camp flow while retaining Aadhaar-unverified status. The acceptable alternative evidence and patient-matching procedure still need to be defined.

The user's latest correction removes the proposed Camp paused state. Admins control printing directly: printing off means pre-registration and patient search remain available while door scanning is hidden; printing on means door scanning replaces pre-registration, with search still available. Apply this even on a scheduled camp date if the admin disables printing. Manual overrides expire at midnight IST (explicit user answer).

Door scanning registers and checks in previously unregistered walk-ins within the same flow, with registration credit assigned to the signed-in staff member (explicit user answer). Existing registrations retain their original registrar; repeated scanning is not a registration and must not transfer credit.

Clinical operators may undo mistaken completion with a required reason before any item or token has been issued, revoking the point and returning the prescription to draft (confirmed). After issue, preserve history and use a recorded correction rather than resetting the visit.

Self-registered patients earn no staff registration prize point, even after clinical completion (confirmed). Door scanning never claims their registration credit.

Manual early printing opens exactly one admin-selected camp day until midnight IST; door check-ins and prints use that selected operating day (confirmed). Automatic scheduling uses today's scheduled camp day. Preserve actual action timestamps separately from the selected camp-day attribution.

## Requested outcomes

- Mobile screens should expose the action appropriate to the camp's operating state: pre-registration before camp; door scanning during camp; patient search throughout. Printing should open automatically on scheduled days and remain controllable by an admin.
- Retain separate registration and doctor-seen counts. Award one prize point when a registered patient has seen the doctor. Show each person's own counts and points, each volunteer's counts to their lead, and a lead's direct contribution plus the team's contribution.
- Prefer Aadhaar scanning for volunteers and team leads. Unlock manual details after three unsuccessful attempts and require camp-day identity rechecking for manual registrations.
- Require a mobile number for patient self-registration. Add a Hindi reminder to bring Aadhaar to camp SMS.
- Offer optional Doctor Rx transcription by a clinical desk operator beside the doctor. Fulfilment desks reuse the saved transcription or enter it themselves, and must check it against the paper prescription before issuing items or tokens.
- Investigate security, performance, operational reliability and useful camp-flow improvements before production deployment.
- User says the database contains no actual patient information and permits wiping it. No wipe is necessary for this design interview; none has been performed.

## Existing behavior and gaps

- backend/routes_camps.py:35 creates a camp with camp_date, while :140 separately creates dated camp-day records. New days have printing_open false (:153); admins toggle that flag (:168). This creates duplicate schedule entry in the current model.
- Root CONTEXT.md:36 describes a lead's score as only the team's sum. The requested direct-plus-team credit changes that definition.
- Root CONTEXT.md:99 excludes a Doctor Rx line and places transcription at fulfilment. The requested optional transcription location changes that definition.
- frontend/src/pages/Desk.js:558 currently permits manual fallback after two failures or one stall. Camera errors do not themselves count failures in frontend/src/components/AadhaarScanner.js:35.
- frontend/src/pages/SelfRegister.js:102 and backend/routes_registration.py:322 currently allow a missing mobile number.
- backend/aadhaar.py:3 documents missing RSA signature verification. Successful decoding must not be described as cryptographic authenticity verification.
- backend/routes_reports.py:44 adds registrations attributed to created_by and arrivals attributed to arrived_by. Lead totals omit direct registrations (:66) and use current team membership (:69).
- backend/routes_desk.py:318 allows require_staff to mark seen after arrival and printing; this does not independently establish completed consultation.
- backend/routes_clinical.py:189 already reuses prescription transcription. Fulfilment saves actor/time (:424) without an explicit physical-prescription review or reviewed revision; corrections (:624) need a policy for downstream review.

## Remaining decisions

All questions needed for the first implementation spec have been answered. The accepted workload is 1,000 patients per camp day and 50 active devices. Verification uses API workflow tests plus mobile component tests, followed by a camp-team phone/printer/SMS rehearsal before production launch. The user explicitly requires a deep UI/UX pass across low-end to high-end phones. The implementation spec records exact execution rules and acceptance cases; no question is pending.

## Recommended first-release priorities

| Priority | Improvement | Camp benefit |
| --- | --- | --- |
| 1 | One camp setup form with all dates; volunteer actions follow printing availability | Removes duplicate setup and contradictory screens |
| 1 | Mobile home with one primary action, persistent patient search and visible signed-in identity | Reduces training and wrong-account work |
| 1 | Original registrar and historical-team credit; Registered / Doctor seen counts and a clear Points total | Makes prizes understandable and auditable |
| 1 | Scan-first recovery, explicit manual recheck status, required self-registration mobile and Hindi reminder | Improves data capture without trapping patients behind broken cameras |
| 1 | Optional Doctor Rx, reused transcription, physical-paper review at each issuing desk and correction history | Reduces repeated typing and prevents unreviewed details being used for issue |
| 2 | Save-in-progress/saved/failed feedback with retry-safe operations | Makes weak connectivity recoverable without duplicate registrations or issues |
| 2 | Reprint reasons, printer readiness and SMS delivery/retry visibility | Exposes operational failures before they create long queues |
| 2 | Actionable lists for identity recheck, completed consultation awaiting fulfilment and changed Rx requiring review | Helps staff find patients who are stuck between steps |
| 3 | Measured query and bundle improvements, followed by load and restore rehearsal | Supports a justified hosting choice and repeatable release |

Suggested volunteer mobile home: camp name/date and printing availability, one large Pre-register or Scan at door action, Find patient, then personal Registered / Doctor seen / Points counts. When printing is enabled, first-time walk-ins are handled inside the door-scanning workflow without exposing a separate pre-registration action, as confirmed by the user.

Suggested lead view: personal contribution separately from team total, then a compact per-volunteer breakdown of Registered and Doctor seen. Points equal valid doctor-seen registrations, so do not present arrivals as prize points. A self-registration has no staff registrar; recommend leaving it without staff prize credit rather than awarding the later door scanner.

Suggested clinical view: patient identity and visit status above one selected operator task (Doctor Rx or a fulfilment line). Reuse existing prescription values; show relevant paper-review details beside the issue action and the last correction indicator. Clinical operators transcribe and fulfil the doctor's instructions; an unclear prescription requires doctor clarification.

Suggested reminder addition: “कृपया शिविर के दिन अपना आधार कार्ड साथ लाएँ।” Keep the existing camp date, venue and patient registration reference in the reminder.

## Execution clarifications

1. Early printing selects one operating day, expires at midnight, and preserves actual action timestamps. Existing registered arrivals do not consume another booking place.
2. Credit stays with the original registrar and registration-time team. Self-registration has no staff point. Automatic merging is out of scope; preserve existing duplicate protections.
3. Clinical operators may reasonedly undo completion before issue, removing current point eligibility. After issue, preserve history and use a recorded correction.
4. Camera sessions end at success/terminal failure or 20 seconds after readiness, count at most once and require explicit Retry. Denied permission receives guidance, not a counter increment or demographic fallback.
5. Completed revisions and paper-review evidence are distinct from drafts. A new committed revision invalidates unconsumed reviews; an unclear prescription remains draft pending doctor clarification.
6. The spec defines narrow-screen, large-text, keyboard, focus, measurement-field and camera-lifecycle acceptance, automated workload checks and a physical-device rehearsal.

## Review findings

The revised implementation spec received fresh parallel correctness and simplicity reviews. Findings about completion bypass, preserving existing arrival capacity behavior and the scan-session end condition were fixed. Both reviewers rechecked and returned no remaining findings. This is document review, not validation of application behavior.

## Proposed production acceptance plan

These are checks to agree and execute during implementation, not completed results:

- Verify IST midnight boundaries on scheduled days, gaps between dates, manual override expiry, canceled dates and clients left open across a mode change. The backend must reject actions inconsistent with the current state even from stale screens.
- Verify registration, arrival, seen, correction and duplicate retries cannot multiply prize points. Test lead direct plus historical-team totals and reassignment across teams.
- Exercise parallel requests for the same patient, scarce stock and the last surgery/specs collection slot. Return a clear recoverable result without duplicate issue or oversubscription.
- Enforce the physical-paper review on the server for the exact prescription revision relevant to the issuing line. Exercise concurrent Rx edits and issue requests, corrections after issue, and token reprints without new allocation.
- Require mobile validation on both self-registration UI and API. Household-shared numbers must not automatically mean duplicate patients; identity deduplication needs its own rule.
- Measure scanner camera-start, decode and fallback rates on an agreed device matrix and poor-light fixtures. Never log Aadhaar payloads, patient images or demographic fields in performance telemetry.
- Measure realistic concurrent registration, lookup, leaderboard and clinical workloads. Use the observed bottleneck to choose optimization. A current concrete candidate is replacing per-person registration/arrival count queries with one scoped aggregation when implementing the new score.
- Verify authentication throttling, role/team authorization, session handover, minimal returned patient fields, redacted logs, HTTPS, protected secrets, backup restoration, reminder retries and deployment rollback. Use synthetic data only.
- Plan a supervised device/printer rehearsal before serving patients. Current repository rules prohibit agent browser/computer testing, so automated checks alone cannot establish real camera or printer reliability.

## Candidate improvements to assess

- A prominent signed-in person's name and easy account switching on shared devices; consultation-based scoring alone does not solve wrong-account registrations.
- Large primary actions, readable Hindi labels, keyboard-appropriate fields, clear scan progress and specific recovery guidance. Retain high contrast and touch targets of at least 44 by 44 pixels.
- Prevent duplicate submissions and show explicit saved/pending/failed states under network retries. Avoid storing patient details in browser persistence by default.
- Show missing-step queues, such as identity recheck pending, waiting for doctor and transcription needing review, only when reliable events exist to support them.
- Label contributions from transferred volunteers in historical team totals without granting their former team new access to unrelated patient records. Credit attribution does not itself grant patient-data access.
- Treat backend authorization and state checks as authoritative: hidden buttons are not access controls. Test cross-team access, duplicate fulfilment, replayed requests, unauthorized seen marks and data exposure.
- Show the patient name, registration number and relevant prescription details together when reviewing an issue. A bare checkbox is insufficient if the operator cannot readily compare the correct patient and paper.
- Add printer readiness and reprint reasons, SMS delivery/retry visibility, and tested backup restoration to the deployment acceptance plan.

## Validation status

Primary-source Aadhaar/browser research is recorded in [Aadhaar mobile reliability research](../aadhaar-mobile-reliability-research.md).

Application code has not been changed in this interview. Tests, typecheck, lint, load tests, device tests and production deployment checks have not been run for this design. Production readiness and universal scanner compatibility are not established. Implementation must follow the repository's test and adversarial-review gate once workflow decisions are settled.
