# ADR 0026: Specs collection days are time windows, not seats

## Context

ADR 0014 treated Specs collection days like OT Schedule Days: a hard seat limit, consume/release, and “full” refusals. Camp operations need many patients to share one collection window. Capacity fields leaked into Tokens, reminders, exports, and the Camp-day board.

## Decision

- A Specs collection day is identified by active `camp_id` + ISO `day_date`.
- Required fields: trimmed `venue`, strict `HH:MM` `start_time` and `end_time` in Asia/Kolkata, `start_time < end_time`, window end after now.
- Create/update/list neither accept nor return `seat_limit`, `seats_taken`, or `seats_free`.
- Clinical may select only a current or future window belonging to the patient's camp. Incomplete legacy rows are Admin-visible as “window required” and are not selectable.
- Newly issued Specs Tokens and reminders snapshot date, venue, start, and end. Later schedule edits do not change issued Tokens.
- OT Schedule Day seats and Camp-day booking capacity are unchanged.

## Consequences

Unlimited collection volume on a scheduled window. OT overbooking protection remains. Historical Specs capacity fields in Mongo stay unread.

## Rejected alternatives

- Keep Specs seats and raise the limit — still encodes the wrong operating model.
- Multiple windows on the same camp/date — needs a separate domain decision.
