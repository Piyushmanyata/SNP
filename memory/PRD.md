# SNP Camps → Emergent — PRD

## Problem Statement
Rebuild the "SNP Camps" medical eye-camp management system (originally Next.js + Supabase + Vercel)
on Emergent (React + FastAPI + MongoDB). Phase 1 = full Camp Management System.

## User Choices (2026-08-27)
- Scope: Full Phase 1 at once.
- Aadhaar Secure QR decode: MOCKED/simulated (demo payload `AADHAAR|name|gender|dob|last4|address`).
- Auth: JWT custom (email+password, roles).
- Data: start empty (only seeded admin).
- Design: Emerald/Slate medical-tech theme, mobile-first, WCAG 2.2 AA, 44x44 targets.

## Architecture
- Backend: FastAPI (`/app/backend`), modular routers (auth, staff, camps, registration, desk, clinical, reports).
- DB: MongoDB (standalone → invariants via unique indexes + atomic conditional updates, not multi-doc txns).
- Frontend: CRA React + Tailwind, react-router, role-aware routing (`roleHome`), portaled modals.
- Auth: JWT (httpOnly cookies + Bearer fallback), bcrypt, email-keyed brute-force lockout, admin seeded on startup.

## Roles & Permissions
- Admin: everything (camps/days/print-window/staff/OT schedule/exports/leaderboards + desk + clinical).
- Team Lead: desk work; can create ONLY volunteers on own team.
- Volunteer: register, print, mark seen, undo, name search, manual exception.
- Clinical Desk Operator: seen-only lookup, transcription, fulfilment, slips, corrections, history.
- Patient: no login; self-registration + patient QR (scanned by staff only).

## Implemented (2026-08-27)
- Auth: login/logout/me, JWT cookies, lockout (email-keyed, 429), password policy, admin seed.
- Camps: CRUD, exactly-one-active (partial unique index), camp-days upsert, per-day print window.
- Registration: desk register (phone required, dummy rejected), self-register (public + rate limit),
  Person↔Registration split via Aadhaar HMAC key, idempotency (registration_request_id),
  hard per-camp (last4,name) dup + soft name+age dup, manual exception, name search, mock Aadhaar decode.
- Desk: QR/reg# lookup, print A4 (presence-once + PRINT_WINDOW_CLOSED gate), mark-seen (never_printed guard),
  undo-seen (10-min window, blocked once transcription exists).
- Clinical: seen-only eligibility (not_seen refusal w/o PHI), transcription (locks on first fulfilment),
  medicine/specs/OT fulfilment, A6 Tokens (versioned, cancel+replace), OT Schedule Days and Specs collection days with
  seat consumption (SEAT_LIMIT_BELOW_ASSIGNED guard, seat released on re-record), D-1 MSG91 reminders, append-only corrections, history.
- Staff mgmt, volunteer/team-lead leaderboards, KPIs, CSV exports (camp records + clinical audit).
- Ops: /api/health, /api/health/ready (fail-closed).
- Prints: A4 prescription (identity + QR + blank clinical area), A6 bilingual Token (105 × 148 mm) for OT and Spectacles to be made.

## Test Status
- Backend: 74/74 pytest pass (/app/backend/tests/backend_test.py). Frontend: all regression flows pass.
- Reports: /app/test_reports/iteration_1.json, iteration_2.json.

## Deferred (Phase 2+)
- MSG91 DLT Devanagari SMS at registration or Token print (D-1 Camp/OT/Specs reminders ship in Phase 2).
- Sponsor-asset object storage + versioned prescription template editor.
- Real Aadhaar Secure QR cryptographic decode.
- Load testing to 10k+; Supabase→Mongo data migration; adversarial security audit.
- Phase 4 modules: Members, Clinic, Matrimony, Events, Donations, CMS.

## Backlog / Next
- P2: ot_eye/gender as strict enums in Pydantic (ot_eye normalized as interim fix).
- P2: skip /auth/me bootstrap on public routes to remove cosmetic 401 console log.
- P2: client-side inline validation on desk phone field.
