# 0029. Fixed-power catalogue and power substitution

## Context

Both spectacles lines shared one seven-field grid — sphere, cylinder and axis per eye, plus Add — and `specs_fixed` could not be issued until right and left sphere were typed. Ready-made spectacles are not ground to a cylinder and axis; they are picked off a shelf by dioptre. Typing seven fields to describe a pair the camp already holds was the largest single cost in the transcription form.

## Decision

- Admin maintains a global **Fixed power catalogue**: twenty to forty stocked dioptres spanning minus (distance) and plus (reading). The list is the stock list; "either we have it or we do not" needs no separate stock mechanism.
- `specs_fixed` records **picked powers only**. The measurement grid is gone from that line. Powers are stored as two numbers, `fixed_power_r` and `fixed_power_l`.
- The picker defaults to **one power applied to both eyes** — one tap, which covers every reading-glasses patient — with a "different power per eye" toggle. Because minus powers are stocked and myopic eyes routinely differ, a single shared power would otherwise force a patient with suitable stock on the shelf into Spectacles to be made.
- Two nullable numbers, not a discriminated union: "same in both eyes" writes the same value twice, and the toggle is purely a UI affordance.
- `specs_made` **keeps the full grid**. Custom lenses are ground to those numbers and the workshop cannot make a pair from a chip.
- A power that has run out may be **substituted at the desk**. The fulfilment records `issued_power_r` and `issued_power_l`; the prescribed powers on the revision never move. No reason is required — the reason is always that the power was out.
- Powers are validated against the catalogue on write, at both transcription and substitution, so a typo cannot enter a prescription. Validation accepts inactive entries so retiring a power mid-camp does not break an in-flight transcription.

Rejected: keeping the grid for fixed specs alongside the picked power (seven fields of typing for the audit trail it was meant to remove); admin-defined whole pairs; refusing substitution outright (the patient goes home with nothing while suitable stock sits on the shelf); recording substitution as a correction (that would overwrite what the doctor wrote).

## Consequence

`_assert_specs_prescription` splits by item type: `specs_made` checks the grid, `specs_fixed` checks the powers. The completion rules follow. The export gains `fixed_power_r`, `fixed_power_l`, `issued_power_r` and `issued_power_l`. Powers are stored as numbers and formatted with an explicit sign and two decimals wherever they are shown.
