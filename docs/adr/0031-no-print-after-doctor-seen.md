# 0031. No print after doctor seen

## Context

Printing was gated on Arrival, the print window and identity recheck, but never on clinical state. `printed_at` is stamped once and every later call re-served the payload, so a patient the doctor had already seen could still be handed a fresh prescription — a blank form for a consultation that is already committed. Both the preview and the stamping route share `_prescription_payload`, and the print page renders from the preview before the operator presses Print.

## Decision

- `_prescription_payload` refuses a patient whose `queue_status` is `seen` with 409 `ALREADY_SEEN`, before the Arrival, print-window and identity checks. The refusal covers `GET` and `POST /desk/print/{id}` together, so a seen patient's prescription is never served and never renders.
- Both desk entry points withdraw Print for a seen patient: the board row, whose status badge already explains the state, and the door scan card, which says so in words because a repeat door scan of a seen patient returns `outcome: "arrived"` and would otherwise offer a live button.
- Clinical undo returns `queue_status` to `arrived` and printing resumes. That is the only route back.

Rejected: blocking only the stamping `POST`, which leaves the rendered slip printable from the browser; keeping the lost-paper reprint open after Seen, which is the loophole this closes; blocking on `printed_at` as well, which would end reprints for patients the doctor has not yet seen.

## Consequence

The lost-paper reprint path ends at Doctor seen. A patient who loses their prescription after consultation cannot be reprinted at the desk without a clinical undo, which requires a reason and revokes the point. No stored field and no index change; the check reads state that clinical completion already writes.

One window stays open and is accepted rather than closed: a print page fetched while the patient was still unseen keeps its rendered sheet, so the operator's own browser print still works until the page is reloaded. Closing it would mean revalidating on every `beforeprint`, a defensive layer for a race that requires holding the page open across the consultation, and the sheet it prints was legitimately served.
