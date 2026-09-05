# ADR 0020: Operator line as an admin default with a session override

> **Amended by [ADR-0030](0030-step-by-step-transcription.md).** Operator line no
> longer selects the initial prescription fields or autofocus: the transcription
> wizard runs an identical sequence for every operator. The line now chooses only
> which fulfilment station opens once the prescription is committed. Everything
> below about how the line is stored, defaulted and overridden still holds.

## Context

Once the clinical desk is line-scoped, something has to say which station an operator is on. There is one `clinical_desk_operator` role covering all five stations, and asking the question on every patient would add a tap at the busiest moment.

Staff records have no edit path at all today. The only mutations are create, disable and enable, so anything stored on the account is currently write-once.

Camps move people between tables during the day. An admin-owned setting with no self-service means the OT desk borrowing the medicine volunteer requires the admin to be reachable, which on a camp morning they often are not.

## Decision

- A `line` is stored on the clinical operator's account: `rx`, `medicine`, `specs_fixed`, `specs_made`, or `ot`. It is nullable, and it is only meaningful for the clinical role.
- The admin sets it at account creation and can change it afterwards. A `PATCH` on the staff record is added for that and accepts nothing else.
- The account's line is the **default**, not a lock. The operator sees their line in the page header and can change it for their own session. The override is client-side, never round-trips to the server, and is gone at the next login.
- An operator with no line — and every admin, who has none — is asked to pick one before they can look up a patient.
- The line does not gate any endpoint. `require_clinical` is unchanged and no new role is created.

## Consequences

Adding the first staff mutation endpoint means being explicit that it accepts one field. Widening it later to a general staff editor is a separate decision.

A table swap is handled on the floor in one tap and reverts on its own the next morning, so a temporary swap cannot silently become permanent.

Attribution is weaker than it looks: because the override is session-local and unenforced, the account's `line` says where someone was posted, not necessarily where they recorded. Fulfilments already carry the operator's identity, which is the value the export actually needs.

Admins get a picker rather than a station, which is what lets them cover a desk without a second account.

## Rejected alternatives

- **Picked at login and kept in browser storage, with no account field** — no schema change, no admin work, no new endpoint, and a volunteer moved to another table fixes it themselves. Rejected because nothing then records where anyone was posted, and a shared desk phone carries the previous shift's choice into the next one.
- **Admin-only, with a line editor and no override** — strongest guarantee that the medicine person never touches OT. Rejected because the desk stalls whenever the admin is busy, which is most of a camp morning.
- **Admin-only with no editor at all** — no `PATCH` endpoint, least code. Rejected because a swap then means creating a second account for the same person, and accounts multiply across a multi-day camp.
- **Ask on every patient** — safest against a stale selection. Rejected as one extra tap per patient, which is the confusion this work exists to remove.
- **A separate role per line** — would let the server enforce the station. Rejected because five roles to express one seating arrangement makes permissions and posting the same thing, and an operator could then never cover another desk.
