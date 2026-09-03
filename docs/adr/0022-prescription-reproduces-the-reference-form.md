# ADR 0022: The printed prescription reproduces the reference form

## Context

ADR 0015 put the prescription layout in code and left the sponsor logo list as the only stored template data. That decision stands. What it did not do was make the printed sheet match the paper the trust actually uses.

What prints today is a generic form: two header lines, a subtitle paragraph, a sponsor footer string, and six labelled blank rectangles for diagnosis, vision, prescription, vitals, advice and a signature. The reference artwork in the repository root is a different document. It has a bilingual masthead in English, Devanagari and Bengali, an address band, a two-line free-services statement, a left identity column with dotted leaders beside a bordered box for registration number, date, age with male and female boxes, and contact number, a four-way diagnosis checkbox row, a vitals column beside a medicines column, a bordered operation box containing the full PRESCRIPTION FOR GLASSES table with RE and LE groups over Dsph, Dcyl, Axis and Vision plus Distance and Near rows and an inter-pupillary distance line, a declaration paragraph, and a footer pairing the sponsor with the optometrist's signature.

The sponsor logos also print in the wrong place. They render at the top beside the title, whereas the reference puts the sponsor at the bottom under "Sponsorer :". The two emblems at the top of the real form are the trust's own, not a sponsor's — and the default logo list currently serves the same header photograph twice, named for those two organisations.

## Decision

- The printed prescription reproduces the reference form band for band. Every string is taken from it verbatim, **including its two original misspellings, `ARRANGMENT` and `Remaks`.**
- The layout stays in code, as ADR 0015 decided. The masthead, address band, services band, identity block, diagnosis row, vitals and medicines split, operation box, glasses table, declaration and signature are constants and markup, editable from no screen and no endpoint.
- The masthead is rendered as text, not as a photograph of the original. Only three decorative drawings — the emblem, the instrument and the eye — are images, cropped once from the reference and committed as fixed assets.
- The sponsor logo list remains the only stored template data, and its editor is unchanged: upload, reorder, delete, a two-megabyte cap, PNG/JPEG/WebP only, and immediate effect with no draft or publish step. It moves to the footer under "Sponsorer :".
- The default logo list becomes a single entry, the sponsor's mark. The header photograph it currently serves twice is deleted.
- The patient QR is kept and placed beneath the bordered identity box. It is the one addition to the original layout.
- The generic header title, subtitle, footer string and the six-block list are deleted.

## Consequences

Doctors are handed the form they have written on for years, so the layout carries no training cost mid-camp.

Rendering the masthead as text rather than as a scan keeps the sheet sharp at print resolution and the patient's details selectable, at the cost of depending on the browser having Devanagari and Bengali faces available. The camp's SMS is already Devanagari, so that dependency is not new.

Preserving the misspellings will read as a defect to anyone who does not know the original. Correcting them is a one-line change, but it is the trust's call, not an implementer's.

Changing the printed form remains a code change and a deploy. For a form that changes once every few years this is still correct, and the sponsor — the one thing that changes per camp — is still data.

The A4 preview on the template screen renders the same component, so it shows the new form with no separate work.

## Rejected alternatives

- **Render the whole masthead as one cropped image from the reference** — guarantees an exact match and removes all risk around Devanagari, Bengali and the Om glyph. Rejected because a bitmap masthead prints soft, scales badly, and turns the organisation names into pixels.
- **Drop the three decorative drawings** — avoids cropping the reference photograph at all, and they carry no information. Rejected because "copy the prescription exactly" is the requirement, and a form missing its artwork does not read as the trust's.
- **Correct `ARRANGMENT` and `Remaks`** — the obvious instinct. Rejected as not the implementer's decision to take; recorded here so it is a conscious choice rather than a silent one.
- **Keep the sponsor logos in the masthead** — no change to the header markup. Rejected because it contradicts the reference and leaves the trust's own emblems modelled as sponsors.
- **Make the glasses table or the checkbox row configurable** — would let a future form change without a deploy. Rejected for exactly the reason ADR 0015 gives: every editable field is a way for the printed prescription to come out wrong on a camp morning.
