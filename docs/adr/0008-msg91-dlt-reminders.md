# ADR 0008: MSG91 DLT for Devanagari reminders

Camp reminder, OT reminder, and Specs reminder send through MSG91 DLT transactional SMS. Template IDs and auth live in env. One ledger row per send.

## Rejected alternatives

- A second SMS provider — DLT templates are registered per-PE and per-header; swapping later is a TRAI process, not a code switch.
- SMS at registration or at Token print — out of scope; D-1 at 10:00 IST only.
