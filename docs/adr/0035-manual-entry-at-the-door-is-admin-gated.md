# ADR 0035: Manual entry at the door is admin-gated, not failure-gated

**Amends ADR 0003. Amended by ADR 0063:** the server no longer accepts a client failure count. An unscanned staff registration needs a written reason, and at the door the open gate. The door's typed form shows as soon as the gate is open, and a typed door entry is arrived when it is saved.

## Context

ADR 0003 made manual Aadhaar entry a recovery route rather than a starting option, and gave the desk a three-Failure counter to reveal it. The door then defeated its own rule: `DoorScanCard` computed `showManual = manualMode || doorFailures >= 3`, and rendered an always-visible "Enter details manually" button whose only job was to set `manualMode`. The counter was real, tested, and unreachable — nobody ever needed three Failures, because the button was right there under the scanner.

ADR 0003's justification for that toggle was that "the desk workflow is manual entry first and a card scan is the exception". That has not been true since ADR 0023 put a USB imager on the desk and ADR 0033 made a Lock the identity evidence. At the door the workflow is now scan-first, and typed identity is the exception that ADR 0033 spent a whole decision making expensive on the public page.

The two desks are not the same problem. **Registration** is a seated task: a volunteer with a patient's documents, time to try the card three times, and a booking to create. **Scan at the door** is a queue: a patient arrives, is identified, and prints. A door that offers typing offers the fastest wrong answer to a volunteer under pressure — and a typed row at the door has no Lock, which is exactly what ADR 0033 said must not be cheap to create.

A failure counter cannot tell those apart. Three bad reads from a scratched card and three bad reads from a dead scanner look identical to the counter, and only one of them is a reason to start typing.

## Decision

- **The door has no failure counter.** `doorFailures`, `onDoorFailure` and the always-visible toggle are deleted. No number of Failures at the door reveals the typed form.
- **An admin opens the door's typed path, for one day.** `POST /api/camps/door-manual {enabled}` (admin only) stamps `door_manual_date` on the active camp with today's IST date, or clears it. `door_manual_open(camp, today)` is true only when the two dates match, so the gate **shuts itself when the camp day ends** with no scheduled job and no clock to trust beyond the one already used for the print window. `ser_camp` exposes it as `door_manual_entry`.
- **The gate governs the whole typed path, not just the form.** While it is shut, `DoorScanCard` passes no `onTranscribed`, so by ADR 0033's rule the decoder's `review` outcome is a Failure at the door and OCR has nowhere to land. Opening the gate reveals both the typed form and the transcription route together.
- **The gate does not weaken any print guard.** A Manual entry it produces is still marked, still carries `identity_recheck_required`, and still cannot print until an admin records an identity check. The gate buys a way to create the row, not a way to print it.
- **Registration is untouched.** `RegisterModal` keeps its own `failures` counter, its own three-Failure reveal, and its own `useWedgeBurst`. ADR 0003 continues to govern it in full.

## Consequences

On a morning when the scanners are dead, the desk is blocked until an admin opens the gate. That is the intended cost and the reason the control is two taps on a screen an admin already has open. It is deliberately not something the volunteer at the door can do alone, because the volunteer at the door is the person under the most pressure to do it.

An admin who opens the gate and forgets it does no lasting harm: it lapses at midnight IST and the next camp day starts shut. An admin who genuinely needs it two days running re-opens it, which is the point — it forces the question "are the scanners still broken?" once per day.

A camp whose scanners fail *after* the admin has gone home has no route to typed registration at the door that day. The desk's own Registration path still has its three-Failure reveal, so the patient can be registered there and then printed; the door is the surface that closes, not the camp.

Storing the decision as a date rather than a boolean means there is no expiry job, no timer and no second source of truth. The cost is that a reader of the `camps` collection sees a date where they might expect a flag, which is why `door_manual_open` exists as a named function rather than an inline comparison.

## Rejected alternatives

- **Remove typed entry from the door entirely** — the user's first instinct and the simplest possible rule. Rejected because a camp whose scanners all fail would have no door at all, and the failure mode is a queue of patients turned away.
- **Keep the three-Failure reveal and only delete the button** — a one-line change that makes the existing counter reachable. Rejected because a counter cannot distinguish a scratched card from a broken scanner, and the answer to the first is "try the other capture route", not "start typing".
- **Lower the threshold to two Failures** — one attempt faster. Rejected for the same reason, and it would have contradicted `CONTEXT.md` and ADR 0003 for the sake of one saved attempt.
- **A boolean flag that stays on until an admin turns it off** — simplest to reason about. Rejected because a flag switched on during one bad morning silently stays on for every later camp day, which is the hole ADR 0033 closed on the public page.
- **A global installation-wide setting** — fewer moving parts. Rejected because it cannot express "this camp's reader is broken and that one's is fine", and it survives across camps by design.
- **A hidden supervisor escape as well as the gate** — guarantees nobody is ever stuck. Rejected: an undocumented escape gets shared on the first bad morning and used routinely by the second.
- **Let a team lead open the gate, not only an admin** — closer to who is actually present. Rejected for now because the print-window override is already admin-only and splitting the authority for two decisions of the same weight would need its own reasoning; worth revisiting if admins turn out not to be reachable on camp mornings.
