# ADR 0044: A typed registration is held until a card or an admin releases it

**Amends ADR 0033, ADR 0035 and ADR 0043. Amended by ADR 0084:** a Manual entry typed at the door is not held. The hold stays only for one typed at Pre-registration, and any desk role releases it with a No-card print (`POST /desk/no-card`), which replaces the admin's Identity check.

## Context

ADR 0035 says a Manual entry "still cannot print until an admin records an identity check". Three things made that rule either leaky or a dead end.

- **The server took the Manual flag from the client.** `_build_patient_document` marked a row manual only when the body sent `manual_entry` or `manual_exception`. A staff body with three failed attempts, a reason and `manual_entry: false` was stored as neither scanned nor manual, with no `identity_recheck_required`, so it printed with no card and no admin check.
- **A card did not release the hold.** When a door scan or a scanned desk registration replaced a Manual entry with the server-decoded card (ADR 0011, ADR 0043), it cleared the Manual flags but left `identity_recheck_required` set. The door reported the patient as arrived and updated, and then `POST /desk/print` refused with `identity_recheck_required`. Review item S9 recorded this; it was never fixed.
- **No screen could record the admin check.** `POST /api/desk/identity-check` existed, but nothing in the frontend called it. On the morning ADR 0035 is written for, the scanners are down and every typed patient is registered and arrived, but none of them can print.

`scan_confirm` also tested whether a chosen candidate matched the card by writing the card onto it and restoring the old values in a second write. That wrote the wrong identity onto a real registration for the length of the request, created a stray Person record, and left the wrong identity behind if the process died between the two writes.

## Decision

- **The server decides what a Manual entry is.** Every registration that is not scanned (as ADR 0043 defines scanned) is a Manual entry with `identity_recheck_required`. `manual_entry` and `manual_exception` are no longer request fields.
- **A card releases the hold.** A server-decoded card that replaces a Manual entry sets `identity_recheck_required` to false in the same conditional update as the overwrite. This applies both to the door scan and to the desk registration path.
- **An admin releases the hold for a patient with no readable card.** The Desk shows a typed registration that has not yet printed as held, with no Print control. An admin sees **Confirm identity** on that row. It asks what evidence was seen and posts `/desk/identity-check`. The row then prints. An identity-checked registration no longer needs a door scan before printing (`identity_checked` in `ser_patient`), because that check stands in for the card.
- **`scan_confirm` compares, it does not write.** A candidate that is not a hit for the card answers `DUPLICATE_IN_CAMP` when the card's existing Person already has a registration in this camp, and `STALE_CANDIDATE` otherwise. It writes nothing and creates no Person.

## Consequences

Test fixtures that registered a typed patient and printed it now record the admin check first, as a real camp must. A registration stored before this change with neither flag keeps `identity_recheck_required` false. Production holds test data only.

Door scans no longer copy the scanned card into the hidden fields of the typed door form. A typed door entry now carries only what the volunteer typed, or what OCR transcribed from the card in hand.

## Rejected alternatives

- **Keep the client flag and force it true only at the door.** Rejected because the desk Registration path is the same staff API. A hold that one screen can omit is not a hold.
- **Clear the hold on arrival.** Rejected because arrival is presence, not identity evidence (ADR 0012).
- **Let the door volunteer record the identity check.** Rejected for the same reason ADR 0035 keeps the door gate admin-only. The volunteer at the door is the person under the most pressure to wave a patient through.
