# E2E Test Suite Ready

## Test Runner
- Commands:
  - Lint: `npm run lint`
  - Typecheck: `npx tsc --noEmit`
  - Unit Tests: `npm test`
  - DB Replay Tests: `npm run test:db:replay`
  - Build: `npm run build`
  - JS Budget Check: `npm run check:js-budget`
  - E2E Tests: `npm run test:e2e`
  - Full Verification Gate: `npm run verify`
- Expected: All test suites pass cleanly with exit code 0.

## Coverage Summary
| Tier | Count | Description |
|------|------:|-------------|
| 1. Feature Coverage | 42 | Happy-path unit & component coverage across camera, decode, and parse |
| 2. Boundary & Corner | 45 | Corrupted payload, malformed XML, dark-mode QR, invalid dates, desk slips |
| 3. Cross-Feature | 18 | Dual-reader fallback, worker Comlink transfer, duplicate Aadhaar checks |
| 4. Real-World Application | 8 | Playwright live camera scan, Y4M video stream, desk registration & print |
| **Total** | **113** | |

## Feature Checklist
| Feature | Tier 1 | Tier 2 | Tier 3 | Tier 4 |
|---------|:------:|:------:|:------:|:------:|
| F1. Camera Lifecycle | 5 | 5 | ✓ | ✓ |
| F2. Probe Geometry | 5 | 5 | ✓ | ✓ |
| F3. Image Preprocessing | 5 | 5 | ✓ | ✓ |
| F4. Web Worker Decoders | 5 | 5 | ✓ | ✓ |
| F5. Payload Parser | 6 | 7 | ✓ | ✓ |
| F6. Desk Form UI | 6 | 6 | ✓ | ✓ |
| F7. Verification Suite | 5 | 5 | ✓ | ✓ |
| F8. Git / CI Lifecycle | 5 | 7 | ✓ | ✓ |
