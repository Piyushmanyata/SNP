# Project rules — SNP Camps (Hostinger KVM stack)

Global rules load automatically from `~/.claude/CLAUDE.md`. This file adds project facts only.

## Stack

- `frontend/`: React 18 SPA (Vite) + Tailwind CSS + Lucide
- `backend/`: FastAPI async, PyMongo Async driver, single-node MongoDB replica set
- `docker-compose.prod.yml`: Hostinger KVM deployment — full stack, reminder worker, TLS, backups
- The root Next.js + Supabase app is legacy and retired. Do not introduce Next.js, Supabase or
  Vercel dependencies.

## Rules and boundaries

- All development happens only in `frontend/` and `backend/`.
- Backend invariants: unique indexes, atomic conditional operations, multi-document transactions.
- Desk flow: Registration → Print Prescription (`printed_at` presence) → Mark Seen → Clinical Fulfilment.
- Accessibility: high contrast, 44×44 minimum touch targets, responsive field-ready layout.
- E2E tests: headless Playwright (`npx playwright test`) — also the CI test runner.

## Agent skills

### Issue tracker

GitHub Issues on `Piyushmanyata/SNP`, via `gh`. See `docs/agents/issue-tracker.md`.

### Triage labels

Canonical five roles, strings equal to names. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context. See `docs/agents/domain.md`.
