# Wrong-patient and wrong-data risks at 15,000: pre-registration to print

Issue #72. Code at `dc404f6` (after PR 68 and PR 69). The only source is the code. Every claim cites `file:line`.

## Answer

At 15,000 patients the main wrong-patient risk is **namesakes who share the last 4 Aadhaar digits**, about 11 pairs (range 6–56). The Duplicate-in-camp rule treats them as one person because it ignores DOB. The door then offers the other person's registration, and Confirm stamps Arrival on it.

The second risk is **lookup by Patient code or reg no followed by Print**. It stamps Arrival on any Aadhaar-scanned registration without the card, so the Lock can be bypassed. The reg-no space is dense, and one Household phone holds up to 6 codes.

The #50 fixes still hold, including after PR 69.

## Collision math (N = 15,000, pairs = C(N,2) ≈ 1.125 × 10^8)

| Identity key | Space | Expected colliding pairs |
|---|---|---|
| last-4 + full DOB | 10^4 × ~29,000 days | ≈ 0.4 |
| last-4 + year-only DOB (assume 40% of patients, 60 birth years) | 10^4 × 60 | ≈ 30 |
| last-4 + same name tokens (name Σp² = 0.001, range 0.0005–0.005) | 10^4 / Σp² | ≈ 11 (6–56) |
| Person key: last-4 + name + DOB + gender (`helpers.py:120-123`) | above × same DOB | ≈ 0.03 |
| Patient code, 8 × Crockford-32 (`helpers.py:129-134`) | 1.1 × 10^12 | ≈ 0.0001, retried on the unique index (`routes_registration.py:353-356`, `db.py:67`) |
| reg no (global sequence, `routes_registration.py:406`) | dense | every same-length typo lands on a real patient |

Last-4 + DOB would collide about 30 times, so keep it out of identity decisions. The code no longer uses it: the Person key includes the name. The collision that matters now is **name tokens + last-4**, which ignores DOB.

## Findings, correctness first

### 1. HIGH: namesakes with the same last-4 are merged by Duplicate-in-camp, and the door can put one on the other's registration (≈ 11 patients, range 6–56)

- The dedupe query matches the camp on `aadhaar_last4` plus sorted name tokens. It does not check DOB or `person_id` (`routes_registration.py:140-145`).
- Any scanned hit refuses registration with DUPLICATE_IN_CAMP. This happens even when the hit belongs to a different Person (`routes_registration.py:299-302`). Both the desk and self-register are refused. The public message tells the patient they are "Already registered" (`routes_registration.py:537-543`).
- The refused patient's Person is still created (`routes_registration.py:389-395`). At Scan at the door, `own` is None. The namesake's row comes back as `mismatch_review` (`routes_desk.py:189-204`), with only a DOB diff and an identical name.
- `scan_confirm` checks only that the chosen row is among the hits. It never compares `person_id` (`routes_desk.py:244-252`). Confirm therefore stamps Arrival, and Print prints the other patient's prescription. The Paper check does not compare identity (CONTEXT.md:195-196).
- Fix: a scanned hit with a different `person_id` whose DOB also differs is a different person. Leave it out of Duplicate-in-camp, and refuse it in `scan_confirm`.

### 2. HIGH: lookup, then Print, stamps Arrival without the card (exposure: every Aadhaar-scanned patient; ≈ 15 at 10% lookup use and 1% mis-entry)

- `/desk/lookup` resolves a Patient code, then a reg no (`routes_desk.py:22-35`). The desk calls it (`frontend/src/pages/Desk.js:232`). Print then calls `/desk/arrive` (`Desk.js:287`).
- `arrive` accepts any `aadhaar_scanned` row with no card present (`routes_desk.py:271`). So the Lock is enforced only for Manual entries.
- The chance of this grows with N in two ways. A reg no is a dense integer, so any typo is another real patient. And one Household phone carries up to 6 family SMS codes (`routes_registration.py:28`), so showing a sibling's SMS selects the sibling.
- Fix: for a scanned row with no Arrival yet, require the Aadhaar Lock, or an admin Identity check. Keep lookup for reprint and for patients who have already arrived.

### 3. MEDIUM: a second Arrival and reprint are silent (amplifies 1 and 2)

- `_stamp_arrival` returns an already-arrived row unchanged (`routes_desk.py:115-116`). Scan returns `arrived` as if new (`routes_desk.py:191-197`). A printed row reprints without a refusal (`routes_desk.py:283-284`).
- So when two people end up on one registration, nobody sees "already arrived at 09:14 by X".
- Fix: return `already_arrived` / `already_printed` with the time and actor, and show it on the card.

### 4. MEDIUM: public-endpoint abuse during a pre-registration surge (0 without an attacker; unbounded with one)

- The server does not check the Aadhaar QR signature (`backend/aadhaar.py:4`). A forged card passes self-register (`routes_registration.py:530-536`).
- The only brake is 30 requests per IP per 10 minutes, held in process memory (`routes_registration.py:26`, `routes_registration.py:31-41`). Rotating IPv6 addresses defeats it.
- Forged rows fill `seat_limit` (`routes_registration.py:155-168`). A forged copy of a real person's card (name, last-4, DOB, gender) creates the real Person key. It also sets the attacker's Household phone. The real patient is then refused at the desk as a duplicate (finding 1 path), and their SMS go to the stranger.
- Legitimate shared IPs (camp Wi-Fi, a kiosk, one ASHA phone) are capped at 180 per hour. The client IP comes from Caddy → nginx `$proxy_add_x_forwarded_for` (`frontend/nginx.conf:32`) → uvicorn `--forwarded-allow-ips *` (`backend/Dockerfile:16`). This is correct only while nginx is reachable solely through Caddy.
- Fix options: rate limit per Household phone as well as per IP, and add a daily global self-register ceiling. Signature verification was rejected in the original ADR; revisit it only if abuse appears.

### 5. LOW: two desks can create one Manual entry twice (≈ 0–5)

- The unscanned dedupe matches on name, age and phone. It reads, then inserts (`routes_registration.py:122-127`, `routes_registration.py:397-428`), with no unique index. Only scanned rows are unique, on `(person_id, camp_id)` (`db.py:69-71`).
- The effect is safe: the later door scan returns `ambiguous` (`routes_desk.py:206-208`).

### 6. LOW: household limits (< 50 patients lose an SMS; not a wrong-patient risk)

- The self-register cap of 6 counts rows and then inserts (`routes_registration.py:383-386`), so concurrent submits can pass 6.
- The registration-SMS cap is 6 per phone per IST day (`backend/sms.py:73-81`). Registering a 7th member at the desk on the same phone gets no SMS.

## #50 fixes: still hold

- The door Lock stamps Arrival automatically only on the card's own `person_id`. It no longer uses last-4 + DOB (`routes_desk.py:190-197`).
- Replacing a Manual entry needs a review when the card differs (`routes_registration.py:309-313`). The overwrite itself is conditional: not scanned, not printed, not seen (`routes_registration.py:204-216`). Nothing is overwritten silently.
- Arrival is a conditional update (`routes_desk.py:132-136`). Capacity is an atomic `$expr` check (`routes_registration.py:162-166`).
- A scanned registration cannot be created twice, because of the `(person_id, camp_id)` unique index (`db.py:69-71`, `routes_registration.py:349-352`).
- PR 69 front page: each scan gets a fresh `registration_request_id`, and "Register another" clears it (`frontend/src/pages/SelfRegister.js:41`, `SelfRegister.js:93-99`). The replay check compares name, last-4 and DOB (`routes_registration.py:318-328`). The public 409 hides the other registration (`routes_registration.py:537-543`). The only backend change in PR 69 was `is_past` (`routes_camps.py:192`).

## Not covered in this pass

- The walk-in phone carry-over fix (Desk.js). Its behaviour is covered by `Desk.test.js`, but that file was not re-read.
- The PR 68 live-scan loop UI (ADR 0082). The backend outcomes it consumes are the ones audited above.
- Whether `MismatchReview` shows the DOB diff prominently enough to stop a Confirm in finding 1.
