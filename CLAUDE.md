@AGENTS.md

## SNP Camps — Hostinger KVM Application

Authoritative stack:
- `frontend/`: React + Tailwind CSS (Vite)
- `backend/`: FastAPI + PyMongo Async on a MongoDB replica set
- `docker-compose.prod.yml`: full-stack deployment, TLS, backups and reminder worker

Do not introduce Next.js, Supabase, or Vercel dependencies.

## Agent skills

### Issue tracker

GitHub Issues on `Piyushmanyata/SNP`, via `gh`. See `docs/agents/issue-tracker.md`.

### Triage labels

Canonical five roles, strings equal to names. See `docs/agents/triage-labels.md`.

### Domain docs

single-context. See `docs/agents/domain.md`.
