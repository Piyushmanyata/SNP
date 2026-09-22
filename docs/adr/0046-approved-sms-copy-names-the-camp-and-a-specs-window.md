# ADR 0046: The approved SMS copy names the camp number, and a specs window spans days

**Amends ADR 0008 and ADR 0040.**

## Context

The trust approved final wording for all six SMS on 22-09-2026, ahead of DLT registration. Once registered, a template's fixed text cannot change without two to three days of operator re-approval. The approved wording differs from the old copy in three ways that the data model did not support:

- Every message names the camp by its number: "SNP के 162वें नेत्र शिविर".
- Both specs messages give a range of days and daily hours: "20-09-2026 से 27-09-2026 तक सुबह 10:00 बजे से शाम 05:00 बजे तक". A Specs collection day held one date and one time window.
- The specs hours sit between the fixed words सुबह and शाम, and the end time is written in 12-hour form (05:00, not 17:00).

## Decision

- **The camp number is a DLT variable, `camp_no`, set by the admin on the camp.** The camp form requires it and the camp card lets the admin edit it. A camp without a number sends no SMS: every message would otherwise read "SNP के वें".
- **A Specs collection day has an `end_date`.** `day_date` is the first day, and `end_date` defaults to it. The window is selectable until `end_time` on `end_date`. The Token snapshots the end as `collection_end_date`. The Token SMS and the printed Token state the range. The day-before reminder still fires the day before `collection_date`.
- **Specs hours must start before 12:00 and end at 12:00 or later.** The SMS sends both in 12-hour form. The fixed words सुबह and शाम are then never false. A day saved before this rule with other hours shows as needing a window and cannot be booked. A Token already issued with such hours is not sent. This avoids a message like "सुबह 02:00".
- **A message with a missing variable is not sent.** A legacy specs Token without hours is skipped, not sent with blanks. A Token without an end date reads as a one-day range.
- The provider receives only the variables its template uses, in `backend/docs/msg91-templates.json`. A test keeps that file identical to the code copy. Its `dlt_portal_body` is the text to register.

## Consequences

The 163rd camp needs no DLT re-approval and no code change. It only needs a number on its camp.

An existing camp sends nothing until an admin gives it a number. Deploying this change therefore includes setting the active camp's number.

Specs hours outside morning-to-evening, such as 14:00–17:00, are refused. An afternoon-only distribution cannot be scheduled without new approved wording.

## Rejected alternatives

- **Freeze "162" in the template text.** This is the simplest change now. It was rejected because every later camp would need six new DLT templates, six new MSG91 flows and a deploy.
- **Take the range from the camp's first and last specs days.** This needs no model change. It was rejected because the SMS would promise a range while the patient stayed booked to one day.
- **Freeze the hours as 10:00 and 05:00 in the template.** This was rejected because the printed Token uses the admin-set hours, so the SMS and the Token would disagree whenever those hours changed.
