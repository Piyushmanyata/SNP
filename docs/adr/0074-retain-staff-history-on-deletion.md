Renumbered from `backend/docs/camp-operations/adr/0006-retain-staff-history-on-deletion.md`.

# ADR 0006: Retain staff history on deletion

## Context

Staff accounts can have registrations, team credit, and clinical actions attached to their IDs. Removing the account document would break historical attribution and reporting. Disabling an account removes access but leaves it in the active staff roster and reserves its login name.

## Decision

Deleting staff revokes access and removes the account from the active roster while retaining its record and historical references. The old login name becomes available for a new account with a different ID. A team lead with assigned volunteers must have them reassigned before deletion; earlier registration credit remains with the original team. An admin cannot delete their own account or the last enabled admin.

## Consequences

Reports can still show who registered patients and which team earned credit. Deleted staff cannot sign in or be reenabled through the staff API. A new account may share a display name with a deleted account, so IDs remain the source of identity.

## Rejected alternatives

- Hard deletion: historical records would lose their staff identity.
- Disable only: deleted people would remain in the roster and prevent name reuse.
