# Clinical and authentication production contract

Date: 2026-09-05

## Context and decision

Clinical operators monitor a line for input focus while physical volunteers direct patients. All clinical operators can transcribe, correct and fulfil any prescription. An account's legacy line preference is not an authorization boundary. A separate prescription station is unnecessary.

Surgery is scheduled at Vimla Ramkrishna Bajaj Eye Hospital, Near Canara Bank, Bilasi Mod, Deoghar 814112 (Jharkhand), phone 9835317006. Camp operators create a hospital token; they cannot mark surgery performed at camp. `ot` accepts only `deferred`, with an OT schedule day. The server supplies the hospital venue and validates an active camp, a current or future date and positive capacity. The picker excludes dates before today in IST, and booking rechecks the date even when the screen was loaded before midnight or the patient already holds a seat. Spectacles collection uses a time window without a seat limit.

## Concurrency and audit

The application uses Mongo conditional updates and unique indexes instead of introducing a replica-set transaction requirement. A prescription has a temporary atomic write claim shared by fulfilments and corrections. Simultaneous writes return 409 so the operator reloads before retrying. Direct transcription updates require an unlocked record with no active claim. Claims expire after two minutes if a worker terminates.

Fulfilment failures release newly reserved OT capacity and restore the prior active slip. The unique `(transcription_id, item_type)` index limits each line to one fulfilment. Corrections preserve their append-only history and validate values using the same prescription model as initial transcription. Fixed-power and made-to-order spectacles remain mutually exclusive.

Consequence: ordinary concurrency and injected write failures are covered. These multi-document operations are not fully atomic during abrupt process termination or loss of Mongo connectivity. After an interrupted clinical write, reconcile the active slip, current fulfilment and schedule occupancy before resuming that patient's booking. A transaction-backed deployment would be required to eliminate this failure window.

## Authentication

Login and PIN changes claim a shared five-attempt Mongo budget before bcrypt verification. The identifier index is unique, and attempts reopen after 15 minutes. Bcrypt work runs in threads so one sign-in does not block unrelated async requests.

A self-service PIN change atomically compares the previous hash, increments `session_version` and issues a replacement access cookie. Older sessions become invalid. An administrator's PIN reset also increments the version. PINs contain exactly four ASCII digits. The same-origin cookie default is `SameSite=Lax`.

Authentication issues one access token, valid for 12 hours. There is no refresh endpoint or background refresh flow; an expired session requires sign-in. Unused refresh-token generation and issuance have been removed. Logout clears any legacy refresh cookie left by earlier versions.

## SMS delivery and latency

HTTP registration and token responses complete before the SMS provider call starts. FastAPI background tasks perform best-effort delivery; Mongo retains the per-patient/type/date ledger. Provider-accepted messages are not resent. Failed rows can be claimed atomically by a later reminder run; cron reports `ok: false` and a `failed` count until failures are cleared. Pending rows are not automatically retried because a provider timeout or interrupted worker can leave acceptance uncertain.

The configured MSG91/DLT templates must use the updated Hindi copy in `sms.py`; changing local text does not change the provider's registered template. Surgery messages include the prescription, token, Aadhaar card, ration card and mobile number, identical to the Bring list on the printed papers (ADR 0039). The provider `date` variable is a Displayed date, DD-MM-YYYY, while the reminder ledger's `event_date` stays ISO. Spectacles SMS appends the collection time window to that variable. Each DLT variable must be at most 30 characters and every SMS venue follows one rule — 3 to 30 characters, no link, no phone number, no placeholder; the backend skips a message that breaks either before provider submission. Camps, OT schedules and Specs collection days whose venue breaks the rule require a short `venue_sms` at their API boundary (ADR 0051). The ledger's `sent` state means MSG91 accepted the request ID, not that the phone received the message; MSG91's delivery report, received at `/api/webhooks/msg91`, records the final status, reason and credit, and a DLT failure pauses that message type (ADR 0052). A failure after the request reached MSG91 is `uncertain` and is never retried, because the provider API has no application idempotency key.

## Performance and checks

Patient clinical history batches patients and camps, reducing 20-visit history from 41 database queries to 3. Added indexes cover person history, active prescription slips, reminder target dates and correction history.

Analytics uses Mongo counts, ID-only reads and grouped volunteer, fulfilment and SMS summaries. Its previous 20,000-record and 5,000-message limits no longer truncate daily totals. Database aggregation was chosen over response caching so counts remain current without cache invalidation. The 10,000-registration profile found an indexed patient query taking 18 ms, while transferring and decoding 21,000 full documents (9.48 MB) across the three principal reads took 152 ms.

The local Docker benchmark used 10,000 registrations, 8,000 arrivals, 6,000 seen patients, 5,000 prescriptions and 8,000 fulfilments. Each case made 100 measured requests after eight warmups. All 400 requests completed without errors, and HTTP analytics totals matched the seeded stages, fulfilments, 100 failed SMS records and 20 volunteers.

| Endpoint | Concurrency | Before p50 / p95 (ms) | After p50 / p95 (ms) |
| --- | ---: | ---: | ---: |
| Analytics | 1 | 200.94 / 239.79 | 55.55 / 74.69 |
| Analytics | 8 | 2032.52 / 2536.07 | 161.15 / 181.86 |
| KPIs | 1 | 16.57 / 18.16 | 22.21 / 29.38 |
| KPIs | 8 | 33.01 / 46.70 | 34.25 / 42.53 |

Analytics p95 improved 92.8% at eight concurrent requests, with throughput increasing from 3.85 to 49.14 requests per second. KPI code was unchanged; its measurements indicate run-to-run host variation. These are local Docker measurements, not Hostinger guarantees. The deterministic dataset remains isolated in `snp_audit`, inactive after restoring the previous active camp. A regression also checks exact totals above 20,000 arrivals.

After this benchmark, review found that selecting the next schedule from 200 unsorted records could omit an earlier day. Analytics now retrieves the earliest matching day directly through sorted Mongo queries; spectacles require nonempty start and end times. Regression coverage puts the earliest day after 200 later records and excludes expired, other-camp and incomplete collection days.

Regression tests cover two overlapping OT bookings, preserving the old slip after an injected persistence failure, hospital-only surgery, response-before-SMS scheduling, malformed correction values, PIN-session replacement, twelve simultaneous wrong logins sharing five attempts, and failed SMS retries. Real Mongo concurrency and Docker HTTP workflow verification are separate deployment checks; mock tests do not establish VPS latency or crash recovery guarantees.
