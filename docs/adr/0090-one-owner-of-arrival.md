# ADR 0090: One module owns Arrival

**Carries ADR 0012 and ADR 0042.**

## Context

- Arrival is "stamped once", but two places wrote it:
  - the door's private `_stamp_arrival` helper, used by the door Lock, the door's scan-confirm and `/arrive`
  - the registration document builder, for a Manual entry typed at the door
- `/arrive` checked `NEEDS_DOOR_SCAN` inline.
- A test imported the private door helper.
- Issue #88 (slice 5) asks for one owner of the Arrival fields and of the Operating-day move.

## Decision

`backend/arrival.py` is the only code that writes the Arrival fields. It has three verbs:

- **`stamp(patient, actor, printing_state)`:**
  - returns an already arrived patient unchanged
  - otherwise refuses `PRINT_WINDOW_CLOSED` unless the state passed shows the door open
  - otherwise sets `arrived_at`, `arrived_by` and `queue_status` (registered → arrived) with a conditional update on "not yet arrived"
  - moves `camp_day_id` to the Operating day and records `camp_day_changed_from` when they differ
  - raises `REGISTRATION_NOT_FOUND` if the patient vanished
  - never reads Camp-day capacity (ADR 0042)
- **`fields_at_creation(arrived_by, now)`:** the Arrival fields of a new registration. For a Manual entry typed at the door, these are the same fields a door Lock stamps. Registration already restricts that entry to the Operating day with `NOT_OPERATING_DAY`.
- **`require_arrivable(patient)`:** refuses `NEEDS_DOOR_SCAN` unless the patient has a Lock, a No-card print or an Arrival.

Every caller already holds the printing state, so `stamp` takes it rather than looking it up. The door still refuses a closed Print window first, before it decodes the card. Print Prescription and No-card print still never stamp Arrival. Responses and stored fields are unchanged.

## Consequences

- Arrival tests (`test_arrival.py`) cover:
  - stamping once under a race
  - the Operating-day move
  - `PRINT_WINDOW_CLOSED`, `NEEDS_DOOR_SCAN` and a vanished registration
  - that a Manual entry at the door gets exactly the fields of a door Lock
- No test imports a private door helper.
- Lock resolution (#88 slice 6) calls `stamp` for the door's Outcomes.

## Rejected alternatives

- **Let `stamp` look up the printing state when none is passed.** That was the old helper's fallback, but no caller used it, and it kept a second route to `PRINT_WINDOW_CLOSED`.
- **Stamp a Manual entry at the door through `stamp` after inserting it.** That would put one registration through two writes, and the insert and the stamp could disagree for a moment.
