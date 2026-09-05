# 0028. Medicine catalogue, name only

## Context

Medicine was one free-text field, `medication_instructions`, that a clinical desk operator retyped from the doctor's paper for every patient. With roughly forty doctors feeding four Fulfilment lines, transcription is done by whichever volunteer sees the patient first, and free text is both the slowest thing on the form and the least useful in the camp records export.

The patient keeps the doctor's written paper. The dose therefore already travels home with them; the system's job at the medicine line is to record what was prescribed and what was actually handed over.

## Decision

- Admin maintains one global **Medicine catalogue** of about ten entries. It is not per camp: a per-camp list adds a mandatory setup step that can fail on camp morning.
- A prescribed medicine is a **name only**. No dose, no strength, no free text. The dose lives on the paper the patient keeps.
- The clinical desk selects from a tap grid. There is no off-catalogue escape: the camp cannot dispense what it does not carry, so a medicine that is not on the list is recorded as not available at the desk.
- Names are **snapshotted onto the prescription revision** at commit. Editing or retiring a catalogue entry can never rewrite a committed prescription.
- Removal is deactivation, never deletion. Re-adding a retired name reactivates the same entry rather than colliding with it.
- Availability is recorded **per medicine**, not per line, at the medicine desk. The line status is derived: all given is `fulfilled`, none given is `not_available`, a mix is `partially_fulfilled`.
- Medicine is not substitutable. Swapping one drug for another is not a volunteer's decision.

Rejected: dose presets per medicine (the paper already carries the dose); a free-text "other" line (the camp cannot dispense it); per-camp catalogues; one status for the whole medicine line (it would record "fulfilled" for a patient who went home missing a drug).

## Consequence

`medication_instructions` is removed from the content fields, the completion rules and the export. Completing with the medicine line ticked now requires at least one selected medicine. `partially_fulfilled` is a new value in the fulfilment matrix and is counted on the camp-day board. The export gains `medicines_prescribed` and `medicines_not_given`. No camp had run, so this is a clean cut with no migration.
