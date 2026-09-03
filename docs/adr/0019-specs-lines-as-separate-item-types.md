# ADR 0019: Fixed-power specs and Spectacles to be made as separate item types

## Context

The glossary says a Fulfilment line is one of four things and that each is a physical desk at the camp and one item type on the record. The code disagrees: `item_type` has three values — `medicine`, `specs`, `ot`. Fixed-power specs and Spectacles to be made are the same stored record, separated only by whether its status is `fulfilled` or `deferred`.

Recording a fulfilment deletes every prior record of that item type before writing the new one, refunding any collection-day seat it held. With one operator on one screen this is invisible and harmless. It stops being harmless the moment the two specs tables have two operators: the second desk to save silently erases the first desk's record. A patient issued a ready-made pair in the morning and later deferred for a made-to-order pair loses the issue entirely, and the Camp records export shows no trace it happened.

The export already pretends the split exists. It carries separate `fixed_power_specs` and `spectacles_to_be_made` columns and derives both from the one record through two lookup tables — which also means a `specs` record marked not required writes "not_required" into both columns at once.

## Decision

- `item_type` becomes `medicine | specs_fixed | specs_made | ot`.
- The valid status matrix becomes exactly: `medicine` accepts `fulfilled` or `not_available`; `specs_fixed` accepts `fulfilled`; `specs_made` accepts `deferred`; `ot` accepts `fulfilled` or `deferred`. `not_required` is accepted for nothing.
- `specs_made` owns the Specs collection day and `ot` owns the OT Schedule Day. `specs_fixed` and `medicine` own no day and can never consume a seat.
- The two specs lines are **mutually exclusive**. Writing one when the other already exists is refused with a `409` naming the other line. It is never an overwrite.
- The export reads the two specs columns directly. The two lookup tables that faked the split are deleted.
- No migration is written. There is no live fulfilment data to preserve.

## Consequences

The delete-before-write routine survives but can now only ever match the same line, so the two specs desks cannot touch each other's records. Re-recording the same line still replaces and still refunds its own seat, which is the behaviour that routine exists for.

The glossary's "four things, each one item type" becomes true rather than aspirational.

The refusal must ship with the split. Splitting the item type alone stops the two desks deleting each other and starts them silently double-recording instead — a different wrong answer, and a harder one to notice.

There is no unique index on fulfilments, so nothing in the index layer changes.

## Rejected alternatives

- **One Specs line, three item types** — collapses the menu from four to three, matches the current schema exactly, needs no migration and no exclusion check. Rejected because there really are two tables with two people at the camp, and a model that denies that pushes the problem into the operator's head.
- **Two desks, one record, last write wins** — cheapest possible change, keeps the schema. Rejected because it is the current defect stated as a decision: the export cannot show that a patient was issued specs before being deferred.
- **Allow both specs lines on one patient** — falls out of the split for free and would cover a patient issued a ready-made pair who also needs a made-to-order one. Rejected because the camp does not work that way; the explicit refusal tells the operator why instead of quietly recording two.
- **Migrate existing `specs` rows** — mapping `fulfilled` to `specs_fixed` and `deferred` to `specs_made` is mechanical, but `not_required` has no honest target and there is no data to migrate.
