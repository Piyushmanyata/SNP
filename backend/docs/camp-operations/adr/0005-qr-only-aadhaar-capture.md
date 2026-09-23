# QR-only Aadhaar capture

Decision accepted 23 September 2026. Supersedes the OCR portion of [0002](0002-reviewed-aadhaar-capture.md) and the reviewed-text path discussed in [0003](0003-manual-entry-as-a-recovery-route.md).

Camera, USB scanner, and uploaded JPEG, PNG, HEIC/HEIF photos and e-Aadhaar PDFs continue to decode Aadhaar QR codes. The document endpoint returns card data only when it finds a readable QR. It returns `QR_NOT_FOUND` when it does not. Password-protected PDFs remain supported. Uploaded bytes and PDF passwords are not retained.

Staff can enter patient details manually when QR reading fails. Manual details remain subject to the existing validation and desk identity recheck. The public self-registration page still requires a readable QR and directs patients to the desk when capture fails.

Remove Tesseract processing, review suggestions, and the OCR review form. The alternative of retaining OCR as a fallback was rejected because the user wants QR decoding only. Browser and backend QR readers remain so large photos, HEIC files and PDFs can still be used without text extraction.
