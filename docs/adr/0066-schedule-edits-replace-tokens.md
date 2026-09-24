# ADR 0066: A schedule edit replaces the Tokens it changes

Issue #50, slice S8 (stories 20, 21, 67, 68).

## Context

- `POST /clinical/ot-days` and `POST /clinical/specs-days` updated an existing day with the same date. That was a second edit path, and it skipped the Tokens. Specs days had no other edit path.
- `PATCH /clinical/ot-days` rewrote the date and venue on the patient's Token document. The paper in the patient's hand still showed the old values, and nothing marked it as out of date. A venue-only change sent no SMS.
- Every later edit of a moved camp day sent the move notice again, which covered its retry after a crash. A booking made after the move had a different ledger key, so a later seat-limit change sent that patient a second SMS.
- A camp-day move started one in-process `BackgroundTask` per patient, up to 15,000. A restart lost them.
- Specs hours were stored on each day and Token, then checked against the fixed 10:00–17:00 (ADR 0049).

## Decision

- **One edit path.** `POST` on a date that already has a day returns 409 `DAY_EXISTS`. Edits go through `PATCH /clinical/ot-days/{id}` and the new `PATCH /clinical/specs-days/{id}`.
- **A material edit is a date or venue change.** For specs days the end date also counts. A material edit gets a new `edit_revision`. In one transaction, each active Token on the day:
  - is replaced by a new Token version with the new values, `replaces` and `edit_revision`;
  - the old Token is marked `active: false` and `superseded_by`;
  - the fulfilment points to the new Token;
  - one `ot_change` or `specs_change` SMS intent is queued per patient, keyed `edit:{revision}`. Its copy says the old paper is no longer valid.

  A seat-limit or SMS short-name change replaces nothing and sends nothing.
- **Camp-day moves use the same ledger.** A date change and its notices commit in one transaction. Each booking gets one queued `registration` intent keyed `edit:{revision}`. Bookings made after the move use the same key, and only a date change queues notices. Queued intents are sent after commit by one background task. S10's worker will retry any that are left.
- **Patients to phone.** `GET /clinical/schedule-notices` lists replaced Tokens whose notice was not sent, failed, was rejected or paused, or has a failed delivery report. `POST /clinical/schedule-notices/{slip_id}/contacted` records the call. Admin shows the list in the OT & Specs tab. Until MSG91 approves the two new flows (`MSG91_TEMPLATE_OT_CHANGE` and `MSG91_TEMPLATE_SPECS_CHANGE`), every affected patient appears there.
- **Specs hours are constants** (`sms.SPECS_PICKUP_START_TIME` and `SPECS_PICKUP_END_TIME`). They are no longer stored on days or Tokens. Screens use one frontend constant, `SPECS_HOURS`.
- **Indexes:**
  - `deferred_slips {ot_schedule_day_id, active}`;
  - `deferred_slips {specs_collection_day_id, active}`;
  - `fulfilments {ot_schedule_day_id, status}`.

## Consequences

- A patient holding an old Token either gets an SMS saying it is void, or appears on the Patients to phone list. The station shows "Print this new Token and take back the old one", and a reprint of the old Token is stamped "Replaced — not valid".
- Moving a day and back sends two notices (two revisions) and leaves three Token versions.
- The operator must register two DLT templates (`backend/docs/msg91-templates.json`) and set their flow IDs. This is a Release gate step.

## Rejected alternatives

- **Keep editing the Token document in place.** The paper in the patient's hand cannot be edited, so the record must say which paper is current.
- **Reuse the approved `ot_token` and `specs_token` copy for the notice.** It does not say that the old paper is void, which the decision in #50 requires.
- **Re-send on every edit, relying on ledger de-duplication.** That is the bug behind story 68: a booking made after the move had a different key.
