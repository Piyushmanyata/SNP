# ADR 0011: Hard Duplicate in camp and in-place Aadhaar overwrite

## Context

Desk New Registration showed the typed form next to the scanner and a volunteer checkbox that pretended two scans failed. A soft name+age check offered “Register anyway”, so duplicates slipped through. There was no later path to put a real Aadhaar Lock onto that same `reg_no`.

## Decision

- Capture-first: typed form is hidden until two Decode Failures (`garbage` or `not-aadhaar`) or a Lock. Empty Detect misses are not Failures. Closing the popup resets the count. The scanner stays after the form appears.
- Manual entry is a mark on the row. No reason field, no admin gate. Self-register still requires a Lock.
- Duplicate in camp is hard on desk and self-register: Person-in-this-camp, last-4 + normalized name, last-4 + DOB, or normalized name + age + household phone. 409 with the existing `reg_no`. No override flag. Phone-only and name+age-without-phone do not hard-block.
- A Lock that matches exactly one Manual entry updates that `reg_no` in place (card identity fields; keep household phone, camp day, `reg_no`, queue/print/seen; clear Manual entry; attach Person). It does not consume a second camp-day seat and does not auto-reprint. Already-scanned match 409s. Two Manual matches 409 and list them. None match creates a new registration.

## Consequences

Volunteers cannot type a patient before trying the card. A later Lock repairs a Manual entry without a second paper identity. Camp-day capacity counts overwrites as the same seat.

## Rejected alternatives

- Volunteer checkbox for “two failed scans” — people ticked it without scanning.
- “Register anyway” — made Duplicate in camp optional.
- A separate “Scan Aadhaar” / bind screen — a second resource and desk flow for what is the same register request.
