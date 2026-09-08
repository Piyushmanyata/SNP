# Aadhaar scan lifecycle

The server owns Aadhaar parsing and returns `card` only for accepted identity data. Camera, upload, and USB/paste capture pass the QR text to `/aadhaar/decode`.

`useAadhaarDecode` exposes `cancelDecode` to invalidate pending recognition and responses. The scanner calls it when stopping, starting, or switching cameras and when using the fallback upload or USB/paste actions. A newer decode, upload, and unmount also invalidate older requests. An invalidated upload cannot start decoding after recognition finishes. An invalidated response cannot populate identity, display an error, or clear a newer request's busy state. Cancellation does not require the HTTP response to stop arriving.

The scanner component tests cover stopping during decoding, restarting before an older success or error arrives, and cancelling upload recognition during bitmap creation or native/WASM detection. Successful XML capture fixtures use the supported `PrintLetterBarcodeData` format and `secure_qr_xml` source.

Run focused scanner verification from `frontend` with `npm test -- --runInBand src/components/AadhaarScanner.test.js src/components/aadhaar/liveScan/liveScanEngine.test.js`.

## Photo decoding budget

Before creating an ImageBitmap or HTML image, uploads inspect at most 64 KiB of bytes for PNG IHDR dimensions or baseline/progressive JPEG SOF dimensions. Only known, positive dimensions with a maximum edge of 2560 pixels and at most 4,000,000 pixels may enter local decoding. A compressed file below 4 MiB can still exceed this pixel budget. Unknown formats, malformed or incomplete headers, JPEG headers outside the inspection window, larger dimensions, HEIC, PDF and files above 4 MiB go directly to `/aadhaar/extract`. The original bytes reach the backend unchanged, preserving available QR detail. The upload cap remains 12 MiB.

This deliberately restricts local format recognition. It is a routing check, not a replacement for either browser decoding validation or backend file validation. High-resolution files require connectivity and backend capacity. Small local files use a 1600-pixel first attempt and, when useful, a 2560-pixel second attempt with preserved aspect ratio. Live preview frames remain bounded to 1600 pixels; still-frame canvases default to 2560 pixels.

The shared `canDecodePhoto(blob)` guard in `liveScan/grabFrame.js` also runs before decoding camera still photos. Oversized or unrecognized still photos are discarded in favor of a bounded video frame, without uploading camera frames to the backend. Valid bounded still photos retain the three-second capture cadence. Bitmap handles close even if canvas extraction fails. The browser and camera still control the internal memory used by `takePhoto()` itself; the guard prevents the subsequent full-resolution bitmap allocation.

Decision: inspect dimensions before decoding instead of relying on `createImageBitmap` resize options alone. The browser API documents output dimensions, not a maximum peak decode allocation. PNG IHDR defines the image width/height; JPEG SOF defines source frame dimensions. These format facts support routing oversized sources before invoking either browser decoder. No device memory or recognition-rate guarantee follows from this policy. [Browser bitmap API](https://developer.mozilla.org/en-US/docs/Web/API/Window/createImageBitmap), [PNG IHDR specification](https://www.w3.org/TR/png-3/#11IHDR), [JPEG T.81 frame-header syntax, B.2.2](https://www.w3.org/Graphics/JPEG/itu-t81.pdf).

## Hook and worker contracts

`scanFile(file, password = "")` tries eligible local QR capture and falls back to the backend. Extraction receives a raw file body, its content type, a 35-second request timeout and, only when supplied, a URL-encoded `X-PDF-Password` header. `passwordRequired` signals a retryable PDF password response. `reviewData` contains unverified OCR suggestions; receiving them never calls `onScanned`. The scanner requires explicit operator confirmation before populating editable registration fields. `cancelDecode()` clears review/password state, aborts an active extraction and invalidates stale work. A new attempt and unmount also invalidate older results.

`detectWasmImageData(imageData)` transfers ownership of `imageData.data.buffer` to its worker. Callers must provide a fresh frame and must not read or reuse that pixel buffer afterwards. A timeout or posting failure terminates the worker, settles outstanding jobs, and allows the next frame to create a replacement. A normal no-result response keeps the healthy worker.

Targeted hook tests include small-byte 48-megapixel PNG/JPEG headers, unknown/truncated headers, dense bounded photos, browser image fallback, password retry and cancelled OCR responses. Run them with `npm test -- --runInBand --runTestsByPath src/components/aadhaar/useAadhaarDecode.test.js src/components/AadhaarScanner.test.js src/components/aadhaar/liveScan/grabFrame.test.js src/components/aadhaar/liveScan/wasmDetector.test.js`.
