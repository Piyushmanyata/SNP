# ADR 0048: Enable each approved SMS flow independently

## Context

On 23 September 2026, SmartPing approved registration, camp reminder, surgery scheduled and surgery reminder templates. Both spectacles templates were rejected because the operator said variables could be static. MSG91 verified the four approved flows. The existing configuration required all six flow IDs, preventing the four approved messages from sending.

## Decision

MSG91 is available when its auth key and at least one flow ID are configured. Each patient SMS checks its own flow ID before creating a reminder ledger row. The spectacles flow IDs remain unset until approved copies are registered in SmartPing and MSG91.

## Consequences

The four approved message types can run while spectacles messages are skipped without failed or pending ledger rows. A missing flow ID does not delay camp or surgery reminders. Operators must add the spectacles flow IDs after approval. We rejected waiting for all six because it would suppress approved registration and clinical messages. We rejected pointing spectacles messages at an approved but mismatched template because it would violate the registered DLT copy.
