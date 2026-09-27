# ADR 0091: Lock resolution is one module, translated per station

**Carries ADRs 0011, 0033, 0063 and 0083.**

## Context

- The Lock decision tree (Duplicate in camp → Trivial diff → Mismatch review → Aadhaar overwrite) was written twice: once for the door, once for the registration desk.
- The door reached it by importing six private helpers from the registration module and reshaping the decoded card into a `RegisterBody`.
- There were two near-identical Aadhaar overwrite writers. ADR 0083 (namesakes born apart) had to be applied to both.
- Issue #88 (slice 6) asks for one module that returns one Outcome, with each station translating it.

## Decision

`backend/lock_resolution.py` has:

- **`find_person(card)`:** looks a Person up and never creates one.
- **`resolve_person(card)`:** finds or creates one. It is used only where registration or the overwrite creates a Person today.
- **`find_candidates(camp, card, person, scanned, phone)`:** the camp's registrations that match by the Duplicate in camp keys, minus namesakes born apart (ADR 0083).
- **`classify(card, candidates, person, scanned)`:** pure. It returns one Outcome:
  - `own`: a scanned candidate of this card's Person
  - `scanned_elsewhere`: a scanned candidate of another Person, with its diff
  - `ambiguous`: more than one Manual entry
  - `overwrite`: exactly one Manual entry and no material diff
  - `review`: exactly one Manual entry with a material diff
  - `none`: no candidates
  - `duplicate`: any candidate of a typed entry
- **`overwrite(patient, card, person, extra_fields)`:** the single Aadhaar overwrite writer. It keeps the shared guard (not scanned, no Person, not printed, not seen). It refuses `ALREADY_PRINTED` when printed or seen, `NOT_A_MANUAL_ENTRY` otherwise, and `DUPLICATE_IN_CAMP` on a unique collision. Registration-only fields (`registration_request_id`) pass in through `extra_fields`.

The Trivial diff stays the rule in `helpers.material_diff`. The stations translate the Outcome exactly as before:

| Outcome | Door (`/desk/scan`) | Registration desk |
|---|---|---|
| `own` | Arrival and the prescription | `DUPLICATE_IN_CAMP` |
| `scanned_elsewhere` | `mismatch_review` | `DUPLICATE_IN_CAMP` |
| `ambiguous` | 200 with `registrations` | `AMBIGUOUS_MANUAL_ENTRY` |
| `overwrite` | overwrite, then Arrival, `overwritten: true` | overwrite (from Self-registration: `DUPLICATE_IN_CAMP`) |
| `review` | `mismatch_review` | `MISMATCH_REVIEW_REQUIRED` until `review_confirmed_id`, then overwrite |
| `none` | `no_match`, nothing created | continue to Lookalikes and create |
| `duplicate` | — | `DUPLICATE_IN_CAMP` |

The door's scan-confirm keeps its order: door open, `REGISTRATION_NOT_FOUND`, `WRONG_CAMP`, not a candidate (`DUPLICATE_IN_CAMP` or `STALE_CANDIDATE`), overwrite a Manual entry, then Arrival.

## Consequences

- Changing the Lock rule is one change, and both stations follow it.
- `classify` has a table of plain-dictionary tests covering every Outcome and each Trivial-diff rule. The candidate search has a born-apart test. The overwrite has guard, collision and field tests.
- The six private cross-module imports, the card-to-`RegisterBody` reshaping and the second overwrite writer are gone.

## Rejected alternatives

- **Have the door call the registration handler's conflict function.** It is less code, but the door would keep reshaping a card into a request body, and the rule would still be written in registration's terms.
- **Return HTTP responses from the module.** One fewer layer, but the two stations answer the same Outcome differently, so the module would need to know which station called it.
