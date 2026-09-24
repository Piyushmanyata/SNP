# Test Credentials — SNP Camps

## Admin (seeded on startup)
- Name: `admin`
- PIN: `864200` (the local `ADMIN_BOOTSTRAP_PIN`; the first sign-in must choose a new one)
- Role: `admin`

## Staff Accounts
Create on the Team page (POST `/api/staff`).
- Each new account gets a random one-time PIN, shown once to the person who created it or reset it.
- Admin and Team Lead PINs are 6 digits; Volunteer and Clinical operator PINs are 4.
- Every account must choose its own PIN at first sign-in.

## Notes
- Patients never authenticate. Self-registration is public at `/self-register`.
- Auth endpoints under `/api/auth`. Authenticates with normalized `name` and a 4- to 6-digit numeric `pin`.
