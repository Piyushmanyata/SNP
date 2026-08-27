# Auth Testing Playbook — SNP Camps

## Admin (seeded)
- Email: `admin@snpcamps.org`
- Password: `AdminCamp@2026`
- Role: admin

## Auth endpoints (all under /api/auth)
- POST /api/auth/login  { email, password }  -> sets httpOnly cookies + returns {user, access_token}
- POST /api/auth/logout (auth)
- GET  /api/auth/me     (auth)

Tokens: httpOnly cookie `access_token` (12h) + `refresh_token` (7d). Bearer header fallback supported.
Password policy for created staff: >=12 chars, upper+lower+digit+symbol.

## Quick check
```
curl -c ck.txt -X POST http://localhost:8001/api/auth/login -H "Content-Type: application/json" \
  -d '{"email":"admin@snpcamps.org","password":"AdminCamp@2026"}'
curl -b ck.txt http://localhost:8001/api/auth/me
```
