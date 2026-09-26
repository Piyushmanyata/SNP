# ADR 0084: Manual entry is a desk decision, not an admin one

**Supersedes ADR 0035. Amends ADR 0044 and ADR 0071.**

## Context

- Patients forget their Aadhaar card, and some cards will not read. On a camp day they still need a prescription.
- ADR 0035 hid the typed form at the door until an admin opened the Door manual gate for the day. ADR 0044 then held every Manual entry from printing until an admin recorded an Identity check. Pre-registration revealed its typed form only after three Failures (ADR 0071).
- A camp runs ten desks and usually has one admin. Every patient without a card queued twice at that admin: once to open the door, once to print. In practice the volunteer can see the same ration card or voter ID that the admin would.
- The admin steps were the only guard against a patient already seen coming back under a second, typed registration. Duplicate in camp does not catch a typed name with a different phone and no last-4.

## Decision

- Any desk role (admin, team lead, volunteer) starts a Manual entry from a **Manual entry** button under the scanner: always at Pre-registration, and at Scan at the door while the Print window is open. There is no Failure count and no admin switch. `POST /camps/door-manual` and `door_manual_date` are gone.
- The volunteer picks a reason: **No Aadhaar card**, **Card won't scan**, **Scanner not working**, or **Other** with a written note. The server stores the code and refuses anything else. When the card is in hand (card won't scan, scanner not working), its last-4 is required. Gender is required.
- A Manual entry typed at the door is arrived when saved and prints straight away.
- A Manual entry typed at Pre-registration still needs its Lock at the door on the camp day. If the card reads, the Aadhaar overwrite applies. If the patient has no readable card, any desk role records a **No-card print** (`POST /desk/no-card`) with the same reasons, and the row prints. This replaces the admin's Identity check.
- Before a Manual entry saves, the server looks for **Lookalikes**: registrations in the camp with the same name, word order ignored, and an age within five years. It answers `409 LOOKALIKES` with each one and its status. The volunteer either opens that registration, where the usual print rules apply, or resubmits with `different_person`, which saves the entry and records the Lookalikes that were overridden.

## Consequences

- A patient without a card waits only for the volunteer in front of them.
- A volunteer can now create and print a typed patient alone. The reason, the volunteer's name and any overridden Lookalike are stored on the registration, and the Camp records export shows the reason.
- A seen patient who returns without a card meets a red "Doctor seen" Lookalike before a second registration can exist. A different name or an age more than five years off still passes. That gap is accepted, because a stricter match blocks too many real namesakes.
- Registrations stored before this change keep their free-text reason. Production holds test data only.

## Rejected alternatives

- **Keep the identity hold for camp-day entries.** Safer against an invented patient, but it keeps the single-admin queue this decision exists to remove.
- **Let a team lead open the gate and record the check.** Closer to who is present, but it still stops a desk for a decision the desk can already see the evidence for.
- **Block a Manual entry that matches a name already in the camp.** At 15,000 patients, namesakes are common and real, and a block turns them away at the door.
- **Keep the three-Failure reveal at Pre-registration.** A patient who says they have no card cannot produce three Failures, so the rule only makes the volunteer scan nothing three times.
