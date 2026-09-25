# ADR 0082: The live scan keeps its QR reader through slow frames

## Context

The WASM reader (ADR 0005, ADR 0048) terminated its worker whenever one frame took longer than four seconds. The next frame then reloaded and recompiled the module, which can take tens of seconds on a low-end phone, so one dense frame stalled the scan. Other costs slowed the first read: the worker started loading only when the camera started, half of all frames were full 1920-pixel frames, the 1280×720 camera fallbacks did not ask for continuous autofocus, and the scan loop kept grabbing and decoding frames in a hidden tab.

## Decision

- A frame that times out resolves as no read and the worker is kept. Only three timeouts in a row (`WASM_MAX_STALLS`), or a worker error, replace the worker. Only an on-time reply resets the count; a late reply to a frame that already timed out does not.
- The worker starts loading as soon as the scanner mounts.
- The WASM lane reads the guide crop twice for every full frame (`roi, roi, full`).
- Every camera constraint attempt at 1080p or 720p asks for continuous autofocus.
- The scan engine skips its tick while `document.hidden`.

Restarting the worker on the first timeout was rejected: a slow frame is common on phones and a restart costs far more than the frame. Turning off `tryRotate` or shrinking full frames was rejected until it can be measured on a real Secure QR; both risk missed reads.

## Consequences

A worker that truly hangs is replaced after about twelve seconds instead of four. Pages that mount the scanner download the reader even if the operator never opens the camera.
