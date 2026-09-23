# ADR 0048: Both decoders race, the reader is warm before the camera, and the door reads in one round trip

**Amends ADR 0004, ADR 0005, ADR 0023 and ADR 0034.**

## Context

Registration is the camp's front door, and a scan is the whole registration. Volunteers reported that the phone camera was slow to Lock and sometimes never did, that photo upload took seconds, and that USB scans at the door felt sluggish. Reading the live-scan path end to end found causes in the code, not in the phones:

- **The platform detector was abandoned after 1.25 s.** ADR 0004 promoted from `BarcodeDetector` to WASM after eight misses or 1.25 s and never went back. Holding a card steady takes longer than that, so every Android phone ended up on the slower WASM reader, and the Android detector, which is the fastest reader we have, was thrown away just before the card came into focus.
- **A still photo every three seconds blocked the loop.** `ImageCapture.takePhoto()` ran on every "full" frame after three seconds. On Android it takes from half a second to two seconds, refocuses the lens and can freeze the preview. Its result was then discarded for any photo over 4 MP, which is every phone photo.
- **The WASM reader was killed on a slow network.** The 4 s per-frame timeout also covered downloading and compiling the 940 kB reader. On a camp connection the first frame always timed out, the worker was terminated mid-download, nothing was cached, and the next frame started the download again. Live scan and photo upload could never succeed there.
- **Photo upload skipped the browser.** Local decoding was gated at 4 MP, so every real phone photo went to `/aadhaar/extract` as a multi-megabyte upload.
- **The door paid two round trips.** The scanner POSTed `/aadhaar/decode`, and the door then POSTed the same payload to `/desk/scan`, which decodes it again.
- **Dense Secure QR needs distance.** Filling the guide box with a 3 cm QR at 1× puts the phone closer than most lenses can focus.

## Decision

- **Two lanes, one race.** Live scan runs the platform `BarcodeDetector` on the video element and the WASM reader on Guide ROI / full-frame pixels at the same time, each with exactly one detect in flight. The first payload to arrive goes to Soft Hold and Decode; the other lane's result is dropped while Decode runs. A lane that cannot load (no `BarcodeDetector`, one that does not list `qr_code`, or a reader that fails to compile) drops out; when every lane has dropped out the camera stops and offers recovery. There is no promotion and no miss counter.
- **The reader is warm before the first frame.** Starting the camera starts the WASM worker, which compiles the module immediately and reports `ready`. Loading has its own 45 s allowance; the 4 s per-frame timeout only starts once the reader is ready. A worker that stalls on a frame is still replaced.
- **No still photos during live scan.** `ImageCapture` is not used.
- **2× zoom where the camera offers it.** If the track exposes `zoom`, live scan starts at twice the minimum, so the card fills the box at a distance the lens can focus. One tap on the zoom button returns to 1×. Tapping the preview asks for focus at that point. The guide box is drawn from the same 90 % short-edge square the reader crops.
- **Photos are read on the phone at full resolution.** A JPEG or PNG up to 16 MP (read from its header) goes to the platform detector as a bitmap and then, whole, to the WASM worker, which decodes the file itself with downscale tries for large images. Only PDFs, HEIC, larger or unreadable images, and photos where no QR was found are uploaded. Phones get a **Take photo** button that opens the camera app directly; the camera app focuses better than any preview stream.
- **The door reads in one round trip.** The door passes its own resolver to the scanner. Any Aadhaar payload, from the camera, a photo or the USB box, goes straight to `/desk/scan`; a 400 `NOT_A_CARD` is a Failure like a `garbage` Decode. `/desk/scan` already decodes the payload server-side (ADR 0043), so nothing is lost.
- **On a laptop the door opens with the USB box ready and focused.** It stays visible, clears after every scan and takes focus back, so the imager needs no button press per patient. A phone door opens on the camera button. Registration keeps its ambient wedge listener (ADR 0023); once a burst is recognised, its keystrokes no longer reach the focused field, and only the few characters typed before recognition are scrubbed.
- **A Lock is felt.** The phone vibrates and plays a short tone on a camera Lock.

## Consequences

A phone with `BarcodeDetector` Locks as fast as the platform detector can read, and a phone without one (iPhone, desktop Chrome) has its reader compiled before the camera shows a picture. The two lanes use two cores for the few seconds a scan takes; that is the price of not guessing which reader will see the card first.

A slow network now delays the WASM lane instead of disabling it, and after the first successful load the reader comes from the browser cache.

The door's scan status comes from the scanner's own busy state, and a new capture abandons a `/desk/scan` still in flight.

ADR 0003's field acceptance criterion (≥95 % Lock within 3 s on the three phone tiers) is unchanged and still measured on real cards.

## Rejected alternatives

- **Keep promotion but raise the limit.** Any limit is a guess about how long a volunteer takes to steady a card; running both lanes removes the guess.
- **Keep `takePhoto()` with a smaller photo size.** Still slow, still refocuses the lens mid-scan, and the preview stream at 1080p already carries enough pixels for the Guide ROI.
- **Auto-zoom by measuring the QR.** Needs a detect to size against, which is exactly what fails when the QR is too small; a fixed 2× with a one-tap 1× is predictable.
- **Keep two round trips at the door for a uniform scanner contract.** One network round trip per patient, a thousand times a day, for symmetry.
- **An ambient, invisible USB listener at the door.** ADR 0034 rejected it and the reason stands; a visible, focused box gives the same zero-press flow and shows what arrived.
