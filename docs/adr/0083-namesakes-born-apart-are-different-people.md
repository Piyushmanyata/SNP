# ADR 0083: Namesakes born apart are different people

**Amends ADR 0063.** Wayfinder map #70, ticket #81.

## Context

- Duplicate in camp matches last-4 + name and ignores DOB. At 15,000 patients, about 11 pairs of different people share a name and the last four Aadhaar digits (range 6–56).
- The second namesake was refused as "Already registered". At the door, their card went to Mismatch review against the first namesake's registration, with an identical name and only a DOB diff. Confirming it stamped Arrival and printed the other patient's prescription.
- ADR 0063 kept Mismatch review for a DOB diff because one person can hold an XML card with a birth year (stored as `YYYY-01-01`) and a Secure QR with a full date.

## Decision

- A scanned registration whose DOB proves a different birth is not a Duplicate in camp hit, and it is not a door or confirm candidate for that card. The DOBs prove a different birth when:
  - the birth years differ, or
  - both are full dates (neither is 1 January) and they differ.
- A year-only DOB against a full date in the same year may be one person. It still goes to Mismatch review.
- A registration of the card's own Person is always a hit.

## Consequences

- The second namesake registers normally and gets their own Patient code. At the door they get `no_match`, then the walk-in path.
- `scan_confirm` onto a namesake born apart is refused with `STALE_CANDIDATE`.
- Someone whose Aadhaar DOB was corrected to a different year gets a second registration. That is rare, and it is safer than printing a stranger's paper.
- Two people with the same name, last-4 and a full DOB, or a DOB on 1 January of the same year, still collide (about 0.4 pairs at 15,000). Mismatch review remains the guard for them.

## Rejected alternatives

- **Compare Person only.** A year-only card and a Secure QR for the same human make two Persons. The door would then register them twice.
- **Keep review and warn harder.** An identical name with a small DOB diff looks like a typo, and at a 20-second door the reviewer confirms it.
