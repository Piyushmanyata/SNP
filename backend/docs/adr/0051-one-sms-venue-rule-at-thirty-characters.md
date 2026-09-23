# ADR 0051: One SMS venue rule, at thirty characters

**Amends ADR 0050.**

## Context

ADR 0050 limited each DLT variable to 40 characters, the value MSG91's help page gives. Jio's DLT guides limit a `{#var#}` to 30 characters, and no production send has yet carried a variable between 31 and 40 characters, so the 40-character limit is unproven. MSG91 charges for every failed message. The default short venue for a new camp was exactly 40 characters.

Operators also reject messages that carry a link or call-back number that is not whitelisted, including one inside a variable. Specs collection days had no short SMS venue and no check at all; the production specs day's venue was `NA`.

## Decision

Every SMS venue — the short name on a camp, OT Schedule Day or Specs collection day, else its full venue — follows one rule. It is 3 to 30 characters after spacing is tidied, and has no link, no run of seven or more digits, and no placeholder such as NA, N/A, TBD or test. The API refuses a schedule whose SMS venue breaks the rule, the admin forms show the reason as it is typed, and the send path checks every DLT variable against 30 characters and the venue against the rule again before claiming a ledger row.

Keeping 40 was rejected because a wrong guess fails and is charged for every patient of a camp. Screening at send time only was rejected because it drops messages without telling the admin.

## Consequences

Admins write shorter place names. A schedule saved before this change is not re-checked until it is edited; if its venue breaks the rule its SMS are skipped, and the admin screens flag it. If MSG91 confirms that 40 characters are delivered on every operator, relax the limit in both `sms.py` and `frontend/src/lib/sms.js`.
