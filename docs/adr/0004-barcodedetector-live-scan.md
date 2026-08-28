# Live scan: getUserMedia, BarcodeDetector, WASM fallback

Live scan owns the camera via `getUserMedia`. Native `BarcodeDetector` is used when the browser provides it; otherwise a local WASM QR decoder. `html5-qrcode` is removed. Photo upload and USB wedge remain after both decoders.

## Context

`html5-qrcode` 2.3.8 crops and downscales through a qrbox — hostile to dense Aadhaar Secure QR. We will not hard-depend on `BarcodeDetector`: iOS Safari before 17 and some Android WebViews lack it. A WASM decoder is extra weight on cheap phones, accepted so live scan still works there.

## Decision

- Request **1280×720 as `ideal`**, back camera. Torch and camera switch stay. **720p is a preference, not a gate.** After start, ROI geometry uses `track.getSettings().width/height` (actual track), never the requested 1280×720. Accept 640×480 or odd 4:3 as-is. Never upscale or downscale frames.
- At most **~8 detect attempts/s** total, **exactly one in flight**; drop the frame if a detect is running. WASM never runs at the same time as native.
- **Detect → Soft Hold → Decode**. Pause the detector on Detect (exactly one Decode in flight). **Lock** only if Decode returns `card`, then Freeze. `garbage` / `not-aadhaar` is Failure: resume live scan and **ignore that exact payload for ~1.5s**. No client-side Aadhaar sniff — backend Decode is the only validator.
- **Decoder promotion (once per live-scan session)**: if `BarcodeDetector` is missing → WASM immediately. If present → native first. Promote to WASM after **8 consecutive native misses or ~1.25s, whichever first**. Await the in-flight native detect, then `decoder = wasm` for the rest of this session. Restarting live scan resets to native-first. Never native again after promotion in that session.
- Photo upload uses the same detector order on an `ImageBitmap`.
- After native and WASM both fail to Lock for **~2–3s**, show photo upload / USB wedge. Those fallbacks are not only for camera-start failure.
- Delete `html5-qrcode`.
- **Guide ROI**: centered square ≈90% of the **actual** video short edge. Overlay and crop are that square. Detect ROI at **native source pixels** — spatial crop only, never resize/downscale. ROI miss → next attempt is the **complete native frame**. Alternate ROI / full-frame until Lock.

## Consequences

Tests that mock `Html5Qrcode` must be rewritten. WASM download/parse cost hits on phones without `BarcodeDetector`, and on phones where native misses eight times. iOS 16 can live-scan. A present-but-blind `BarcodeDetector` cannot block WASM.

## Rejected alternatives

- Tune `html5-qrcode` — still a canvas middleman.
- `BarcodeDetector` only — fails live scan where the API is missing.
- Paid SDK / native shell — rejected in ADR-0003.
