# SNP frontend workflow and UI/UX source review

Baseline: `Piyushmanyata/SNP`, commit `0e1c9feb8211820f241df0b05e22f55bbba4c91f`.

This is a source review of the frontend routes, shared shell, public/staff registration, clinical workflow, fulfilment, printing, administration, team and analytics. It does not claim browser, visual, accessibility-tool, device-camera, printer, network-load or user-task validation. Camera decoding internals and backend enforcement are reviewed separately. Paths below are relative to the repository root. “Confirmed” means the described branch/state exists in source; consequences requiring timing or backend semantics have explicit reproduction scenarios. Hindi-primary use, approximately 15,000 patients and 40–50 concurrent staff are planning assumptions, not observed traffic.

## Route, role and workflow coverage

Authorization source: `frontend/src/constants/roles.js:8-11`; route source: `frontend/src/App.js:45-56`. Frontend visibility is not a replacement for server authorization.

| Route/workflow | Allowed UI roles | Existing steps/guardrails | Review focus / executor acceptance |
|---|---|---|---|
| `/`, `/login` | Public; existing sessions redirected by role | Name + PIN; submit disabled while signing in; public seat counts | Preserve role home; distinguish session lookup failure from anonymous; restore safe intended deep link after login; accessible numeric PIN keyboard |
| Change/reset own PIN | All signed-in roles through Layout | Required first-change modal cannot close; validates exactly 4 digits, rejects 1234, confirms match | Keep required gate; no action ambiguity while pending; keyboard/screen-reader regression |
| `/self-register` | Public | Active camp/day → QR → readonly identity → household phone → receipt QR | Never expose manual transcription; explicit loading/failure/retry/no-camp/full states; understandable Hindi; receipt survival/retrieval plan |
| Assisted pre-registration `/desk` | Admin, team lead, volunteer | Scanner/modal → identity + phone + day → registration; stable modal request ID | Manual alternative only after 3 distinct failed camera sessions, reset for each person/session; keep form until success; show actual notification status |
| Door scan: already registered | Same desk roles | Scan → auto arrival; mismatch review before replacement; print link | Preserve request sequencing; show identity/day and next action; never show stale person's result after new scan |
| Door scan: ambiguous manual records | Same desk roles | Lists candidates and asks to find one below | Currently no usable candidate-selection/confirmation path; UX-01 |
| Door scan: no booking/walk-in | Same desk roles | Card preview → household phone → register → arrive → print | Stable operation identity, partial-success recovery, prevent duplicate taps; UX-05 |
| Door manual registration | Same desk roles + camp emergency flag today | Admin-controlled emergency manual form | Existing unconditional emergency exposure conflicts with new camera-attempt requirement; reconcile explicitly in root scanner spec |
| Find patient `/desk` | Same desk roles | Registration number or name; sequenced responses; print gates for arrival/scan/window/seen | Add lookup progress, names for controls, actionable duplicate/candidate recovery; preserve clinically required gates |
| A4 prescription `/print/prescription/:id` | Desk roles | Reads prescription then logos; record-print POST precedes browser dialog; guards stale print completion | Essential print must not wait on optional logos; responsive preview only, preserve actual A4 dimensions; print cancellation accurately described |
| Clinical line selection `/clinical` | Admin, clinical desk operator | Session-persisted doctor, medicine, fixed specs, made specs, hospital choice | Dirty-draft guard; clear station identity; patient/line changes cannot silently lose work |
| Clinical lookup | Same clinical roles | Arrived-and-printed patient only; number/name/USB/phone QR; race sequencing | Keep availability guards; lookup failure must not silently discard unsaved prescription |
| Diagnosis and complete prescription | Same clinical roles | Conditional wizard; saved checkpoint at each Next; explicit “copied every instruction”; final mark seen | Dirty/commit snapshot protection; input freeze while saving; reference-data retry; save status; concurrent edit conflict recovery |
| Medicine fulfilment | Same clinical roles, medicine line | Saved prescription; paper review; per-medicine given/not available; operation ID and reviewed revision | Preserve confirmation/concurrency; consider explicit outcome choice rather than preselected all-given only after operator validation |
| Fixed-power spectacles | Same clinical roles, fixed line | Both eyes; separate-eye option; substitution warning; issued and prescribed power preserved | Prevent changing choices during request; include unavailable-power recovery; any approval policy change is a clinical decision |
| Spectacles to be made | Same clinical roles, made line | Requires measurements and valid collection window; defer then token | Fresh days and collection capacity; explain source of schedule failure; resume print after persisted fulfilment |
| Hospital referral | Same clinical roles, hospital line | Referral completed in prescription; no invented surgery schedule action | Preserve referral versus surgery distinction |
| IOL surgery | Same clinical roles, hospital line | Eye/outcome required; schedule available day or decline; paper comparison; print token | Capacity conflict refresh; patient-specific busy guards; decline acknowledgement; no physical-surgery claim |
| Correction | Same clinical roles | Reason required, changed fields, generation/operation ID; modal inputs disabled while pending | Prevent close/underlying patient change during commit; reload errors must be visible; show changed/reissued items |
| History | Same clinical roles | Prior camp/date/diagnosis modal; response tied to lookup sequence | Only a diagnosis summary is currently exposed; richer prescription/fulfilment history is a product opportunity |
| A6 token `/print/slip/:id` | Clinical roles | Read persisted token; Hindi/English patient/date/time/venue/instructions; print button | Reprint/retry return path, long-name and actual-printer validation; no duplicate fulfilment required |
| Admin overview, camps, days | Admin | KPI overview, camp CRUD/activation, print-window control, emergency door control | Accurate loading states; pending action locks; explicit effect of activation/deletion; stale client handling |
| Admin OT/specs schedules | Admin | Hospital/date/seats, specs time windows | Validate positive limits/time order; acknowledge create versus update; refresh clinical clients |
| Admin medicines/powers | Admin | Add, retire, restore | Pending per-item action; error/retry separate from genuine empty catalogue; preserve retired values in history |
| Admin prescription logos | Admin | Camp-specific logos, file-type/2 MB validation, ordering/removal, preview and save | Keyboard-operable upload/buttons; dirty camp-switch guard; logo payload/print performance budgets |
| Admin leaderboards/exports | Admin | Volunteer/team rankings and camp-record CSV | Export busy/progress/error states; avoid success styling on failure; accurate export context |
| `/analytics`, legacy `/board` | Admin, team lead | 15-second polling; hidden/in-flight suppression; stale snapshot displayed | Preserve existing suppression/stale states; cap polling cost with actual measurements; link back predictably |
| `/team` | Admin, team lead (team-scoped volunteers) | Add staff, role/lead choice for admin; reset PIN, enable/disable | Pending per-staff controls; refresh reset badge; impact confirmation for disabling/resetting another user's access |

## Findings and execution work packages

### UX-01 — P1: ambiguous Aadhaar/manual match has a circular recovery path (confirmed source defect)

Evidence: `frontend/src/components/desk/ScanOutcome.js:93-109` lists ambiguous registrations with no clickable candidate and instructs “find … then check … in”. `frontend/src/pages/Desk.js:447-480` considers any not-arrived, not-scanned manual registration `needsDoorScan`, hides its only action (Print), and tells staff to scan again. `Desk.js:119-126` only confirms an already-selected `scanResult.registration`, which an ambiguous result does not supply.

Reproduction: seed two manual records matching a scanned identity, neither arrived; scan → ambiguous → search one number/name → row demands Aadhaar scan → scan returns same ambiguity. No UI step chooses the candidate and confirms the current card against it.

Implement an explicit candidate-selection path, using the existing server verification/confirmation contract if sufficient. Show discriminating details (reg no, name, age, masked household contact/day), then stored-versus-card review and a deliberate confirmation. Never silently pick first and never bypass server comparison. Preserve raw scan only for the active attempt; clear on new person/camera capture.

Acceptance: two/three candidates can each be deliberately selected; cancellation returns to candidate list; stale response never updates another patient; only selected registration arrives after successful confirm; conflict gives recovery; no disclosure beyond role permissions. Test ambiguous scan → select → mismatch → confirm → print end to end with server/API fixtures.

### UX-02 — P1: clinical draft is discarded by next lookup/scanner input (confirmed source defect)

Evidence: `frontend/src/pages/Clinical.js:152-160` clears patient/draft context before lookup success; `:169-170` replaces rx after success; `:191-195` enables wedge lookup whenever not picking/busy/correcting, including unsaved editing. `components/clinical/ClinicalLookupForm.js:19-37` leaves lookup and phone scanner available during ordinary edits. No dirty-state/navigation guard exists in reviewed source.

A wrong scan or failed lookup can erase unsaved diagnosis/measurements. The wizard saves on Next (`PrescriptionWizard.js:172-174`), not on every change, so current-step work is vulnerable even if earlier steps were saved.

Implement a draft baseline and a single guarded patient-transition function shared by number/name result/USB/phone scanner, station change, shell navigation and logout. Offer Save draft and continue / Discard / Keep editing where the server draft contract supports this. Keep current patient visible while looking up the next one until transition is accepted and lookup succeeds. Do not put unencrypted Aadhaar/patient payloads in localStorage as an expedient persistence mechanism.

Acceptance: edit each wizard step then scan another patient, search an invalid ID, change line, navigate home, and reload; no silent data loss. Save failure retains current patient and input. Cancel returns focus. Approved transition invalidates old async response. Server draft checkpoints remain intact.

### UX-03 — P1: failed clinical reference-data requests masquerade as empty setup (confirmed)

Evidence: `frontend/src/pages/Clinical.js:110-150` logs five independent fetch failures and sets each list to `[]`; there is no UI failure/retry state. `MedicinePicker.js:10-14` and `FixedPowerPicker.js:61-65` tell the operator that no items have been added. `PrescriptionWizard.js:36-40` cannot advance medicine/fixed-power steps without selections. DayPicker (`FulfilmentStation.js:80-113`) similarly describes empty failed schedules as not configured/full.

Implement independent loading/error/empty/loaded states and retry per resource (or a shared reference-data layer); make network failure visibly different from empty catalogue. Cache successful camp-versioned immutable references and refresh on focus/configuration invalidation; do not replace usable cached data silently with []. Critical unavailable catalogues prevent affected actions with an explanation; unaffected workflow continues.

Acceptance: individually fail diagnosis, medicines, powers, OT days and specs days; operator sees correct reason/retry, retry repopulates without losing patient or edits, actual empty still gives admin instructions, previous camp data never leaks after camp switch. A last-seat conflict refreshes OT availability rather than repeating stale choices.

### UX-04 — P1: editable controls and modal cancellation can race committed requests (confirmed source paths)

Evidence: `PrescriptionWizard.js:197-282` sends child fields `disabled={locked}`, not busy, while Next/complete requests set busy (`Clinical.js:212-258`). Thus values/confirmation may change after submitted payload was captured. `Desk.js:603` passes unconditional modal onClose, and `:662` keeps Cancel enabled during registration. Modal Escape/backdrop invokes onClose (`components/ui.js:145-165`). `CorrectionModal.js:69-92` correctly freezes its fieldset but parent `Clinical.js:394-408` can close the modal while save is outstanding. Fulfilment day selector and paper checkbox lack busy disabling (`FulfilmentStation.js:88-94,291-300,382-383`).

Implement an immutable submitted snapshot and consistent pending-action state. Freeze inputs affecting an in-flight commit; prevent closing/discarding or swapping patient while a mutation's outcome is unresolved. Use synchronous in-flight guards where multiple entry paths can initiate the same operation. Keep a clear “Saving…” status and reconcile successful response before the next patient. Cancellation of a read can abort it; cancelling a write in the UI must never imply the server rolled it back.

Acceptance: delay save/registration/fulfilment/correction responses, attempt edits, Escape/backdrop, another scan and double-click. Exactly one operation commits; no new person's form is closed by the previous response; selected schedule shown equals payload; failure unfreezes and preserves inputs. Test final prescription confirmation cannot be unticked/changed after payload submission while success is pending.

### UX-05 — P1/P2: door walk-in retry does not retain operation identity; multi-step completion is not recoverable (confirmed frontend behavior; backend outcome must be tested)

Evidence: `Desk.js:218-231` creates a new `v4()` inside every submit, whereas public/modal/manual paths retain IDs. `Desk.js:187-205` saves registration then calls arrival. If arrival fails, the catch (`:238-244`) reports a generic error/duplicate path while leaving no dedicated “registered, check-in pending” state. A lost registration response followed by retry uses a different operation key; whether duplicate prevention catches this safely depends on backend identity matching.

Implement one stable request ID per patient attempt; retain persisted registration ID after first success and retry only the unfinished arrival. On uncertain timeout, reconcile by operation ID before issuing a new registration. Keep actual success/notification state separate. Reset IDs only on new identity/new patient or conclusively completed operation, not on retry.

Acceptance: response loss after server commit, arrival failure after successful register, repeated taps and retry after error yield one registration and eventual arrival. No false new-person creation and no “start again” loop. Existing duplicate becomes a direct Open existing registration action after allowed verification, not only text asking staff to search again.

### UX-06 — P2: optional sponsor-logo request blocks the entire essential print screen (confirmed performance bottleneck)

Evidence: `frontend/src/pages/PrintPrescription.js:27-41` awaits prescription then sponsor logos before loading=false; `frontend/src/lib/api.js:25-28` allows the logos call to take 30 seconds. The comment says printing can proceed without logos, but this happens only after timeout. Logos are fetched again for every patient's print route.

Implement camp-versioned logo cache/prefetch and a short independent asset loading budget. Show the essential prescription promptly; do not print before required identity/QR/fonts are ready, but give explicit “Print without sponsor logos” recovery if optional assets fail. Avoid adding a sequential duplicate dependency. Resize/compress logos to print-appropriate dimensions and a total-payload cap after measurement; preserve existing image-type/size checks.

Acceptance: with logos stalled for 30 seconds and prescription fast, essential preview and safe recovery are available within the agreed print-ready budget; cached same-camp logos reused; camp/logo update invalidates correctly. Stale responses never combine patient/camp assets. Record physical print validation separately.

### UX-07 — P2: initial loading shown as no camp/no staff/zero metrics; weak recovery (confirmed)

Evidence: `SelfRegister.js:36-46,83-86` initializes camp=null and shows “No active camp” before the fetch resolves; failed load has only Alert and no retry. `AdminDashboard.js:58-77,80-83` similarly initially claims no camp/zero; `Team.js:19,29-44,202-203` initially claims no staff. Desk immediately shows no-camp alert at `Desk.js:290`. Lookup requests in Desk/Clinical have response sequencing but no dedicated visible pending state (`Desk.js:137-173`, `Clinical.js:152-178`).

Implement explicit loading/ready-empty/error/stale states. Use shared accessible LoadState/Retry components; don't blank already-useful context for unrelated refresh failures. In Desk `load()` fetches KPIs and camp together (`:55-73`) and whole-page ErrorCard on either failure (`:280`); decouple noncritical KPI failures from registration availability. Maintain errors near the failed task.

Acceptance: throttled initial requests never claim no camp/staff; real no-camp is distinct; public Retry succeeds without refresh/scanned-data loss; KPI-only failure does not remove an otherwise usable desk; lookup progress resolves/clears and previous request cannot overwrite newer selection.

### UX-08 — P2: stale operational configuration is not refreshed on working screens (confirmed fetch lifetime)

Evidence: Desk loads camp/print window on mount and its own successful actions (`Desk.js:55-76`); public registration loads days once (`SelfRegister.js:36-46`); clinical catalogues/schedules load once (`Clinical.js:110-150`). Admin may change camp, printing window, emergency entry, catalogues or last-seat capacity in another session. Existing Board polling is already visibility-aware, unlike these on-demand configuration snapshots.

Implement a small centralized camp/configuration cache, refresh on visibility/reconnect and recoverable server conflict, plus a bounded refresh policy for active desks. Publish or poll a compact config/version endpoint if justified. Do not add rapid whole-patient polling. Explicitly notify if the active camp changes; invalidate old day selections and patient context safely.

Acceptance: admin opens/closes printing while desk is idle; emergency manual flag expires; last OT seat is taken elsewhere; public day fills; resource is retired. UI reconciles without wrong-camp writes and presents next action. Unavailable network shows last-updated/stale when preserving cached data.

### UX-09 — P2: registration validation is inconsistent and causes avoidable server round trips (confirmed)

Evidence: public Register requires exactly ten literal digits (`SelfRegister.js:129`) while its phone input stores spaces/+91/non-digits unchanged (`:119`). Door phone normalizes input (`ScanOutcome.js:126`). Assisted modal marks age/phone required (`Desk.js:632-641`) but Register disables only for busy/name/day (`:663`), and it is not a native form with required controls. Required Field (`ui.js:38-48`) is visual only. Door/manual age input has no range (`Desk.js:427-428`).

Define shared phone normalization and validation matching backend rules; safely handle common pasted India contact formats without silently changing a different country's number. Validate bounded age and name/day/phone before mutation, show field-level errors, focus first invalid control and preserve QR-derived readonly fields. Avoid blocking missing optional fields. Surface full-day availability and backend conflicts at the day picker.

Acceptance: empty/whitespace names, age 0/negative/out-of-range, 9/10/11 digits, spaces, pasted +91, Devanagari digits if supported, disabled day, and backend duplicate/full-day errors have deterministic accessible feedback. Client and server agree. Never allow manual mode on public route as a validation workaround.

### UX-10 — P2: source has concrete accessible-name and keyboard gaps (confirmed)

Evidence: desk search icon-only button and placeholder-only field have no name/label (`Desk.js:337-340`); logo reorder/delete buttons are icon-only (`TemplateLogosEditor.js:42-55`); upload is a nonfocusable label around `display:none` input (`:10-24`); admin trash controls are icon-only (`AdminDashboard.js:156,239`). Field wraps interactive groups in a label (`ui.js:38-48`; `PrescriptionFields.js:16-37`, `FixedPowerPicker.js:87-116`), rather than fieldset/legend. App loading spinner has no text/status (`App.js:16-20`).

Implement explicit contextual aria-labels or visible text, native keyboard-operable upload button with file ref, meaningful disabled first/last reorder state, fieldset/legend for groups, associated error/hint IDs, and announced progress/status. Keep existing focus trap/restore, minimum 44px shared targets, input focus rings, pressed states and reduced-motion support. Audit actual contrast and mobile layout with authorized tooling later; no visual failure is asserted from colors alone.

Acceptance: all meaningful buttons have unique names; keyboard-only upload/reorder/remove; modal open/trap/Escape/restore behavior; live save/lookup errors; no unnamed form inputs; screen reader identifies groups and selection. Test 320/360/390px plus 200% text zoom and long Hindi names when browser validation is permitted.

### UX-11 — P2: locale does not match Hindi-primary public-use goal (source fact, product intent from context)

Evidence: `SelfRegister.js:76-153` is substantially English, including failure instructions/receipt, and `frontend/index.html:2` has lang=en. Printed tokens already contain useful Hindi/English labels (`PrintSlip.js:63-82`). This is a mismatch with the stated intended audience, not a measured usability score.

Implement centralized messages and Hindi-first public-registration/scan/help/receipt copy with explicit language choice. Staff terminology should remain bilingual where training/materials use English; retain familiar reg number/day/phone labels. Set document and mixed-language semantics correctly. Have a Hindi-speaking local operator approve terminology and aloud-read instructions; do not blindly machine-translate clinical names or drug catalogue.

Acceptance: a Hindi-speaking first-time user can locate scan, correct phone, understand failure/retry, choose day and retain receipt without staff translation. Every error path matches selected language. Existing English users can switch; long strings wrap; printed clinical content retains approved wording.

### UX-12 — P2: admin mutations and team actions have inconsistent pending/error feedback (confirmed)

Evidence: camp/day create, activation, deletion and print controls have no busy guard (`AdminDashboard.js:107-135,204-222`); OT/specs Add buttons only validate fields (`:295,345`); catalogue toggles lack pending lock (`:380-386`). Staff reset/enable/disable lacks pending state (`Team.js:79-110,227-241`); resetPin does not reload staff, leaving `must_change_pin` badge stale (`:84-85,219`). Export catch and success both render emerald Alert (`AdminDashboard.js:511-524`), no busy guard, and blob API errors can become generic.

Implement a per-action/per-row pending state, action-specific success/failure, and clear destructive/operational impact confirmation for camp delete/activation, print-window shutdown, account disable and PIN reset. Don't prompt on every reversible low-impact edit. Refresh affected entities; show newly reset account's required-PIN badge. Download action must distinguish preparation, dispatched browser download and failure; don't claim disk write was verified.

Acceptance: rapid taps produce one mutation; failed POST never shows green success; deleting wrong/active/in-use camp is guarded server-side and explained; reset badge updates; export 401/500/blob JSON error displays correctly and can retry; no duplicate 15k-row exports during pending.

### UX-13 — P2: route/session and render-failure recovery is incomplete (confirmed source coverage)

Evidence: `AuthContext.js:18-22` treats any /auth/me failure as anonymous; `:13-16` skips valid session detection for direct login/public navigation. `App.js:27` sends expired/deep-linked users to login without preserving safe intended location. `lib/api.js` has timeout/error formatting but no centralized 401 session-expired transition; lazy routes have Suspense but no error boundary (`App.js:43-57`).

Implement distinct auth loading/anonymous/error states with retry, safe intended-route restoration, and session-expiry UX for protected requests. A server-confirmed 401 clears staff state and closes cameras/PII-bearing screens; a transient network failure must not masquerade as logout. Add shell/route error boundary with a recoverable message and reload of a failed lazy chunk, without logging patient payloads.

Acceptance: /auth/me 503 versus 401, mid-form expiry, disabled account, unauthorized role route, direct print deep link and lazy-chunk failure all recover predictably. Reauthentication cannot accidentally submit a stale patient's draft under another staff identity. No automatic replay of uncertain writes.

### UX-14 — P2: notification claim outruns evidence (confirmed frontend wording; delivery semantics need backend check)

Evidence: `Desk.js:265` and `:585` unconditionally say “SMS sent” after registration, without reading a delivery/send status. They also say this on a request's successful replay. A queued/failed/offline provider cannot be accurately represented by a blanket sent claim unless backend explicitly guarantees that state.

Bind UI to actual response notification state: registered, SMS queued/sent/failed as available, with visible reg number/QR and staff recovery. Avoid requiring SMS success for otherwise saved registration. Do not send duplicate notifications on retries. Validate backend contract before changing terminology.

Acceptance: SMS provider disabled, queued, sent and failed responses show accurate status and a usable registration receipt; response replay never promises a second delivery or duplicates registration.

## Additional improvement opportunities (not claimed defects without user/device evidence)

1. **Public receipt retention:** currently receipt lives only in component state (`SelfRegister.js:18,136-155`); refreshing loses that screen. Offer clearly labelled Save receipt/print and an approved minimal-data recovery path. For “register another”, show whether household phone is intentionally reused (`:152` leaves phone/day intact). Do not expose patient records publicly via predictable reg number.
2. **Print semantics and mobile preview:** A4 uses fixed 210mm width, 297mm height and overflow:hidden (`PrintPrescription.js:115-117`). Preserve physical template; create a fitted screen-only preview, test long address/name/logos for actual clipping, and keep printer output at true size. Server print record is made before native dialog (`:98-100`); user cancellation cannot be detected reliably as physical print failure/success. Decide whether it means “print requested” and give safe reprint. Source alone cannot validate paper fit.
3. **Clinical station completion:** existing fulfilment view supports reprint and hospital decline but not obvious “next patient” on already fulfilled/referral-only states (`FulfilmentStation.js:304-349`). Add clear Next patient/reset focus for throughput after verifying operator needs. Treat added collection/actual surgery workflows as scope decisions; current code records scheduling/deferral, not physical completion.
4. **Explicit medicine selection:** `FulfilmentStation.js:224` defaults every prescribed medicine to given. Paper confirmation exists; assess with medicine operators whether neutral initial given/not available selection reduces mistakes enough to justify extra taps. Do not call this a proven dispensing bug or silently change clinical policy.
5. **Useful clinical history:** HistoryModal shows date/camp/diagnosis only (`HistoryModal.js:12-27`). Expand to saved prescription, fulfilment and correction history in a compact disclosure if operators need it; permissions/PHI minimization still apply.
6. **Role navigation:** common Layout has logo/home, PIN and logout only (`Layout.js:27-74`). Admin reaches workspaces via home; lead links appear only on Desk (`Desk.js:284-288`). Consider compact role-specific navigation and persistent active-camp/operating-day/station name. Deep-linkable admin tabs and dirty-tab guard improve back button predictability; tab local state currently resets on unmount (`AdminDashboard.js:29-51`).
7. **Catalogue/large-team usability:** lists are fully rendered, without filter/pagination (`Team.js:205-246`, `MedicinePicker.js:24-45`). Measure real size first; search/filter and bounded server results can be more useful than adding virtualization blindly.
8. **Template editing:** switching camps drops unsaved logo changes (`TemplateEditor.js:31-41,107`), and parent tab change unmounts the editor; add a dirty indicator and guard. Per-file 2 MB cap exists (`templateHelpers.js:1,14-24`); total count/payload cap and resized assets require backend alignment. No claim of exploitable upload issue is made here.

## Performance and production-feel targets for the executor

These are proposed acceptance targets to measure on an agreed representative Android handset and desktop, not current benchmark claims. Use source unit/integration evidence now; actual device/browser validation follows only when authorized by repository instructions.

| User-visible metric | Proposed target and measurement |
|---|---|
| Interaction acknowledgement | <100ms local status/pressed state; all saving/searching shows immediate feedback |
| Route load | Agree cold/warm network/device profile; record p50/p95, transferred bytes, LCP/INP/CLS; targets LCP <=2.5s, INP <=200ms, CLS <=0.1 when measured appropriately |
| Essential print ready | p95 <=2s on agreed camp network excluding native printer; stalled optional logos cannot add 30s |
| Lookup | p95 <=1s for agreed seeded 15k-patient dataset at 40–50 active operators; clear progress/retry beyond target; avoid duplicate requests |
| Save/complete | no silent input loss; one logical effect under timeout/retry/double-click; announce pending and reconcile |
| Polling | Preserve Board's 15s, visibility/in-flight suppression (`Board.js:19-46`); login already uses 5s suppression (`Login.js:21-38`). 50 login tabs would make 600 requests/minute before server cache, so assess necessity/adapt/backoff rather than adding polling elsewhere indiscriminately |
| Bundle | App already lazy-loads pages (`App.js:7-14`); record route chunks/transfer and scanner WASM separately; preload only imminent tasks rather than removing working split points |
| Accessibility | Automated name/role checks plus keyboard/screen-reader scenarios; 44px targets already provided, check exceptions; no visual/perfect claim without review |
| Failure recovery | Offline, timeout, 401, 409, 429, 500 and unknown-write-outcome cases explicitly exercised per critical workflow |

Do not remove existing correctness safeguards to make screens “faster”: generation/revision checks, paper review, mismatch confirmation, arrived/printed clinical lookup gate, stable operation IDs, scoped role routes, and readonly QR identity remain mandatory.

## Minimum regression scenario set

1. Public QR success/failure/retry; manual buttons absent always; authorized assisted attempts count three camera sessions only (not video frames, backend outages, upload/USB or cancellations); new patient resets count.
2. Desk pre-register scanned and allowed manual, duplicate, ambiguous, full-day, timeout and retry; camp opening/closing while page stays open.
3. Door scan registered, seen, mismatched manual identity, ambiguous manual identities, no booking/walk-in; stable register/arrive recovery and no double arrivals/notifications.
4. Number/name/QR lookups arriving out of order; no-match progress; stale response and camera completion cannot change active identity.
5. Prescription none/medicine/fixed/made/hospital-referral/IOL combinations; incomplete data and line exclusivity; all step checkpoint failures and final complete conflict; dirty new-patient transitions; editing during delayed saves.
6. Medicine partial availability, fixed different powers, specs collection, OT final-seat race/decline, already-fulfilled reprint; paper review and revision mismatch handling.
7. Correction with audited reason, stale generation, cancellation/pending request, visible failed reload; history on current versus new person.
8. Print A4 and A6 with long bilingual identity/address/venue, logos delayed/failing, direct refresh, reprint and cancelled native print dialog; QR scans from actual paper when permitted.
9. Admin create/activate/deactivate/delete camp, add day and window, emergency manual scope, schedules, retire/restore, logos keyboard and dirty switch, export errors; all double-tap pending states.
10. Team admin/lead role boundaries, create/reset/enable/disable, updated badge, PIN required change, auth timeout versus expiry, role/session switch; tab navigation and analytics stale recovery.

## Good safeguards verified in current source

- Route splitting already exists; do not recommend adding it as missing (`App.js:7-14`).
- Auth cookies sent with credentials, 30s request timeout and structured API error formatting exist (`lib/api.js:25-39`); backend cookie/security policy still needs separate review.
- Board and login polling already avoid hidden tabs and overlap; Board retains a stale snapshot and timestamp (`Board.js:17-48,69-72`).
- Desk/clinical lookups guard out-of-order responses (`Desk.js:137-172`, `Clinical.js:152-178`); do not discard those guards.
- Shared Modal already traps/restores focus and locks body scroll; shared inputs/buttons have >=44px minimum targets; reduced-motion preference exists (`ui.js:129-184`, `index.css:25-27`).
- QR-derived assisted identity fields are readonly where data exists (`Desk.js:630-653`); mismatch review shows stored-versus-card differences before confirm (`ScanOutcome.js:48-90`).
- Clinical completion/correction/fulfilment carry generation/revision and operation IDs (`Clinical.js:235-243`, `CorrectionModal.js:77-84`, `FulfilmentStation.js:254-268`). Correction inputs already freeze while saving.
- A4 print waits for print-record API success and ignores late completion after patient change (`PrintPrescription.js:75-104`); token print does not create fulfilment.
- Template fetch/upload callbacks already guard camp changes; saving locks inputs (`TemplateEditor.js:31-41,54-56,106,124`).
- Explicit logout failure keeps user signed in and tells them to retry (`Layout.js:53-62`), rather than falsely claiming logout.

Review execution: targeted source inspection only. No production writes, app implementation, browser/dev-server run or test-suite execution performed by this reviewer.
