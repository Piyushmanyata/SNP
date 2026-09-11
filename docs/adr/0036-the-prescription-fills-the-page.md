# ADR 0036: The prescription fills the page, and sponsors get a band of their own

**Amends ADR 0032.**

## Context

The sheet is declared `210mm × 297mm` and laid out in normal flow, so every band takes its natural height and whatever is left over collects as white space above the footer. On a form whose whole purpose is to be written on, that slack is in the wrong place: the MEDICINES column is three fixed rules (`h-10`, `h-6`, `h-6`) while several centimetres of empty paper sit below them. ADR 0032 already had to add a third medicine line because two were not enough and doctors were writing into the margin. The paper to fix that was there the whole time.

The sponsor footer has a second, sharper problem. Logos render in a `flex-wrap` row inside the left cell of a `grid-cols-2` footer — about 90mm wide — at 18mm tall. The trust expects roughly five sponsors. Five logos at 18mm in 90mm wrap to two or three ragged rows against the signature block, and the backend already permits six (`routes_templates.py:30`, `[:6]`).

There is also a dead rule. `index.css` set `.print-a4 { width: 210mm; min-height: 297mm; padding: 16mm }` inside `@media print`, but the component sets `width`, `minHeight` and `padding: 10mm 12mm` as **inline styles**, which win over any class selector. The print stylesheet's geometry has never applied. Two declarations of the page box, one of them inert, is a trap for the next person who tries to change the margins.

## Decision

- **The sheet is a flex column.** `display: flex; flex-direction: column` on the A4 box. The page geometry stays where it already was: `210mm × 297mm` with `10mm 12mm` padding, `box-sizing: border-box`, under the existing `@page { margin: 0 }`.
- **Slack goes to the doctor.** The vitals / MEDICINES grid becomes `flex-1` and carries `data-testid="rx-write-area"`. Inside it the medicine column is a flex column and its three rules become `flex-[2]`, `flex-1`, `flex-1` with `min-h-10`, `min-h-6`, `min-h-6`. ADR 0032's tall-then-short rhythm is preserved as the *ratio*, and its heights survive as the *minimums*; the lines can only get taller than they were, never shorter.
- **Sponsors get a full-width band pinned to the bottom.** The two-column footer is split: the signature block is its own right-aligned row (`rx-signature`), and `rx-footer` becomes a full-width band below it, separated by a rule, holding `Sponsorer :` and `rx-sponsor-strip`. Each logo is `flex-1 min-w-0 object-contain` at 18mm tall, so five share ~186mm at about 35mm each and six at about 29mm — one row either way, evenly spaced, no wrapping.
- **The page box is declared once.** `.print-a4` in `@media print` keeps only `margin: 0 auto` and the shadow reset. Its `width`, `min-height` and `padding` are deleted as dead weight.

## Consequences

The form is taller in the places that get written on and identical everywhere else. Because `flex-1` distributes only the space that is already inside the fixed 297mm box, the sheet cannot grow past one page — the one-page guard ADR 0032 relied on now holds by construction rather than by the bands happening to add up.

A camp with no sponsors gets an empty band with just the `Sponsorer :` label and a rule. That matches the printed reference, which has the label whether or not anyone sponsored.

A very wide logo and a very narrow one now occupy the same width, so a wordmark will render smaller than a roundel of the same height. That is the cost of one tidy row; `object-contain` guarantees nothing is cropped or distorted.

The reference-form snapshot was regenerated. It is a deliberate guard on ADR 0022's artwork, so the diff is the record of what changed: the write area's flex classes, the medicine rules, and the footer split.

`rx-footer` still exists and still means "the sponsor area", so the existing assertion on it holds. `rx-signature`, `rx-write-area` and `rx-sponsor-strip` are new.

## Rejected alternatives

- **Pin the sponsor band to the bottom and leave the gap above it** — the smallest change, and no ADR needed. Rejected because the page would be technically full while still looking half empty, and the doctor would gain nothing from the change.
- **Scale every band proportionally to fill 297mm** — looks deliberate and uniform. Rejected because it enlarges printed text and fixed bands nobody asked to change, drifting furthest from the artwork ADR 0022 protects.
- **Keep the two-column footer and shrink the logos to fit five in 90mm** — no layout restructuring. Rejected: five logos in 90mm is 16mm each including gaps, small enough that a sponsor's name is unreadable on paper.
- **Cap the logo list at five to match the stated expectation** — simpler to lay out. Rejected as a narrowing of a limit the backend already validates at six, to serve an "approximately" in a requirement.
- **Give the slack to a fourth medicine line instead of taller lines** — more lines for more medicines. Rejected for ADR 0032's own reason: the row count is not something to change without being asked, and a taller line takes a wrapped medicine name just as well.
- **Make the write area's growth configurable per camp** — lets a camp tune the balance. Rejected for ADR 0015's reason: every editable field is a way for the printed prescription to come out wrong on a camp morning.
