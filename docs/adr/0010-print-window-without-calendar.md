# ADR 0010: Print window without a calendar check

## Context

Printing a prescription required the camp day's calendar date to be today (IST) *and* `printing_open`. A Docker or field clock that was not "today" blocked paper even when an admin had opened the Print window.

## Decision

Print prescription checks the per-camp-day Print window boolean only. Open: print succeeds regardless of calendar date. Closed: 409 with the existing code `PRINT_WINDOW_CLOSED`.

## Consequences

Admins keep the same Open/Close control. A wrong host clock no longer silently closes printing. Closed still means closed.

## Rejected alternatives

- Keep the IST "today" conjunct — field clocks and Compose dates made printing flaky.
- Derive open/closed from the calendar — admins already declare the window.
