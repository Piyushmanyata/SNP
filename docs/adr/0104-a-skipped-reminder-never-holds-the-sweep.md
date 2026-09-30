# ADR 0104: A skipped reminder never holds the sweep

## Context

- A reminder is skipped, with no ledger row, when it must not be sent: the patient's number is the registrar's own phone, the camp has no number, the template is not configured, or the venue is unusable.
- The sweep advanced its cursor by the count of sends it made. When every patient it picked was skipped, it kept the cursor where it was and stopped. The next call picked the same patients again, forever.
- Under the Canary gate a sweep picks one patient. If the first patient by `_id` was skipped, no Canary was ever sent, so nobody after them got that reminder for the event date.
- The call reported `complete: false` and not `waiting`, so the worker called again at once: a hot loop of full sweeps until the day rolled over, with system health red.
- The cursor also carried no event date. A cursor left by an unfinished sweep, for example one held by a paused type overnight, was reused for the next day's event date and skipped whole reminder types for it.

## Decision

- **The cursor moves past every patient the sweep attempted.** `_send_fresh` returns how many picked patients were attempted before the first deferred one, and the cursor moves to the last of them. A skipped patient counts as attempted. Only a deferred send, one whose turn came after the time budget, holds the cursor (ADR 0096).
- **A skipped Canary is not a Canary.** The sweep sets `waiting` only when the Canary was actually sent; otherwise it picks the next patient.
- **The cursor belongs to one event date.** The lease stores `event_date` with the cursor, and a sweep uses the cursor only when the date matches. A cursor with another date, or none, is dropped; the ledger's sent rows stop any second send.

## Rejected alternatives

- **Hold the cursor on a fixable skip and wait 60 seconds.** It keeps retrying until an admin adds the camp number, but one camp's missing number would hold every later patient of every camp for that date, and a registrar-phone skip never clears.
- **Filter skipped patients before choosing.** It repeats `_compose`'s rules in a second place.

## Consequences

- A camp with no number finishes its sweep with nothing sent to its patients. When the admin adds the number, the next slot's sweep starts afresh and sends to them.
- The 10:00 and 20:00 slots record completion even when some patients were skipped. The skip is logged with its reason, as before.
