# 0031. No print after doctor seen

## Context

Printing was gated on Arrival, the print window and identity recheck, but never on clinical state. `printed_at` is stamped once and every later call re-served the payload, so a patient the doctor had already seen could still be handed a fresh prescription — a blank form for a consultation that is already committed. Both the preview and the stamping route share `_prescription_payload`, and the print page renders from the preview before the operator presses Print.

## Decision

- `_prescription_payload` refuses a patient whose `queue_status` is `seen` with 409 `ALREADY_SEEN`, before the Arrival, print-window and identity checks. The refusal covers `GET` and `POST /desk/print/{id}` together, so the prescription never reaches the screen and the browser's own print cannot bypass it.
- The Desk board offers Print only to a patient who has arrived and is not seen. The row's status badge already explains the state, so no disabled control is shown.
- Clinical undo returns `queue_status` to `arrived` and printing resumes. That is the only route back.

Rejected: blocking only the stamping `POST`, which leaves the rendered slip printable from the browser; keeping the lost-paper reprint open after Seen, which is the loophole this closes; blocking on `printed_at` as well, which would end reprints for patients the doctor has not yet seen.

## Consequence

The lost-paper reprint path ends at Doctor seen. A patient who loses their prescription after consultation cannot be reprinted at the desk without a clinical undo, which requires a reason and revokes the point. No stored field and no index change; the check reads state that clinical completion already writes.
