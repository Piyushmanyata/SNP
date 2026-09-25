# ADR 0080: The admin holds clinical desk operator access

## Context

The admin dashboard links to the Clinical Desk, and the frontend route already admitted admins. The backend still refused them: every `/api/clinical` operator endpoint required the `clinical_desk_operator` role, and a second check, `assert_clinical_operator`, repeated the same refusal inside each handler. On a short-staffed camp day the admin could not cover a clinical line without a separate operator account.

## Decision

`require_clinical` admits `admin` and `clinical_desk_operator`. `assert_clinical_operator` is deleted; the route dependency is the single role check. An admin picks a line for the browser session exactly as an operator does (ADR 0020), and every write is attributed to the admin's own account.

Creating a second, operator-role account for the admin was rejected: it splits one person's work across two identities and needs a PIN of its own.

## Consequences

Team leads and volunteers are still refused the clinical desk. The admin's clinical writes appear under the admin's name in histories and exports.
