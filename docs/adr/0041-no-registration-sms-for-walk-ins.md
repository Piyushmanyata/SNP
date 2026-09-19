# ADR 0041: No registration SMS for a walk-in registered on the camp day

## Context

The registration confirmation fired on every created registration, from both `POST /register` and `POST /self-register`. `POST /register` serves two different situations: a volunteer pre-registering a patient for an upcoming camp day, and a walk-in registered at the door on the day itself.

For a walk-in the message is pointless. It arrives while the patient is standing at the desk, tells them they are registered for a camp they have already reached, and asks them to bring their Aadhaar card on the day. It also costs three SMS segments per walk-in, on a camp day when walk-ins are the bulk of registrations.

Rewording the template to suit both situations is the expensive fix: the text is frozen by DLT approval, so it would need another operator review. When to send is application logic and needs none.

## Decision

`_confirm_registration` takes `skip_if_today`. `POST /register` passes it; `POST /self-register` does not.

- A desk registration for a camp day that is not today sends the confirmation. This is pre-registration, where the reg_no, date and venue are what the patient needs later.
- A desk registration for today sends nothing.
- Self-registration always sends, including on the camp day. The patient registered from their own phone, and the receipt on screen is the only other place the reg_no appears.

"Today" is the camp day's date compared against `today_ist_str()`, not the registration timestamp, so a registration typed just after midnight for that morning's camp is still a walk-in.

## Consequences

Walk-ins get no SMS, which removes most registration sends on a camp day.

The camp reminder is unaffected: it selects patients on tomorrow's camp day, so a walk-in was never going to receive one.

Self-registration on the camp day still sends, which is the one case where the message may also be redundant. It is kept because the patient chose to register remotely and nothing else hands them their reg_no.

## Rejected alternatives

- **Suppress for every desk registration** — one condition, no date comparison. Rejected because it also kills pre-registration, which is the case the message was written for.
- **Reword the template to suit both** — one message that reads sensibly whether the camp is today or next week. Rejected because the wording is frozen by DLT approval and a later change costs another operator review, while send timing costs nothing.
- **Suppress on any same-day registration, self-registration included** — the most consistent reading of "pointless". Rejected for now because self-registration is remote by definition and the receipt is the only other place the patient sees their reg_no.
