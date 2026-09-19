# ADR 0040: The surgery venue is admin-typed, with a separate short name for SMS

**Amends ADR 0039.**

## Context

`create_ot_day` read `body.venue` from the request and then ignored it, forcing every OT Schedule Day to the 93-character `HOSPITAL_VENUE` constant on both insert and update. The admin form offered a Hospital field, pre-filled it and posted it, and the backend discarded the value silently. The invariant was deliberate and was pinned by a test named "surgery can only be scheduled at the hospital": the trust operates at one hospital, so the venue was not the admin's to choose.

The trust can move a surgery day to another hospital, so that invariant is now wrong. It also leaked into the SMS copy: `ot_token` and `ot` named बजाज हॉस्पिटल in fixed text while the same message ended with `स्थल: {venue}`. A day held anywhere else produced a message that contradicted itself. Fixed text in a DLT-registered template cannot be corrected without operator re-approval, so the hardcode was in the most expensive possible place.

Removing the hardcode surfaced a cost. `HOSPITAL_VENUE` is the full postal address, and Devanagari SMS carries 67 characters per concatenated segment, so surgery messages rendered with it run to four segments. The short name in the old template text was doing real work: keeping the message cheap.

## Decision

- `create_ot_day` honours `body.venue` and rejects a blank one with a 400, matching the specs-day route. The hospital is admin-typed, in Hindi or English, and is not validated against a list. The full address survives as the admin form's default, not as a server-side substitution, so the backend `HOSPITAL_VENUE` constant is deleted.
- An OT Schedule Day carries an optional `venue_sms`, a short display name used only in SMS. Both surgery sends prefer it and fall back to `venue`: the Token send through `deferred_slips.collection_venue_sms`, the D-1 reminder through the day document.
- The printed prescription and Token keep the full `venue`. A patient travelling to the hospital needs the address; the SMS only needs to name the place.
- The two surgery templates name no hospital. The location reaches the patient through `{venue}` alone.

## Consequences

A surgery day can be held at a second hospital without a code change and without DLT re-approval, which is the whole point: the template text is frozen once the operator approves it.

Admins now fill two venue fields where they filled one. Leaving the short name blank is safe and sends the full address at four segments, so the cost is opt-out rather than a trap.

The DLT `venue` variable must still be registered long enough for the full address, because a day with no short name sends it.

Because the endpoint upserts by date, posting an existing date now rewrites its venue. The admin form loads the selected date's stored venue, short name and seat limit before posting, so an admin editing only the seat count cannot silently move a scheduled day to a different hospital.

## Rejected alternatives

- **Keep the venue forced and delete the dead form field** — honest about the old invariant and the smallest change. Rejected because the trust needs a second hospital, which is the requirement that started this.
- **Shorten `HOSPITAL_VENUE` everywhere** — one constant, no new field, cheap SMS. Rejected because the printed Token would lose the Near Canara Bank and Bilasi Mod landmarks, which are how patients actually find the building.
- **Derive the short name from the full venue** — no second field for admins to fill. Rejected because no truncation rule survives a Hindi venue, an English venue and a landmark-first address, and a wrong guess is posted to a patient.
