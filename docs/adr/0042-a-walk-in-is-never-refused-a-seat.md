# ADR 0042: A walk-in is never refused a camp-day seat

## Context

`_assert_capacity` claimed a camp-day seat with a conditional increment and raised `CAMP_DAY_FULL` when the day was at its limit. It applied to every registration path, so a patient who had travelled to the camp and was standing at the desk could be turned away by a counter.

The trust does not refuse a patient who has come to the camp. The seat limit exists to plan footfall and to stop remote registration overfilling a day, not to cap who is seen on the day.

Camp-day capacity is already the soft one of the three limits. ADR-era behaviour records it as "a planning number for footfall", and Arrival already moves a patient between days without consuming or releasing a seat. OT Schedule Day and Specs collection day seats are different: they are surgical and workshop capacity, and stay a hard block.

## Decision

`_assert_capacity` takes `enforce_limit`. `_create_registration` computes `walk_in = not is_self and day.get("day_date") == today_ist_str()` and passes `enforce_limit=not walk_in`.

- **Walk-in** (a desk registration for a camp day that is today): the seat is counted, never refused. `booked` may exceed `seat_limit`.
- **Pre-registration** (a desk registration for a later day): refused with `CAMP_DAY_FULL` when full.
- **Self-registration**: refused with `CAMP_DAY_FULL` when full, including on the camp day itself.

A walk-in still increments `booked`, so the count stays truthful and the overflow is visible rather than hidden. A day whose `day_date` is missing is treated as not a walk-in, so an unreadable date enforces the limit rather than silently disabling it.

This is the same walk-in predicate as ADR 0041, which suppresses the registration SMS for the same registrations.

## Consequences

Nobody who reaches the camp is turned away by the software. The desk operator never has to explain a counter to a patient who has already travelled.

`booked` can exceed `seat_limit` on a camp day. The public projection is unaffected: it counts patient documents rather than reading `booked`, and already clamps remaining seats with `max(0, …)`, so the figure bottoms out at zero instead of going negative. `ser_day` exposes neither counter.

Remote demand is still capped. A day that fills up stops accepting self-registration, which is what protects the day from being oversubscribed before it starts.

Camp-day seat limits no longer bound the day's real attendance, so the limit is a planning input rather than a guarantee. Anyone sizing staff or supplies from `seat_limit` alone will under-count a busy day; the booking count is the number to read.

## Rejected alternatives

- **Drop the camp-day seat limit entirely** — no counter, no asymmetry, much less code. Rejected because the limit still does useful work against remote registration: without it a popular day could be fully booked online before any walk-in arrives.
- **Let a walk-in exceed the limit but stop counting it** — keeps `booked` within `seat_limit`. Rejected because the count would then understate attendance, which is the number the camp actually needs.
- **Give camp days an explicit "allow overflow" flag per day** — admin-controlled rather than implied by the date. Rejected as configuration for a rule that has no exception: the trust never refuses a walk-in, on any day.
