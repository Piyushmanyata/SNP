# E2E Test Infra: SNP Camps — Aadhaar Camera Scanning Reliability

## Test Philosophy
- Opaque-box, requirement-driven testing deriving directly from `ORIGINAL_REQUEST.md`.
- Zero assumptions on internal implementation quirks; test against user-facing APIs, DOM events, camera video streams, and command-line verification scripts.
- Methodology: Category-Partition + Boundary Value Analysis + Pairwise Interaction + Real-World Workload Testing.

## Feature Inventory & Test Coverage Mapping
| # | Feature | Source | Tier 1 (Equivalence) | Tier 2 (Boundaries) | Tier 3 (Pairwise) | Tier 4 (Workloads) |
|---|---------|--------|:--------------------:|:-------------------:|:-----------------:|:------------------:|
| 1 | Camera Stream Lifecycle & Focus | ADR 0012 / `qr-camera-session.ts` | 5 | 5 | ✓ | ✓ |
| 2 | Multi-Scale Geometry & Probes | `qr-decode-geometry.ts` | 5 | 5 | ✓ | ✓ |
| 3 | Image Preprocessing & Binarization | `qr-decode-pipeline.ts` | 5 | 5 | ✓ | ✓ |
| 4 | Web Worker & Dual WASM Decoders | `aadhaar-decode.worker.ts` | 5 | 5 | ✓ | ✓ |
| 5 | Secure QR & XML Payload Parsing | ADR 0014 / `aadhaar-qr.ts` | 5 | 5 | ✓ | ✓ |
| 6 | Desk Registration Form Integration | `patient-form.tsx` | 5 | 5 | ✓ | ✓ |
| 7 | Full Verification Suite Compliance | `package.json` | 5 | 5 | ✓ | ✓ |
| 8 | Git & CI Automation Lifecycle | `ORIGINAL_REQUEST.md` | 5 | 5 | ✓ | ✓ |

## Test Architecture
- **Unit & Component Suites**: `scripts/run-unit-tests.mjs` using `node:test` runner.
- **Database Replay Suite**: `npm run test:db:replay` using local Supabase Postgres.
- **E2E Browser Suite**: Playwright with Chromium video device flags (`--use-fake-device-for-media-stream`, `--use-file-for-fake-video-capture`) fed with synthetic Y4M video stream (`e2e/fake-aadhaar-camera.mjs`).
- **Linter & Typecheckers**: `eslint` and `tsc --noEmit`.
- **Bundle & Env Budget Guards**: `scripts/check-js-budget.mjs` and `scripts/check-env.mjs`.

## Real-World Application Scenarios (Tier 4)
| # | Scenario | Features Exercised | Target |
|---|----------|--------------------|--------|
| 1 | Desk Live Camera Scan (Standard Lighting) | F1, F2, F4, F5, F6 | Fast registration <15s |
| 2 | High-Contrast / Inverted Aadhaar Card in Low Light | F1, F2, F3, F4, F5, F6 | Decode via adaptive/invert filters |
| 3 | Mobile OS Photo Capture (`capture="environment"`) | F1, F3, F4, F5, F6 | High-res ImageBitmap decode |
| 4 | Hardware USB Wedge Scanner Rapid Ingestion | F5, F6 | Debounce/Enter instant capture |
| 5 | Duplicate / Re-scan Confirmation Workflow | F5, F6 | Confirmation modal & deduplication |

## Coverage Thresholds
- Tier 1: ≥5 test cases per feature (Total ≥ 40)
- Tier 2: ≥5 boundary test cases per feature (Total ≥ 40)
- Tier 3: Pairwise interaction coverage across camera, worker, parser, and UI
- Tier 4: ≥5 realistic camp field registration workloads
