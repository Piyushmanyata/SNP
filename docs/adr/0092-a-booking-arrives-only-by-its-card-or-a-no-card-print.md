# ADR 0092: A booking arrives only by its card or a No-card print

**Amends ADR 0033 and ADR 0034.**

## Context

- ADR 0033 made a Lock the identity evidence, taken once. A booking whose card was scanned at registration (Self-registration or Pre-registration) therefore needed no door scan: a typed lookup found it and Print stamped Arrival.
- At the 15,000-patient camp that path is the exposure. A typed reg no or Patient code puts a sheet in the hands of whoever stands at the desk. Reg nos are sequential, so a typo is another real patient who never showed a card. The wayfinder audit (#72) expects about 15 wrong-patient prints at 15,000.
- A scanned Door walk-in registered in one request and arrived in a second. A lost reply to the second left a registered walk-in who had not arrived.
- A scanned booking whose patient left the card at home had no way forward: No-card print covered only Manual entries from Pre-registration.

## Decision

- **Arrival for a booking comes from a door Lock or a No-card print.** `arrival.require_arrivable` accepts only a registration that has a No-card print or has already arrived. Anything else, a scanned booking included, is refused with `NEEDS_DOOR_SCAN`: "Scan this patient's Aadhaar card at the door, or record a No-card print."
- **No-card print covers every booking that has not arrived** in the active camp and is not Doctor seen (`ALREADY_SEEN`). The Print window must be open. The reasons are the Manual entry list.
  - For a scanned booking with a card-in-hand reason (Card won't scan, Scanner not working), the typed last-4 must equal the booking's. A missing one is `AADHAAR_LAST4_REQUIRED`; a different one is `NO_CARD_LAST4_MISMATCH`.
  - It records reason, note, actor and time, clears `identity_recheck_required`, and never sets the scanned mark.
  - On a patient who has already arrived it changes nothing.
- **A Door walk-in arrives in the request that registers it.** `at_door` now applies to a scanned registration too; the server re-decodes the payload (ADR 0043) and stamps the Arrival fields at creation. A replay of the same request returns the arrived registration without a second stamp. `at_door` still means the Operating day (`NOT_OPERATING_DAY`), and Self-registration ignores it.
- **The desk.** A typed lookup or Patient code read of a registration that has not arrived shows the row with "Scan the card" (which puts the cursor in the USB box) and "No-card print", and no Print. An arrived, unprinted row offers Print, so a neighbouring desk can take over from a failed printer. A printed row keeps the Reprint rules.

## Rejected alternatives

- **An identity-confirm dialog before print.** It depends on a volunteer reading carefully at about 40 s a patient.
- **Keeping it as is.** It leaves the typo exposure.

## Consequences

- About 45% of the door (booked patients) now needs its card at the door or a recorded reason. The door scan was already the normal path, so the common case is not slower.
- The Camp records export stays honest: a No-card print is never "scanned".
- A scanned walk-in that races a Manual entry for the same card is overwritten, not arrived; the next door scan arrives it.
