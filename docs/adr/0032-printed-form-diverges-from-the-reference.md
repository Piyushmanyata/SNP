# ADR 0032: The printed form diverges from the reference where camp operations require it

**Amends ADR 0022.**

## Context

ADR 0022 decided that the printed prescription reproduces `EYE CLINIC.jpg` band for band, every string verbatim, down to the original misspellings `ARRANGMENT` and `Remaks`. That decision did its job: doctors were handed the form they have written on for years, with no training cost mid-camp.

Three things about the reference no longer match how the camp runs.

The MEDICINES column has two ruled lines. The trust's own dispensing now routinely exceeds two medicines per patient, and the third is written into the margin or squeezed between the rules, where the fulfilment operator has to guess at it during transcription.

The glasses box opens with `Operation will be done at : ____`. Cataract surgery venue is no longer decided at the screening desk — it is settled later and carried in the SMS and the operation list, not on the screening sheet. The line is left blank on every form, and a blank on a form invites someone to fill it in with a guess.

Patients arrive for surgery without the documents the hospital needs. Nothing on the paper they are given tells them what to bring. The registration SMS carries a Devanagari line about the Aadhaar card, but the sheet the patient keeps says nothing.

## Decision

- The printed form **may diverge from the reference where camp operations require it**. ADR 0022's rule becomes: the reference is the starting point and the default, not a frozen specification. A divergence is a deliberate, recorded decision — this ADR, or a successor — never an implementer's tidy-up.
- The MEDICINES column has **three** ruled writing lines. The added line matches the second (`h-6`), preserving the tall-then-short rhythm. Each line carries `data-testid="rx-medicine-line"` so the count is asserted by name rather than only by snapshot.
- `Operation will be done at : ____` is **deleted**. The box that contained it holds only the glasses table, so its test id becomes `rx-glasses-box`.
- The declaration's `...Cataract (IOL) Operation will be done by : ____` **stays**. It names the surgeon, not the venue, and it is filled in.
- A **carry-documents disclaimer** is added as its own bordered band between the declaration and the Sponsorer / Signature footer: *"Please carry your Aadhaar card, ration card and mobile phone on the day of the operation."* English only.
- ADR 0022's other decisions are untouched: layout stays in code, the masthead stays text, the misspellings stay, the sponsor logo list stays the only stored template data.

## Consequences

The sheet's height is close to unchanged — the removed venue line and the added medicine line roughly cancel, and the disclaimer band adds one short row. The one-page guard still applies.

The disclaimer is English on a form whose masthead is trilingual, so a patient who reads only Hindi or Bengali depends on the desk volunteer reading it aloud. Every other label on the form is already English-only, and the volunteer already walks the patient through the sheet, so this is consistent rather than a new gap. Translating it is a one-line change if the trust wants it.

`rx-operation-box` is gone as a test id. Anything outside this repository keying on it breaks; inside it, the two references were updated.

## Rejected alternatives

- **Keep the form frozen and put the disclaimer in the SMS instead** — no layout risk at all, and the SMS already carries a Devanagari Aadhaar line. Rejected because the SMS goes out at registration, weeks before surgery, and is long gone from the patient's notifications by the operation day. The sheet is the artefact they keep.
- **Three equal ruled lines in the MEDICINES column** — tidier than tall-then-short. Rejected as a change to two rows that nobody asked to change, drifting the form further from the reference for cosmetics.
- **Keep `Operation will be done at` and leave it blank** — zero risk. Rejected because a printed blank is an instruction to fill it in, and a venue guessed at the screening desk is worse than no venue.
- **Make the medicine row count configurable per camp** — would let a camp choose two or four. Rejected for ADR 0015's reason: every editable field is a way for the printed prescription to come out wrong on a camp morning.
- **Translate the disclaimer into Hindi and Bengali** — most inclusive. Rejected for now as three lines of disclaimer is the tallest option and the likeliest to break the one-page fit; it is the trust's call, not an implementer's, and recorded here so it is a conscious choice.
