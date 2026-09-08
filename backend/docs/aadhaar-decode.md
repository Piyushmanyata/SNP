# Aadhaar QR capture

The decoder accepts the existing legacy XML and compressed numeric Secure QR formats. The former `AADHAAR|...` demo parser has been deleted. Demo strings now return `garbage` and cannot populate a registration through the scan endpoint. Tests use equivalent legacy XML fixtures, with explicit regression coverage proving demo strings are rejected.

No production configuration can re-enable the demo format. This avoids carrying a test-only parsing branch or an accidental production enablement switch.

This module extracts card fields for registration; it does not authenticate the card holder or cryptographically verify UIDAI signatures. Existing bounded decompression, native field normalization and last-four-digit handling remain unchanged. Secure QR and legacy XML regression fixtures establish parsing behavior, not authenticity.

Validation: Aadhaar, material-difference, camp-lifecycle, hardening and adversarial targeted suites passed after fixture migration. The live HTTP suites use equivalent XML input and must be run against the rebuilt API by the integration harness.

## Versioned Secure QR fields

The numeric decoder accepts the unversioned indicator-first layout and the `V2`, `V3`, `V4`, and `V5` version-prefixed demographic layout. It consumes the version before mapping the 16 demographic fields, preserving empty address segments and stopping before optional mobile/photo/signature data. Gzip, zlib, raw deflate, UTF-8 names, and whitespace inserted by USB scanners remain supported.

Before returning `outcome: card`, Secure QR parsing requires all demographic delimiters, an indicator from 0–3, an 18- or 21-digit reference, a printable name containing letters and no digits, a supported gender, and a valid nonfuture birth date/year. Malformed or unsupported layouts return `garbage` without identity data. A numeric reference can never become a locked name. The response shape is unchanged for the decode endpoint, desk scan/lock routes, and self-registration.

This is field extraction, not UIDAI signature verification. The synthetic fixtures cover field alignment and rejection behavior; they cannot guarantee capture from every damaged, blurred, or glared card.

## Decision: parse the version at the shared boundary

Context: a leading version shifted the reference into `full_name`, the name into DOB, and DOB into gender; the API still returned `card`. The registration UI then correctly locked those incorrect values.

Decision: handle the explicit version header and validate the demographic structure in `parse_secure_qr`. Reject heuristic searches for a plausible name or a UI-only correction: either can hide incorrect reference/address fields or miss USB and self-registration callers.

Consequence: known layouts decode consistently across input methods; unknown or incomplete layouts require rescanning. No database schema or index migration is required. Existing numeric-name records, if any, require a fresh card scan; a reference number alone cannot reconstruct the person's identity. Raw Aadhaar payloads are not persisted for repair.

References: [UIDAI field inventory](https://uidai.gov.in/en/306-faqs/aadhaar-online-services/secure-qr-code-reader-beta/10781-what-is-uidai-secure-qr-code-how-qr-code-enhance-the-security-of-e-aadhaar.html) and [PyAadhaar version-prefix parsing implementation](https://github.com/tanmoysrt/pyaadhaar/blob/main/pyaadhaar/decode.py). Regression coverage uses synthetic records only.
