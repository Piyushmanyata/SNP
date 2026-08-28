# Stay in the browser for Aadhaar Secure QR capture

Desk capture of Aadhaar Secure QR runs in the existing React SPA (getUserMedia + a browser decoder). We will not introduce a native shell or a paid scanning SDK for this.

## Context

Volunteers register patients by pointing a BYOD Android or iPhone at a PVC Aadhaar Secure QR. The app is already a browser SPA. Photo upload and USB wedge already exist when the camera cannot start. Dense Secure QR on cheap phones is a capture/decode-quality problem, not a missing-native-app problem.

## Decision

Keep live capture in the browser. Replace or strip `html5-qrcode` as needed. Do not add Capacitor, CameraX/AVFoundation wrappers, or a licensed scanner SDK.

Live scan must work on Android Chrome and iOS Safari without treating `BarcodeDetector` as the only decoder. Photo upload and USB wedge remain when the camera cannot start or no decoder can Lock.

Live-scan success is Lock (`POST /aadhaar/decode` → `card`), not Detect. Decode stays on the server.

**CI proves the state machine** (Jest). It does not assert 3s. **3-second Lock is a field-performance acceptance criterion**, validated on physical phones with real Aadhaar Secure QR under camp lighting. Tiers: cheap 4GB Android, mid-range ₹15–25k Android, iPhone Safari. Measure camera-ready → Lock, ≥20 scans/device. Pass: **≥95% Lock within 3s**, **zero false Locks** (Decode `card` on non-Aadhaar).

Merge when Jest invariants, typecheck, and lint are green. The 3s trial is post-deploy acceptance, not a git gate. No feature flag unless a live event needs rollback. Miss on 3s → reopen ADR-0003/0004 with measured evidence.

## Consequences

One codebase still serves Android Chrome and iOS Safari. Focus, torch, and resolution are limited to what the browser exposes. A local WASM QR decoder is the live-scan fallback when `BarcodeDetector` is missing or promoted (see ADR-0004, ADR-0005). If field evidence later shows the browser cannot resolve PVC Secure QR even with a proper decoder, this ADR is the thing to reopen.

## Rejected alternatives

- Native shell (Capacitor or similar) — better camera control, new install path, two camera stacks, camp sideload.
- Paid SDK (Scandit and similar) — faster lock, per-device license, still wrapped in web or native.
