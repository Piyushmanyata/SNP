# SMS volume and MSG91 limits for a 15,000-patient camp

Issue #75. Researched 2026-09-26 from the repo code and MSG91/TRAI sources. There was no access to the live MSG91 account or the VPS.

## Answer

A 15,000-patient camp sends about **24,000 SMS**. Every template is Hindi (Unicode), so each SMS costs **3–4 credits**, which comes to **about 87,000 credits, roughly ₹15,000 + 18% GST ≈ ₹17,500**. The reminder worker, MSG91 and the delivery-report webhook can all handle that volume. The largest D-1 run (5,000 reminders) finishes in about 10–30 minutes. The real limits are **Unicode segment cost** and **DLT template coverage**: `ot_change`/`specs_change` are not DLT-registered, so a schedule change cannot be sent at all today.

## Assumptions

- 15,000 patients over 3 camp days. The design day is 5,000 patients (at 4 days it is 3,750).
- The shares come from the throughput model (branch `research/throughput-model`): 50% pre-booked, 45% walk-in with a card, 5% no card. Of all patients, 20% get spectacles made, 10% go to Hospital (OT), 40% get fixed-power specs and 70% get medicine. Only the first two shares send SMS.
- Every patient has a unique phone. This is an upper bound: the household-phone cap of 6 registration SMS per phone per IST day (`backend/sms.py:73` `REGISTRATION_DAILY_CAP = 6`, CONTEXT.md) only lowers the count.
- The segment estimates use these variable lengths: `camp_no` 2 characters, `reg_no` 8, `date`/`end_date` 10, `venue` 20. The DLT cap on `venue` is 30 characters (`VARIABLE_LIMIT = 30`, `sms.py:40`). A longer venue can add one credit.

## Which code sends what

| Flow | Trigger | Code |
|---|---|---|
| `registration` | Pre-booked registration only. Walk-ins get none (ADR 0041). Limited to 6 per phone per IST day. | `sms.py:292` |
| `camp` (D-1) | Worker sweep of patients whose `camp_day_id` is tomorrow's camp day | `routes_reminders.py:162` `_camp_page` |
| `ot_token`, `specs_token` | Desk, when an OT or specs-made slip is issued | `sms.py` `send_patient_sms` |
| `ot`, `specs` (D-1) | Worker sweep of active `deferred_slips` whose `collection_date` is tomorrow | `routes_reminders.py:175` `_slip_page` |
| `ot_change`, `specs_change` | A patient's OT or collection date moves | Not DLT-registered (owner follow-up), so not sent (ADR 0075) |

Walk-ins are not registered the day before, so the D-1 camp reminder only reaches pre-booked patients.

## Volume per flow

| Flow | Share | Whole camp | Per camp day (5k) | Fixed Unicode characters (`sms.py`) | Estimated length | Credits per SMS | Credits |
|---|---|---|---|---|---|---|---|
| Registration | 50% pre-booked | 7,500 | before the camp | 156 | ~196 | 3 | 22,500 |
| D-1 camp reminder | 50% | 7,500 | 2,500 (5,000 worst case) | 196 | ~236 | 4 | 30,000 |
| OT Token | 10% | 1,500 | 500 | 161 | ~201 | 3 (4 if venue > 20) | 4,500–6,000 |
| Specs Token | 20% | 3,000 | 1,000 | 156 | ~206 | 4 | 12,000 |
| OT D-1 reminder | 10% | 1,500 | after the camp, by OT day | 168 | ~208 | 4 | 6,000 |
| Specs D-1 reminder | 20% | 3,000 | after the camp, by collection date | 153 | ~203 | 4 | 12,000 |
| Walk-in exclusion | 50% | −7,500 registration SMS avoided | — | — | — | — | −22,500 saved |
| `ot_change` / `specs_change` | event | 0 today; one moved day's cohort (~500 OT or ~1,000 specs) once registered | — | 176 / 219 | ~216 / ~269 | 4 / 5 | per event |
| **Total** | | **~24,000 SMS** | | | | | **~87,000–88,500** |

The credit rule is from MSG91: Unicode is 70 characters for one credit and 67 per part when multipart (134, 201, 268…) [1]. The fixed lengths were measured from the `sms.py` template strings with the placeholders removed.

## Volume per day (3-day camp)

| Day | Worker (D-1 run) | Desk (Tokens) | Total |
|---|---|---|---|
| Weeks before the camp | — | 7,500 registration, spread across the booking window | ~1,100/day if booked in the last week |
| Evening before day 1 | 2,500 camp | — | 2,500 |
| Camp days 1–2 | 2,500 camp (for the next day) | 500 OT + 1,000 specs | 4,000 |
| Camp day 3 | — | 1,500 | 1,500 |
| After the camp | 1,500 OT + 3,000 specs, grouped by OT/collection date | — | depends on scheduling |

On a camp day, desk sends average about 3 per minute over an 8-hour day, which is negligible.

## Throughput

**MSG91.** MSG91 publishes no numeric requests-per-second limit for the Flow API. Its 429 page says rate limits "currently apply only to the MSG91 panel" and that "API integrations remain unaffected, unless specified otherwise". For heavy traffic it recommends retrying with delays or contacting the account manager [2]. The code already treats HTTP 429/503 as `Throttled` (`msg91.py:73`) and retries after `RETRY_AFTER = 10 min` (`sms.py:39`, ADR 0045).

**Reminder worker, 5,000 reminders in one run** (`reminder_worker.py`, `routes_reminders.py`):

- The worker runs its slots at 10:00 and 20:00 IST (`SLOTS = (10, 20)`). Each `POST /api/cron/reminders` sends at most `SEND_LIMIT = 200` or stops after `SWEEP_SECONDS = 60`, whichever comes first. When a run returns `complete: false` the worker calls again straight away, but it waits 60 s if the result is `waiting` (`reminder_worker.py:69-72`).
- Sends run with `asyncio.Semaphore(4)` concurrency (`routes_reminders.py:203`). Each send opens a new HTTPS connection to `control.msg91.com` with a 20 s timeout (`msg91.py:52`).
- **Canary:** each message type sends 1 SMS first, then waits for its delivery report or up to `CANARY_WAIT = 10 min` (`routes_reminders.py:25,42-56`). The worker polls every 60 s during that wait.
- **Estimate (latency not measured):** at 0.3–1.0 s per send, 4 at a time gives 4–13 SMS/s, so 200 per call takes 15–50 s. 5,000 reminders take 25 calls, about 6–21 min, plus 1–10 min of canary. **Total ≈ 7–31 min** starting at 10:00 IST, which leaves plenty of time before the 20:00 catch-up slot.
- **Risk to watch:** if MSG91 hangs, one call of 200 sends can take up to 200 / 4 × 20 s = 1,000 s. That is past the worker's 120 s HTTP timeout (`reminder_worker.py:19`) and the 90 s lease (`LEASE_SECONDS`). The worker then logs a failure and backs off, up to 300 s. The ledger's unique keys should prevent double sends, but that path was not tested here.

**Delivery-report webhook** (`POST /api/webhooks/msg91`, `routes_sms.py:40`). The load equals the send rate: at most ~13 reports/s during the D-1 run and ~5,000 over 10–30 min. The handler accepts a JSON list or a single object and does one `record_delivery_report` per item. The measured API p95 is under 20 ms (perf baseline), so this is not a constraint.

## DLT constraints

- TRAI's TCCCPR 2018 lets commercial SMS go out only from a registered header and content template, and every message is scrubbed against the DLT [3]. TRAI's standing direction of 12 May 2023 tightened controls on misuse of headers and templates [4].
- Each `{#var#}` value may be at most 30 characters and a template may have about 5–6 variables. These figures come from a **secondary** aggregator doc [5] and were not confirmed in the TRAI primary text. The code enforces 30 (`VARIABLE_LIMIT`). The templates use 4–5 variables.
- URLs must be whitelisted. The code rejects any link-like variable (`sms.py:42` `_LINK`).
- Scrub failures come back in the delivery report as status 16/25 (`sms.py:46` `_DLT_STATUS`). They pause the flow and the canary catches them (ADR 0079).
- **Blocker:** `ot_change`/`specs_change` have no registered template, so no schedule-change notice can be sent until the owner registers them on DLT (ADR 0075, 0077).

## Cost

- MSG91 India list prices per SMS credit [6]: ₹0.25 (5,000), ₹0.20 (16,500), ₹0.18 (30,000), ₹0.17 (60,000+), ₹0.16 (9,62,500). All are **+18% GST**. Sales quotes can go down to ₹0.13.
- For ~87,000 credits at ₹0.17: **≈ ₹14,800 + GST ≈ ₹17,500**, about ₹1.17 per patient. Buying a 1-lakh pack is ≈ ₹20,000 including GST.
- MSG91 charges for failed and delivered messages alike. Only "API failed" requests are free [7]. A DLT-rejected send still costs credits, which is why the canary and pause exist.
- **Cost lever:** the Hindi text uses 3–4 credits per SMS. Cutting each template to ≤134 Unicode characters (2 credits) would save ~40% (≈ ₹7,000 per camp). That needs re-registering the templates on DLT.
- DLT entity and header registration fees were not researched.

## Limiting constraint

It is not throughput. MSG91 publishes no API rate limit [2], the worker clears 5,000 reminders in under ~30 min, and the webhook load is trivial. What does limit the camp:

1. **DLT template coverage.** Schedule-change notices cannot be sent at all.
2. **Unicode length.** It drives cost at 3–4 credits per SMS.

Open verification: measure the real per-send latency from backend logs during the first D-1 run, and confirm the 30-character variable rule in the operator DLT portal.

## Sources

1. MSG91, "What is the character limit for a single credit in English & Unicode?" https://msg91.com/help/more/what-is-the-character-limit-for-a-single-credit-in-english-unicode-how-is-credit-calculated
2. MSG91, "All About the 429 Rate Limit Error" https://msg91.com/help/all-about-the-429-rate-limit-error
3. TRAI, Telecom Commercial Communications Customer Preference Regulations, 2018 https://www.trai.gov.in/sites/default/files/2024-09/RegulationUcc19072018.pdf
4. TRAI, Direction on misuse of Headers and Content Templates, 12 May 2023 http://trai.gov.in/node/2311
5. WebEngage, "TRAI DLT Regulations (India)" (secondary) https://docs.webengage.com/docs/trai-sms-dlt-regulations-india
6. MSG91, "SMS Pricing in India" https://msg91.com/in/pricing/sms
7. MSG91, "Pricing Guidelines | Service Deductions" https://msg91.com/help/all-service-deductions-
8. Repo: `backend/sms.py`, `backend/msg91.py`, `backend/reminder_worker.py`, `backend/routes_reminders.py`, `backend/routes_sms.py`, `backend/tests/test_s10_sms.py`; ADRs 0008, 0013, 0041, 0045, 0075, 0077, 0079
