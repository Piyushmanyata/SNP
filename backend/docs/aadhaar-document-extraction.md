# Aadhaar QR extraction from documents

Status: implemented, 23 September 2026. [ADR 0073](../../docs/adr/0073-qr-only-aadhaar-capture.md) records the removal of OCR.

## Interface

`POST /api/aadhaar/extract` accepts raw JPEG, PNG, HEIC/HEIF or PDF bytes, checked by file signature. `X-PDF-Password` optionally contains a percent-encoded UTF-8 password. The password travels to the isolated worker through stdin and is not passed in process arguments.

- Readable Aadhaar QR: `{outcome: "card", data, payload, source}`. Parsing does not establish cryptographic authenticity.
- No readable QR: `422 QR_NOT_FOUND`. Staff may enter details manually. Public self-registration requires a QR and directs the patient to the desk.
- Other errors use `detail: {code, message}`: `413 DOCUMENT_TOO_LARGE`, `415 UNSUPPORTED_DOCUMENT`, `422 UNREADABLE_DOCUMENT`, `422 PDF_PASSWORD_REQUIRED`, `422 INVALID_PASSWORD`, `429 QR_BUSY/RATE_LIMITED`, `503 QR_UNAVAILABLE`, `504 QR_TIMEOUT`. A disconnected client cancels its work (`499 REQUEST_CANCELLED`). Error messages do not contain document contents or passwords.

## Processing and retention

The bounded Python worker uses Pillow, HEIF/PDF conversion and ZXing QR reading. PDFium runs in the worker process. Uploads have a 12 MiB cap and a 30-second total deadline. One extraction runs per API process; public callers are limited to 12 attempts per IP per ten minutes within a bounded 2,048-IP window.

The worker rejects PDFs with more than two pages and images with more than 24 million decoded pixels. PDF pages render at 216 DPI. On Linux the worker has a 1 GiB address-space ceiling, 25 CPU seconds, disabled core dumps and a zero file-write limit. Uploaded documents and passwords are not stored by application processing. Reverse-proxy request buffering and logging must also avoid retaining them.

## Verification

`tests/test_aadhaar_extract.py` exercises real synthetic QR images, HEIC, PDF, a password-protected synthetic PDF, unreadable QR, upload/page/rate limits, timeouts and disconnect cancellation. The fixture contains only fictional Test Patient data. Synthetic tests do not establish universal card support; representative consented devices and cards are still needed to measure reading success.
