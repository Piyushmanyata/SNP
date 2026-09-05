# 0030. Step-by-step transcription

## Context

The prescription form was one long screen carrying every field for every line, reordered per operator by CSS `order-*` classes and conditional autofocus. Every operator saw specs, surgery and medicine fields regardless of what the doctor had written.

Roughly forty doctors will feed four Fulfilment lines. Finding forty volunteers competent at free-form transcription is not realistic, so the operators at the medicine, fixed-power, made-specs and surgery desks all transcribe, and the flow has to be learnable in one pass by someone who has never done it before.

## Decision

- Transcription is a **wizard: one question per screen**, with Back and Next.
- The sequence follows the paper and is **identical for every operator**: Diagnosis, then what the doctor prescribed, then a step for each ticked line only, then Review.
- The **line-selection step routes everything below it**. A medicine-only patient sees four screens and never meets a specs or surgery field. This pruning is where most of the speed comes from.
- The last step is a **read-back of the whole prescription** beside the "I copied every instruction on the paper" attestation. A wizard that commits without showing the whole prescription would weaken what that attestation claims.
- **Blood sugar, BP and remarks are not a step.** They sit behind one control on the review screen, opening automatically when a value is already recorded. At an eye camp most patients have no vitals taken, and a skippable step is a screen every patient must dismiss.
- Advancing a step **saves a draft** through the existing versioned draft endpoint, so a dead laptop or a closed tab loses nothing.
- **Corrections keep their own modal** — a flat field set with an audit reason. Walking six steps to fix a typo is worse than the form it replaced.

Rejected: one page with progressively unfolding sections (still a long form on a laptop); a wizard with no final review; a skippable vitals step; reusing the wizard for corrections.

## Consequence

**This amends ADR-0020.** Operator line no longer selects initial fields or autofocus — the sequence is the same for everyone, and the line now only chooses which fulfilment station opens after the prescription is committed. Every volunteer is trained on one identical flow, which matters when volunteers rotate between lines.

`PrescriptionForm` is replaced by `PrescriptionWizard`; the `order-*` shuffling and the conditional `firstFieldRef` branching are deleted. Step visibility and step gating are pure exported functions (`visibleSteps`, `stepComplete`) so the flow is testable without rendering.
