# Test Credentials — SNP Camps

## Admin (seeded on startup)
- Email: `admin@snpcamps.org`
- Password: `AdminCamp@2026`
- Role: `admin`

## Other roles
Create via Admin → Staff tab (or POST /api/staff). Passwords must be >=12 chars
with upper/lower/digit/symbol. Suggested test accounts to create:
- Volunteer: `volunteer1@snpcamps.org` / `VolunteerPass@1`
- Team Lead: `lead1@snpcamps.org` / `TeamLeadPass@1`
- Clinical Desk Operator: `clinic1@snpcamps.org` / `ClinicalPass@1`

## Notes
- Patients never authenticate. Self-registration is public at `/self-register`.
- Auth endpoints under `/api/auth`. Cookies are httpOnly; Bearer fallback supported.
