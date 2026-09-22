# ADR 0047: The SMS copy names the registered entity, not SNP

**Amends ADR 0046.**

## Context

On 22-09-2026 SmartPing (STPL), the DLT operator, rejected all six content templates. The reason on each was "Entity /brand name is not mentioned in the SMS content". DLT requires a complete business name, brand name or trademark in every template. The entity is registered as SIKAR ZILLA WELFARE TRUST, and "SNP" is not registered anywhere on the portal.

## Decision

Every message names the trust in full where it said "SNP": "Sikar Zilla Welfare Trust के 162वें नेत्र शिविर". The rest of the approved wording, the variables and their order do not change. The text to register is still `dlt_portal_body` in `backend/docs/msg91-templates.json`.

## Consequences

Each message is 22 characters longer. Unicode SMS are billed in 67-character parts, so some messages take one more part.

The six templates must be registered again with this text.

## Rejected alternatives

- **Keep "SNP" and upload proof that it is the trust's brand.** This keeps the wording, but acceptance is at the approver's discretion. Each rejection costs another one to three days.
- **Use "SZWT" or another abbreviation.** Like "SNP", it is neither the entity name nor a registered brand.
- **Keep "SNP" and add "- Sikar Zilla Welfare Trust" at the end.** The owner chose to name the trust once, in place of "SNP".
