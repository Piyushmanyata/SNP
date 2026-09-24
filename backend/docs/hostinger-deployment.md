# Hostinger deployment — 22 September 2026

## Deployment record

- Application domain: `sikarkolkata.io`.
- VPS: `82.112.234.39`, Ubuntu 24.04.4 LTS, 2 CPUs, 8 GB RAM.
- Runtime: Docker Engine 29.8.0 and Docker Compose 5.5.1.
- Application release: `c363debd62b33e5dca86b33e5984d6968431cb05` (SMS cost guard and phone UI, 23 September 2026).
- Release directory: `/opt/snp/releases/c363debd62b33e5dca86b33e5984d6968431cb05`.
- Previous releases kept for rollback: `a2a4415c3247b34753bf93fbd5337352b1019e49`, `a889edb77b887fa12d084b114f910c7b8b7e3c69`, `f2e4592f0dcee138f77c4630964ba92dfb37e664`, `68c978b860edaf9db0dc093740a2228f8ca45ec6`, `730112cb5a122f99b592cce50bb8faf082b3eece`, `13854767e93b1f95bda958680ef27aff387bd36e`, `6f5ab0cb4bd7e58bbf1aacefbaf54db97ff0f3e7`, `ac60bdfe2ecb13555ae449a7d299229ca8758afd`, `7eaed607ba0946c04dd32a405920a49db5e96fe7`, `a5acdcdb2398b9af8bce14b2fcacf6f2ff2228d6`, `9ccb9d888f128277cefa790854c71f8cf7d4c72e`, `51a2a0382c20ce07f3cd4829d5e3c0c4803920e1`.
- Current release link: `/opt/snp/current`.
- Production Compose project: `snp`.
- Production environment: `/opt/snp/.env.production`, readable only by root.
- Certificate contact: `iipiyushsodhaniii@gmail.com`.

The owner selected a fresh production database. Startup created one admin account; no camps or patient records were imported. Production uses newly generated independent secrets and an initial PIN requiring replacement at first login. The initial credentials are in `/opt/snp/initial-admin.txt`; a private copy is on the operator's computer at `C:\Users\piyus\.ssh\snp-initial-admin.txt`. Do not commit either credentials file.

The existing production Compose architecture is unchanged. MongoDB, the API, frontend, Caddy, reminder worker, and local backup service are running. Authoritative and public DNS now return `82.112.234.39`. Caddy obtained a valid Let's Encrypt certificate for `sikarkolkata.io`; the homepage returns HTTP 200, `/api/health` returns `{"status":"ok"}`, and HTTP redirects to HTTPS with status 308. These endpoint checks used an explicit address override while local and VPS recursive resolvers still cached the earlier missing-domain result; certificate and hostname verification remained enabled. The `www` CNAME points to the apex. Caddy issues a certificate for `www.sikarkolkata.io` and redirects it to `https://sikarkolkata.io`.

## Reviewed Aadhaar transcription release

The 8 September 2026 release adds `/api/aadhaar/extract`. The backend image now installs `tesseract-ocr` with the `eng` and `hin` language data, and the build fails if either language is missing. Deployed images for the previous release are retained as `snp-backend:rollback-<sha>`, `snp-frontend:rollback-<sha>` and `snp-reminders:rollback-<sha>`, so a rollback is a retag and `up -d --no-build`.

Post-deployment checks against the live host: `/api/health` returned `{"status":"ok"}`, the homepage returned 200, HTTP redirected with 308, and `/api/aadhaar/extract` rejected a non-document with 415. A generated QR image returned `outcome: card` with only the last four digits, and a text-only image returned `outcome: review`, which confirms Tesseract runs in the deployed container rather than reporting `OCR_UNAVAILABLE`. These probes used synthetic data; no real Aadhaar document was uploaded.

No database migration was required. `server.py` calls `init_indexes()` on startup, and this release adds no stored field or index.

## Manual-entry recovery release

The second 8 September 2026 release ([PR 25](https://github.com/Piyushmanyata/SNP/pull/25)) removes `AadhaarScanner`'s own manual-entry control, gates the public page's control on a failed read, and derives age from a transcribed date of birth. See [ADR 0003](camp-operations/adr/0003-manual-entry-as-a-recovery-route.md) and [ADR 0004](camp-operations/adr/0004-age-derived-from-date-of-birth.md).

The running `a5acdcd` images had no rollback tags — the previous deployment did not create them — so `snp-backend`, `snp-frontend` and `snp-reminders` were tagged `rollback-a5acdcdb2398b9af8bce14b2fcacf6f2ff2228d6` before rebuilding. Retag those to `:latest` and run `up -d --no-build` to roll back. Release directories are unpacked from `git archive` of the merge commit; they contain no `.git`.

No database migration was required. This release adds no stored field and no index; `server.py` calls the idempotent `init_indexes()` on startup, and the API container started clean. An on-demand pre-deployment archive, `snp_camps-20260908T115929Z.archive.gz`, was taken by restarting the backup container, which dumps on startup. MongoDB was not recreated, so the data volume stayed attached throughout.

Post-deployment checks against the live host: `/api/health` returned `{"status":"ok"}`, the homepage returned 200, HTTP redirected with 308, and `/api/aadhaar/extract` rejected a non-document with 415. The served frontend bundle contains the new `self-enter-details` control and no longer contains `aadhaar-enter-details`. A generated text-only image returned `outcome: review` carrying `dob: 1975-06-14` with `age: 51`, which confirms both that Tesseract runs in the deployed container and that age derivation reaches production. This probe used synthetic data; no real Aadhaar document was uploaded.

CI run [34223121551](https://github.com/Piyushmanyata/SNP/actions/runs/34223121551) passed every step: 266 frontend tests across 31 suites, 548 backend tests against real HTTP and MongoDB services, lint, dependency audits and the production image build.

## No print after doctor seen release

The 11 September 2026 release ([PR 26](https://github.com/Piyushmanyata/SNP/pull/26)) stops the desk printing a prescription for a patient the doctor has already seen. `_prescription_payload` refuses `queue_status == "seen"` with 409 `ALREADY_SEEN`, covering both the preview and the stamping route, and both desk entry points — the board row and the door scan card — withdraw Print. Clinical undo returns the patient to `arrived` and printing resumes. See [ADR 0031](../../docs/adr/0031-no-print-after-doctor-seen.md).

The running `7eaed60` images again had no rollback tags, so `snp-backend`, `snp-frontend` and `snp-reminders` were tagged `rollback-7eaed607ba0946c04dd32a405920a49db5e96fe7` before rebuilding. Retag those to `:latest` and run `up -d --no-build` to roll back.

No database migration was required. This release adds no stored field and no index; the guard reads `queue_status`, which clinical completion already writes. The pre-deployment archive `snp_camps-20260911T121231Z.archive.gz` was taken by restarting the backup container, which dumps on startup, and sits in the `snp_backups` volume beside the daily archives. MongoDB was not recreated, so the data volume stayed attached throughout.

Post-deployment checks against the live host: `/api/health` returned `{"status":"ok"}`, the homepage returned 200, HTTP redirected with 308, and all six services reported healthy. The deployed backend image carries the `ALREADY_SEEN` guard and the served frontend bundle `static/Desk-K6WqbTAz.js` carries the new `scan-already-seen` control. The API container started clean with no errors in its log. No probe created or altered patient data.

CI run [34597291085](https://github.com/Piyushmanyata/SNP/actions/runs/34597291085) passed every step: 268 frontend tests across 31 suites, 549 backend tests against real HTTP and MongoDB services, lint, dependency audits and the production image build.

The first CI run on this branch failed on eight fulfilment tests the branch does not touch. They hardcoded `2026-09-10` and `2026-09-11` as future booking dates, which `routes_clinical.py` rejects once that date passes, so the suite rotted on the calendar — main was red on 11 September for the same reason, having last gone green on 8 September. Those dates now derive from `now_ist()`. Other test files still hold hardcoded future dates that will rot the same way.

## One-scan door, full-page prescription and short patient code release

The 12 September 2026 release deploys four merged pull requests at once: [PR 27](https://github.com/Piyushmanyata/SNP/pull/27) (QR-only self-registration, a Lock taken once), [PR 28](https://github.com/Piyushmanyata/SNP/pull/28) (the door is one scan and a print, manual entry admin-gated), [PR 29](https://github.com/Piyushmanyata/SNP/pull/29) (the prescription fills the page) and [PR 31](https://github.com/Piyushmanyata/SNP/pull/31) (the short patient code). See ADRs [0033](../../docs/adr/0033-a-lock-is-the-identity-evidence-taken-once.md), [0034](../../docs/adr/0034-the-door-is-one-scan-and-a-print.md), [0035](../../docs/adr/0035-manual-entry-at-the-door-is-admin-gated.md), [0036](../../docs/adr/0036-the-prescription-fills-the-page.md) and [0037](../../docs/adr/0037-the-patient-code-is-short-and-alphanumeric.md).

The running `ac60bdf` images had no rollback tags, so `snp-backend`, `snp-frontend` and `snp-reminders` were tagged `rollback-ac60bdfe2ecb13555ae449a7d299229ca8758afd` before rebuilding. Retag those to `:latest` and run `up -d --no-build` to roll back — but see the database note below before doing so.

**The production database was dropped as part of this release, at the owner's instruction.** It held test data only: 8 patients, 7 persons, 2 camps, 3 camp days, 3 OT schedule days, 2 specs collection days, 11 clinical operations, 5 fulfilments, 6 prescription revisions, 4 transcriptions and 3 user accounts. The drop was required, not cosmetic: ADR 0037 changes `patient_qr` from a lowercase UUID to an uppercase 8-character code, and `parse_patient_identifier` uppercases every identifier, so every code stored before this release had already stopped resolving. A pre-wipe archive, `snp_camps-20260912T040119Z.archive.gz`, was taken by restarting the backup container and copied to `/opt/snp/backup-export/` and to the operator's computer. **A rollback to any earlier release must restore that archive as well**, or the old code will run against an empty database.

The database was dropped with `db.dropDatabase()` through `mongosh`, never with `down -v`; the `mongo_data` volume stayed attached throughout. `seed_admin()` then recreated the single `admin` account on backend startup. That account's PIN comes from `ADMIN_BOOTSTRAP_PIN` in `/opt/snp/.env.production` rather than being generated, so `/opt/snp/initial-admin.txt` and its private copy at `C:\Users\piyus\.ssh\snp-initial-admin.txt` remain correct and were not rewritten — their 8 September timestamp is expected, not stale. The account is again marked `must_change_pin`.

No migration script was needed. `server.py` calls the idempotent `init_indexes()` on startup, which rebuilt every index against the empty database, the unique `patient_qr` index included.

Post-deployment checks against the live host: `/api/health` returned `{"status":"ok"}`, the homepage returned 200, HTTP redirected with 308, and `https://www.sikarkolkata.io/` returned 301 to the apex under a valid certificate for `CN = www.sikarkolkata.io` (valid to 10 December 2026) — the first live confirmation of the `www` block added to the `Caddyfile` in `a7cdb38`. All six services reported healthy. An admin login returned 200 with `must_change_pin: true`, confirming the bootstrap account works. The served `Desk-glgWCkf3.js` carries `desk-find-input`, `door-manual-form` and `door-scan-status` and no longer carries `desk-lookup-input`, `wedge-panel` or `checkin-print-button`; `PrintPrescription-CtKaq14M.js` carries the `SNP:` QR prefix and `rx-sponsor-strip`. No probe created patient data.

CI passed on all four pull requests before merge. On `main` at the deployed commit: 281 frontend tests across 31 suites, 110 pure backend tests, ESLint, the Vite production build and Flake8 all pass.

Two adversarial reviews ran against the change set. Correctness found that a scanned patient code left the camera stream and torch running, because the live scan engine only tears the camera down for a result whose `outcome` is `card`; and that the desk lookup and name search had no request sequencing, so a slow lookup could place a stale patient above a newer search and print the wrong prescription. Both were fixed before merge and both have regression tests that were verified to fail against the pre-fix code. Simplicity removed a `patient_qr` collision retry, the dead `new_uuid` helper, and class-name assertions duplicated by the reference snapshot.

## Reliability and CI audit release

[PR #32](https://github.com/Piyushmanyata/SNP/pull/32) merged after all five checks passed in [CI run 34685321529](https://github.com/Piyushmanyata/SNP/actions/runs/34685321529). The merged commit also passed [main CI run 34685464681](https://github.com/Piyushmanyata/SNP/actions/runs/34685464681). Backend, frontend and reminder images were rebuilt from that exact merge commit, and all six services started successfully under the existing `snp` project.

The pre-deployment database archive is `/opt/snp/backup-export/pre-audit-13854767e93b1f95bda958680ef27aff387bd36e.archive.gz`. A `mongorestore --dryRun` accepted it without importing data. An off-machine copy is stored at `C:\Users\piyus\.ssh\snp-pre-audit-1385476.archive.gz`; both copies have SHA-256 `d8c34e8c662cb4737f83424ce78a638a00aed7423d39f6bb96a271e6a286767f`.

No data migration was required. Startup ran the existing index initializer. Before/after counts and index-name sets were identical across all 18 collections, preserving two patients, one person, one camp and two users. No database reset or volume removal occurred. The prior images retain `rollback-13854767e93b1f95bda958680ef27aff387bd36e` tags. HTTPS homepage returned 200 and `/api/health` returned `{"status":"ok"}`; the deployed clinical module hash matches the release source. The current-release symlink points to the new release.

See `adr-2026-09-ci-reliability.md`, `clinical-audit.md` and `production-registration-security.md` for fixes, verification boundaries and remaining reconciliation requirements.

## Hospital outcomes and Clinical find release

[PR #35](https://github.com/Piyushmanyata/SNP/pull/35) implements [issue #34](https://github.com/Piyushmanyata/SNP/issues/34).

- The Hospital line records IOL surgery (one eye) or Hospital referral, and the station records scheduled or Surgery declined.
- Line rules are enforced on the prescription.
- The Token and prescription share one Bring list; the prescription has an IOL-only bilingual band and a declared A4 page box.
- Every displayed date, SMS date and export date is DD-MM-YYYY.
- Clinical find is scoped to the active camp.
- Pre-registration mode no longer offers Scan at the door.

See ADRs [0038](../../docs/adr/0038-hospital-outcomes-are-explicit-and-iol-is-the-only-surgery.md) and [0039](../../docs/adr/0039-iol-only-band-shared-bring-list-and-a4-page-box.md).

The PR merged after all five checks passed on its head commit in [CI run 35206682594](https://github.com/Piyushmanyata/SNP/actions/runs/35206682594), and the merge commit passed [main CI run 35206934454](https://github.com/Piyushmanyata/SNP/actions/runs/35206934454). Backend, frontend and reminder images were rebuilt from merge commit `730112c`, and all six services reported healthy under the existing `snp` project.

The pre-deployment database archive is `/opt/snp/backup-export/pre-hospital-outcomes-730112cb5a122f99b592cce50bb8faf082b3eece.archive.gz`. `mongorestore --dryRun` accepted it without importing data. An off-machine copy is at `C:\Users\piyus\.ssh\snp-pre-hospital-outcomes-730112c.archive.gz`. Both copies have SHA-256 `954c6576569120376c815de11deb0d78eb5dc1660a51847c7d66dd3ce871d2b6`.

No data migration was run, as the issue specified, because production holds test data only.

- The stored `ot_procedure` field is no longer read, and a revision without `ot_outcome` is refused at the Hospital station.
- Before and after counts and index-name sets were identical across every collection (`before-730112c…json`, `after-730112c…json` in `/opt/snp/backup-export/`).
- No database reset or volume removal occurred.
- The prior images carry `rollback-13854767e93b1f95bda958680ef27aff387bd36e` tags.

Post-deployment checks against the live host:

- `/api/health` returned `{"status":"ok"}`, the homepage returned 200, and HTTP redirected with 308.
- `/api/clinical/search` exists: it returns 401 without a session.
- The deployed `routes_clinical.py`, `clinical_state.py`, `routes_reports.py`, `sms.py` and `helpers.py` hashes match the release source.
- The served bundles carry the new strings: `Clinical-CUOvmLoo.js` has the "Registration number or name" field, `PrintSlip-CqEw_a8Y.js` has "IOL Surgery", and `PrintPrescription-ZqWrJVxv.js` has the `size: A4` page rule.
- The backend log showed no errors.
- No probe created patient data.

Two items remain before the camp:

- One physical print of the prescription on the camp printer, to confirm it fits one A4 sheet.
- Confirmation in the MSG91 console that a DD-MM-YYYY `date` value is accepted.

The SMS copy names ration card, matching the Bring list of ADR 0039. It was aligned before any DLT template was registered, so no re-approval was needed.

## SMS copy and walk-in rules release

The 19 September 2026 release ([PR 36](https://github.com/Piyushmanyata/SNP/pull/36)) changes the surgery SMS copy to राशन कार्ड, removes the hardcoded hospital name from both surgery templates, makes the OT Schedule Day venue admin-typed with an optional short name for SMS, and stops sending the registration SMS to walk-ins while exempting them from the camp-day seat limit. See ADR 0040, 0041 and 0042.

No database migration was required. `venue_sms` on an OT Schedule Day and `collection_venue_sms` on a deferred slip are optional and absent on existing documents, where both fall back to the full venue. `server.py` calls the idempotent `init_indexes()` on startup and this release adds no index.

Images for `730112cb5a122f99b592cce50bb8faf082b3eece` were tagged `snp-backend:rollback-730112cb…`, `snp-frontend:rollback-730112cb…` and `snp-reminders:rollback-730112cb…` before rebuilding. A pre-deployment archive, `snp_camps-20260919T074441Z.archive.gz`, was taken by restarting the backup container. MongoDB was not recreated and its container stayed up throughout, so the data volume never detached.

Post-deployment checks against the live host: all six containers reported healthy, `/api/health` returned `{"status":"ok"}`, the homepage returned 200, and HTTP redirected with 308. The deployed backend container was read directly and returns the new surgery copy, naming राशन कार्ड and carrying no hospital name in its fixed text.

CI run [35429981396](https://github.com/Piyushmanyata/SNP/actions/runs/35429981396) passed every check: backend, frontend, dependencies, workflow and verify.

## Approved DLT SMS copy release

The 22 September 2026 release deploys two merged pull requests together. [PR 39](https://github.com/Piyushmanyata/SNP/pull/39) closes deep-review findings. [PR 40](https://github.com/Piyushmanyata/SNP/pull/40) sends the six SMS in the wording approved for DLT registration. Every message names the camp by an admin-set camp number (`camp_no`). A Specs collection day now runs from `day_date` to `end_date`. Specs hours must run from a morning start to an evening end, and the SMS sends both in 12-hour form. See ADR 0046. The text to register on the DLT portal is `dlt_portal_body` in `backend/docs/msg91-templates.json`.

No database migration was required. `camp_number`, a Specs collection day's `end_date` and a Token's `collection_end_date` are all optional. Documents without an end date read it as the first day. `server.py` calls the idempotent `init_indexes()` on startup, and this release adds no index. At deployment the production data was test data only. The active camp, "SNP test", had no camp number, so it sends no SMS until an admin sets one on the Camps tab. Its one specs day, 13:20–15:20, predates the hours rule. It now shows as needing a window until it is re-saved with morning-to-evening hours. MSG91 remains unconfigured.

Images for `68c978b860edaf9db0dc093740a2228f8ca45ec6` were tagged `snp-backend:rollback-68c978b8…`, `snp-frontend:rollback-68c978b8…` and `snp-reminders:rollback-68c978b8…` before rebuilding. A pre-deployment archive, `snp_camps-20260922T090533Z.archive.gz`, was taken by restarting the backup container. MongoDB was not recreated and its container stayed up throughout, so the data volume never detached.

Post-deployment checks against the live host:

- All six containers reported healthy.
- `/api/health` returned `{"status":"ok"}`, the homepage returned 200, and HTTP redirected with 308.
- The deployed backend container returns the new copy, and it renders 17:00 as 05:00.
- The served `AdminDashboard-D_mxvN3i.js` carries `camp-number-input` and `specs-end-date-input`.
- The backend log showed no errors after the restart.

PR CI run [35708043135](https://github.com/Piyushmanyata/SNP/actions/runs/35708043135) and main CI run [35708357250](https://github.com/Piyushmanyata/SNP/actions/runs/35708357250) passed every check: backend, frontend, dependencies, workflow and verify.

## DLT brand name release

The second 22 September 2026 release deploys [PR 41](https://github.com/Piyushmanyata/SNP/pull/41). SmartPing rejected all six DLT content templates because the entity or brand name was missing from the text. Every message now says "Sikar Zilla Welfare Trust के" where it said "SNP के". See ADR 0047. The six templates were re-submitted on SmartPing with this exact text on header SZWTRT, and approval is pending. MSG91 remains unconfigured.

No database migration was required. This release changes message text only.

Images for `f2e4592f0dcee138f77c4630964ba92dfb37e664` were tagged `snp-backend:rollback-f2e4592f…`, `snp-frontend:rollback-f2e4592f…` and `snp-reminders:rollback-f2e4592f…` before rebuilding. A pre-deployment archive, `snp_camps-20260922T121200Z.archive.gz`, was taken by restarting the backup container. Only backend, frontend and reminders were recreated. MongoDB stayed up throughout.

Post-deployment checks against the live host:

- All six containers reported healthy or running.
- `/api/health` returned `{"status":"ok"}`, the homepage returned 200, and HTTP redirected with 308.
- In the deployed backend, each of the six messages contains "Sikar Zilla Welfare Trust के" once and "SNP के" nowhere.
- The served `AdminDashboard-BBQyw4kq.js` carries the new camp-number hint.
- The backend log showed no errors after the restart.

PR CI run [35725192959](https://github.com/Piyushmanyata/SNP/actions/runs/35725192959) passed every check: backend, frontend, dependencies, workflow and verify.

## Access and operation

The dedicated SSH key is installed. Connect from the operator's computer:

```powershell
ssh -i C:\Users\piyus\.ssh\snp_vps_ed25519 root@82.112.234.39
```

UFW is enabled with inbound TCP 22, 80, and 443 allowed. Database and API ports are not published. Manage the complete production stack from the VPS:

```sh
cd /opt/snp/current
docker compose --env-file /opt/snp/.env.production -p snp -f docker-compose.prod.yml up -d --no-build --wait
docker compose --env-file /opt/snp/.env.production -p snp -f docker-compose.prod.yml ps
curl --fail https://sikarkolkata.io/api/health
```

Keep the explicit `-p snp` project name across releases so the existing database and certificate volumes remain attached. Never use `down -v` for this production project.

## Verification evidence

- Frontend: ESLint with zero warnings passed, 31 Jest suites passed, 289 tests and one snapshot passed, and the Vite production build passed. Initial gzip sizes are 85,589 JavaScript bytes and 5,448 CSS bytes.
- Backend: Python 3.12 compilation and fatal-error Flake8 passed; all 580 tests passed against isolated HTTP/API and MongoDB services with zero skips. The suite emitted 24 non-failing upstream/test-secret warnings; production uses a generated 64-character secret.
- Production Docker builds, Compose configuration validation, `nginx -t`, and Caddy configuration validation passed.
- Correctness and simplicity reviews ran independently; neither found a confirmed deployment blocker.
- Mypy passes all 24 production Python modules. Checked JavaScript passes the six utility modules explicitly listed in `frontend/tsconfig.json`; React component static coverage remains incomplete.
- The isolated verification project and its synthetic database were removed after the checks.

## Data wipe — 22 September 2026

The owner ordered a full wipe of the live test data, including backups. `snp_camps` was dropped with `db.dropDatabase()` through authenticated `mongosh`. The `mongo_data` volume was not removed. Startup recreated the single `admin` account from a newly generated `ADMIN_BOOTSTRAP_PIN`, again with `must_change_pin`. The new PIN is only in `/opt/snp/initial-admin.txt` and `C:\Users\piyus\.ssh\snp-initial-admin.txt`.

Every archive under the `snp_backups` volume and `/opt/snp/backup-export/` was deleted, the unused `snp_snp_backups` volume was removed, and the operator copies `snp-pre-audit-1385476.archive.gz` and `snp-pre-hospital-outcomes-730112c.archive.gz` were deleted. There is no off-box backup destination. The backup container was started again; its next dump is of the empty database. Do not treat any archive named in the sections above as restorable.

## Backups and remaining integrations

The owner requested daily backups. `/opt/snp/.env.production` now sets `BACKUP_INTERVAL_SECONDS=86400`, and the recreated backup container reports that value. The worker creates a compressed archive on startup, then waits 24 hours after each backup; this is not a fixed midnight schedule. It retains 14 days in the `snp_backups` Docker volume. Set this environment override on any replacement server, because the Compose fallback remains hourly.

A post-bootstrap archive, `snp_camps-20260908T072922Z.archive.gz`, was restored into a separate MongoDB instance: one user, zero patients, zero persons, and zero camps. The restore instance was removed afterward. The backup container also completed a new archive after its daily-interval restart. Both archives were deleted in the 22 September wipe above.

An ongoing off-machine backup destination is still required. Archives on the VPS do not protect against loss of that VPS. Follow the root README's backup instructions; `docs/ops/backups.md` refers to a `backup-sync` service and `BACKUP_REMOTE` variable that the current Compose file does not implement.

At the time of this baseline deployment, MSG91 credentials and approved templates had not been configured. Later SMS setup is recorded below. Real phone scanning and printer acceptance remain operator checks.

## SMS template setup — 23 September 2026

At this stage SmartPing had approved the registration, camp reminder, surgery scheduled and surgery reminder content on header `SZWTRT`. Their DLT IDs and the matching MSG91 flow IDs are recorded in [msg91-templates.json](msg91-templates.json). All four flows showed “Verified by DLT” in MSG91. The two spectacles templates were still rejected with the operator remark “Variable can be reduce to static information.” Their later approval is recorded below.

The backend now allows configured message types to send independently ([ADR 0048](adr/0048-enable-only-configured-sms-flows.md)). An `SNPProdSMS` auth key was created with the SMS send rule and IP security limited to the VPS egress address `82.112.234.39`. At this stage, the key and four approved flow IDs were set in `/opt/snp/.env.production`; `MSG91_TEMPLATE_SPECS_TOKEN` and `MSG91_TEMPLATE_SPECS` were empty. The key is not stored in the repository. A consented test message and its provider delivery result are required before live patient messaging.

## Fixed spectacles collection hours — 23 September 2026

[ADR 0049](adr/0049-fixed-spectacles-collection-hours.md) fixes collection at 10:00 AM–5:00 PM. The backend persists `10:00` and `17:00`; staff screens and printed tokens use AM/PM. The revised spectacles SMS copies place those hours in static text, leaving five DLT variables. The two rejected IDs in [msg91-templates.json](msg91-templates.json) describe the old text only. The matching flows were approved and verified later on 23 September, as recorded below.

Before this deployment, production had one future spectacles day (5 October–6 November 2026) at 10:00–15:00 and zero active spectacles slips. After deploying the code, re-save that date range in Admin → OT & Specs to set 10:00–17:00, then verify the listed hours before assigning patients. Other environments must audit their active slips before changing a schedule because printed tokens snapshot the hours.

## SMS cost guard — 23 September 2026

[ADR 0051](adr/0051-one-sms-venue-rule-at-thirty-characters.md) limits every DLT variable to 30 characters and holds every SMS venue to one rule. [ADR 0052](adr/0052-delivery-reports-pause-and-canary.md) reads MSG91 delivery reports, pauses a message type after a DLT failure, and sends one reminder per type before the rest of the batch. Admin → SMS shows each message type, pauses and today's credits, and resumes a paused type.

Delivery reports need one shared secret. `MSG91_WEBHOOK_SECRET` is set in `/opt/snp/.env.production`, which only root can read; read it on the VPS with:

```sh
grep '^MSG91_WEBHOOK_SECRET=' /opt/snp/.env.production | cut -d= -f2-
```

In MSG91, open **SMS → Webhook (New)**, add a webhook for SMS delivery reports with:

- URL: `https://sikarkolkata.io/api/webhooks/msg91`
- Method: POST, JSON body
- Header: `X-SNP-Webhook-Secret` with the value read above

Until the webhook is saved, no reports arrive: each reminder canary waits ten minutes and then releases its batch, and nothing pauses on its own. Admin → SMS warns that delivery reports are off only while the backend has no secret. Once the webhook is saved, the next delivered message shows under Delivered, with its credit.

Before the spectacles flows are configured, open Admin → OT & Specs and give the specs collection day a real SMS venue; the production day still reads `NA`, which the rule refuses.

### Deployment

[PR 47](https://github.com/Piyushmanyata/SNP/pull/47) merged as `c363debd62b33e5dca86b33e5984d6968431cb05` and was deployed from a `git archive` of that commit. CI run [35839859500](https://github.com/Piyushmanyata/SNP/actions/runs/35839859500) passed backend, frontend, dependencies, workflow and verify.

- The running `a2a4415` images were tagged `snp-backend:rollback-a2a4415c…`, `snp-frontend:rollback-a2a4415c…` and `snp-reminders:rollback-a2a4415c…`. Retag them to `:latest`, point `/opt/snp/current` back at `a2a4415`, and run `up -d --no-build` to roll back.
- A pre-deployment archive, `snp_camps-20260923T085922Z.archive.gz`, was taken by restarting the backup container. Only backend, frontend and reminders were rebuilt and recreated; MongoDB stayed up.
- A random `MSG91_WEBHOOK_SECRET` was generated on the VPS and appended to `/opt/snp/.env.production` (mode 600, root). It was not printed or copied off the server. The owner pasted it into MSG91; the `SNPdeliveryreports` webhook (SMS, On Report Received, POST JSON to `/api/webhooks/msg91` with the `X-SNP-Webhook-Secret` header) was created on 23 September 2026. Its Test Run returned 200 `{"ok": true, "recorded": 0}`. The value also appeared once in an operator chat; rotate it by replacing the line in `.env.production`, recreating the backend, and updating the header in MSG91.
- No migration was needed. Startup created the `provider_id_1` and `created_at_1` indexes on `reminder_ledger`.

Post-deployment checks against the live host:

- `/api/health` returned `{"status":"ok"}`, the homepage returned 200, and HTTP redirected with 308. All services reported healthy or running, and the backend log had no errors.
- `/api/webhooks/msg91` refused a missing or wrong secret with 401. With the configured secret it answered `{"ok":true,"recorded":0}` to a probe for an unknown request ID, which changed no data. `/api/sms/status` refused an anonymous request with 401.
- The backend reports the four approved flows set and both spectacles flows empty.
- The reminder worker's restart run completed and submitted nothing: the ledger still holds its 5 earlier rows, and no camp day falls on 24 September.
- The served `AdminDashboard-DT6YFXjq.js` carries the new SMS tab and the live SMS venue check.

## Spectacles SMS approval — 23 September 2026

SmartPing approved the revised `SNP Specs Token` and `SNP Specs Reminder` texts as Promotional on header `SZWTRT`. The DLT IDs are `1777179015421050461` and `1777179015427680603`. Matching Unicode MSG91 flows were created as `6ab3a55711b0c861c10e65e2` and `6ab3a56d4313c436210f3de3`, with variables `camp_no`, `date`, `end_date`, `venue`, and `reg_no` in that order. The exact copies and IDs are in [msg91-templates.json](msg91-templates.json).

Both new flows now show “Verified by DLT” in MSG91. Set `MSG91_TEMPLATE_SPECS_TOKEN` and `MSG91_TEMPLATE_SPECS` in `/opt/snp/.env.production` and recreate the backend and reminders containers after deploying. The 5 October–6 November spectacles day still needs fixed 10:00–17:00 hours and a real SMS venue before patient sends can occur.

## Replica set and database users — issue #50 S1

[ADR 0060](../../docs/adr/0060-replica-set-transactions-and-pymongo-async.md) runs MongoDB as the replica set `rs0` with a key file, gives the API the `snp_app` user and backups the `snp_backup` user, and moves the backend to PyMongo Async. The users are created by `ops/mongo/init-users.js`, which runs only on an empty data directory, so an existing deployment needs a fresh `mongo_data` volume:

1. Take a final archive by restarting the backup container, and copy it to `/opt/snp/archive/`.
2. Append `MONGO_APP_PASSWORD` and `MONGO_BACKUP_PASSWORD` to `/opt/snp/.env.production`, each from `openssl rand -hex 32`.
3. `docker compose --env-file /opt/snp/.env.production -p snp -f docker-compose.prod.yml down` (without `-v`), then `docker volume rm snp_mongo_data`.
4. `up -d --build --wait`. The `mongo` healthcheck initiates `rs0`; startup recreates `admin` from `ADMIN_BOOTSTRAP_PIN` with a forced PIN change.
5. Check that `/api/health/ready` returns `ready: true` and that the backend's user lists only `DB_NAME`.

## Staff sign-in (#50 S4)

[ADR 0025](../../docs/adr/0025-name-and-pin-auth-with-team-lead-delegation.md), as amended, makes Admin and Team Lead PINs 6 digits and removes the shared default PIN. Before deploying:

1. Replace `ADMIN_BOOTSTRAP_PIN` in `/opt/snp/.env.production` with 6 digits that are not one digit repeated or a straight run such as `123456`, and update `/opt/snp/initial-admin.txt` and its private copy. The existing `admin` account keeps its PIN; the new value applies when the database is next wiped. A 4-digit value stops the backend at startup on an empty database.
2. `up -d --build --wait`.
3. Existing Admins and Team Leads keep signing in with 4 digits until they next change their PIN, which then needs 6.
