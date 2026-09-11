# ADR 0033: A Lock is the identity evidence, and it is taken once

**Amends ADR 0012.**

## Context

The camp's identity evidence is a Lock: a successfully decoded Aadhaar secure QR. Everything else — a transcription reviewed on screen, a typed name and age — is a claim, not evidence. Two places had drifted from that.

**The public page could mint claims.** `/self-register` accepted a submission with no readable QR: it validated the typed fields, marked the row `manual_entry` with `identity_recheck_required`, and created it. The desk-scan-first spec says the opposite in as many words — "Self-register continues to require a Lock and has no typed path", user story 11, "so that the public page cannot mint typed junk rows" — but a later OCR-review feature reopened the path. An unauthenticated endpoint that creates patient rows from typed identity is the one place in this system where a claim costs nothing to make.

**The desk retook evidence it already had.** ADR 0012 says "Arrival is stamped by a desk Lock that matches a registration in this camp." Taken literally, a patient who self-registered from home by scanning their own card — a Lock, decoded by the server, already on file — had to produce the same card again at the door before anything would print. `PatientRow` hid Print and said "Scan their card at the door to check in" for every unarrived booking regardless of how it was made. On a camp morning that is a queue of people re-presenting cards the system has already read, to prove something it already knows.

## Decision

One rule, applied in both directions.

- **Only a Lock counts.** `/self-register` refuses any submission whose `qr_payload` does not decode as a card: 400 with code `AADHAAR_QR_REQUIRED`. The refusal is unconditional — no combination of client-supplied `aadhaar_scanned`, `manual_entry` or `manual_exception` flags reaches the create path. The public page's typed affordance and its reviewed-details form are deleted; a failed read tells the patient to register at the camp desk. A caller that supplies no `onTranscribed` has no transcription route, so for that caller the decoder's `review` outcome **is a Failure**: `useAadhaarDecode` reports it through `onFailure` instead of holding it as review data. The desk keeps the OCR recovery route; the public page has no route to it and, crucially, no silent dead end where a card OCRs but will not decode.
- **A Lock is taken once.** A registration with `aadhaar_scanned` true may be checked in and printed from a name or number lookup, with no door re-scan. The desk control is "Check in & print"; it stamps Arrival through the existing `/desk/arrive/{id}` and goes to the sheet. Arrival is still a real state, still stamped once, still subject to the print window and the operating-day move.
- **A Manual entry still needs a Lock at the door.** It has none on file, so it keeps "Scan their card at the door to check in" and no print control. Its `identity_recheck_required` mark continues to refuse the print until an admin records an identity check.
- **`/desk/arrive` is not narrowed.** It stays open to staff for any registration, because the door walk-in path registers a typed patient and arrives them in one action. The gate that protects a Manual entry is `identity_recheck_required` at print time, which already exists and already works.
- **The desk does not offer a control it knows will fail.** While the print window is closed, both the patient row and the door scan card replace Print with "The print window is closed." A registration that already has `printed_at` keeps its button, because the server still permits that reprint and a lost sheet is exactly when the desk needs it.

## Consequences

Self-registration is now all-or-nothing: a patient whose card will not scan cannot register from their phone at all, and must go to the desk. That is a real loss of reach, and it is the point — the desk has a USB imager, a photo-upload path, an OCR review and a volunteer, and it produces a `manual_entry` row that is marked, counted, and blocked from printing until an admin looks at the patient. The public page produced the same row with nobody looking.

Existing rows are unaffected and no migration is required. A self-registered `manual_entry` row created before this change keeps `identity_recheck_required` and is still unblocked by the admin identity check. A row predating the `aadhaar_scanned` field reads as `False` and falls back to the door scan, which is the safe direction.

The desk's camp-morning path for a pre-registered patient is now: look them up, press one button. The queue no longer forms around re-presenting cards.

Withdrawing Print when the window is closed removes a class of dead-end click where the volunteer navigated to the sheet and got a 409 there. The server-side `PRINT_WINDOW_CLOSED` guard is unchanged and remains the authority; the UI now agrees with it in advance.

## Rejected alternatives

- **Keep the public typed path behind two Failures, as the desk has** — symmetric with the desk and keeps reach for patients whose card will not scan. Rejected because the two situations are not symmetric: the desk path is taken by an identified volunteer in front of the patient, and the public path is taken by an unauthenticated HTTP client that may not be a patient at all.
- **Remove the button but leave the endpoint accepting typed identity** — smallest diff, fewest tests to change. Rejected outright: the affordance was never the control. Anyone who can POST to a public endpoint can still create rows.
- **Re-scan every patient at the door, as ADR 0012 read** — one rule, no branch on registration provenance. Rejected because it retakes evidence already on file, costs the camp its worst queue on the busiest morning, and proves nothing a stored Lock does not already prove.
- **Restrict the skip to self-registered rows only** — narrower blast radius. Rejected because a desk volunteer's Lock and a patient's own Lock are the same decoded card, and it would make the desk's own pre-registrations the slowest path through the door.
- **Narrow `/desk/arrive` to scanned rows** — defence in depth for the new control. Rejected because it breaks the door walk-in, which registers a typed patient and arrives them in one action, and because it duplicates a gate that already exists at print time.
- **Hide Print when the window is closed with no message** — quieter row. Rejected because a volunteer who expected the button and finds nothing goes hunting for the patient again.
- **Hide Print whenever the window is closed, reprints included** — one rule, no `printed_at` special case. Rejected because it removes from the UI a reprint the server permits, on the exact patient who has lost their sheet.
