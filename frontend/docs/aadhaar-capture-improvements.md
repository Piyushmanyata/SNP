# Aadhaar capture improvements

Status: implementation under verification, 8 September 2026. Scope confirmed by the user.

> **Partly superseded by [ADR 0033](../../docs/adr/0033-a-lock-is-the-identity-evidence-taken-once.md).** The public self-registration page no longer offers reviewed transcription or manual entry of any kind: `/self-register` refuses a submission without a readable QR with 400 `AADHAAR_QR_REQUIRED`, and the patient is sent to the desk. Every clause below about public review, public manual provenance, or a public desk-recheck receipt is history, not current behaviour. The **staff** capture, OCR and reviewed-transcription paths described here are unchanged and still in force.

## Agreed scope

Improve camera scanning and photo uploads across phones, expose USB scan progress while printing is open, and make the SNP Camps heading return to the existing role-specific home page.

When QR capture fails, offer OCR suggestions with mandatory submitter review before saving. For staff registration the operator reviews. OCR suggestions must not become locked or verified card identity. (Public review was withdrawn by ADR 0033.)

Run OCR on the existing backend without retaining uploaded photos. Manual registration must be available immediately, without waiting for three failed scans. Both decisions were confirmed by the user. The immediacy clause was later narrowed for the public page: see [ADR 0003](../../backend/docs/camp-operations/adr/0003-manual-entry-as-a-recovery-route.md).

Include JPEG, PNG and iPhone HEIC photos, English/Hindi text extraction, and e-Aadhaar PDF uploads. Ask for a password when a PDF requires one; do not retain passwords or documents. The user selected photos and PDFs during the discussion.

Staff registration only. ADR 0033 withdrew the public typed and reviewed paths: a patient whose QR will not read is sent to the desk, which keeps the capture, OCR and review routes described here.

The backend assigns OCR/manual provenance on the **desk** path: `aadhaar_scanned=False`, `manual_entry=True`. `identity_recheck_required` and the desk identity check before the first stamped prescription are preserved, as are mobile validation, active day/capacity checks, duplicate detection and request replay. Manual name and age/DOB are validated server-side; unknown Aadhaar digits remain optional.

## Language

**Reviewed Aadhaar transcription**: Details extracted from the printed text on an Aadhaar image and checked or corrected by the submitting patient or staff member. This does not establish that the document is authentic or that staff have verified it.

**Received Aadhaar QR**: A complete QR payload captured from a camera, image, or USB scanner. Receipt alone does not mean its contents have been accepted or its signature verified.

## Issues addressed

- USB capture previously waited for the terminating Enter/Tab before showing any activity. The hook now exposes receiving status and interruption feedback; the desk shows an accessible spinner through transmission and server processing.
- The brand previously rendered as plain text. It now returns to `/`, which already resolves each signed-in user's home page.
- Photo processing previously allocated full-size pixel buffers and copied them to the worker. Frames are bounded and worker buffers are transferred. Source image dimensions must be checked before local decoding; unknown/large documents use the backend.
- Native photo-detector exceptions previously skipped the WASM fallback. Detection now recovers through that fallback, then offers backend document reading and reviewed text suggestions.
- Worker timeouts now terminate/reset the stalled worker so later frames do not queue behind it.
- `../../backend/aadhaar.py` explicitly states that parsing does not verify the RSA signature. Accepted QR fields must not be described as cryptographically verified.

## Behavior

1. USB: ready, receiving data, decoding/checking registration, then result or actionable failure. Show an accessible spinner and status while receiving and processing. Start receiving feedback only when keyboard activity can reasonably be identified as a scanner burst. Do not display or log raw QR digits. An ordinary keyboard-wedge scanner cannot expose its internal optical decoding before it sends data.
2. Keep scanner detection separate from ordinary typing. Cover long payloads, interrupted transmission, supported terminators, duplicate scans and overlapping requests. Avoid a fake percentage when total length is unknown.
3. Camera and upload: recover from native-decoder failure using the existing WASM decoder; recover or replace timed-out workers; cap image-processing work and use staged attempts that retain dense-QR detail. Distinguish unreadable QR, unsupported image, camera denial, decoder failure and server/network failure.
4. OCR: offer editable suggestions when QR capture fails. Process JPEG/PNG/HEIC photos and e-Aadhaar PDFs on the existing backend without retaining documents or PDF passwords. Try QR extraction before text transcription. Require explicit review; retain the existing manual-entry identity semantics and last-four-only Aadhaar storage. Do not infer missing fields or silently submit extracted text. Allow immediate manual registration at the desk. The public page offers no typed or reviewed path at all (ADR 0033); a failed read tells the patient to register at the desk.
5. Home navigation: make the brand an accessible link to `/`, using the existing role routing.

Switching files, changing capture modes, choosing manual entry, leaving the page, or starting to edit must invalidate superseded recognition results. A late QR/OCR response must never overwrite reviewed/manual fields or clear a newer request's loading state. Keep the existing scanner cancellation behavior and extend it to the new upload/review path.

These behaviors do not establish performance guarantees. Browser and image support still need a representative device and card test matrix; damaged or out-of-focus QR images require fallback.

## Backend integration

The backend uses bounded Tesseract processing with English/Hindi language data, HEIC conversion and PDF rasterization. PDFium work is isolated in a subprocess. Upload, pixel, page, execution-time and concurrency limits protect registration traffic; public extraction is rate limited. Only `/api/aadhaar/extract` accepts up to `12m` at nginx, with request/response buffering disabled and a `35s` upstream timeout. Other API upload limits remain separate.

See [primary-source OCR research](../../backend/docs/aadhaar-ocr-research.md). Tesseract is invoked through its command-line interface; no paid OCR provider or separate OCR service is used. Do not claim a recognition rate from synthetic tests.

## Evidence limits

- Assess backend OCR dependencies and capacity. Temporary processing data must be cleaned up, excluded from logs and backups, and never treated as stored patient photographs.
- Representative oldest phones and browser versions, and measured timing and success targets. Preserve browser-native and WASM paths; manual entry remains available when capture is unsupported.
- Cryptographic signature verification is not established by this proposal; existing parsing and reviewed transcription must not be represented as signature verification.
- No universal recognition rate or phone-speed guarantee has been established.

## Verification plan

Add targeted regressions for receiving status before the terminator, status cleanup, ordinary typing, native-to-WASM recovery, worker timeout recovery, bounded image handling, reviewed OCR without identity locking, late OCR responses after editing/manual fallback, public refusal without a readable QR, desk recheck enforcement, and role-home navigation. Run the repository's typecheck, lint and test gates and parallel correctness/simplicity reviews for implementation.

Measure capture-to-result timings and success rates on authorized test cards across the agreed phones, lighting and image quality. Synthetic tests cannot establish real camera focus or universal card support. Do not use real Aadhaar data in committed fixtures or logs.

## Sources

- [UIDAI Secure QR reader FAQ](https://www.uidai.gov.in/en/contact-support/have-any-question/306-faqs/aadhaar-online-services/secure-qr-code-reader-beta%20.html): Secure QR includes holder details and a digital signature.
- [MDN BarcodeDetector](https://developer.mozilla.org/en-US/docs/Web/API/BarcodeDetector): native detection has limited browser availability.
- Existing design: `../../docs/adr/0003-browser-aadhaar-secure-qr-capture.md` retains browser scanning and camera alternatives.
