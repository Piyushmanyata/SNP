# Reviewed Aadhaar document extraction

Status: implemented, 8 September 2026. Device/corpus accuracy and production capacity are not yet established.

## Decision

Use one bounded Python subprocess per backend process, containing Pillow, HEIF/PDF conversion, ZXing QR reading and Tesseract English/Hindi text extraction. This keeps native parsing and OCR outside the API event loop and lets production Linux terminate the complete process group on deadline or cancellation. A new OCR service and PaddleOCR inference stack were rejected because this deployment already has a CPU backend and the simpler runtime has not yet been shown inadequate by representative-card measurements. See [research](aadhaar-ocr-research.md).

The Python ZXing binding accepts Pillow images and supports QR-only searches. This complements browser decoding for HEIC/PDF input without another image conversion dependency. [Binding API](https://github.com/zxing-cpp/zxing-cpp/blob/master/wrappers/python/zxing.cpp)

## Interface and provenance

`POST /api/aadhaar/extract` accepts raw JPEG, PNG, HEIC/HEIF or PDF bytes, checked by file signature. It does not accept multipart or base64 JSON. `X-PDF-Password` optionally carries a percent-encoded UTF-8 PDF password, passed to the worker through stdin and never through process arguments.

- Readable Aadhaar QR: `{outcome: "card", data, payload, source}`. Parsing does not establish cryptographic authenticity.
- Text fallback: `{outcome: "review", data, message}`. Suggestions contain only supported name, DOB, gender, last-four and address fields. Low-confidence words are omitted. Unknown fields remain absent. Raw OCR text, source photos and passwords are not returned or saved. Every suggestion requires review; it never creates or locks a person.
- Errors use `detail: {code, message}`: `413 DOCUMENT_TOO_LARGE`, `415 UNSUPPORTED_DOCUMENT`, `422 UNREADABLE_DOCUMENT`, `422 PDF_PASSWORD_REQUIRED` for missing/wrong PDF passwords, `422 INVALID_PASSWORD`, `429 OCR_BUSY/RATE_LIMITED`, `503 OCR_UNAVAILABLE`, `504 OCR_TIMEOUT`. Disconnected clients cancel their work (`499 REQUEST_CANCELLED`). Error messages do not contain document contents or passwords.

Public `/api/self-register` independently decodes supplied QR payloads. Without a readable QR, it validates reviewed manual fields and forces `aadhaar_scanned=False`, `manual_entry=True`, and `is_self_registered=True`; client provenance flags cannot create a scanned person. Manual submissions require a nonblank name, valid household mobile, and age 0–130 or valid DOB/year. Conflicting age/DOB must be corrected. Optional Aadhaar digits must be exactly four. Existing camp/day, capacity, duplicate, replay and first-prescription staff identity recheck behavior remains in force.

## Resource and retention boundaries

Requests stream into memory with a 12 MiB cap and 30-second total deadline. There is one active extraction per API process; excess work receives actionable 429 feedback. Public callers are limited to 12 attempts per IP per ten minutes with a bounded 2,048-IP window. Production already trusts the internal reverse proxy's forwarded client address; the backend must remain behind that proxy.

The worker rejects more than two PDF pages and more than 24 million decoded pixels per document. PDF pages render at 216 DPI. PDFium runs in the isolated worker, so no parallel threads enter PDFium. Linux applies a 1 GiB address-space ceiling and 25 CPU seconds per process, inherited by the OCR child, with disabled core dumps and a zero file-write limit. These are per-process limits, not an aggregate memory reservation. Tesseract uses fixed arguments, one OpenMP thread and stdin/stdout with a 20-second per-call limit. OCR output is capped at 2 MiB and the API worker response at 128 KiB. Windows supports development checks; production process-group/resource guarantees apply to Linux.

No documents, normalized photos, OCR text or passwords are written by application processing. Reverse-proxy request buffering and upload limits must match the extraction path; omitting a database write alone does not prove end-to-end no retention. Do not enable request-body/header logging or put extraction documents in backups. The Docker build installs Tesseract English/Hindi models and checks their presence. Pinned Python packages are in `requirements.txt`.

## Verification

`tests/test_aadhaar_extract.py` exercises real synthetic QR images, HEIC, PDF and a password-protected synthetic PDF; reviewed transcription through a mocked OS OCR boundary; upload/page/rate limits; timeouts and disconnect cancellation. `tests/test_self_register_review.py` covers forced provenance, invalid fields, duplicate privacy and idempotent retries. `tests/test_desk_scan_first.py` updates the public manual-registration contract. `tests/fixtures/aadhaar-password.pdf` contains only fictional Test Patient data and has the test password `TEST 1234`.

The actual Tesseract runtime and full deployment tests must pass before rollout. No synthetic test establishes universal card support, a recognition percentage, or low-end-phone speed. Measure representative consented cards/devices, correction rates, worker memory and shared-server latency before changing limits or advertising performance.
