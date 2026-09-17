# ADR 0038: Hospital outcomes are explicit, and IOL is the only surgery

**Amends ADR 0019.**

## Context

ADR 0019 gave the `ot` line one outcome at the station: `deferred`, meaning a seat on an OT Schedule Day, a surgery Token and an SMS. Everything the doctor sends to the hospital was treated as an operation. The trust arranges only cataract (IOL) surgery, so a glaucoma patient referred to the hospital got a surgery date that would never happen, and a patient who refused the operation kept a seat. There was nowhere to record either.

The prescription carried a free-text procedure and allowed "Both" eyes, so one seat and one Token could stand for two operations. Nothing stopped the transcription from combining spectacles with a cataract operation that will change the power, or ready-made with made-to-order spectacles; ADR 0019 caught the second only at the station.

## Decision

- The Hospital line carries an explicit **Hospital outcome**, stored as `ot_outcome` on the prescription content. The prescription records the doctor's choice: `iol_surgery` or `referral`. It is required when `ot` is prescribed and absent otherwise.
- `ot_eye` is `R` or `L`, required for `iol_surgery` and absent for `referral`. "Both" is refused. The second eye goes in `ot_notes` for a later camp.
- The free-text `ot_procedure` field is removed.
- A prescription names at most one of `specs_fixed`, `specs_made`, or `ot` with `iol_surgery`. A `referral` combines with either specs line, and medicine combines with anything. Completion and correction both refuse a clash as `incomplete_prescription`, with a field error naming the clashing lines. ADR 0019's station-level specs exclusion stays as a second guard.
- The `ot` fulfilment matrix becomes `deferred` (scheduled) or `declined`. `fulfilled` is accepted for nothing on this line.
- Any `ot` record for a prescription whose outcome is not `iol_surgery` is refused with `409 hospital_referral`. A referral is complete once the prescription is committed.
- `declined` over a prior `deferred` uses the existing re-record path. It releases the held seat once, cancels the active Token and sends nothing. OT reminders read only active Tokens, so no reminder follows.
- Stored names do not change: the line key and item type stay `ot`, as ADR 0034 did for stored fields. "Hospital" is the glossary name.
- No migration. Production holds test data only.

## Consequences

Only a scheduled IOL surgery takes a seat, prints a Token and sends an SMS. A referral and a refusal consume nothing.

A patient who declines IOL surgery and then wants spectacles needs a correction with an audit reason: untick the Hospital line, clear its outcome and add the specs line. The record then shows why the plan changed.

The Camp records export's `ot` column reads `scheduled`, `declined` or `referred`, and OT date and venue are filled only when scheduled. The Camp-day board counts `deferred` and `declined` on the Hospital line.

A revision stored before this change has no `ot_outcome`, so the station refuses it as not an IOL surgery. That is acceptable only because there is no live data.

## Rejected alternatives

- **Infer the outcome from the diagnosis** (Glaucoma means referral) — no extra tap. Rejected because a patient can have cataract in one eye and glaucoma in the other, and the operator should copy the doctor's decision rather than interpret a diagnosis.
- **Allow "Both" as one seat** — matches papers that prescribe both eyes. Rejected because one Token would stand for two operations the hospital schedules separately.
- **Keep the free-text procedure alongside the outcome** — preserves what the doctor wrote. Rejected because the trust arranges exactly one procedure, and a free-text field invites typing one it does not.
- **Record a referral at the station too** — every line would end with a station record. Rejected because there is nothing to do there, and a station action for a referral is one tap away from a booking.
