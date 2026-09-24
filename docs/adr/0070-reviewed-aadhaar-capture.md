Renumbered from `backend/docs/camp-operations/adr/0002-reviewed-aadhaar-capture.md`.

# Reviewed Aadhaar transcription on the existing backend

Historical decision. The OCR and reviewed-text portions were superseded on 23 September 2026 by [0005](0005-qr-only-aadhaar-capture.md).

Design decision accepted during the 8 September 2026 discussion; implemented on the same date.

Unreadable QR codes must not prevent registration. Add OCR suggestions with mandatory review and immediate manual entry to staff and public registration. Run extraction on the existing backend to reduce processing demands on low-end phones, and do not retain uploaded documents or PDF passwords. Cover phone photos and e-Aadhaar PDFs. Browser-only OCR was declined because it places recognition work on the phone; third-party OCR was declined in favor of the existing backend.

OCR and manual text are transcribed identity, not verified Secure QR data. Assign provenance on the server and preserve the existing desk identity recheck before printing the first stamped prescription for these public submissions. Public OCR needs bounded processing and rate limits; document processing depends on connectivity and backend capacity.

Both registration paths share one server-side identity check for reviewed and manual submissions, because reviewed transcription now reaches the desk `/register` route as well as public `/self-register`. It normalises the name and accepts a date of birth only as `YYYY-MM-DD` or a four-digit year, deriving age when the submitter left it blank. A four-digit year is a supported stored value: many Aadhaar cards print only a year of birth. Rejecting free text here keeps the equality-based duplicate and person-match queries meaningful.

The stricter public-only rules stay on `/self-register`: age must agree with the date of birth, and gender, address and last-four digits are constrained. The desk keeps its existing tolerance — operator-entered age need not agree with the date of birth, and gender words are normalised — because the desk resolves those differences through its mismatch review rather than by refusing the registration.

See [capture design](../../../../frontend/docs/aadhaar-capture-improvements.md) and [OCR research](../../aadhaar-ocr-research.md). The engine choice and performance claims remain subject to implementation validation.
