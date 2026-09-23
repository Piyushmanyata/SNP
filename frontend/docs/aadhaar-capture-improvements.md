# Aadhaar QR capture

Status: QR-only behavior adopted 23 September 2026. See [ADR 0005](../../backend/docs/camp-operations/adr/0005-qr-only-aadhaar-capture.md).

Camera, USB/paste, phone photos, HEIC/HEIF images and e-Aadhaar PDFs are QR inputs. Browser native and WASM readers handle eligible photos; the backend reads larger photos, HEIC files and PDFs. A password prompt lets the user retry an encrypted PDF without retaining its password. The scanner never extracts printed text or offers OCR suggestions.

If a QR cannot be read, staff can enter patient details manually in the desk registration form. The existing manual-entry validation and identity recheck apply. Public self-registration still requires a readable QR and directs the patient to the desk when capture fails. QR parsing alone does not verify a cryptographic signature.

Starting a new scan, changing capture modes, leaving the page or choosing manual entry invalidates earlier responses. A late upload result must not overwrite newer identity or loading state. The upload and backend processing limits are described in [document extraction](../../backend/docs/aadhaar-document-extraction.md).

Focused verification covers QR reading across current inputs, PDF password retry, unreadable QR fallback, cancellation and stale responses. Real camera focus and card quality still need testing with consented representative devices and cards; synthetic tests cannot establish a universal success rate.
