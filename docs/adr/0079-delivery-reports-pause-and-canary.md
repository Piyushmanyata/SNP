Renumbered from `backend/docs/adr/0052-delivery-reports-pause-and-canary.md`.

# ADR 0052: Delivery reports pause a failing message type, and reminders send a canary first

## Context

MSG91 charges for every failed message. A DLT failure — a variable too long, content that does not match the template, an operator rejection — repeats for every patient until the cause is fixed, and the reminder worker submits up to 200 messages in one pass. Before this change nothing read MSG91's delivery reports, so a misconfigured flow would be charged for the whole batch before anyone noticed.

Every failed send was also retried up to three times. A read timeout or a dropped connection after MSG91 had received the request counted as a failure, so a retry could send and charge a second copy.

## Decision

- **Submission outcome by phase.** A failure before the request reaches MSG91 (DNS, refused connection, TLS) is `failed` and is retried on a later run. HTTP 429 and 503 are also `failed`, with `retry_after` five minutes later: MSG91 did not accept the message, so a retry cannot double-charge. A failure after the request was sent (timeout, reset, other 5xx, unreadable reply) is `uncertain` and is never retried. MSG91's own error reply is `rejected`, with its reason. A rejected canary pauses that message type. A rejected row from before the last resume may be retried once.
- **Delivery reports.** MSG91 posts each final status to `POST /api/webhooks/msg91` with the `X-SNP-Webhook-Secret` header. The ledger row with that request ID records delivered or failed, the reason, and the credit charged.
- **SMS pause.** The first DLT failure pauses that message type until an admin resumes it in Admin → SMS. A report about a message sent before the last resume does not pause again. A failure whose reason starts with `DND` is about one number's preferences, not the template, and does not pause; pausing on it was rejected because it would stop a Promotional template for every patient after one DND recipient. Registration and Token SMS that fall due during a pause are recorded as `paused` and not sent later; the day's reminder batch waits and goes out if the type is resumed that day.
- **Canary.** Each reminder type sends one message per event date first. The rest wait up to ten minutes for its delivery report, or go at once if MSG91 refused it outright. A resume sends a new canary.

Holding paused messages and sending them on resume was rejected at the owner's choice: dropping is simpler, and the board counts what was held back. Pausing without a canary was rejected because a batch is fully submitted before its first report arrives. Retrying every failure was rejected because a lost reply is indistinguishable from an accepted message.

## Consequences

`MSG91_WEBHOOK_SECRET` must be set on the server and the same value entered as a header in MSG91's webhook settings. Until then no reports arrive: every canary waits its ten minutes and nothing pauses on its own. The reminder batch starts about ten minutes later than before on a day with no reports. An `uncertain` message may or may not have reached the patient; MSG91's report, when it arrives, settles it.
