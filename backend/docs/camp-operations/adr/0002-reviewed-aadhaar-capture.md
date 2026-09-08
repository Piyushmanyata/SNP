# Reviewed Aadhaar transcription on the existing backend

Design decision accepted during the 8 September 2026 discussion; implementation is pending final shared understanding.

Unreadable QR codes must not prevent registration. Add OCR suggestions with mandatory review and immediate manual entry to staff and public registration. Run extraction on the existing backend to reduce processing demands on low-end phones, and do not retain uploaded documents or PDF passwords. Cover phone photos and e-Aadhaar PDFs. Browser-only OCR was declined because it places recognition work on the phone; third-party OCR was declined in favor of the existing backend.

OCR and manual text are transcribed identity, not verified Secure QR data. Assign provenance on the server and preserve the existing desk identity recheck before printing the first stamped prescription for these public submissions. Public OCR needs bounded processing and rate limits; document processing depends on connectivity and backend capacity.

See [capture design](../../../../frontend/docs/aadhaar-capture-improvements.md) and [OCR research](../../aadhaar-ocr-research.md). The engine choice and performance claims remain subject to implementation validation.
