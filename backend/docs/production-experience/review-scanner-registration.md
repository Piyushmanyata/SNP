# Scanner and registration audit / executor specification input

Reviewed source: `Piyushmanyata/SNP`, main `0e1c9feb8211820f241df0b05e22f55bbba4c91f`.

Scope: `frontend/src/components/AadhaarScanner.js`, `frontend/src/components/aadhaar/**`, registration callers in `Desk.js` and `SelfRegister.js`, `backend/routes_registration.py`, `aadhaar.py`, `aadhaar_extract.py`, `aadhaar_document.py`, related models/tests and relevant ADRs. This is static source review plus a small synthetic decoder probe. No browser, camera, deployment, or real-device performance experiment was performed. Source line references below refer to the reviewed SHA.

## Most urgent confirmed findings

### S1 — Manual registration is available before a single camera attempt (P1, explicit user requirement)

- `Desk.js:618–621`: unconditional `reg-manual-toggle` enters manual identity mode immediately.
- `Desk.js:536–559`: generic `garbage`/`not-aadhaar` outcomes increment `failures`, including USB bursts; `showForm` becomes true at three generic failures. This measures decoder responses, not deliberate camera attempts.
- `Desk.js:611`: `onCaptureStart` resets the counter on every camera retry or source change, preventing a correct cross-attempt gate.
- `Desk.js:612–617`: OCR review sets manual mode immediately regardless of camera history.
- `Desk.js:394–398,418–441`: an admin's `door_manual_entry` camp flag directly exposes the door form and OCR review; this is a separate bypass of the requested camera-attempt policy.
- `RegisterModal` does not itself inspect the authenticated role; surrounding route and `/register` currently restrict staff. Keep server restriction and add an explicit UI capability derived from role so shared/reused components cannot accidentally expose it.

The public SelfRegister page already supplies no `onTranscribed` and has no real manual identity form (`SelfRegister.js:97`; `useAadhaarDecode.js:86–98`). Its shared scanner still says “type the details” after a stall (`AadhaarFallbackPanel.js:23`) and multiple upload errors advise “enter details manually.” These contradict the public flow and must be replaced with context-appropriate copy.

Important distinction: `AadhaarManualInput`/`mode="manual"` are **USB/pasted QR payload**, not editable identity fields. Rename this internal mode to `qr-text` or equivalent to avoid conflating policies; do not make an invalid pasted payload count as a camera attempt. A public phone experience can hide USB/paste, but its removal is not a substitute for server validation.

### S2 — The server can mark client-invented staff data as scanned (P1)

`routes_registration.py:453–468` trusts `body.aadhaar_scanned` and only validates manual age/DOB when it is false. It does not decode `qr_payload`. `Desk.js:188–200,565–577` sends editable fields and a boolean instead of original QR evidence. A direct staff request can bypass manual gating and create an identity “lock.” `RegisterBody` already defines `failed_scan_attempts` and `manual_reason` (`models.py:84–86`), but the endpoint does not use either.

`require_staff` correctly restricts `/register` to admin/team_lead/volunteer (`security.py:99–109`). Preserve this. `/self-register` already server-decodes the QR and overrides submitted identity/flags (`routes_registration.py:490–508`); keep its public no-manual invariant.

Required contract: a claimed scanned staff registration must include `qr_payload`; the server must decode and replace identity fields from that result. Otherwise it is manual and must satisfy the explicit manual policy, be marked manual/recheck-required on the server irrespective of client flags, and validate age/date/name/contact. Preserve request idempotency, deduplication, seat handling and asynchronous SMS. `failed_scan_attempts` is client-reported workflow information; it is not cryptographic proof of camera activity. Do not claim that adding the field makes the browser tamperproof.

### S3 — Arbitrary or broken XML is accepted as a valid Aadhaar card (P1)

`aadhaar.py:159–171` falls back to regex-extracting attributes from malformed XML; `190–207` requires only a nonempty name; `210–217` accepts any string beginning `<`, without checking the document root. These all reach public self-registration's otherwise-correct QR gate.

Observed with the actual decoder in a Python process (synthetic data only):

| Input | Actual result |
| --- | --- |
| `<anything name="Not Aadhaar" />` | `outcome="card"`, no DOB, empty last4 |
| `<PrintLetterBarcodeData name="Not Aadhaar"` | `outcome="card"`, malformed document |
| `<PrintLetterBarcodeData name="Invalid Patient" uid="ABCD" dob="2999-01-01" />` | `outcome="card"`, last4 `ABCD`, negative age |

Require the supported `PrintLetterBarcodeData` root and well-formed document (with only the existing safe bare-ampersand repair if needed). Validate bounded nonempty name, supported gender, valid nonfuture DOB/year/age, and numeric supported UID/last4 format. Cap overall QR text length before XML parse as well as numeric conversion. Keep legitimate case-insensitive attributes, BOM/XML declaration, Unicode names, year-only birth dates and real supported legacy formats. Explicitly update permissive unit fixtures rather than accidentally rejecting known good cards.

RSA signature verification is intentionally absent and documented in `aadhaar.py:1–5`; do not describe structural parsing as UIDAI-authenticated identity. Fix malformed-input acceptance independently of any future signature-verification project.

## Additional confirmed findings and bounded recommendations

### S4 — A non-Aadhaar QR can suppress camera recovery forever (P1)

`liveScanEngine.js:91–97` disables stall detection once `detects > 0`; this counts any detected QR before server acceptance (`:125`). The test at `liveScanEngine.test.js:321` codifies this behavior. One unrelated QR, followed by a camera that cannot read the actual card, never reaches a stall. Invalid detections can also be submitted repeatedly after the 1.5 s payload ignore interval (`:3,130–140`). Three responses are not three attempts.

Replace “no Detect ever” with “no accepted card during this deliberate camera attempt.” A bounded attempt deadline must run independently of successful/missed frame callbacks and be cancellable. Preserve the shorter 2.5 s guidance hint, 1.25 s/8-miss native-to-WASM promotion, one detect in flight, and lock only on a valid card. At the attempt deadline, emit one terminal failure, stop/release the stream, and offer an explicit retry. Stopping manually or backgrounding must not count as failure. An unrelated QR should receive a useful short message and must not remove the eventual retry route.

### S5 — Still capture and native detection can hold the scan loop indefinitely (P2; control-flow gap confirmed, device occurrence unmeasured)

- `useAadhaarCamera.js:91–109`: `ImageCapture.takePhoto()` and image decoding have no timeout; each awaited still blocks the engine's in-flight slot.
- `liveScanEngine.js:110–120`: native detection is awaited without a deadline; promotion and stall checks occur only afterward.
- `cameraHelpers.js:95–113`: `video.play()` is awaited before the 800 ms metadata bound; a never-settling play promise prevents startup recovery.
- WASM requests already have a 4 s watchdog and worker termination/restart (`wasmDetector.js:1,19–27,48–56`), and existing tests cover it. Preserve this working protection.

Add bounded lifecycle-aware timeouts around native/frame acquisition, fail over from native to WASM, and fall back from still to preview. Do not leave abandoned results able to write state; close late bitmaps/stop late streams. Avoid stacking new captures after timeout. Real camera implementations may behave differently, so acceptance includes deferred-promise tests and later physical-phone trials.

### S6 — Camera continues while the page is hidden; torch state can lie (P2)

The hook has stop/unmount cleanup (`useAadhaarCamera.js:55–89`) and session guards for late acquisition (`:165–172`), which are good. There is no page-visibility/pagehide handler. Add a hide/pagehide stop with no automatic failure increment and no surprise automatic restart.

`cameraHelpers.js:129–136` catches torch constraint failure but returns no success flag; the hook then sets the requested torch state regardless. Return applied status or read settings and show honest state; gracefully keep unsupported capabilities absent. Camera-switch and other programmatic restarts remain the same deliberate attempt; they must not increment/reinitialize attempt counts.

### S7 — Dense phone photos often lose the intended still-resolution benefit (P2 improvement, not measured defect)

`useAadhaarCamera.js:94–99` captures full-resolution stills every 3 s but discards them when `canDecodePhoto` rejects dimensions. That helper only permits max side 2560 and <=4,000,000 pixels (`grabFrame.js:37–40`), so a common large phone still will fall back to the preview. This limit is intentional protection against huge browser allocations. Do not simply remove it. Prefer capability-based bounded still dimensions/capture settings or an explicit “take a photo” route that uses the existing bounded server extractor. Evaluate hit rate and latency on actual devices before changing resolution/frequency.

The existing frame work remains on the main thread: `drawImage` + `getImageData` + canvas resizing (`grabFrame.js:59–66,75–81`). A 1600×900 RGBA readback is 5.76 MB; the theoretical 8/s interval is ~46 MB/s for full-frame reads, before ROI alternation/backpressure. This is an allocation estimate, not a device benchmark. Low-risk: reuse same-size canvases instead of resetting width/height each frame, avoid duplicate source frames when supported, and keep the current one-in-flight guard. Higher-risk worker/OffscreenCanvas migration should be driven by field measurements.

### S8 — OCR concurrency/rate limits can block a shared camp network (P2 capacity issue)

`aadhaar_extract.py:56–68` permits 12 attempts per IP per 10 minutes and only one active worker per application process, rejecting concurrent readers immediately with `OCR_BUSY`. All users behind one public IP share the limit; PDF password retries consume attempts. The configured recognition timeout is 30 s (`:14,71`), so worst-case sequential capacity is 2 jobs/min/process before rate limiting. This is a bound, not measured OCR throughput.

Preserve the 12 MB byte limit, 24 MP image/PDF safeguards, process resource limits, disconnect cancellation and password nonretention. Consider separate authenticated per-user quotas plus a small bounded concurrency/queue based on VPS memory/CPU; return retry guidance/Retry-After. Skip OCR when the consumer is QR-only (public registration or staff before the manual gate) so the backend does not spend up to 20 s extracting fields that the UI cannot use. Never raise resource limits blindly.

### S9 — Successful manual-to-card conversion retains identity-recheck flag (P1 workflow defect)

`routes_registration.py:188–198` and `routes_desk.py:179–186` set `aadhaar_scanned=true`, clear manual flags and assign a person, but do not clear `identity_recheck_required`. The print endpoint later rejects `identity_recheck_required` (`routes_desk.py:301–305`). A card scan can therefore update a manual patient and arrive them successfully while print still fails. Existing ADR 0033 describes an admin-only identity check for manual rows; once a row is successfully replaced with card identity, explicitly decide that the QR now fulfills the check and clear the flag atomically with overwrite (consistent with the source-of-identity transition). Test both registration overwrite and door mismatch-confirm paths. Do not clear the flag merely because the browser says “scanned.”

### S10 — Registration form/request details need completion (P2)

- `Desk.js:571`/`:191` use `form.age ? Number(form.age) : null`; numeric zero from a scanned infant becomes null. Use an explicit empty/null check.
- `Desk.js:667` enables Register based only on full name/day/busy; required household phone and age fail only after round-trip. Align with backend validation and show short inline errors, including ages 0 and 130.
- `SelfRegister.js:88–91` renders “No active camp” while initial load is still pending. Use an actual loading state and a retry on failure.
- `SelfRegister.js:151` register-another resets identity/request but retains household phone/day; preserving a family phone may be intentional, but make the state explicit and ensure camera-failure history and prior error are reset for a new patient.
- Door walk-in idempotency must use one request id for the same scanned patient across lost-response retries. The page's shared form/reset code must not generate a new registration request for an unchanged retry. Coordinate this with the page owner.
- Background confirmation is enqueued (`routes_registration.py:471–474`), yet `Desk.js` says “SMS sent.” Change to “Registration saved” with queued/delivery state if available. Do not assert delivery before the gateway confirms it.

## Required manual-fallback state machine

**Single policy:** allow real manual identity only when `assisted && role ∈ {volunteer,team_lead,admin} && failedCameraAttempts >= 3 && !busy && !hasAcceptedCard`. Self-registration always returns false. OCR-reviewed editable identity is the same exception path and must satisfy the same predicate. A camp admin switch cannot bypass the predicate.

Suggested source-of-truth: registration session owns the accumulated count/capability; scanner owns a unique attempt id and emits structured terminal `onCameraAttemptFailed({attemptId, reason})`. De-duplicate ids. A shared pure helper/reducer makes the invariant testable and avoids multiple counters with different meanings.

| State/event | Action / next state | Count change |
| --- | --- | --- |
| New patient, fresh modal open, role/camp change | Idle; clear payload/form/error/old attempt ids | Reset to 0 |
| User presses Scan camera / Retry | Allocate attempt id; Starting → Scanning after stream ready | None |
| Resolution fallback, camera switch, native→WASM promotion, individual missed/invalid QR | Same active attempt | None |
| Permission denied, no camera, camera busy, terminal reader startup failure | Fail this explicit attempt once; stop/idle; show targeted retry | +1, saturate at 3 |
| Ready camera reaches 20 s without accepted Aadhaar card | Fail this attempt once; stop; show progress and Retry | +1, saturate at 3 |
| API/network failure while validating detected QR | Connection error/retry; never manufacture a camera failure from repeated HTTP errors | None |
| Upload, USB/paste, OCR failure/password retry | Independent capture route; no count unlock | None |
| User stops, changes source, closes, component disables, page hides | Cancel current attempt; release resources; invalidate late callbacks | None |
| Third distinct eligible failure in same patient session | Show explicit “Enter details manually”; keep retry/photo/USB options | Count remains 3 |
| Click permitted manual action | Stop/cancel scanning; editable form with unverified identity note | None |
| Accepted card from any source | Identity fields locked; revoke manual gate; save original QR for server | Reset to 0 |
| Successful registration / Register another | Clear identity, attempt ledger, QR and errors; begin fresh session | Reset to 0 |

If stopping a camera at 20 s is too disruptive to the existing live loop, a single failed terminal attempt may pause it and show Retry; it must not continue auto-counting subsequent 20 s periods. The user must explicitly start each new attempt. An error emitted both by hook and engine still counts once. A delayed response from a previous attempt cannot unlock, lock, clear errors, or replace the next patient's state.

Suggested UI copy: “Camera attempt 1 of 3 did not read an Aadhaar QR. Try better light, hold steady, or upload a clear photo.” Permission/no-device errors retain their specific explanation. After three failures staff see “Enter details manually”; the public page sees “Please register at the camp desk.” Do not announce a failure for every camera frame or repeat long messages through live regions.

## Executor work packages / dependencies

1. **Contracts + decoder:** strengthen XML validation with synthetic negative tests; add server-side scanned evidence handling and bounded manual attempt metadata. Coordinate model edits with backend owner. All successful staff QR paths (modal/USB/photo/door walk-in) must now retain/send raw QR evidence.
2. **Shared attempt policy:** implement structured camera events and a session-aware gate, replacing generic decoder-failure counters. Explicitly include role and public context. Gate OCR review as well as the button/form. Update old tests that intentionally count generic failures.
3. **Caller integration:** new registration modal and door/manual route use the same predicate. Update request IDs/infant age/validation/SMS confirmation copy. Preserve household contact when changing capture source. No camp flag bypass; amend the relevant old ADR/spec.
4. **Camera reliability:** useful stall after invalid QR; independent bounded attempt deadline; lifecycle-safe stop/hide/cancel; bounded native/still operations and honest torch status. Preserve current backpressure, native/WASM fallback and camera cleanup.
5. **Identity transition:** server clears recheck only on accepted card replacement; page offers a useful confirmation/print route. Coordinate ambiguous candidate flow and identity-check UI with desk/backend owners.
6. **Performance follow-up:** reduce avoidable canvas resets and QR-only OCR work; keep resource safeguards. Measure real phones and VPS workloads before adopting capture-resolution/worker/concurrency changes beyond these bounds.

## Acceptance coverage (meaningful regressions)

### Component/pure-state tests

- Manual control/form absent for 0,1,2 **completed distinct camera attempts**; visible after exactly 3 for each eligible staff role. A duplicate event id cannot increment twice. No automatic counter increment from frames or retries internal to camera acquisition.
- Manual control/form never present for public, clinical_desk_operator, unauthenticated or unknown roles, including after >3 failures, OCR review, mode switching and forged callback props.
- Upload failures, USB malformed payloads, decode HTTP errors, password retries and pressing Stop cannot unlock manual entry. Repeated invalid QR frames inside one 20 s attempt count at most one terminal failure.
- Closing/reopening, patient change, successful scan, registration completion reset; camera retry and switching lens preserve correct same-session history. Old/stale responses cannot alter current state.
- Gate covers OCR review and door form/admin-switch routes. Successful QR upload still works before 3 failures.
- Permission denial/no device/busy count once per explicit user action and remain recoverable; no silent dead end when no native barcode API or torch exists.
- Camera deadlines fire even when detector/still promise never resolves; cancel/unmount/hidden stop tracks, cancel timers, suppress late callbacks and close late bitmap resources. Native timeout promotes to WASM; still timeout uses preview.
- Invalid QR once followed by blank frames eventually reaches retry; success before deadline locks once and cancels deadline. Preserve engine one-in-flight, 1.25 s promotion, 4 s WASM recovery.
- Age zero sent as 0; empty age sent null; required contact/age validation displayed before registration POST. Same-patient retry uses same idempotency key.

### API/decoder tests

- Public registration rejects typed flags/attempt counts/manual OCR fields without structurally valid QR; valid QR overrides all submitted identity fields.
- `/register`: anonymous 401, clinical role 403, valid staff roles permitted. For unscanned/manual body, counts 0–2 rejected; count 3 permitted and server marks manual/recheck, even when client clears flags. Negative/noninteger/out-of-bound counts rejected as invalid input. Do not label these numbers proof of camera use.
- Claimed scanned staff body without payload or with invalid payload rejected; valid QR overwrites typed fields and manual flags. QR cannot bypass identity validation via arbitrary XML or regex rescue.
- Arbitrary/malformed XML, missing identity essentials, nondigit last4, future/invalid/over-130 DOB, unsupported gender, excessive text and XML entity declarations rejected. Preserve supported legitimate XML/secure-QR fixtures and Unicode cases.
- Manual→QR overwrite clears identity-recheck atomically, retains reg_no, seat/idempotency semantics and allows subsequent valid print; mismatch path uses selected candidate and does not overwrite another camp's patient.
- Existing seat concurrency/duplicate/idempotency/SMS tests stay green; update request fixtures for new evidence and manual contract deliberately.

### Physical-device acceptance (unverified here)

Retain ADR 0003's proposed benchmark: ≥20 scans/device on a low-cost Android (4 GB), midrange Android and iPhone Safari under actual camp lighting; report camera-ready→accepted-card median/p95 and success within 3 s, with **zero false accepted cards**. Separate QR on paper/PVC/screen, distance/glare/orientation, dense secure QR and small patient codes. Record native/WASM support, first vs warmed scan, worker startup, focus/torch/zoom availability and fallback usage. Never claim “95% within 3 seconds” from mocked CI tests. No real Aadhaar payload, image, full number or patient name in telemetry/logs.

## Already good / preserve

Rear-camera preference independent of enumeration order; ideal 1080p continuous focus with graceful lower-resolution constraints; torch/camera switching; ROI/full-frame alternation; native-first then locally hosted QR-only WASM in a worker; one frame in flight and server soft hold; WASM watchdog/restart; ignored duplicate payload window; late-decode request generations, abortable uploads, late camera stream cleanup; bounded local image allocations; QR before OCR, EXIF orientation correction; PDF/HEIC support; max two PDF pages and bounded subprocess resources; no retained upload/password; last-four-only stored identity; public QR-only registration; database deduplication/idempotency and capacity rollback.

The review should improve these existing paths rather than replace the scanner wholesale. Source-level correctness is testable now; physical camera speed and camp-scale latency remain explicit post-deploy evidence to collect.
