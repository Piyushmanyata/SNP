# SNP Camps

React frontend, FastAPI backend and MongoDB, hosted together with Docker on a Hostinger KVM. Production serves the frontend and API at one HTTPS origin.

## Test locally with Docker

Install Docker Desktop and run from this directory:

```sh
docker compose --env-file .env.example up -d --build --wait
```

Open http://localhost:3000. Sign in as **admin**, PIN **8642**, then choose a new PIN. These credentials are only for the local stack. MongoDB data persists in a Docker volume; stopping or rebuilding does not erase it. Both frontend and backend run production builds without development servers or source mounts.

For phone camera testing, use a trusted HTTPS address; see [local HTTPS setup](docs/dev-https.md). Plain HTTP on a LAN IP cannot use the camera. The local site binds to localhost by default.

## Camp workflow

1. Admin creates/activates the camp, opens camp days and the print window, and creates team leads and operators.
2. A patient registers, then a desk volunteer scans their Aadhaar to record arrival. Manual fallback remains available to desk staff.
3. Staff prints the prescription, the doctor examines the patient, and staff marks them Seen.
4. A clinical operator chooses Medicine, Fixed-power specs, Spectacles to be made, or Hospital. At that same desk they transcribe the paper prescription, then issue supplies or schedule collection/hospital treatment.
5. A scheduled IOL surgery and later spectacle collection produce a short A6 token. A Hospital referral or Surgery declined produces none. IOL surgery is the only operation arranged, and it is performed at the hospital only.

Team Management and Analytics are beside each other in the admin overview (also available to team leads from the desk). Reset PIN sits beside Logout. Forgotten PINs can be reset by the user's lead or an admin.

Camp default: Hansa Garden, Rohini Road in Baghmara, Jasidih, Deoghar 814142.

Hospital default: Vimla Ramkrishna Bajaj Eye Hospital, Near Canara Bank, Bilasi Mod, Deoghar 814112 (Jharkhand). Phone: 9835317006.

## Hostinger KVM deployment

Use a Linux KVM with Docker Engine and the Compose plugin. Hostinger provides an [Ubuntu Docker template](https://www.hostinger.com/support/1583571-what-are-the-available-operating-systems-for-vps-at-hostinger/). Point your domain's DNS to the KVM, and allow TCP 80/443 through the firewall.

Copy `.env.production.example` to `.env.production`. Set the domain, TLS email, a private 4-digit bootstrap PIN other than 1234, and four independent random secrets. Generate each secret using `openssl rand -hex 32`; use hex for MONGO_PASSWORD so the database URL needs no escaping. Keep this file private.

```sh
docker compose --env-file .env.production -f docker-compose.prod.yml config --quiet
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build --wait
```

Caddy obtains and renews TLS certificates. Only ports 80/443 are published; MongoDB and the API remain internal. The backend runs without root privileges. No Emergent account or hosting files are required.

Configure the MSG91 key and approved DLT template IDs before using real SMS. Without them, sending is reported as skipped. Register the six texts from `dlt_portal_body` in `backend/docs/msg91-templates.json`, which a test keeps identical to `backend/sms.py`. Every message names the camp number, so a camp sends no SMS until an admin sets its number on the Camps tab. Real carrier delivery requires a live provider test.

The reminder container dispatches day-before reminders at 10:00 Asia/Kolkata and retries failures. Details: [reminder worker](backend/docs/reminder-worker.md).

## Backups and recovery

Production creates a compressed MongoDB dump every hour in the `backups` volume and keeps 14 days by default. A failed dump does not remove previous successful backups. Copy archives off the KVM using your backup provider or rclone; a backup on the same disk is not disaster recovery.

To export the archive directory:

```sh
docker compose --env-file .env.production -f docker-compose.prod.yml cp backup:/backups ./backup-export
```

Restore an archive into an isolated MongoDB instance first using `mongorestore --gzip --archive=<file>`; confirm registrations, prescriptions and schedules before restoring a live database. Do not run `down -v` on the production project.

## Verification

Use Node 24 and Python 3.12. Frontend: `npm ci`, `npm run lint`, `npm test -- --runInBand`, `npm run build` from `frontend/`.

Backend: install `backend/requirements-dev.txt`, run `python -m compileall -q backend`, `python -m flake8 --select=F,E9 backend`, and `python -m pytest backend/tests -q`.

The complete backend suite includes live HTTP tests. Run it serially against a fresh isolated Docker project with `SNP_LIVE_API=http://localhost:3000`, `SNP_TEST_ADMIN_NAME=admin`, and `SNP_TEST_ADMIN_PIN=8642`. It changes the bootstrap PIN and creates synthetic camp records. Without a live endpoint, those integration tests are explicitly skipped.

See [audit evidence and limits](frontend/docs/production-audit.md), [clinical workflow](frontend/docs/clinical-workflow.md) and [scanner audit](frontend/docs/scanner-audit.md). Automated tests do not replace checking the real A6 printer, older phones and SMS carrier before the camp.
