# Project: SNP Application Remediation & PR Lifecycle

## Architecture
The application stack consists of:
- `frontend/`: React single-page application (React 18 + Tailwind CSS + Lucide + getUserMedia / BarcodeDetector + zxing-wasm)
- `backend/`: FastAPI async Python application with Motor MongoDB driver
- `.github/workflows/`: CI verification workflows

```
                    ┌─────────────────────────┐
                    │      React Frontend     │
                    │  (Desk, Clinical, Admin)│
                    └────────────┬────────────┘
                                 │ REST API (JSON)
                                 ▼
                    ┌─────────────────────────┐
                    │     FastAPI Backend     │
                    │  (Auth, Reg, Clin, Rpt) │
                    └────────────┬────────────┘
                                 │ Async Motor
                                 ▼
                    ┌─────────────────────────┐
                    │     MongoDB Database    │
                    └─────────────────────────┘
```

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Backend Lifespan & Deprecation Cleanup | Upgrade `@app.on_event("startup")` in `backend/server.py` to FastAPI lifespan handler | M1 | Survey E1 |
| 2 | MongoDB Motor Index Synchronization | Verify and maintain automated index setup in `backend/db.py` | M1 | Survey E1 |
| 3 | Frontend Lint Script & ESLint Configuration | Add `"lint": "eslint src"` and `eslintConfig` in `frontend/package.json` | M1 | Survey E2 |
| 4 | Desk Flow State Machine Verification | Ensure registration -> print -> mark seen -> fulfilment invariants | M1 | Survey E1/E2 |
| 5 | Automated Verification Suite | Run `pytest backend/`, `npm run build`, and `npm run lint` | M2 | Survey E1/E2 |
| 6 | Feature Branch Creation & Commit | Create `remediation/audit-and-lifecycle-fixes` branch with clean commits | M3 | Survey E3 |
| 7 | PR Creation & CI Resolution | Open PR targeting `main` via `gh pr create` and verify all CI checks green | M3 | Survey E3 |
| 8 | PR Merge & Branch Purge | Squash merge PR into `main`, push to `origin`, delete branch locally/remotely | M3 | Survey E3 |
| 9 | Multi-Agent Review & Forensic Audit Gate | Independent Reviewers, Challengers, and Forensic Auditor verification | M4 | Survey/Gate |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Codebase Remediation & MongoDB Index Sync | `backend/server.py`, `backend/db.py`, `frontend/package.json` | none | DONE |
| M2 | Automated Verification & Typechecks | `pytest backend/`, `npm test`, `npm run build`, `npm run lint` | M1 | DONE |
| M3 | PR Lifecycle, CI Resolution & Branch Purge | Git branch, `gh pr create`, CI verify, merge, branch delete | M2 | IN_PROGRESS |
| M4 | Comprehensive Verification Gate & Audit | Reviewers, Challengers, Forensic Auditor Gate | M1, M2, M3 | PLANNED |

## Interface Contracts

### Backend Lifespan & DB Setup
- `lifespan(app: FastAPI)`: Context manager running `init_indexes()` and graceful startup/shutdown.
- `init_indexes()`: Ensures unique `(person_id, camp_id)` partial index and 11 collection indexes.

### Frontend Package Scripts
- `npm run lint`: Runs `eslint src` with 0 warnings/errors.
- `npm run build`: Compiles production bundle with exit code 0.
- `npm test`: Runs Jest suites with 100% pass rate.

## Code Layout
- `backend/server.py`
- `backend/db.py`
- `backend/routes_*.py`
- `frontend/package.json`
- `frontend/src/*`
