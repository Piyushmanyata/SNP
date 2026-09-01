# ADR 0012: Arrival as a distinct registration state

## Context

Registration opens one to two months before a camp. A pre-registered patient is a booking, not a person standing at the desk. The lifecycle was `registered -> seen`, with `printed_at` as the only marker between them, so there was no way to say who had actually turned up. Counting arrivals meant counting prints.

On camp day the desk scans the card again, compares it to what is stored, and may need a volunteer to confirm an overwrite. That review sits between the scan and the print and can pause or be abandoned there.

## Decision

- The lifecycle is `registered -> arrived -> seen`. Arrival is stamped by a desk Lock that matches a registration in this camp.
- Print Prescription is gated on Arrival. Pre-registration never prints.
- A registration reaches Seen only through Arrival.
- A walk-in registers and arrives in one action.
- A patient booked for one camp day who arrives on another is checked in on the day they came. The registration moves to that day and the change is recorded.

## Consequences

Public occupancy can distinguish a booking from a body. No-shows are visible as a registration with no `arrived_at`, and the export carries that column. Camp-day arrivals may exceed that day's seat limit — see ADR 0014.

## Rejected alternatives

- Infer arrival from `printed_at` — a failed print, a closed Print window, or a reprint of a lost slip all corrupt the count. It counts prints, not people.
- A separate Pre-registration collection converted on camp day — duplicate detection, `reg_no` allocation, and occupancy counting would each have to work across two collections.
