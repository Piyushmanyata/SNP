# ADR 0063: Registration trusts only what the server can check

**Amends ADR 0035.** Issue #50, slice S5. **Amended by ADR 0084:** the reason is one of four codes, there is no door gate, and Arrival refuses a typed pre-registration with `NEEDS_DOOR_SCAN` until a card or a No-card print.

## Context

- The browser sent `failed_scan_attempts`, and the server accepted a Manual entry after three. Any client could send `3`. At the door, the same count forced three failed camera scans per patient even with the Door manual gate open. ADR 0035 said the door has no failure counter; the code still had one.
- A door scan matched on last-4 + DOB and stamped Arrival on the first hit. Two people who share both were checked in as each other.
- Year-only Aadhaar DOBs collapse to `YYYY-01-01`. The "last-4 + DOB" duplicate rule refused real, different patients, with no override.
- The registration desk overwrote a Manual entry with any card, silently, even after print.
- Walk-in used the IST calendar date. After midnight on a late camp day, staff registrations were treated as bookings and sent SMS.
- Phone fields cut input to 10 digits as typed. A pasted `+91 98765 43210` became `9198765432`, another household's number.
- Public endpoints took unbounded payloads and 300 self-registrations per IP per 10 minutes, each sending an SMS. One slow upload held the single document-reading slot for every desk.

## Decision

- **Manual entry needs a reason, not a count.** An unscanned staff registration needs a non-empty `manual_reason` (≤ 200 characters). At the door it also needs the Door manual gate open (403 `DOOR_MANUAL_SHUT`). It is always saved with `identity_recheck_required`. `failed_scan_attempts` is gone from the API. The registration desk's three-Failure reveal stays as desk UX only. With the gate open, the door's typed form shows at once. A typed door entry is for the Operating day only (409 `NOT_OPERATING_DAY`) and is arrived when it is saved.
- **Arrival needs evidence.** `/desk/arrive` refuses a Manual entry with neither a scan nor an Identity check (409 `IDENTITY_CHECK_REQUIRED`), unless it was typed at the door with the gate open.
- **A door scan arrives only the same Person.** Any other scanned registration it matches goes to Mismatch review, never straight to Arrival. Confirming that review arrives the registration and keeps its stored card, because it was already scanned once (the same person can hold an XML card with a birth year and a Secure QR with a full date).
- **Duplicate in camp** is Person, last-4 + name (word order ignored), or name + age + household phone. The standalone last-4 + DOB rule is deleted.
- **Every Aadhaar overwrite with a material diff goes through Mismatch review**, at the door and at the registration desk (409 `MISMATCH_REVIEW_REQUIRED` with the card, the stored row and the diff; the desk resubmits with `review_confirmed_id`). No overwrite happens after print or Doctor seen (409 `ALREADY_PRINTED`). The overwrite stores the request id, so a network retry replays.
- **The Operating day decides.** A staff registration on the Operating day is a walk-in (no SMS, no seat block). A past day that is not the Operating day takes no bookings (409 `DAY_PASSED`).
- **One household phone rule, on the server.** Strip non-digits; accept an optional `91` or `0` prefix; keep 10 digits starting 6–9; refuse anything else. The client keeps what was typed, checks it with the same rule (`lib/phone.js`) and sends the canonical value.
- **Public limits.**
  - Payloads are capped at 16,000 characters; names (100), addresses (300) and reasons are bounded. A decoded card is cut to the same name and address limits, so a long card address never fails a scan.
  - Anonymous `/aadhaar/decode` is limited to 60 per network per 10 minutes. A staff session is never limited, because the desks share one venue IP.
  - Self-register is limited to 30 per network per 10 minutes and 6 per household phone per camp (409 `HOUSEHOLD_LIMIT`).
  - A number gets at most 6 registration SMS per IST day. The ledger row is `skipped` with reason `daily_cap`.
  - Document extract reads and size-checks the whole body before it takes one of two slots; nginx buffers the upload.
  - The limiters live in memory, which needs one uvicorn worker (ADR 0060).
- **Login and PIN change answer with the cookie only.** An unknown name still checks a dummy hash.

## Consequences

- A volunteer can create a Manual entry by typing a reason. The server cannot tell a real reason from a made-up one, so it records the reason and the volunteer, and the identity hold still blocks print until a card or an admin's Identity check.
- Two people with the same name, last-4 and DOB can still collide at the door. Mismatch review shows the stored row next to the card, so the volunteer decides.
- A family larger than six must register the rest at the desk.
- A restart clears the rate-limit counters. That is acceptable: they limit bursts, not totals.

## Rejected alternatives

- **Count failed scans on the server.** The server sees only decode requests, not camera attempts, so it would still be counting what the client chose to send.
- **Keep last-4 + DOB with an override.** An override at a 20-second door becomes the default answer.
- **Per-IP limits for staff too.** Ten desks behind one venue router would lock each other out.
- **Redis-backed limiters.** A new service for a one-VPS deployment. Revisit if the API ever needs a second worker.
