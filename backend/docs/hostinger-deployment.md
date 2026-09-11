# Hostinger deployment — 11 September 2026

## Deployment record

- Application domain: `sikarkolkata.io`.
- VPS: `82.112.234.39`, Ubuntu 24.04.4 LTS, 2 CPUs, 8 GB RAM.
- Runtime: Docker Engine 29.8.0 and Docker Compose 5.5.1.
- Application release: `ac60bdfe2ecb13555ae449a7d299229ca8758afd` (no print after doctor seen, 11 September 2026).
- Release directory: `/opt/snp/releases/ac60bdfe2ecb13555ae449a7d299229ca8758afd`.
- Previous releases kept for rollback: `7eaed607ba0946c04dd32a405920a49db5e96fe7`, `a5acdcdb2398b9af8bce14b2fcacf6f2ff2228d6`, `9ccb9d888f128277cefa790854c71f8cf7d4c72e`, `51a2a0382c20ce07f3cd4829d5e3c0c4803920e1`.
- Current release link: `/opt/snp/current`.
- Production Compose project: `snp`.
- Production environment: `/opt/snp/.env.production`, readable only by root.
- Certificate contact: `iipiyushsodhaniii@gmail.com`.

The owner selected a fresh production database. Startup created one admin account; no camps or patient records were imported. Production uses newly generated independent secrets and an initial PIN requiring replacement at first login. The initial credentials are in `/opt/snp/initial-admin.txt`; a private copy is on the operator's computer at `C:\Users\piyus\.ssh\snp-initial-admin.txt`. Do not commit either credentials file.

The existing production Compose architecture is unchanged. MongoDB, the API, frontend, Caddy, reminder worker, and local backup service are running. Authoritative and public DNS now return `82.112.234.39`. Caddy obtained a valid Let's Encrypt certificate for `sikarkolkata.io`; the homepage returns HTTP 200, `/api/health` returns `{"status":"ok"}`, and HTTP redirects to HTTPS with status 308. These endpoint checks used an explicit address override while local and VPS recursive resolvers still cached the earlier missing-domain result; certificate and hostname verification remained enabled. The existing `www` CNAME points to the apex, but this deployment configures only the apex hostname for HTTPS.

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

- Frontend: ESLint passed, 26 Jest suites passed, 209 tests and one snapshot passed, and the Vite production build passed.
- Backend: Python 3.12 compilation and fatal-error Flake8 passed; all 474 tests passed against isolated HTTP/API and MongoDB services. The suite emitted 24 existing warnings about short test-only JWT keys; production uses a generated 64-character secret.
- Production Docker builds, Compose configuration validation, `nginx -t`, and Caddy configuration validation passed.
- Correctness and simplicity reviews ran independently; neither found a confirmed deployment blocker.
- No separate static typechecker is configured for this JavaScript/Python application; compilation is not static type coverage.
- The isolated verification project and its synthetic database were removed after the checks.

## Backups and remaining integrations

The owner requested daily backups. `/opt/snp/.env.production` now sets `BACKUP_INTERVAL_SECONDS=86400`, and the recreated backup container reports that value. The worker creates a compressed archive on startup, then waits 24 hours after each backup; this is not a fixed midnight schedule. It retains 14 days in the `snp_backups` Docker volume. Set this environment override on any replacement server, because the Compose fallback remains hourly.

A post-bootstrap archive, `snp_camps-20260908T072922Z.archive.gz`, was restored into a separate MongoDB instance: one user, zero patients, zero persons, and zero camps. The restore instance was removed afterward. An export is held at `/opt/snp/backup-export/`. The backup container also completed a new archive after its daily-interval restart.

An ongoing off-machine backup destination is still required. Archives on the VPS do not protect against loss of that VPS. Follow the root README's backup instructions; `docs/ops/backups.md` refers to a `backup-sync` service and `BACKUP_REMOTE` variable that the current Compose file does not implement.

MSG91 credentials and approved templates have not been configured. SMS remains skipped until those are supplied and actual delivery is tested. Real phone scanning and printer acceptance remain operator checks.
