# SNP production experience: review and executor specification

Date: 21 September 2026. Repository: `Piyushmanyata/SNP`.
Reviewed baseline: `0e1c9feb8211820f241df0b05e22f55bbba4c91f` (`main`, 19 September 2026).
Status: PARTIALLY IMPLEMENTED. R1, R2, R3, R5, R6, R7, R8 and R9 are implemented with tests. R4 blocks a wrong-camp confirm and chooses among ambiguous matches; a same-camp confirm that is not a scan hit is rejected after the existing duplicate check. R10 bounds provider attempts and retries a known failure at most three times. R11 is deployment of this release. R12-R17 are not started. See the completion ledger.

## Outcome and authority

Make registration, arrival, printing, clinical recording and fulfilment easier to recover, faster under ordinary camp load, and safer under retries and concurrent staff actions. Preserve the existing React 18/Vite/Tailwind and FastAPI/Motor/MongoDB architecture and its domain rules.

The owner authorized reviewing, specifying, implementing, opening a PR, monitoring CI, merging only when green, deleting the merged branch, and updating the existing VPS. All existing VPS application data may be treated as test data and reset if necessary. This permission does not require a reset when none is needed, and does not require deleting TLS certificates, environment secrets or backups.

This is an implementation contract, not a claim that the application is perfect or certified production-ready. A code review cannot establish camera recognition rates, clinical suitability, physical print quality, real carrier delivery or performance on the deployed server. Those are explicit release checks below.

## Evidence and review limits

- Source inventory: 24 backend production Python modules (5,544 lines), 58 frontend production JavaScript modules (7,208 lines), 33 frontend test files and 35 backend `test*.py` files at baseline. Counts exclude dependencies, historical reports, assets and docs; they are inventory, not a claim every line was independently verified.
- The baseline GitHub CI run `35430320874` completed successfully. Its results are historical baseline evidence, not validation of this change.
- Reviews trace routes, callers, state transitions, models, authorization, tests, resource bounds, persistence and deployment configuration. Confirmed findings below have source evidence; implementation tests must independently reproduce the applicable defect.
- Repository `AGENTS.md` prohibits browser/dev-server/screenshot verification. Therefore this is a source-based UX review with automated behavioural tests, not a visual browser audit. No real Aadhaar document, patient database, SMS send or physical phone was used.
- Planning load: about 15,000 patients and 40–50 concurrent staff, from owner context. These are workload assumptions, not measured operating numbers.
- Local `lean-ctx`, `ponytail`, and the named `/to-spec` skill are not available. Use this explicit specification and targeted source/test inspection; do not manufacture evidence from unavailable tools.

## Existing strengths to preserve

Keep lazy-loaded routes, self-hosted ZXing assets, worker decoding, single-flight scan/decode protection, native detector plus WASM fallback, 1080p-to-lower-resolution camera fallback, capability-checked torch/focus, throttled full-resolution still capture, bounded backend extraction, backend-authoritative identity fields, stable idempotency keys where already implemented, atomic capacity reservations, unique indexes, clinical operation/revision records, role guards, HTTP-only session handling, minimum 44px shared controls, modal focus management, and the existing real-Mongo HTTP CI gate. Do not replace these with new frameworks or a general state-management layer merely for consistency.

## Workflow and role coverage

| Workflow / entry | Roles | Desired result and recovery checks |
|---|---|---|
| Login, first PIN change, logout, expired session | Staff | Clear pending/error state; no duplicate submits; invalidated sessions cannot mutate data; safe role home |
| Public camp availability and self-registration | Public, including staff visiting public route | Loading differs from no active camp; retry failed load; readable QR required; no manual identity entry after any number/type of failures; retained form on recoverable error |
| Assisted pre-registration | Volunteer, team lead, admin | Scan first; verify card; select camp day/contact; duplicate reconciliation; stable retry identity; manual option only after 3 failed camera sessions |
| Camp door scan and arrival | Volunteer, team lead, admin | Recognized patient → arrival → print; mismatch requires explicit review; ambiguous matches allow safe candidate selection; wrong-camp candidate rejected before write |
| Walk-in registration | Volunteer, team lead, admin | Same patient operation retains request ID through response loss and arrival retry; walk-ins retain existing no-refusal seat rule and no registration SMS rule |
| Door manual exception | Volunteer, team lead, admin; existing camp admin gate retained | Both admin-enabled camp policy and 3 failed camera sessions required; no direct form on initial load; explicit reason; unverified identity label |
| Patient search and lookup | Authorized desk/clinical roles | Bounded inputs/results; no integer overflow; explicit none/error states; old patient QR compatibility preserved |
| Prescription print / repeat print | Authorized desk roles | Essential prescription not blocked by optional sponsor service; clear print/return actions; no seen-patient reprint regression; no false physical-print guarantee |
| Clinical lookup and transcription | Clinical operator, admin | Reference failures visible and retryable; preserve dirty draft before patient switch; optimistic concurrency rejects stale write; keyboard scanner cannot discard active edits |
| Complete / undo / correct prescription | Authorized clinical roles | Version checks; retries of the same operation resume safely after partial failure; no duplicate revision/stock/seat mutation; conflict remains visible |
| Medicine issue | Assigned clinical line, admin | Catalogue unavailable differs from empty; valid selected medicines; completion/issue idempotency retained |
| Fixed-power spectacles | Assigned clinical line, admin | Required measurements and explicit substitution preserved; no issue on stale prescription generation |
| Spectacles to be made and collection | Assigned clinical line, admin | Required measurements, valid collection window, reservation/release, token, cancellation and later collection stay consistent |
| Hospital outcome / IOL scheduling | Assigned clinical line, admin | Referral, declined surgery and scheduled IOL remain distinct; no unwanted token; capacity and expiry rules preserved |
| Camp setup / activation / days / print windows | Admin | Validation, concurrent setup protections and activation rules preserved; actionable failures and safe pending actions |
| Staff / team assignment / PIN resets / disable | Admin, scoped team lead | Delegated permissions preserved, session revocation and attribution correct, failures retryable |
| Analytics / leaderboard / live board | Admin, scoped team lead | Eliminate sequential count query growth; no overlapping/stale refresh results; expose refresh failure without replacing useful last result |
| CSV export / sponsor logos / catalogue settings | Authorized admin/staff | Existing role/data scope preserved; errors recoverable; optional logo failure cannot block patient care |
| Registration/token SMS and reminders | Server worker | Provider error is never recorded as sent; sent/uncertain/failed states distinguished; no 10,000-row silent cutoff; bounded sending; no blind resend of uncertain accepts |
| Deployment / health / backup / rollback | Operator | Same Compose project and named volumes; exact merged source; health/readiness; rollback image and backup; no live destructive test suite |

## Prioritized findings and implementation requirements

Line references identify the reviewed baseline and may move after implementation.

### R1 — Staff-only manual entry after three failed camera attempts (P1, required)

Evidence: `frontend/src/pages/Desk.js:418,559,611–618` exposes immediate door/manual controls, uses generic decode failure counters, and resets them on capture start. The existing modal's manual button is unconditional. `backend/routes_registration.py:453–468` does not enforce the existing `failed_scan_attempts` / `manual_reason` fields. Public QR-only checks already exist; strengthen regression coverage rather than reintroducing an OCR/manual path.

One patient registration session owns `failedCameraAttempts` (0–3). A camera attempt begins only on an explicit camera start/retry. One session contributes at most one terminal failure. A terminal failure is a camera-start/device/permission failure, a detector failure that prevents scanning, or a completed 20-second scanning attempt with no accepted Aadhaar result. Repeated frames, repeated backend decode errors within that attempt, photo upload, OCR review, USB/pasted QR, cancelled permission prompts, normal Stop, switching lenses and opening/closing a panel do not independently add failures. A user retry begins a new attempt; it must not reset accumulated failures.

Visibility predicate:

`context === assistedRegistration && role in {volunteer, team_lead, admin} && failedCameraAttempts >= 3 && !acceptedIdentity`

For the camp door, also require the existing admin-enabled `door_manual_entry` setting. This extra gate is retained; the new rule never grants a clinical-only operator manual access. The public self-registration component does not receive/render a manual-entry callback at all, including when a logged-in admin visits it. Do not auto-open the manual form: reveal a secondary action after attempt 3. Display a concise count and practical retry/photo/USB guidance. Manual form requires a reason and records the count, source and actor; it stays unverified until the existing identity-check workflow verifies it.

Reset on accepted identity, completed/cancelled patient session, registration modal close/new patient, camp change, role/session change and logout. Do not persist eligibility in localStorage or across patients. Closing a retry panel must not unlock entry. Backend staff registration rejects unscanned submissions below the threshold or without a reason; roles and current camp policy remain server-controlled. Client counters are workflow evidence, not tamper-proof proof of a physical camera attempt; document this limit rather than inventing surveillance or a heavyweight attestation service.

Acceptance: 0/1/2 failures hidden; third distinct failure reveals for each allowed staff role; third frame/error in one attempt does not; upload/USB failures do not; public and clinical-only roles never; success/next patient resets; camp door gate off still forbids; direct unauthorized/public API calls cannot bypass identity rules; late scan responses cannot overwrite a manual draft.

### R2 — Recoverable and efficient phone scanning (P1 correctness; measured tuning later)

Evidence: `components/aadhaar/liveScan/liveScanEngine.js:93` clears the stall timer on any detected QR before Aadhaar acceptance, allowing an unrelated QR to suppress recovery indefinitely. Camera helpers, worker and grab-frame code already implement several important performance safeguards.

Make the recovery deadline depend on accepted identity, not merely detection of a barcode. Preserve ignored-payload throttling so a non-Aadhaar QR does not spam the API. Release streams, worker requests and timers on stop, error, unmount and stale permission completion. Report one camera-attempt failure to R1. Ensure late failures and successes are tied to the current attempt. Keep preview decoding serial, maximum current 8 Hz, and still-photo capture no more than once per 3 seconds; do not increase resolution or detector effort globally without evidence.

Improve instructions within existing screen patterns: rear camera, clean lens, whole QR inside guide, avoid glare, hold steady, supported torch, retry and photo fallback. Only expose device capabilities actually available. Unsupported focus/torch constraints must degrade gracefully. Network failure differs from unreadable QR; neither should falsely mark identity locked.

Acceptance: unrelated QR then 20-second timeout still gives recovery; stop/resume cannot deliver old results; worker failure terminates pending work and permits a fresh attempt; no simultaneous detector/decode work; no camera still-photo burst. Tests use fake clocks and controlled decoder promises. Real-phone success rate and battery/thermal improvements remain unmeasured until the hardware matrix is run.

### R3 — Server-derived scanned identity and strict legacy QR parsing (P1)

Evidence: staff `/register` trusts `aadhaar_scanned` and supplied identity fields whereas `/self-register` re-decodes `qr_payload` (`routes_registration.py:453–535`). `aadhaar.py` treats arbitrary XML-looking text and a regex fallback as identity: a synthetic `<anything name="Not Aadhaar" />`, malformed XML and a future DOB can be accepted.

Apply the same server-derived scanned identity contract to assisted registration: require and decode the QR payload when claiming scanned identity; derive protected identity fields from it. Preserve manual registrations only through R1. Reject unknown XML roots, malformed/truncated XML, invalid UID/last-four structure, impossible/future date of birth and impossible derived age. Preserve supported legacy Aadhaar XML variants and existing narrowly justified bare-ampersand compatibility tests. Do not claim that parsing legacy XML or a compressed secure QR cryptographically verifies a UIDAI signature; that remains a separate trust decision already recorded in the repository.

Acceptance: forged scanned boolean with no payload rejected; tampered client identity replaced by decoded card fields; valid legacy and secure QR fixtures pass; malformed/unknown-root/future-DOB fixtures fail cleanly with no patient/person/seat write; raw identity payloads do not enter logs.

### R4 — Complete desk recovery without duplication or cross-camp mutation (P1)

Evidence: `ScanOutcome.js:93–108` tells ambiguous matches to use a lookup path that `Desk.js:447–480` cannot use to arrive an unverified patient; `Desk.js:218–231` generates a new registration request ID on each walk-in submit; `routes_desk.py:249–263` loads a scan-confirm target without active-camp scope; `_resolve:21–30` converts arbitrarily long digit strings.

Render explicit candidate selection for an ambiguous scan, with sufficient minimal identity/contact context to distinguish records. Require explicit confirmation using the scanned payload and chosen patient. Validate candidate membership/current camp and door-open policy before any identity write. Re-evaluate scanned identity on confirmation and preserve already-locked records. Never arrive an arbitrary lookup row without the existing identity checks.

Use a stable walk-in registration ID for the patient attempt, retain the committed patient when arrival fails, and retry arrival rather than creating another registration. Bound numeric lookup before conversion and return a defined client error. Preserve first-arrival attribution, same-card idempotency, existing mismatch diff review, walk-in capacity exception and no-registration-SMS behaviour.

Acceptance: two similar manual registrations can be disambiguated and exactly one arrives; wrong-camp/stale candidate changes nothing; response loss then retry yields one registration/seat/arrival; arbitrary long numeric lookup returns controlled error, never 500.

### R5 — Clinical draft concurrency and dirty-draft protection (P1)

Evidence: `models.py:142` defines `expected_draft_version` but `routes_clinical.py:271–311` does not enforce it. `Clinical.js:152–195` can replace a patient while editing via lookup or scanner. This permits silent lost work or last-writer-wins overwrites.

Implement atomic optimistic concurrency on draft update. Return/increment a draft version and require the client's expected version for an existing draft; missing legacy versions must have an explicit safe transition. Reject stale writes with 409 and a stable machine code. Preserve unsaved client fields on conflict and offer reload/review, never silent overwrite. New-draft creation must also handle simultaneous creation under the existing unique patient index. Completion must not apply a stale draft over a newer save.

Prevent a new keyboard-wedge lookup, manual lookup, line switch or patient replacement from discarding dirty work. A concise discard confirmation is sufficient; do not create a general autosave system. Keep success/failed-save/pending state distinct. Preserve draft on failed network request. Register a before-unload warning only while dirty; remove it when clean.

Acceptance: two operators load version N; first save succeeds, second gets conflict and keeps their input; a delayed initial save cannot overwrite later state; cancel discard stays on same patient; confirmed discard changes once; background wedge does not silently change active patient.

### R6 — Clinical correction and undo recover after partial writes (P1)

Evidence: correction changes patient generation/revision before updating transcription, audit and operation completion (`routes_clinical.py:981–1009`); retry then compares the previous revision to the newly current revision (`clinical_state.py:237–262`). Undo has an analogous multi-write sequence (`routes_clinical.py:391–415`). Existing completion/fulfilment recovery is a pattern to reuse.

Use existing operation/revision IDs to make correction and undo resumable and payload-bound. A retry of the identical operation must finish its incomplete stages; a different payload or competing operation must conflict. Never blindly reapply stock or capacity changes. Preserve audit history and correct lifecycle generation. Make the smallest change compatible with standalone MongoDB; do not add multi-document transactions requiring an unconfigured replica set.

Acceptance: inject failure after each durable stage and retry same operation; final state equals one successful operation, one audit/revision, consistent patient/transcription generation, no duplicate fulfilment or seat release. Different operation IDs or payloads do not steal an incomplete mutation.

### R7 — Loading, errors and draft recovery are explicit (P1 UX)

Evidence: `SelfRegister.js:84` initially renders no active camp before request completion and offers no load retry. `Clinical.js:110–150` converts reference-data failures into empty lists, making an outage look like an empty catalogue. Existing shared forms and modals already cover much basic accessibility.

Separate initial loading, genuine empty/no-active-camp, recoverable load failure and ready states. Provide visible Retry without losing user input. Clinical reference failure should identify which capability is unavailable; do not offer an unusable empty picker or silently substitute invalid catalogue data. Patient-facing critical instructions/errors should be understandable to the Hindi-primary audience; introduce focused bilingual text for registration/scanning/retry where practical rather than an unreviewed site-wide translation rewrite.

Acceptance: pending public fetch never says no camp; 503 then successful Retry recovers; clinical load failure is announced and can retry; no stale patient's data appears after a late response; loading does not wipe a draft or present fake zero occupancy.

### R8 — Printing and frontend resilience (P1/P2)

Evidence: `PrintPrescription.js:27–41` awaits optional logo fetch before making the prescription available; API timeout is 30 seconds. `App.js` has route Suspense but no error boundary for rejected lazy chunks or render exceptions.

Render the valid essential prescription independently of optional sponsor loading. Retain fixed print layout and clinical print restrictions. A missing logo must not block care. Add a simple accessible application error boundary with a deliberate retry/reload action; keep technical stack traces out of patient-facing UI. Do not create an automatic reload loop or a service worker that caches patient data.

Acceptance: unresolved/erroring logos do not indefinitely block the essential print content; patient fetch failure remains visible; printing cannot include a loading/error scaffold; lazy import/render failure exposes recovery instead of a blank app. Existing A4/A6 snapshot tests pass; physical margins/legibility are still an operator check.

### R9 — Predictable reporting work (P2 performance)

Evidence: `routes_reports.py:45–75` performs two sequential counts per volunteer plus four per lead. Fifty volunteers and five leads therefore incur 120 count queries in one leaderboard request, excluding initial reads.

Replace the count-per-person loops with scoped grouped counts/aggregation or another constant-number database query design. Preserve role visibility, attribution and response shape. Use existing indexes where suitable; add indexes only for demonstrated query patterns. Avoid speculative cache layers. Refresh loops should remain single-flight, ignore stale results, and retain last successful data on transient failure.

Acceptance: leaderboard fixture totals are unchanged, team lead sees only authorized scope, empty groups are zero, query count does not grow linearly with staff count. Verify with real Mongo in CI, not a fake DB that silently ignores operators. Do not claim an elapsed-time speedup until benchmarked.

### R10 — Honest and scalable SMS outcomes (P1 correctness; P2 throughput)

Evidence: `msg91.py:48–50` returns any HTTP-200 body's message as acceptance without validating provider success. `routes_reminders.py:48,60` truncates targets at 10,000. `_send_each` sends sequentially; the reminder worker HTTP timeout is 120 seconds. Background-task notification creation also has a process-crash gap.

Validate MSG91 success type and nonempty request identifier using its current official response contract; a provider error/malformed body is not sent. Preserve the existing distinction between known failure and uncertain provider acceptance. Do not blindly retry `pending` messages: a response/ledger failure may have occurred after the provider accepted the SMS.

Remove silent recipient truncation using streaming or bounded pagination. Process bounded batches with explicit progress/completion so an HTTP timeout does not create overlapping long-running dispatches. Persist queued intents before sending where feasible in the existing ledger, then let retries process safe queued/failed items. Any larger outbox change must specify how patient commit and enqueue failure reconcile, stale/cancelled tokens are excluded, uncertain sends are surfaced for operator reconciliation, and duplicate accepted messages are avoided. If not implemented and tested in this release, record that limitation explicitly, not as a completed guarantee.

Acceptance: HTTP 200 error body stays unsent; success body records request ID; malformed/empty identifier fails safely; repeated cron is idempotent; a recipient beyond position 10,000 is eventually processed; batch memory/concurrency bounded; provider unconfigured stays visibly skipped; uncertain acceptance is not auto-resent; no real SMS in tests. Existing approved Hindi message copy is unchanged.

### R11 — Production and observability follow-through (release gate)

Preserve existing liveness/readiness separation, HTTPS, private Mongo/API ports, nonroot backend and backup rotation. Keep logs free of Aadhaar payloads, full patient details, tokens, credentials and SMS authentication keys. Record deployed source hash and CI links. Verify actual readiness, not only HTTP 200 at the homepage. Off-host backup destination, real SMS templates/provider credentials and phone/printer testing are external prerequisites; repository docs already identify them. Do not treat old deployment notes as proof they are configured today.

The documented VPS is `82.112.234.39`, application `https://sikarkolkata.io`, project `snp`, current release `/opt/snp/current`, configuration `/opt/snp/.env.production`. The documented SSH private key is on the owner's Windows machine; no key or SSH agent is present in this execution environment as of the review. Prepare the concrete tested release first. If authenticated VPS access remains unavailable, report deployment blocked and provide the prepared deployment command/package; do not claim deployment or request secrets in committed files.

## Scanner improvement experiments after correctness fixes

These are hypotheses requiring device evidence, not reasons to replace the current decoder:

1. Compare guide-region versus full-frame sampling on dense and small QR codes; retain periodic full-frame recovery and correct cover/rotation mapping.
2. Compare device-adaptive preview frequency against the existing 8 Hz ceiling. Optimize long tasks, temperature and battery, not just iterations/second. Never overlap work to increase apparent throughput.
3. Inspect actual camera settings after capability negotiation; test rear-lens selection on multi-camera Android/iOS phones. Do not hard-require 1080p or continuous focus.
4. Measure first-use WASM initialization separately from steady-state scan time. Warm only after camera intent where it materially helps, preserving the small initial route bundle.
5. Improve image fallback by distinguishing unsupported image, password-required PDF, blur/glare, unreadable QR, network timeout and extraction-busy errors. Public registration must not unlock via OCR. Staff suggestions remain editable/unverified behind R1.
6. Revisit the current extraction quota (12 attempts/10 min/IP, one worker per process) using representative shared-Wi-Fi demand. Keep bounded resource use; a staff-scoped quota or bounded queue needs authentication, expiry, cancellation and abuse tests. Do not just raise global limits.

## Performance acceptance plan

Targets below are proposed gates to measure; none is a measured baseline claim.

| Measurement | Workload / target |
|---|---|
| Initial JS/CSS transfer | Preserve existing build-budget gate; record compressed bytes before/after; no eager scanner/report imports |
| User action feedback | Visible pending/disabled action within 100 ms in a browser/device run |
| Camp/lookup/arrival APIs | 15k synthetic patients, 50 concurrent staff; initial target p95 <1 s, p99 <2 s excluding OCR/SMS; record host and network |
| Scanner | At least 3 representative phones, 30 authorized/synthetic QR trials per lighting condition; measure success within 10 s, median/p95 accepted-identity latency, cold vs warm WASM |
| Scanner scheduling | At most one detector/decode in flight, ≤8 preview attempts/s, ≤1 full-resolution photo/3 s, stopped streams after teardown |
| Reporting | Staff-count-independent database call count; response p95 measured at 15k patient load |
| SMS | Bounded batch work, explicit remaining/failed/uncertain counts; no omitted recipient at 10k boundary |
| Endurance | 30-minute scan/register/print loop and rapid patient-switch simulation; no growing outstanding workers/timers/requests |

A physical recognition trial should cover printed legacy QR, dense secure QR, phone-screen QR, rotation, glare, low light, permission denied, no rear camera, interrupted tab, orientation change, slow network and network loss after save. Store only anonymized aggregate results, never real Aadhaar captures in the repository.

## Execution order and independent work

1. Reproduce R1–R10 with focused regression tests; record intentional current rules before edits.
2. Scanner/registration owner: R1–R3 and frontend portion of R4. Backend workflow owner: R4 backend, R5 concurrency, R6, R9. Frontend workflow owner: R5 dirty protection, R7, R8 print. Integrator: R8 error boundary, R10, spec/evidence/release.
3. Owners agree request/response/error contracts before editing shared callers. One owner per file; tests stay with their feature. Use existing patterns and minimal dependencies.
4. Run targeted tests red then green. Typecheck/lint; full frontend suite/build and full backend suite once integrated. Real HTTP/Mongo tests run in CI when local Docker is unavailable. Do not report skipped live tests as successful live verification.
5. Two independent adversarial reviews: correctness (race, bypass, response loss) and simplicity (unnecessary layers/options). Resolve or explicitly decline every finding with evidence.
6. Open PR with this spec and implementation evidence. Wait for frontend/backend/dependencies/workflow/verify on the exact final head. Fix and rerun failures; do not weaken tests, security, type/lint/audit gates or skip jobs to obtain green.
7. Merge with expected head SHA; confirm merge result and main CI. Delete only this merged work branch where supported. Never delete another branch or repository.
8. Deploy exact merged source to the existing VPS using authenticated access. Record source hash, readiness, backup and rollback evidence. If access missing, preserve completed GitHub work and clearly name only the remaining access requirement.

## Deployment procedure and rollback requirements

- Read current release link and image IDs. Create rollback tags for backend/frontend/reminders before rebuilding. Keep the exact `-p snp` Compose project and existing TLS/data/backup volumes.
- Create an on-demand archive and validate it before an optional test-data reset. Do not reset merely to hide a migration defect. Never use production `down -v`.
- Stage the merged archive under `/opt/snp/releases/<full-commit-sha>`, preserving `/opt/snp/.env.production` separately. Validate production Compose; build before switching the current symlink.
- Run `docker compose --env-file /opt/snp/.env.production -p snp -f docker-compose.prod.yml up -d --build --wait` from the staged release. Update current link only as part of a recoverable release operation.
- Check all six services, HTTPS homepage, `/api/health`, `/api/health/ready`, HTTP redirect, static scanner worker/WASM assets and image/source revision. Use synthetic harmless checks; never run the destructive full CI suite against the live camp.
- If readiness fails, restore previous release/images and rerun Compose with `--no-build`. Record failure and rollback; do not announce success from a successful image build alone.

## External primary references

- W3C MediaStream Image Capture: https://www.w3.org/TR/image-capture/ — camera controls are capability-dependent, not universally available.
- MDN `getCapabilities` / `applyConstraints`: https://developer.mozilla.org/en-US/docs/Web/API/MediaStreamTrack/getCapabilities and https://developer.mozilla.org/en-US/docs/Web/API/MediaStreamTrack/applyConstraints .
- Installed ZXing WASM is 2.2.4; verify APIs against installed types. Upstream docs: https://github.com/Sec-ant/zxing-wasm . Do not infer installed options from a newer major version.
- MSG91 Send SMS: https://docs.msg91.com/sms/send-sms and response contract https://api.msg91.com/apidoc/textsms/send-sms-flow.php . Provider acceptance is distinct from carrier delivery.

## Detailed evidence appendices and remaining work packages

The full independent source reviews are part of this specification: [backend](production-experience/review-backend.md), [UI and workflows](production-experience/review-ux-workflows.md), and [scanner/registration](production-experience/review-scanner-registration.md). They contain 11 backend, 14 UX and 10 scanner findings (overlapping findings are intentionally consolidated into R1–R11). Their role/workflow matrices and negative test scenarios remain acceptance inputs.

The following concrete subrequirements must also receive an explicit completion decision:

- **R12 admin and accessibility:** distinguish loading from empty staff/camps/metrics, freeze mutation controls during save, correct stale PIN badges, accessible names for search/delete/reorder/upload, accurate export success/error colour, and focused bilingual patient instructions. Sources: UX-04,07,09–12. Root owns shared group semantics/loading status; frontend owner handles page/template controls.
- **R13 session resilience:** distinguish authentication-service failure from expired login; provide retry; recover expired sessions without automatically replaying an uncertain write; add render/lazy-load fallback. Sources: UX-13. Do not retain a previous operator's clinical draft for submission under a different identity.
- **R14 scanner lifecycle:** pause/stop when hidden and resume only safely; update torch state only on successful constraints; bound stuck native/still work without building unbounded replacement workers. Validate age zero consistently. Sources: S5,S6,S10.
- **R15 interrupted issue recovery:** an issue authorization may survive when the originating browser loses its operation ID, and an OT seat consumed before the issue/slip write can leak on process death. Reuse server operation identity and operation-bound seat reservation/release, or expose a safe reconciliation path. Do not add a lease that blindly expires a potentially committed clinical mutation. Source: B03. This is a correctness risk, not measured production corruption.
- **R16 schedule and setup consistency:** reject an in-use schedule's incompatible venue/window changes until an explicit reschedule/notification workflow exists; reject mismatched setup-ID reuse and recover unique-key races; reject reducing a booked day below booked count. Camp activation and check-then-delete races need a tested tombstone/serialization design before any claim of atomic administration. Source: B07,B09.
- **R17 export and readiness:** avoid truncating related fulfilment records; bound export working memory or document measured camp-size ceiling; healthcheck should use existing readiness when database readiness is required. Off-machine backup and restore validation are operational prerequisites. Source: B08,B10.

These items are not automatically completed by changing one shared component. The final implementation ledger must list unimplemented or externally blocked work plainly.

## Completion ledger

Each requirement receives one of: implemented + test evidence; external validation outstanding; explicitly deferred + concrete reason. Blank or planned is not done.

Verification available in this environment: backend 536 passed / 141 skipped, mypy and flake8 clean; frontend 35 suites / 355 tests, tsc, eslint and the build-budget gate clean. Docker was NOT available, so the 141 live HTTP and MongoDB tests skipped locally and run only in CI. No claim below rests on a skipped test.

| Requirement | Status |
|---|---|
| R1 manual gate | Implemented. Assisted manual entry is hidden until three terminal camera failures (a stall or a camera error, not a frame inside one attempt) and then requires a reason. The door also requires the admin gate. `/register` rejects an unscanned staff body below that threshold or without a reason, and a door body while the gate is shut. The client-supplied count is workflow evidence, not proof a camera was used. |
| R2 scanner recovery | Implemented. Stall recovery gates on an accepted Aadhaar card rather than any detected barcode, and an attempt counter retires late detect and decode results. Real-phone success rate remains unmeasured. |
| R3 server identity | Implemented. Assisted registration derives identity from a server-side decode; XML parsing requires a `PrintLetterBarcodeData` root, a 4 or 12 digit uid and a possible age, and the regex attribute fallback is deleted. `Desk.js` threads the payload to both call sites. ADR 0043 records that nothing here verifies a UIDAI signature. |
| R4 desk recovery | Implemented for the three named gaps. Ambiguous matches are buttons that confirm one registration. A walk-in keeps one registration request id and retries arrival after the registration succeeds. Scan confirm rejects another camp. A same-camp id that is not a hit for this card is not arrived: a person already in the camp is reported as a duplicate, and any other non-hit is reverted and answered `STALE_CANDIDATE`. |
| R5 concurrency / dirty drafts | Implemented. Draft writes are one conditional update; a stale write gets 409 `draft_version_conflict`; the clinical page echoes the version, preserves typed input on conflict and confirms before discarding dirty work. `expected_draft_version` is optional: a client that sends none keeps last-writer-wins rather than being locked out, and every accepted save still increments the version. |
| R6 mutation recovery | Implemented. Correction retries from the revision already stored for that operation id and does not increment generation twice. Undo stores the predecessor before clearing the completion and finishes the same operation on retry. A different payload for the same operation id conflicts. |
| R7 loading / errors | Implemented for the named screens. Public registration shows loading, a retryable failure, or no active camp, and does not say there is no camp while the request is pending. Clinical reference failures name the capability, offer retry, and do not present a failed catalogue as an empty one. |
| R8 printing / app resilience | Implemented. Optional sponsor logos no longer block the prescription; loading and error scaffolds are excluded from print; one error boundary offers a deliberate retry. Physical print quality remains an operator check. |
| R9 reporting work | Implemented. Leaderboard database calls go from 123 to 6 and stay flat at 3, 50 and 200 volunteers. Query count only: no elapsed time was measured, and the real-Mongo index plan is unverified without Docker. |
| R10 SMS outcomes / throughput | Implemented for the budget. Provider attempts, including known failures, consume the send limit; skipped rows (no phone, already sent, already pending) do not, so a later recipient is still reached. A known failure is retried on a later run and abandoned after three attempts. Uncertain acceptance is not auto-resent. NOT implemented: a durable outbox for clinical SMS that was only queued in process memory. |
| R11 deployment | Blocked. Deployment needs authenticated VPS access; the documented SSH key is on the owner's Windows machine and no key or agent is present in this environment. Nothing was deployed. |
| R12-R17 | Not started. |
| Visual, phone, printer, carrier and target-host load acceptance | External validation outstanding. None of it can be performed in this environment. |

### Defects found while implementing

- Six fulfilment tests passed only by wall-clock luck. `routes_clinical` binds `now_ist` through a direct import, so patching `helpers.now_ist` never reached it, and the tests began failing once real time passed their hardcoded 2026-09-20 fixture day. Both `_mock` helpers now freeze `routes_clinical.now_ist`.
- Enforcing `expected_draft_version` with a default of 0 locked a lone operator out of completing a prescription: the draft version had already advanced past 0, so completion answered 409. Reproduced, then fixed by making the claim opt-in. Regression tests cover it.
- Making that field optional initially disabled the `locked` and clinical-write-token guards, because they sat inside the version branch. Two existing safety tests caught it; the guards now apply to every client draft write.
