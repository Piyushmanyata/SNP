# ADR 0105: A line desk with nothing prescribed offers nothing to record

## Context

- ADR 0018 said a patient at a line their prescription does not imply gets "an advisory warning and an explicit override, never a block".
- The server now refuses any Fulfilment, of every status, for a line the committed revision does not name (`require_line_prescribed`, `LINE_NOT_PRESCRIBED`). ADR 0065 keeps unprescribed lines free of content.
- The desk still said "Record anyway" and enabled the station, so the operator's only possible outcome was a 409.

## Decision

- When the operator's line is not on the committed revision and no record exists for it, the desk says "This prescription has no <line>. Nothing to record at this station." and shows no station.
- When a record for the line exists, for example one a later correction removed the line from, the station shows as before so its Token can be reprinted.
- This supersedes ADR 0018's advisory-override clause. The server rule is unchanged.

## Rejected alternatives

- **Drop the server refusal.** It would let a medicine or specs record be written for a line the doctor never prescribed.

## Consequences

- A patient at the wrong line is sent on without a failed save. A missing line is fixed with a correction at Doctor's Rx, which is audited.
