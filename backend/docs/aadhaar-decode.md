# Aadhaar QR capture

The decoder accepts the existing legacy XML and compressed numeric Secure QR formats. The former `AADHAAR|...` demo parser has been deleted. Demo strings now return `garbage` and cannot populate a registration through the scan endpoint. Tests use equivalent legacy XML fixtures, with explicit regression coverage proving demo strings are rejected.

No production configuration can re-enable the demo format. This avoids carrying a test-only parsing branch or an accidental production enablement switch.

This module extracts card fields for registration; it does not authenticate the card holder or cryptographically verify UIDAI signatures. Existing bounded decompression, native field normalization and last-four-digit handling remain unchanged. Secure QR and legacy XML regression fixtures establish parsing behavior, not authenticity.

Validation: Aadhaar, material-difference, camp-lifecycle, hardening and adversarial targeted suites passed after fixture migration. The live HTTP suites use equivalent XML input and must be run against the rebuilt API by the integration harness.
