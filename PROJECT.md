# Project: Camp lifecycle — pre-registration, Arrival, per-patient SMS, four Fulfilment lines

Spec: `docs/specs/camp-lifecycle-arrival-sms-fulfilment.md`

## Architecture
The application stack consists of:
- `frontend/`: React single-page application (React 18 + Tailwind CSS + Lucide + BarcodeDetector / zxing-wasm)
- `backend/`: FastAPI async Python application with Motor MongoDB driver

```
                    ┌─────────────────────────┐
                    │   React SPA (frontend)  │
                    │  Desk · Clinical · Admin│
                    └───────────┬─────────────┘
                                │ HTTPS /api
                    ┌───────────▼─────────────┐
                    │  FastAPI (backend)      │
                    │  registration · desk    │
                    │  clinical · reports     │
                    │  sms · cron             │
                    └───────────┬─────────────┘
                                │ Motor
                    ┌───────────▼─────────────┐
                    │       MongoDB           │
                    └─────────────────────────┘
```

## Feature Inventory
| # | Feature | Description | Milestone | Status |
|---|---------|-------------|-----------|--------|
| 1 | Per-patient SMS with `reg_no` | `sms.py` sends one DLT message per patient per type per event date; six templates; ledger keyed on patient/type/date | M1 | DONE |
| 2 | Registration confirmation and Token SMS | Best-effort sends on the registration create path and on OT/Specs deferral | M1 | DONE |
| 3 | Arrival as a distinct state | `arrived_at` on the registration; `registered -> arrived -> seen`; Print and Seen gated on Arrival | M2 | DONE |
| 4 | Camp-day scan resolution | `POST /api/desk/scan` returns arrived / mismatch_review / ambiguous / no_match; `POST /api/desk/scan/confirm` applies the overwrite and checks in | M2 | DONE |
| 5 | Wrong-day check-in | Arrival moves the registration to the day they came and records the change; capacity never blocks Arrival | M2 | DONE |
| 6 | Camp-day capacity and public occupancy | Seat limit must be > 0; public endpoint returns camp totals; login screen leads with registrations / seats | M3 | DONE |
| 7 | Four Fulfilment lines | Medicine, Fixed-power specs, Spectacles to be made, OT; measurements required on both specs lines; day picker pre-selects the earliest free day | M3 | DONE |
| 8 | Desk patient list removed | `GET /api/patients` removed; Seen is reached through QR, `reg_no` or name lookup | M3 | DONE |
| 9 | Single wide export | One admin-only CSV, one row per patient, no-shows included | M4 | DONE |
| 10 | Prescription lockdown | Layout constants in the print component; only sponsor logos editable; draft/publish/restore removed | M4 | DONE |
| 11 | Live scan on poor hardware | 1080p + continuous focus ladder, full-sensor still where offered, twenty-second Scan stall revealing torch / upload / manual entry | M4 | DONE |
| 12 | Cloud deployment over HTTPS | `docker-compose.prod.yml`, static frontend behind nginx, Caddy terminating TLS with automatic certificates | M5 | DONE |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | SMS grain change | `backend/sms.py`, `backend/msg91.py`, `backend/routes_reminders.py`, `backend/db.py` | none | DONE |
| M2 | Arrival and scan resolution | `backend/routes_desk.py`, `backend/routes_registration.py`, `backend/serializers.py`, `frontend/src/pages/Desk.js`, `frontend/src/components/desk/` | none | DONE |
| M3 | Capacity, occupancy and the four lines | `backend/routes_camps.py`, `backend/routes_clinical.py`, `frontend/src/pages/Login.js`, `frontend/src/components/clinical/` | M2 | DONE |
| M4 | Reporting, prescription lockdown, live scan | `backend/routes_reports.py`, `backend/routes_templates.py`, `frontend/src/pages/PrintPrescription.js`, `frontend/src/components/aadhaar/` | M3 | DONE |
| M5 | Production deployment | `docker-compose.prod.yml`, `Caddyfile`, `frontend/Dockerfile.prod`, `frontend/nginx.conf` | M4 | DONE |

## Interface Contracts

### Desk scan resolution
- `POST /api/desk/scan {payload}` → `{outcome: "arrived" | "mismatch_review" | "ambiguous" | "no_match", ...}`.
  `arrived` stamps Arrival and returns the registration; `mismatch_review` returns the card values, the
  stored registration and a field-level `diff`, and mutates nothing; `ambiguous` lists the candidates;
  `no_match` returns the card and registers nobody.
- `POST /api/desk/scan/confirm {patient_id, payload}` → applies the Aadhaar overwrite (name, age, gender,
  DOB, last-4, address) and stamps Arrival in one operation, preserving phone, camp day, `reg_no` and
  lifecycle timestamps.
- `POST /api/desk/arrive/{patient_id}` → stamps Arrival for a walk-in or a lookup match.

### SMS
- `sms.send_patient_sms(db, patient, message_type, event_date, venue) -> bool` — never raises; records one
  ledger row per `(patient_id, message_type, event_date)`; skips missing or dummy numbers.
- Message types: `registration`, `camp`, `ot_token`, `ot`, `specs_token`, `specs`. Each is its own DLT
  template taking `reg_no`, `date` and `venue`.

### Fulfilment
- `POST /api/clinical/fulfilment` refuses a `specs` line with 400 `SPECS_MEASUREMENTS_REQUIRED` unless the
  transcription carries a power for both eyes.
- A deferral to a full day is 409 `full or not found`; when no day of that type has a free seat it is
  409 `NO_CLINICAL_DAY_AVAILABLE` naming the admin action.

### Prescription template
- `GET /api/templates/logos?camp_id=` → `{logos}` (any staff). `PUT /api/templates/logos` → saves live (admin).
- Header, subtitle, footer and block layout are constants in `frontend/src/pages/PrintPrescription.js`.

### Export
- `GET /api/exports/camp-records?camp_id=` (admin) → one CSV row per patient of the camp, including
  no-shows, with the header fixed by `EXPORT_COLUMNS` in `backend/routes_reports.py`.

## Code Layout
- `backend/*.py`
- `frontend/src/**/*.js`
- `docker-compose.prod.yml`, `Caddyfile`, `frontend/Dockerfile.prod`, `frontend/nginx.conf`

## Outstanding, external to this repository
- The six DLT template approvals. Sending is skipped entirely until `MSG91_AUTH_KEY` and all six template
  ids are set, so the app runs without them.
- A domain and certificate for `APP_DOMAIN`. Live scan cannot be tested on a phone until HTTPS is in place.
- Camp days created before this change with a zero seat limit need a one-time backfill to a real number.
