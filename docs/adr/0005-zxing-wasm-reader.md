# WASM fallback is self-hosted zxing-wasm (reader, QR only)

The live-scan WASM decoder is Sec-ant's `zxing-wasm` reader build. The `.wasm` file is self-hosted in the CRA app. It loads lazily on a Worker the first time native `BarcodeDetector` is missing or promoted. No CDN, no `barcode-detector` ponyfill, no JS-only decoder.

## Context

ADR-0004 requires a local WASM QR decoder so live scan does not hard-depend on `BarcodeDetector`. Dense Aadhaar Secure QR needs a real zxing-cpp reader. Camp networks cannot be assumed to reach jsDelivr.

## Decision

- Package: `zxing-wasm`, reader subpath, format `QRCode` only.
- Self-host the `.wasm` in the frontend build.
- `import()` + Worker only on first WASM use.
- Feed the same native-resolution Guide ROI / full-frame pixels as native. One detect in flight.
- Reader flags: `tryHarder: true`, `tryRotate: true`, `tryInvert: false`, `tryDownscale: false`, `maxNumberOfSymbols: 1`.

## Consequences

First WASM use pays parse/compile cost (promotion or no native API). `tryDownscale: false` preserves module resolution; `tryHarder` may make WASM slower than 8 Hz — 8/s is a cap, not a target. Worker and wasm assets must be wired through CRA.

## Rejected alternatives

- `barcode-detector` ponyfill — same engine, CDN wasm by default, second `BarcodeDetector` name.
- `@zxing/browser` / jsQR — no WASM, weak on dense Secure QR.
