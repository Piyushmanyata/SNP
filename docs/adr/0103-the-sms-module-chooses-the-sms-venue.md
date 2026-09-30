# ADR 0103: The SMS module chooses the SMS venue, and a reminder reads the Token's

**Carries ADR 0040 and ADR 0078** (file `0078-one-sms-venue-rule-at-thirty-characters.md`, whose header still reads ADR 0051). Leans on ADR 0089.

## Context

- ADR 0040 gave a camp, an OT Schedule Day and a Specs collection day a short SMS name, and ADR 0078 made the SMS venue one rule. The rule for judging a venue lived in `sms.py`. The rule for choosing which text to judge did not: "the short name, else the full venue" was written out seven times.
  - `models._checked_sms_venue` (save time)
  - registration confirmation (`routes_registration`)
  - camp-day edit notice (`routes_camps`)
  - camp reminder (`routes_reminders._camp_page`)
  - Token SMS (`tokens.defer`)
  - Schedule-edit notice (`tokens._replace_tokens`)
  - Token reminder (`routes_reminders._slip_page`)
- Each copy read a different field pair (`venue_sms` / `venue` on a camp or day, `collection_venue_sms` / `collection_venue` on a Token) and handled a missing venue differently: `""`, a `KeyError`, or nothing.
- The OT reminder had a second source. It read the Token's stored SMS venue, then replaced it with the live OT Schedule Day's, which meant every sweep loaded the whole `ot_schedule_days` collection. Specs reminders already trusted the Token.
- The override dates from before `tokens.py` kept Tokens in step with their day (ADR 0089): `defer` copies the day's venue onto the Token, a material Schedule edit replaces every active Token with the day's new venue and short name, and any other edit syncs `collection_venue_sms` in the same transaction. Only `tokens.py` writes those fields.
- Issue #110 (slice 6) asks for one place that chooses the SMS venue.

## Decision

- `sms.sms_venue(place)` is the only place that decides which text an SMS gives for a venue. It is pure and takes any document that carries a venue: a camp, an OT Schedule Day or Specs collection day, or a Token.
  - It returns the admin's short name if it is not blank after `clean_sms_venue`, else the cleaned full venue, else `""`.
  - It reads `venue_sms` or `collection_venue_sms` for the short name and `venue` or `collection_venue` for the full venue. No document carries both pairs, so a caller never says which shape it holds.
  - It never raises for `None`, `{}`, missing keys or `None` values. It does not judge the result.
- The six SMS callers and the save-time check in `models.py` use it. The save-time check keeps its own cleaned short name, only to choose its error message.
- The rule stays in `sms_venue_problem`, checked at save time by `models.py` and again at send time in `_compose`. A missing or bad venue still ends as a message that is not sent and not charged. Nothing empty or placeholder is submitted.
- The Token reminder no longer looks up the live OT Schedule Day. The Token is the source, because `tokens.py` writes the day's SMS venue onto every Token when it issues one, replaces one or edits the day's short name. A test (`test_every_edit_path_leaves_each_active_token_reading_its_days_sms_venue`) drives `defer` and `edit_day` through every edit path and fails if any active Token stops reading its day's SMS venue.
- `routes_reminders._slip_page` loses its `ot_days` parameter and `_context` returns `(camps, staff)`. `_gate` and Canary are untouched.
- ADR 0040's clause "the D-1 reminder through the day document" is amended: the reminder reads the Token's SMS venue.

## Consequences

- A seventh message that names a place calls `sms.sms_venue`. The choice cannot drift between save time and send time, because both use the same function.
- The reminder sweep makes one query fewer, and an OT reminder and a Specs reminder now read their venue the same way.
- **Legacy Tokens.** The Token is now the only source for an OT reminder, so a Token that `tokens.py` never brought into step with its day changes what it sends:
  - a Token issued before the non-material sync shipped (2026-09-24) whose day's short name was edited afterwards sends the Token's older short name
  - a Token issued before `collection_venue_sms` existed (2026-09-19) sends its full venue: sent if it is 30 characters or fewer, skipped and not charged if longer
  - a Token or day edited directly in the database
  - Before deploying, run a read-only check on production for active OT Tokens with `collection_date` on or after today whose `collection_venue_sms` differs from their day's `venue_sms`. If any exist, repair them once from the day, or let the next Schedule edit do it.
- A whitespace-only stored short name now falls back to the full venue instead of giving an empty venue that is skipped. The API cannot store one, because `_checked_sms_venue` turns a blank short name into `None`.
- A camp document with no `venue` key used to raise `KeyError` in the registration confirmation and the camp-day edit, and now yields `""` and skips the SMS. `CampBody.venue` is required, so the API cannot produce one.
- `frontend/src/lib/sms.js` (`smsVenueFor`) still repeats the short-else-full choice for the live admin form. It is the cross-language mirror ADR 0078 records, and it is the one copy left.
- A future write to `ot_schedule_days` or `specs_collection_days` outside `tokens.py` would break the guarantee the reminder now relies on. `routes_clinical` only inserts new days, which have no Tokens.

## Rejected alternatives

- **Keep the reminder's live-day override and only move the `a or b` expression into `sms.py`.** It leaves two sources of truth for an OT reminder's venue. A Token that went stale would be hidden by the override instead of caught by a test, the sweep would keep loading every OT Schedule Day to override a value `tokens.py` already keeps correct, and "which venue" would still have a special case in the reminder job.
- **A resolver that takes a database and looks the day up itself.** The rule is pure and every caller already holds the document.
