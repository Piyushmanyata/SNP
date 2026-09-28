# ADR 0097: Corrections after issue carry forward and flag

## Context

- A correction can reach a patient whose medicine or Fixed-power specs line was already handed over (#73 finding 2, grilling #82, #89 slice 3).
- The Camp records export then paired the corrected prescribed power with the power issued against the earlier revision, which reads like a desk substitution.
- A medicine added by the correction had no way to be issued.
- About 75–225 export rows at the 15,000-patient camp are expected to be affected.

## Decision

On a correction commit, inside the correction's `apply` step and its one transaction, each issued medicine and Fixed-power specs line is re-derived against the new revision (`routes_clinical._carry_forward`, rules in `clinical_state`).

**Medicine line (by catalogue name):**
- a medicine given stays given;
- one recorded not available stays not available while still prescribed;
- one the correction adds is open (`given: null`);
- one it removes after it was given stays recorded as given, with `prescribed: false`.

The status is derived as before, so a line with open medicines is Partially fulfilled. The line is reopened at the Fulfilment station for the open medicines only.

**Fixed-power specs:** if the correction moved the prescribed power away from the Issued power, the Issued power stays, and nothing reopens. A desk substitution without a correction is not marked.

**The mark:** any line the correction changed gets `corrected_after_issue: {revision_id, at, by}`. A reopened line is issued again only after a fresh Paper review against the corrected revision and generation (`STALE_REVIEW` until then), and a re-issue never turns a given medicine back.

**Export:** the Camp records export gains a `corrected_after_issue` column naming the marked lines. Medicines prescribed come from the current revision, and open medicines count as not given until issued. The fixed power columns already show the current prescribed power and the actual Issued power.

**Unchanged:**
- Hospital referral and Surgery declined;
- IOL surgery and Spectacles to be made, still refused while scheduled or active (`SURGERY_SCHEDULED`, `SPECS_SCHEDULED`);
- Undo completion, still refused after issue (`UNDO_AFTER_ISSUE`).

## Rejected alternatives

- **Refusing corrections after issue.** A mistyped line could never be fixed once goods left the camp.
- **Revision history in the export.** It is wide and hard to read, and it still would not say which goods left.

## Consequences

- The export no longer states something untrue after a correction, and a medicine added late can be handed over and recorded.
- A line keeps its mark after the open medicines are issued, so the export still shows that it was corrected after issue.
