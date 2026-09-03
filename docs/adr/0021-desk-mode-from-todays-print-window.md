# ADR 0021: Desk mode from today's Print window

## Context

The registration desk shows three cards at once and always in the same order: Scan at the door, Find one patient, Pre-registration. Before the camp the only useful action is Pre-registration, and it sits last. During the camp the only useful action is the door scan, and Pre-registration is still on screen inviting a volunteer to book a seat for someone standing in front of them.

The desk also makes the volunteer scan the same card twice. A door scan that finds no booking already carries the decoded card — name, age, gender, date of birth, last four digits, address — and offers a button that opens an empty registration form with a fresh scanner. Everything the form needs is already on screen except the household phone.

Print window is already an admin-declared open/closed state on a camp day, and the days served to the desk already carry it along with a flag for whether the day is today.

## Decision

- The desk has two modes, chosen by today's camp day and its Print window. Open is camp-day mode. Closed, or no camp day matching today at all, is pre-registration mode.
- Pre-registration mode: the Pre-registration card first, Find one patient below it, Scan at the door collapsed at the bottom, and the counter strip reduced to Registered.
- Camp-day mode: Scan at the door first, Find one patient below it, Pre-registration not rendered, and the full Registered / Seen / Pending strip.
- No camp-level print flag is added. The per-day state and its existing admin control stay the single source of truth, and the server's print gate is unchanged.
- A door scan that finds no booking registers the walk-in from the card it already read: card values shown read-only, one household-mobile field, one button that registers and stamps Arrival. No second scan, no modal, and no new endpoint — it reuses the walk-in path the registration popup already uses.
- The door scanner gains the Failure and Scan stall handling the registration popup's scanner already has, so two Failures or a Scan stall reveal the typed form inline and mark the row a Manual entry.

## Consequences

Every control on screen can do something. The disabled Print and Seen buttons and the permanently zero counters disappear from the pre-camp desk.

Opening the Print window becomes the single action that turns the desk from a booking desk into a camp desk, which is the mental model the admin already has.

The Failure counter at the door is load-bearing, not a nicety. A door scan only ever reports no-match after a **successful** decode, and Manual entry previously lived only inside the Pre-registration popup. Hiding that popup in camp-day mode without moving Manual entry to the door would leave a patient whose card will not read with no registration path anywhere in the application. If the two land separately, Pre-registration stays visible until the Failure counter ships.

A door walk-in is booked onto today's camp day with no day to choose, and still respects Camp-day capacity and the Duplicate in camp rules, because it goes through the same registration path as before.

## Rejected alternatives

- **Any open day switches the desk** — simpler to reason about for a single-day camp. Rejected because on a multi-day camp an admin who forgets to close yesterday leaves the desk stuck in camp-day mode, hiding Pre-registration for tomorrow's bookings.
- **A camp-level Print window separate from the per-day one** — one unambiguous switch, matching how people describe it. Rejected because it creates two sources of truth about printing that can disagree, and the server gate reads the per-day one.
- **Keep all three cards in both modes and only reorder them** — smallest possible change. Rejected because it leaves the dead controls and the zero counters that make the pre-camp desk confusing.
- **Hide Pre-registration entirely and escalate an unreadable card to a team lead** — cleanest volunteer screen. Rejected because the screen a team lead would use does not exist.
- **Prefill the existing registration popup from the card instead of an inline field** — keeps one registration code path in the UI. Rejected because it is still a modal over a queue for what is one field.
