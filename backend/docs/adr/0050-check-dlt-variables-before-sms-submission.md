# ADR 0050: Check DLT variables before SMS submission

## Context

On 23 September 2026, MSG91 charged for two registration messages that failed DLT scrubbing. The exported failure reason was `DLT Template variable exceeded max length`. Both request IDs matched production ledger rows whose camp venue was 64 characters. MSG91 permits at most 40 characters in each DLT variable and charges for failed messages.

## Decision

Check every rendered DLT variable before claiming a ledger row or submitting to MSG91. Skip a message if any variable exceeds 40 characters. Let an admin set an optional camp `venue_sms` of at most 40 characters; registration and camp reminders use it in place of the full venue. Keep the full venue for camp records. A camp or OT schedule with a longer full venue requires a short SMS venue at its API boundary. New camp and OT forms start with recognisable short SMS venues.

Automatic truncation was rejected because it can remove the part of an address patients need. Changing the approved template text was rejected because it requires new DLT approval.

## Consequences

An existing camp or OT day with an overlong venue and no short SMS venue will not submit SMS until an admin sets one. The UI identifies that state. Previously accepted submissions remain in the ledger and are not retried automatically; provider acceptance does not prove delivery. The operator must inspect MSG91 delivery reports for final status.
