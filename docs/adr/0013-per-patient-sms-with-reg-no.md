# ADR 0013: Per-patient Devanagari SMS carrying reg_no

Supersedes the send policy in ADR 0008. The MSG91 DLT transport and the one-ledger-row-per-send rule from ADR 0008 stand.

## Context

ADR 0008 sent one SMS per unique household number, date and venue only, D-1 only, no SMS at registration. One phone commonly serves a whole household, and the dedup held volume down.

Registration now opens months ahead, so a patient needs confirmation at the time they register, and the confirmation has to identify them. `reg_no` is the identifier the desk, the prescription QR, and the clinical lookup already use. A `reg_no` belongs to a patient, not to a phone.

Devanagari SMS is UCS-2: 70 characters per segment, not 160. Adding `reg_no` to date and venue puts a typical message at two segments.

## Decision

- Every SMS is per patient and carries that patient's `reg_no`. A household number covering three patients receives three messages.
- Six DLT templates, each with its own approval: Registration confirmation, Camp reminder, OT Token SMS, OT reminder, Specs Token SMS, Specs reminder.
- Registration confirmation sends on registration, from self-register and from a volunteer alike.
- OT Token SMS and Specs Token SMS send at the clinical desk at the moment of deferral, alongside the printed Token.
- The three reminders send the calendar day before their event date.
- `send_dlt_sms` carries `reg_no`, date, and venue as variables. Venue is no longer the only variable.
- The ledger key becomes patient plus reminder type plus event date. It is no longer keyed on the phone number.

## Consequences

Volume rises by roughly the mean household size on every send, and again by the four new send points. At fifteen thousand patients the camp SMS alone is on the order of sixty thousand segments. Six template approvals are external work that must complete before pre-registration opens; that is the critical path for the release. A patient can now be told their number without a volunteer reading it out.

## Rejected alternatives

- Keep household dedup and list every `reg_no` in one message — DLT templates have fixed variable slots, a variable-length list is unlikely to be approved, and three numbers in Devanagari overruns two segments.
- Per-patient at registration, per-household at D-1 — halves volume, but leaves two grains to reason about and a D-1 that no longer confirms who is registered.
