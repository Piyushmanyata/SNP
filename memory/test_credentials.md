# Test Credentials — SNP Camps

## Admin (seeded on startup)
- Name: `admin`
- PIN: `1234`
- Role: `admin`

## Staff Accounts
Create via Admin → Staff tab, or Team Lead → Team page (POST `/api/staff`).
- All new accounts are seeded with default PIN: `1234`
- All non-admin staff must change their PIN upon first login via the mandatory PIN change prompt.

## Notes
- Patients never authenticate. Self-registration is public at `/self-register`.
- Auth endpoints under `/api/auth`. Authenticates with normalized `name` and 4-digit numeric `pin`.
