# ADR 0018: Line-scoped clinical desk, Doctor's Rx as a fifth station

## Context

One `clinical_desk_operator` role opens one screen carrying the whole prescription form and all four Fulfilment lines, each with its own status menu. The volunteer at the medicine table has to find their line among four, then pick from a menu that includes options they can never legitimately choose. On a camp morning with a queue, people pick the wrong line.

Recording any fulfilment locks the transcription. With one operator on one screen that ordering is incidental. Split across four desks it becomes load-bearing: whichever desk saves first freezes the prescription for every desk after it, and the two specs desks — the ones that must read the prescribed power — are the likeliest to be locked out.

`not_required` and `not_available` exist because one screen recorded all four lines. Once a desk only sees the patients who walk up to it, a patient who needs no medicine simply never reaches the medicine desk, and nobody is ever in a position to press "not required". The column would then be blank for two different reasons: not needed, and never seen.

## Decision

- A clinical operator works one station. Five exist: Doctor's Rx, Medicine, Fixed-power specs, Spectacles to be made, OT.
- Doctor's Rx is the only station with an editable prescription form, and it carries no Fulfilment controls. The four line desks show the prescription read-only and record only their own line's outcome.
- The lock on first fulfilment is retained and is now the intended sequencing rule: Doctor's Rx finishes, then the patient walks the lines.
- Which lines a patient is due is derived from the transcription — recorded powers imply a specs line, an OT eye or procedure implies OT, a recorded diagnosis implies medicine. Nothing is stored to say so. A patient standing at a line their prescription does not imply gets an advisory warning and an explicit override, never a block.
- `not_required` is never written. A line is recorded or it is absent, and absence means not needed.
- The prescribed power stays on the Doctor's Rx station. The Correction form gains a real seven-field measurements editor so a missed power is fixable without a walk-back to a locked prescription.
- The line is a station, not a permission. The server does not check which line an operator records against.

## Consequences

Each desk shows one control with at most two buttons. Medicine is Given or Out of stock; Fixed-power specs is a single Issue; Spectacles to be made is a collection-day picker and Defer; OT is Done at camp or Schedule. There is no dropdown anywhere on a line desk.

A blank line column in the Camp records export now has exactly one meaning.

Doctor's Rx becomes a hard prerequisite. A line desk that scans a patient with no transcription can do nothing but send them back, and a transcriber who omits the powers blocks both specs desks until someone files a correction. The correction path is audited, which the previous walk-back to an unlocked prescription was not.

Because the line is not enforced server-side, a mis-set line records against the wrong desk with no refusal. That is accepted: enforcing it would make an operator's own override useless and would stop an admin covering a desk.

## Rejected alternatives

- **First desk to see the patient fills the prescription, later desks read it** — no fifth station and one less account setting, but it makes the medicine volunteer transcribe eye powers they cannot verify, and which desk owns the prescription then depends on the order patients happen to walk.
- **Let the specs desks write powers into a locked transcription** — matches the glossary's older wording and removes the correction round-trip, but two stations then write the same seven fields and the lock stops meaning anything.
- **Drop the lock entirely** — simplest to build, but the prescription stays editable by four desks for the whole visit and the correction history disappears.
- **Store the required lines as a field the Doctor's Rx operator ticks** — unambiguous routing, but it duplicates what the prescription fields already imply and adds one more thing to get wrong at the busiest station.
- **Keep `not_required` as an escape hatch on every desk** — preserves an explicit "not needed" in the export, but reintroduces exactly the option that makes the menus confusing.
