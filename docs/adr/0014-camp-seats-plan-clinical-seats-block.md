# ADR 0014: Camp-day seats plan footfall, clinical day seats block

## Context

A camp day's seat limit could be zero, meaning unlimited. The public occupancy panel is meant to show total seats against registrations so far, and a total that includes an unlimited day has no value.

Separately, the same word "seats" covered two different physical things. A camp day's seats are how many people the venue and the volunteers can handle. An OT Schedule Day's seats are how many operations a surgeon can perform, and a Specs collection day's seats are how many pairs the workshop can produce. Only one of those bends.

## Decision

- Every camp day has a seat limit greater than zero. Unlimited is removed.
- Camp-day capacity refuses a new registration on that day once registrations reach the limit.
- Camp-day capacity does not refuse an Arrival. A patient booked for one camp day who arrives on another is checked in on the day they came, and arrivals on a day may exceed its limit.
- OT Schedule Day and Specs collection day seats stay a hard block. When every day of a type is full, the clinical desk cannot record the deferral and is told to call the admin, who adds a day.
- Public occupancy shows registrations against the sum of the camp's day limits.

## Consequences

The public number is honest about capacity and about how full the camp is. Nobody who has travelled to a camp is turned away at the door. A day's arrival count can exceed its limit, so the limit is a planning number for footfall, not a door policy, and reports must not treat an overage as an error.

The clinical hard block has a known cost: if no admin is reachable while every OT day is full, the patient's surgical need is not recorded anywhere. This was accepted deliberately in favour of not overbooking a surgeon.

## Rejected alternatives

- Keep unlimited days and hide the denominator when one is present — the public headline would silently change shape with admin configuration.
- A cosmetic camp-level target decoupled from the real per-day limits — the headline could read comfortably while a day was actively rejecting people.
- Recording a clinical deferral with no day assigned, for an admin to schedule later — preserves the clinical fact, but adds an unscheduled state, an admin assignment screen, and a Token the patient never receives in hand.
- Overbooking a clinical day behind a team-lead confirm — the seat limit would stop meaning anything, and the overflow lands on the actual surgery date.
