# Project: SNP Camps — Aadhaar Camera Scanning Reliability & CI Delivery

## Architecture
The Aadhaar scanning system provides reliable, high-speed camera-based and photo-based extraction of Aadhaar QR codes (Secure QR v2 binary compressed and Legacy XML) during eye camp desk registration. It runs fully offline with zero external network dependencies and adheres to ADR 0004, 0008, 0012, 0013, and 0014.

### Component & Data Flow:
```
[ Video Stream / Photo File ]
            │
            ▼
[ QrCameraSession (Resolution & Hardware Focus) ]
            │
            ▼
[ Multi-Scale Probe Geometry (AADHAAR_PROBES) ]
            │
      ┌─────┴─────────────────────────────────┐
      ▼ (hint)                                ▼ (frame)
[ Native BarcodeDetector ]        [ Offscreen Canvas / ImageBitmap ]
      │ (if valid)                            │ (transferable ArrayBuffer)
      │                                       ▼
      │                         [ Web Worker: aadhaar-decode.worker ]
      │                                       │
      │                         [ Multi-Pass Image Processing ]
      │                         (Grayscale, Contrast, Otsu, Adaptive, Invert)
      │                                       │
      │                         [ Dual WASM Decoders ]
      │                         (zxing-wasm + zbar-wasm from /public/wasm)
      │                                       │
      └─────────────────┬─────────────────────┘
                        ▼
            [ attemptAadhaarDecode ]
                        │
                        ▼
            [ parseAadhaarQrPayload ]
            (pako ungzip / XML / Date validation)
                        │
                        ▼
            [ Desk Form Auto-fill & Locked State ]
```

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Camera Stream Lifecycle & Hardware Adaptation | 1440p/1080p fallback cascade, continuous autofocus, zoom, permission error handling, session token cleanup | M2 | Survey / ADR 0012 |
| 2 | Frame Processing & Multi-Scale Geometry | 12 FPS throttled loop, 8 geometric probes (`AADHAAR_PROBES`), sub-crop zoom for dense QR | M2 | Survey / `qr-decode-geometry.ts` |
| 3 | Image Preprocessing & Binarization | Grayscale luminance, contrast stretch, Otsu, integral adaptive binarization, inversion | M2 | Survey / `qr-decode-pipeline.ts` |
| 4 | Web Worker Dual-Engine Decoding | Dedicated worker, zero-copy ArrayBuffer transfer, `zxing-wasm` + `@undecaf/zbar-wasm`, offline local WASM assets | M2 | Survey / `aadhaar-decode.worker.ts` |
| 5 | Dual-Reader Hinting & Payload Parsing | ADR 0014 native hint fallback, Secure QR v2 `pako` decompression, XML parser, calendar date validation | M2 | Survey / `aadhaar-qr.ts` |
| 6 | Desk Registration Form Integration | `AadhaarCapture` UI, consent gating, auto-fill, field locking, manual & USB wedge scanner fallback | M2 | Survey / `patient-form.tsx` |
| 7 | Comprehensive Verification Suite & Quality Gates | `npm run lint`, `npx tsc --noEmit`, `npm test`, `npm run test:db:replay`, `npm run build`, `npm run check:js-budget`, `npm run test:e2e` | M1 / M3 | Survey / ORIGINAL_REQUEST |
| 8 | Git & CI Automation Lifecycle | Feature branch, commit/push, `gh pr create`, CI workflow monitoring to green, merge to main, push upstream, branch cleanup | M4 | Survey / ORIGINAL_REQUEST |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | E2E Testing Track & Test Infrastructure | Create `TEST_INFRA.md`, verify and expand opaque-box test suites and harnesses, publish `TEST_READY.md` | none | DONE |
| M2 | Aadhaar Camera Scanning Reliability Implementation | Ensure camera acquisition, multi-probe decoding, and lint/typecheck/build integrity across all environments | M1 | DONE |
| M3 | Multi-Agent Review, Challenge & Forensic Audit Gate | Parallel review (2 Reviewers), empirical challenge (2 Challengers), and Forensic Integrity Audit | M2 | DONE |
| M4 | Git & CI Automation Lifecycle Delivery | Create dedicated feature branch, push, open PR via `gh`, monitor CI to green, merge to main, push upstream, delete branch | M3 | IN_PROGRESS |

## Interface Contracts
### `attemptAadhaarDecode`
- Signature: `attemptAadhaarDecode(client: AadhaarDecodeClient, nativeText: string | null, imageData: ImageData, options?: { thorough?: boolean }): Promise<AadhaarAttemptResult>`
- Returns: `{ kind: "success", card: AadhaarCard } | { kind: "rejected", reason: string } | { kind: "none" }`

### `AadhaarDecodeClient` Web Worker Interface
- `decodeFrame(imageData: ImageData, options: { thorough: boolean }): Promise<string | null>`
- `decodePayload(payload: string): Promise<AadhaarCard | null>`

## Code Layout
- `src/components/patient-form.tsx`: Desk registration form and Aadhaar data binding.
- `src/components/aadhaar-capture.tsx`: Capture modal, camera view, photo capture, error banners.
- `src/components/use-aadhaar-scanner.ts`: React hook managing stream, frame loop, and worker dispatch.
- `src/lib/qr-camera-session.ts`: MediaStream lifecycle, token generation, track termination.
- `src/lib/qr-detector.ts`: Native `BarcodeDetector` probing and camera track constraint tuning.
- `src/lib/qr-decode-geometry.ts`: Multi-scale probe bounding boxes and max decode edge.
- `src/lib/qr-decode-pipeline.ts`: Binarization algorithms, image processing, WASM decoding.
- `src/lib/aadhaar-decode.worker.ts`: Web Worker host for image processing and WASM execution.
- `src/lib/aadhaar-attempt.ts`: ADR 0014 dual-reader attempt coordinator.
- `src/lib/aadhaar-qr.ts`: Secure QR v2, legacy XML, date parsing, slip rejection.
- `tests/`: Unit and database integration tests.
- `e2e/`: Playwright end-to-end tests with synthetic camera video stream (`e2e/fake-aadhaar-camera.mjs`).
