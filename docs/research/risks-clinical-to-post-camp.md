# Wrong-patient and wrong-data risks at 15,000: clinical to post-camp

Question (#73): where can the wrong patient or wrong data happen from clinical work through post-camp when a camp has 15,000 patients over 3–4 camp days? The focus is on risks that grow with N or with many concurrent operators.

Method: a code read of `backend/` and `frontend/src` at `dc404f6`. Every claim cites file:line. The patient counts are estimates. Each one states its assumption.

## Ranked findings (correctness first)

### 1. Clinical find hides today's namesake behind a silent 20-row cap (High, wrong patient)

- `clinical_search` matches only a full-name prefix across the whole camp. It sorts by `reg_no` ascending and caps at 20 rows (`backend/routes_clinical.py:193-198`).
- Patients who registered later have higher `reg_no` values, so on day 3–4 the patient at the station is the most likely to be cut off. The UI has no "more results" signal (`frontend/src/components/clinical/ClinicalLookupForm.js:44-61`).
- The only disambiguators are age, gender and the household phone's last 4 digits (`routes_clinical.py:203-205`, `ClinicalLookupForm.js:58`). Family members share that phone, and there is no village or relative's name.
- Once the wrong row is opened, every later guard passes because it is a real patient. `_claim_patient` and the generation checks protect against concurrency, not identity (`routes_clinical.py:38-45`).
- Estimate: 5% of 15,000 lookups use Clinical find because of a lost paper or an unreadable QR, which is ~750 searches. 15–25% of those land on a name with more than 20 matches by day 3, which is **~110–190 searches where the right patient is not listed**. 10–20% of those pick a same-age, same-gender namesake, which is **~10–40 wrong-patient opens**.

### 2. A correction after issue leaves Fulfilment lines on a superseded prescription (Medium-high, wrong data)

- A correction refuses only when there is a deferred IOL surgery or an active Spectacles to be made Token (`routes_clinical.py:840-847`). It does not check an issued medicine line or a Fixed-power specs line.
- `reviewed_revision_id` is written at issue (`routes_clinical.py:676`). Nothing reads it back to flag a stale line: its only reads are the issue-time checks (`routes_clinical.py:624-626`, `:660`).
- The Camp records export mixes the two versions:
  - Prescribed medicines come from the corrected transcription, but "not given" comes from the old line's outcomes (`backend/routes_reports.py:142-147`). A newly added medicine therefore looks given.
  - The corrected Fixed-power specs power is printed beside the old Issued power (`routes_reports.py:168-169`), which reads as a desk substitution.
- Estimate: corrections on 1–3% of ~15,000 seen patients, about half of them after issue: **~75–225 export rows wrong**.

### 3. The Camp-day board forgets carry-over patients (Medium, count drift)

- Awaiting print, awaiting seen and the transcription backlog count only patients whose `arrived_at` is today (`routes_reports.py:289`, `:300-311`).
- `seen_today` counts by `seen_at` (`routes_reports.py:317`), and Fulfilment line buckets count by `patient_seen_at` (`:319-323`).
- A patient who arrived yesterday and was not transcribed leaves the backlog at midnight, and "seen" can exceed "arrived".
- Estimate: 1–5% end-of-day carry-over on ~4,000/day, which is **~40–200 patients a day invisible to the board**.

### 4. A Schedule edit is one transaction over every Token on the day (Low-medium, availability)

- `_supersede_tokens` loads every active Token on the day and does the following in one transaction (`routes_clinical.py:887-915`, `:927-943`):
  - inserts a replacement for each Token;
  - deactivates each old Token;
  - repoints each Fulfilment line;
  - queues one SMS per patient.
- A Specs collection day can hold thousands of Tokens. While the edit runs, concurrent Spectacles to be made bookings `$inc booking_seq` on the same day document (`routes_clinical.py:526-528`). They write-conflict with the edit's day update (`:928`) and fall back to `in_transaction` retry (`backend/db.py:28`).
- The outcome is atomic, so no data is wrong. The risk is a slow or aborted edit during a live camp day.
- Estimate: **0 wrong rows**. Up to every Token on the edited day (~1,000–4,500) waits for its notice if the transaction aborts.

### 5. Schedule notices query is unbounded and not camp-scoped (Low)

- `list_schedule_notices` loads every active edited Token with no camp filter and no limit (`routes_clinical.py:1103-1105`). It filters by camp only afterwards (`:1106-1108`).
- The query is correct, but it grows with every camp that is kept.
- Estimate: **0 wrong rows**, with growing latency.

## Checked and holding (0 patients at 15,000)

- **Patient code collisions:** the space is 32^8, protected by a unique index and a retry (`backend/helpers.py:129-134`, `backend/routes_registration.py:353-356`). `reg_no` is a unique sequence (`backend/db.py:66`, `routes_registration.py:406`). Lookup tries `patient_qr` before `reg_no` (`routes_clinical.py:167-169`). An all-digit code (p ≈ (10/32)^8, ~1.4 codes) could shadow a `reg_no` only if someone typed 8 digits.
- **OT Schedule Day seat races:** the conditional `$expr` `$inc` is atomic (`routes_clinical.py:444-451`). A seat is released on re-defer or decline (`:689-693`), and lowering the limit is guarded inside the update filter (`:1011-1016`).
- **Wrong-patient or wrong-line commits between operators:**
  - Every write claims the patient (`routes_clinical.py:38-45`) and runs in one transaction (ADR 0065).
  - Issue rejects a stale reviewed revision or generation (`:660-661`).
  - Correction rejects a stale generation (`:837-838`), and undo is blocked after issue (`:385-386`).
- **Correction audit:** revisions are append-only, with `predecessor_id`, a required reason and the author (`backend/clinical_state.py:174-202`, `routes_clinical.py:771-773`). The gap is finding 2, not the audit trail.
- **#50 fixes still hold:**
  - An unticked prescription line drops its medicines (`clinical_state.py:103-104`).
  - The transcription backlog is printed but not committed (`routes_reports.py:309-311`), though it is arrival-day scoped (finding 3).
  - Stale Tokens and SMS after a Schedule edit: replaced Tokens are deactivated (`routes_clinical.py:901-904`). Reminders read only active Tokens (`backend/routes_reminders.py:178`), and failed rows for a gone Token are abandoned (`routes_reminders.py:143-159`).

## Suggested fixes (not implemented)

1. Clinical find:
   - Sort by `reg_no` descending, or put today's arrivals first.
   - Return `has_more` and show "refine the name".
   - Show the village beside the phone's last 4 digits.
2. Correction:
   - Refuse a correction that changes the medicines or the Fixed-power specs power after that line is issued, the same way it already refuses for OT and Spectacles to be made.
   - Or mark such lines stale where `reviewed_revision_id` differs from `committed_revision_id`.
3. Board: count the backlog and awaiting seen across the camp, not just today's arrivals, or show carry-over separately.

## Limits

This is a static read only: no load test and no VPS data. The patient counts rest on the stated assumptions. I did not audit the transcription wizard's draft-version path or the reminder worker's retry path beyond the lines cited.
