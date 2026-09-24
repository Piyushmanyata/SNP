# Production audit — 5 September 2026

## Release scope

The deployment target is a single Hostinger KVM running the React frontend, FastAPI backend and MongoDB through Docker Compose. This audit prepares the application for local acceptance testing and subsequent deployment. No Hostinger machine or real domain was supplied, so the audit does not claim a live production deployment.

Existing working-tree changes were preserved. The retired Next.js/Supabase application was not restored. Emergent runtime and cron files, the scanner demo path, duplicate account-switch UI and unused refresh-token issuance were removed.

## User workflows

| Area | Result | Automated evidence |
| --- | --- | --- |
| Authentication | Name/PIN login, mandatory first change, manual PIN reset beside Logout, session revocation, shared concurrent attempt limits | `backend/tests/test_auth_pin.py`, `test_production_backend.py`; `Layout.test.js`, `ui.test.js` |
| Team and analytics | Team Management and Analytics together in overview; no duplicate header links; team-lead delegation preserved | `backend/tests/test_team_delegation.py`, `test_board.py`; `AdminDashboard.test.js`, `Team.test.js`, `Board.test.js` |
| Registration and arrival | Aadhaar decode, manual desk fallback, idempotent registration, matching/conflict review, arrival and print gates | `backend/tests/backend_test.py`, `test_desk_scan_first.py`, `test_camp_lifecycle.py`; `Desk.test.js`, `SelfRegister.test.js` |
| Clinical care | Four self-selected lines; transcribe and fulfil at one desk; autofocus, stale-result protection, unsaved-change handling | `Clinical.test.js`, `FulfilmentStation.test.js`, `CorrectionModal.test.js`; `test_operator_line.py` |
| Corrections and capacity | Audited changes include surgery eye and notes; conflicting writes cannot silently overwrite; failed bookings release capacity and restore slips | `test_fulfilment_invariants.py`, `test_ot_expiry.py`, `test_production_backend.py` |
| Hospital surgery | Camp schedules surgery at the hospital only; past dates and camp-issued OT outcomes rejected | `test_ot_expiry.py`, `test_production_backend.py` |
| Spectacles | Fixed-power and made-to-order outcomes remain mutually exclusive; collection windows and rescheduling supported | `test_specs_windows.py`, `test_camp_lifecycle.py`; `FulfilmentStation.test.js` |
| Printing | Short A6 tokens; hospital phone and required-document reminder; prescription asset/snapshot checks | `PrintSlip.test.js`, `PrintPrescription.test.js` |
| SMS and reminders | Revised Hindi copy, per-patient ledger, response-before-provider scheduling, retrying daily worker | `test_reminders.py`, `test_reminder_worker.py`, `test_production_backend.py` |
| Static deployment | SPA deep links, immutable hashed assets, uncached API errors/successes, preserved security headers and distinct client limits | `backend/tests/test_deployment_http.py` |

Paths without a directory in the table refer to adjacent backend tests or frontend tests under `frontend/src/`. These are HTTP integration and component tests, not browser-driven end-to-end tests. Repository instructions prohibit browser/manual UI automation.

## Performance changes

- Patient history for 20 visits now needs 3 database queries instead of 41. Relevant lookup, reminder and correction indexes were added.
- Bcrypt runs off the async event loop. Concurrent wrong PINs reserve their shared attempt budget before doing expensive hashing.
- SMS provider latency no longer delays registration/token HTTP responses. Delivery remains best effort with the ledger limitations below.
- Routes load on demand. The final initial JavaScript bundle is 251.74 kB, about 85.6 kB gzip; CSS is 25.31 kB, 5.29 kB gzip. Scanner and clinical/admin screens are separate chunks.
- Vite/Jest replace the legacy CRA toolchain, removing a net 424 packages. nginx serves the compiled frontend; no Node development server runs in the deployed image.
- The interface uses system fonts. Removing the external Google Fonts stylesheet removes a render-blocking third-party request and three downloadable font families from the critical path; the page no longer depends on that font service.
- Hashed static assets use immutable caching; HTML is revalidated, API responses use `no-store`, and compressible assets use gzip. Caddy additionally supports zstd at the public edge.
- On the deterministic scanner timing fixture, expensive full-resolution still captures fell from 4 to 0 in the first second, with all 9 preview attempts preserved. One still is allowed by four seconds. This measures scheduling, not scan success on physical phones.

### Local HTTP baseline

Windows host → Docker nginx → FastAPI → MongoDB, 100 measured requests per case after 8 warmups, no browser and no external network. The initial active camp had one registration. All 400 measured requests succeeded.

| Endpoint | Concurrent requests | p50 | p95 |
| --- | ---: | ---: | ---: |
| `/api/kpis` | 1 | 5.87 ms | 7.69 ms |
| `/api/kpis` | 8 | 20.13 ms | 22.33 ms |
| `/api/board` | 1 | 7.33 ms | 9.15 ms |
| `/api/board` | 8 | 35.65 ms | 46.57 ms |

The larger synthetic camp contained 10,000 patients/persons, 5,000 transcriptions, 8,000 fulfilments, 1,750 deferred slips, 20 volunteers and 100 failed-SMS fixtures. Before the Analytics optimization, KPIs measured p50/p95 16.57/18.16 ms at concurrency 1 and 33.01/46.70 ms at concurrency 8. Analytics measured 200.94/239.79 ms and 2,032.52/2,536.07 ms respectively. All 400 requests completed successfully. Profiling found that each Analytics request materialized 21,000 complete documents, about 9.48 MB BSON, to compute summaries.

The same 400-request benchmark after the aggregation change completed with zero errors, and HTTP results matched the dataset's stage totals, fulfilments, 100 SMS failures and 20 volunteers:

| Endpoint | Concurrent requests | Before p95 | After p95 |
| --- | ---: | ---: | ---: |
| `/api/kpis` | 8 | 46.70 ms | 42.53 ms |
| `/api/board` | 1 | 239.79 ms | 74.69 ms |
| `/api/board` | 8 | 2,536.07 ms | 181.86 ms |

Analytics p95 fell 92.8% at concurrency 8, approximately 14 times faster, with throughput rising from 3.85 to 49.14 requests/second. Aggregation avoids full document materialization and removes the previous 20,000-patient summary cap. No response cache was added. These benchmarks do not establish capacity for a purchased KVM, internet latency or simultaneous write-heavy camp traffic.

## Deployment decision

Context: both app layers must run on the same KVM and the same stack must be testable locally. A separate hosted frontend and Emergent cron would add deployment dependencies and cross-origin configuration.

Decision: use one Compose stack: Caddy for public HTTPS, nginx for static assets and `/api`, internal FastAPI and authenticated MongoDB, a stdlib reminder worker, and compressed MongoDB backups. Production publishes only 80/443. Development/watch services and source mounts are absent from both normal local and production stacks. [Docker production guidance](https://docs.docker.com/compose/how-tos/production/) and [Caddy automatic HTTPS](https://caddyserver.com/docs/automatic-https) describe the platform behavior.

Consequence: the operator manages the KVM, DNS, secret environment file, disk space and off-machine backup copies. Local Docker defaults are intentionally separate from required production secrets. Only trusted internal proxies can reach the backend: Caddy sanitizes forwarded client headers, nginx retains the chain, and Uvicorn consumes it for per-client limits. Do not publish the backend port or put an unconfigured proxy in front of Caddy.

Build-tool decision: replace CRA with Vite and an explicit Jest/Babel/ESLint setup instead of retaining `react-scripts` and its larger dependency graph. This removes a net 424 packages while preserving `.js` JSX, existing environment variables, the `build/` output directory and imported-image snapshot filenames. The consequence is a small visible build/test configuration that the project owns. Node 24 is the documented runtime; production serves only static output.

The production configuration was started with an isolated database and synthetic secrets: MongoDB, backend, frontend, reminders and backup services started successfully. Both Caddy configurations validated. No public TLS certificate was requested. A compressed authenticated database dump was restored to an isolated namespace, including indexes, with one bootstrap account restored and zero failures; this is a recovery smoke test, not a large-database recovery-time measurement. The scheduled backup also produced an archive. Failed dumps remove their partial file and preserve previous successful archives.

## Adversarial reviews

Two independent review agents ran in parallel for correctness and simplicity. Confirmed findings were fixed:

1. A stale OT picker could book a date that became past at midnight, including a patient with an existing seat. Booking now rechecks IST date and the picker excludes expired days.
2. An operator correcting an already fulfilled prescription could not change all clinical fields. Corrections now reuse the complete prescription form, submit only changed values and require an audit reason.
3. Proxy forwarding could merge public users into one rate-limit bucket. The trusted proxy chain now preserves distinct client addresses; live HTTP tests exhaust one bucket and verify another remains available.
4. Failed backups could leave accumulating partial archives. Failure cleanup now removes the incomplete archive.
5. Refresh tokens had no usable refresh flow. Unused generation/issuance was removed, and logout still clears old cookies.

An additional parallel correctness/simplicity review covered the final Analytics optimization. Correctness returned no findings. Simplicity identified the earliest-date query's unsorted 200-row limit, the misleading OT-done display and duplicate font utilities. Date lookups now use sorted single-document queries and require complete spectacles windows; a regression verifies the earliest date beyond 200 later records. The OT-done display and duplicate styles are removed. The backend retains its uniform fulfilment-count response shape while the UI shows only scheduled hospital surgery. The small date-query correction followed the recorded benchmark; the final full suite includes it.

## Remaining acceptance checks and operational limits

- Test the real older phones with physical Aadhaar cards, glare, movement and low light. Camera permission, browser support and focus differ by handset. The scanner's parsing is not UIDAI signature authentication; see [Aadhaar decode contract](../../backend/docs/aadhaar-decode.md).
- Print a real token at A6, 100% scale, without browser headers/footers, and verify the complete Hindi text fits the printer's margins. Automated layout checks do not prove paper output.
- Configure the MSG91 account and approved DLT templates, then verify actual carrier delivery. Surgery texts include आधार कार्ड, राशन कार्ड और मोबाइल नंबर. A missing provider configuration intentionally skips delivery and causes the reminder worker to retry; it does not imply that SMS was sent.
- Ordinary concurrency and injected persistence failures are tested. MongoDB uses conditional writes and compensation, not multi-document transactions. Abrupt process loss during a clinical mutation can still require reconciliation of the fulfilment, active slip and OT occupancy. See [clinical production contract](../../backend/docs/production-clinical-contract.md). Pending provider deliveries can also be uncertain after interruption and must not be blindly resent.
- Run the documented deployment on the purchased KVM, confirm real HTTPS, restart recovery, off-machine backups and representative simultaneous staff traffic before entering patient data.

## Earlier verification baseline

The earlier review passed 531 automated tests: **356 backend tests**, including live HTTP/MongoDB workflows against the then-current rebuilt images, and **175 frontend tests across 25 suites**, including the prescription snapshot. No backend tests were skipped in that full live run. Anonymous HTTP clients are isolated per test so prior login cookies cannot invalidate unauthorized-access checks.

Frontend lint, backend Flake8 `F,E9`, Python compilation, `git diff --check` and the production frontend build pass. Both Docker images build and all three normal app containers become healthy. Application dependency audits report zero known vulnerabilities for both the complete npm lockfile and Python runtime requirements as of the audit date; container operating-system vulnerability scanning is outside that result.

The isolated `snp-audit` and `snp-production-check` projects and their generated data volumes were removed after verification. The normal local Compose stack is running on `http://localhost:3000`; its health endpoint and bootstrap login both returned HTTP 200, and the admin account requires choosing a new PIN at first sign-in. Existing normal-project volumes were retained.

JavaScript has no separate static typechecker configured; compilation/build success is not a claim of static type coverage. The backend run retains 24 non-failing warnings from upstream TestClient deprecations and short test-only JWT keys; production examples require independently generated long secrets. React Router's ignored `use client` build directives and intentional scanner-worker failure-test logging are also non-failing. Physical-device, printer, carrier and KVM acceptance checks remain as listed above.

## Final deep review follow-up

This follow-up reviews the active React/FastAPI application, its tests and deployment configuration. It preserves the retired status of the root Next.js/Supabase application. The user confirmed local records are test data. Regression tests exercise confirmed failures before their fixes; live integration and network recovery use the disposable `snp-final-review` project on port 3101.

| Area | Confirmed failure and correction | Evidence |
| --- | --- | --- |
| Registration | Missing request IDs collided under a sparse unique index; concurrent identity creation could fail; replay keys could return unrelated registrations; public duplicate errors exposed stored patient records | `backend/tests/test_registration_staff_production.py`; [registration contract](../../backend/docs/production-registration-security.md) |
| Staff and camp setup | Concurrent duplicate staff creation returned a server error; disable/enable revived old sessions; malformed calendar dates reached stored camp configuration | Same regression file and registration contract |
| Clinical writes | Operations were not bound to patient/content, explicit correction clears were ignored, and delayed drafts could overwrite completed care; each write is now one transaction (ADR 0065) | `backend/tests/test_clinical_operation_safety.py`; [clinical operation contract](../../backend/docs/clinical-operation-safety.md) |
| Patient and session UI | Stale scans/history and print-route transitions mixed patient state; failed logout appeared successful while its cookie survived | `Desk.test.js`, `Clinical.test.js`, `PrintPrescription.test.js`, `AuthContext.test.js`; [patient/session contract](patient-session-safety.md) |
| Printing and templates | Failed print stamps silently opened printing; camp switches retained another camp's editable logos and stale uploads | `PrintPrescription.test.js`, `TemplateEditor.test.js`; patient/session contract |
| Scanner recovery | Fatal worker startup/runtime failures left an unusable cached worker; subsequent scans now create a new worker | `wasmDetector.test.js`; patient/session contract |
| Template input | Malformed logo list/data types raised server errors or erased logos; invalid base64 was silently accepted. The existing validator now rejects these with HTTP 400 and uses strict stdlib base64 decoding | `backend/tests/test_template_validation.py` |
| Container replacement | nginx retained an obsolete backend address indefinitely; the shared upstream now refreshes Docker DNS | Live failing-then-passing `frontend/scripts/verify-proxy-recovery.py`; [proxy recovery decision](proxy-recovery.md) |

Two new independent adversarial reviews ran in parallel. Simplicity returned no findings. Correctness reproduced three additional failures: replaying an older fulfilment could overwrite a newer result, a replay after a post-save failure could leave issue authorization stuck, and a delayed print-stamp response could print a different page after navigation. All were fixed with failing-then-passing regressions. A follow-up found a paused original request could retain an obsolete pending-operation snapshot after its retry and a newer update completed. The final path refreshes the ledger and fulfilment under acquired ownership, and the exact interleaving is now tested. Independent follow-up reviews confirmed these fixes, including a separate run of the final race regression; no findings remain from those reviews.

### Final verification

**683 automated tests pass: 474 backend tests and 209 frontend tests across 26 suites, plus the existing passing prescription snapshot.** The full backend suite ran under Python 3.12 against the rebuilt nginx/FastAPI images and a fresh real MongoDB database, with zero skips and 24 non-failing upstream/test-secret warnings. Hashes of both final clinical source files inside the backend image matched the workspace. One older integration assertion was updated to require that the anonymous duplicate response omit the patient record; its authenticated assertions still verify that the stored identity was not overwritten.

Frontend ESLint, backend fatal-error Flake8, Python 3.12 compilation, `git diff --check`, Vite production build, Docker builds, nginx configuration validation and production Compose configuration validation pass. The initial JavaScript bundle is 251.54 kB (85.52 kB gzip); CSS is 26.14 kB (5.37 kB gzip). The complete npm dependency audit and Python runtime requirements audit each report zero known vulnerabilities on 5 September 2026. The Python audit ran in an isolated Python 3.12 container. There is still no separately configured JavaScript/TypeScript static typecheck; compilation is not a claim of static type coverage.

The Docker address-change regression failed before the nginx change and passed afterward without restarting the frontend, including a repeat against the final image. The normal local Compose stack was rebuilt, all three services are healthy, and its proxied health endpoint returns `{"status":"ok"}`. The disposable test container, stack, network and database volume were removed. No public production deployment or real certificate issuance is claimed. The physical phone/scanner, A6 printer, SMS provider/carrier, purchased KVM and off-machine restore acceptance checks above remain necessary. Multi-document interruptions before durable fulfilment storage retain the explicit reconciliation limit in the clinical operation contract.
