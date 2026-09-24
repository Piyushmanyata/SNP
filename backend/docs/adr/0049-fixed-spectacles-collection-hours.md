# 0049 Fixed spectacles collection hours

Amended by ADR 0066 (S8): the hours are constants and are no longer stored on days or Tokens. "Days with older hours" no longer exist.

## Context

SmartPing rejected both spectacles SMS templates because variable content could be static. The start and end times came from the admin schedule, were copied onto patient slips, and appeared in the SMS. Fixing only the message text would give patients conflicting pickup hours.

## Decision

Spectacles collection runs from 10:00 AM to 5:00 PM each day of its scheduled date range. The backend stores these as `10:00` and `17:00`, sets them for every new or updated collection day, and rejects requests with different hours. The admin form no longer edits hours. Patient and staff screens display AM/PM times. Both revised SMS copies state the hours as fixed text and use five variables. Days with older hours cannot receive new token assignments or appear as the next valid collection day. Spectacles SMS stays disabled until the revised copies receive new DLT approval and matching MSG91 flows.

## Consequences

The production data audit on 23 September 2026 found one future collection day at 10:00–15:00 and no active spectacles slips. That day must be updated to 10:00–17:00 during deployment before staff assigns patients. Existing slip snapshots in other environments retain their original hours; their SMS is skipped if those hours differ. The rejected DLT IDs remain historical references and cannot be used for the new text.

We rejected keeping admin-defined hours and seeking a seven-variable exception because the operator specifically identified reducible variables. We rejected changing the SMS alone because the schedule and printed token would disagree.
