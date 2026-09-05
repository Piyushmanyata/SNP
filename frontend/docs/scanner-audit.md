# Aadhaar scanner audit

## Decision

Preserve native camera pixels and the existing native/ZXing decoder order; reduce repeated still-photo capture instead of downscaling dense Aadhaar QR images or adding another decoder dependency.

The camera now requests the environment camera without first pinning the first enumerated device, which may be the front camera. Camera switching uses the actual track device ID when available. This also removes a device-enumeration round trip before requesting camera access.

Preview detection continues at a maximum of eight attempts per second, with only one detector or decode request in flight. A full-resolution still capture is attempted after three seconds and no more frequently than every three seconds. Native-resolution preview frames fill the remaining full-frame attempts. In the deterministic component test, the previous code took four still photographs during the first second; the new code takes zero, keeps all nine initial preview attempts, and takes one still photograph after four seconds. This measures scheduled work, not a physical phone's frame rate or decoding accuracy.

Stopping the camera invalidates a pending permission request; a later stream is immediately released. The starting state remains visible while permission is pending. QR worker startup and detector failures stop the scan and offer retry/photo/USB recovery instead of leaving an unhandled rejection. Switching to fallback photo or USB input stops the live camera. The scanner provides lens, lighting, glare, distance and steadiness guidance.

Demo card generation and its active UI/export have been removed. The backend remains the only Aadhaar payload validator; no client-side acceptance heuristic has been added.

## Validation and limits

Regression tests exercise the public scanner component and live-scan engine. Existing tests retain camera permission denial, no secure context, 640×480 fallback, torch/switching, file upload, manual Enter submission, single detection in flight, backend-only locking and ignored non-Aadhaar payload coverage.

Physical old-phone camera quality, real dense QR decoding accuracy, low light, glare, rear autofocus and sustained thermal performance require representative devices and cards. HTTPS is required for camera access outside localhost. Normal preview scanning, high-resolution still fallback, photo upload and USB capture remain available; no camera-resolution minimum is imposed.

No browser, dev server, camera hardware, or live Aadhaar card was used in this audit. The deterministic tests do not establish a measured real-device speedup.
