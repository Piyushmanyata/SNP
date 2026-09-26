# Throughput model: desks, printers and staff for 4–5k patients a day

Issue #71. Evidence is the code, the runbook and the measured backend p95s. No camp has run yet, so every human time below is an assumption (A1–A12) the owner must confirm or replace. The sizing formula is given so any number can be changed and the table recomputed.

## Answer

- The **clinical desk** is the bottleneck: about 70 s per patient against about 40 s at the door, because one operator transcribes the paper and then issues every Fulfilment line at the same desk (`docs/ops/camp-day.md:16`).
- For 5,000 patients in 8 hours: **14 door desks, 23 clinical desks, 37 desks at peak**, 16 A4 printers, 25 A6 Token printers.
- The server is not a constraint: about 3.5 requests/s at peak against an estimated 25+ requests/s on the 2 vCPU VPS.
- The doctors are outside the app. If fewer doctors are writing papers than the clinical desks can take, the doctors become the bottleneck and the clinical desk count can drop to match them.

## Stations and what the code makes a person do

### Self-registration and pre-registration: no staff

A booking the household makes on its own phone. There is no typed path and it never stamps Arrival (`CONTEXT.md:263-264`). One `POST /self-register` (`frontend/src/pages/SelfRegister.js:76`), plus `POST /aadhaar/decode` for a camera read or `POST /aadhaar/extract` for an uploaded photo or PDF (`frontend/src/components/aadhaar/useAadhaarDecode.js:52`, `:181`). The only cost it has on a camp day is server time: `/aadhaar/extract` is about 1.4 s p95 live. Its value is that each booking makes the door shorter (A7).

### Door desk: Scan at the door, Arrival, print, Paper check

| Path | Round trips (file:line) | Human steps |
|---|---|---|
| Booked | `POST /desk/scan` (`frontend/src/pages/Desk.js:184`) returns the Arrival and the prescription, so Print reuses it (`Desk.js:286-290`, `:299`); `POST /desk/print/{id}` on "Printed — next patient" (`Desk.js:309`). 2 trips. `POST /desk/scan/confirm` (`Desk.js:208`) only when the desk must confirm a match. | scan card, press Print, wait for the sheet, check it, press "Printed — next patient" |
| Walk-in | `/desk/scan`, then `POST /register` (`Desk.js:74`, about 170 ms p95), then `POST /desk/arrive/{id}` (`Desk.js:400`), then `/desk/print/{id}`. 4 trips. | as booked, plus type the Household phone |
| Manual entry (no card) | name/number lookup, register, Identity check (`Desk.js:343`), arrive, print. 5+ trips. | type the whole record and a reason |

The print is `window.print()` into a hidden page root, awaited until `afterprint` (`frontend/src/lib/printJob.js:19-35`), at A4 (`Desk.js:69`). Logos are cached per camp (`frontend/src/lib/logoCache.js:10`) and capped at 3 s (`printJob.js:5`, `Desk.js:60-64`), so only the first print of the day can wait. With Chrome `--kiosk-printing` there is no dialog (`docs/ops/camp-day.md:8`, `docs/adr/0064-print-in-the-page-and-record-the-paper.md:27`). The Paper check is a deliberate human step: the print event alone never records a print (`CONTEXT.md:195-196`).

### Clinical desk: Clinical find, wizard, Doctor seen, Fulfilment lines, Token

One operator does all of it (`docs/ops/camp-day.md:16`).

1. **Clinical find**: the Patient code on the paper through the USB imager, `POST /clinical/lookup` (`frontend/src/pages/Clinical.js:167`). A typed name adds `GET /clinical/search` (`Clinical.js:163`). 1–2 trips.
2. **Wizard**: 3 fixed steps (Diagnosis, What was prescribed, Review and save) plus 1 step per prescribed line: medicine, Fixed-power specs, Spectacles to be made, Hospital (`frontend/src/components/clinical/PrescriptionWizard.js:13-25`). Each Next saves a dirty draft with `POST /clinical/transcription` (`Clinical.js:228-236`, `PrescriptionWizard.js:183-186`). With k lines that is k+3 screens and k+2 saves.
3. **Doctor seen**: `POST /clinical/transcription/complete` (`Clinical.js:267`). This is the step that confers Doctor seen (`CONTEXT.md:283-284`).
4. **Fulfilment**: one `POST /clinical/fulfilment` per line (`frontend/src/components/clinical/FulfilmentStation.js:260`). Spectacles to be made ("Defer and print Token", `FulfilmentStation.js:35`) and a scheduled IOL surgery ("Schedule and print token", `:45`) also do `GET /clinical/slip/{id}` and print an **A6** Token (`FulfilmentStation.js:186-191`, `:278-282`). A Hospital referral or Surgery declined prints nothing (`CONTEXT.md:147-148`).

With the line mix in A9, mean k = 1.4, so about 7 round trips per patient at the clinical desk and about 3 at the door.

## Assumptions to confirm

| # | Assumption | Value | Why it matters |
|---|---|---|---|
| A1 | Door: hand over card, find QR, scan | 8 s | on every patient |
| A2 | Door: read the card, press Print | 3 s | on every patient |
| A3 | A4 click to sheet in hand, kiosk printing, warm laser | 10 s | on every patient; a cold printer or no kiosk flag adds 5–15 s |
| A4 | Door: check the sheet, hand it over, press "Printed — next patient" | 5 s | on every patient |
| A5 | Door: extra for a walk-in, type phone and confirm | +15 s | walk-in share |
| A6 | Door: Manual entry, whole record typed plus Identity check | 90 s total | Manual share |
| A7 | Door mix: booked / walk-in with card / Manual | 50% / 45% / 5% | biggest door lever |
| A8 | Clinical fixed time: find 5 s, Diagnosis 10 s, What was prescribed 5 s, Review and save 5 s, paper and patient handling 10 s | 35 s | on every patient |
| A9 | Line mix per patient: medicine / Fixed-power / Spectacles to be made / Hospital | 70% / 40% / 20% / 10% | biggest clinical lever |
| A10 | Wizard step per line: medicine 12 s, Fixed-power 10 s, Spectacles to be made 30 s (measurements grid), Hospital 15 s | as listed | per line |
| A11 | Fulfilment per line: medicine 8 s, Fixed-power 15 s, Spectacles to be made 8 s + 8 s A6, Hospital 8 s + 8 s A6 | as listed | per line |
| A12 | Peak hour = 1.5 × the day's average hour; each desk run at 80% utilisation | 1.5, 0.8 | every desk count |

API time is left out of every service time: each call is under 20 ms p95 live, register about 170 ms, and none is on a path more than 5 times per patient.

## Service times

- **Door** booked = A1+A2+A3+A4 = 26 s, rounded to **30 s** for moving the queue along. Walk-in = 45 s. Manual = 90 s. Mean with A7 = 0.5×30 + 0.45×45 + 0.05×90 = **40 s**. Each door desk takes 3600 × 0.8 / 40 = **72 patients/hour**.
- **Clinical** = 35 s fixed + 19.9 s wizard lines (0.7×12 + 0.4×10 + 0.2×30 + 0.1×15) + 16.4 s fulfilment (0.7×8 + 0.4×15 + 0.2×16 + 0.1×16) = **71 s, taken as 70 s**. Each clinical desk takes 3600 × 0.8 / 70 = **41 patients/hour**.

## Sizing

Formula: `desks = ceil( N / H × 1.5 × t / (3600 × 0.8) )`, where N = patients per day, H = operating hours, t = service seconds.

| Patients/day | Hours | Peak patients/hour | Door desks | Clinical desks | **Peak concurrent desks** | A4 printers | A6 Token printers |
|---|---|---|---|---|---|---|---|
| 4,000 | 6 | 1,000 | 14 | 25 | **39** | 16 | 27 |
| 4,000 | 8 | 750 | 11 | 19 | **30** | 13 | 21 |
| 4,000 | 10 | 600 | 9 | 15 | **24** | 11 | 17 |
| 5,000 | 6 | 1,250 | 18 | 31 | **49** | 20 | 33 |
| 5,000 | 8 | 938 | 14 | 23 | **37** | 16 | 25 |
| 5,000 | 10 | 750 | 11 | 19 | **30** | 13 | 21 |

- **Operators**: one per desk at peak. Add break relief of about 1 per 6 desks for 8- and 10-hour days.
- **Printers**: one per desk, because `--kiosk-printing` prints to the laptop's default printer (`docs/ops/camp-day.md:8`), plus 2 spares of each kind. A door printer at peak prints about 72 sheets an hour, so the printer is never the limit; the person is.
- **Paper per day**: A4 = N × 1.03 for reprints (about 5,150 sheets, 11 reams, at 5,000). A6 Tokens = 30% of N under A9 (about 1,500 at 5,000).
- **Off-peak**: the same formula without the 1.5 gives the desks needed outside the rush; for 5,000 in 8 hours that is 9 door and 16 clinical.

## Sensitivity

- **Door, no bookings at all** (A7 = 0 / 95 / 5): t = 47 s, so door desks go up by about 18%. Every 10 points of bookings takes 1.5 s off the door mean, about 4% of door desks.
- **Clinical, Spectacles to be made at 40%** instead of 20%: t rises by 9.2 s (13%) if the extra patients are new, or 4.2 s (6%) if they come out of Fixed-power specs. Clinical desks rise in step.
- **No kiosk printing on clinical laptops**: each Token opens a print dialog. At 3–5 s per Token that adds 1–1.5 s per patient on average, about 2%.
- **Splitting the clinical desk** into a transcription desk and a separate fulfilment desk does not reduce total desks. It moves 16 s per patient to other people and adds a hand-off, so it is only worth it if the fulfilment work is physical (fetching medicine or glasses) and slower than A11 assumes.

## Server headroom

At 5,000 patients in 6 hours the peak is 1,250 patients/hour, and each patient makes about 10 requests (3 at the door, 7 at the clinical desk), so about **3.5 requests/s**. The CI budget holds the desk scan at 150 ms p95 at concurrency 8 on a 4 vCPU runner (`docs/adr/0068-performance-budgets.md:11`). By Little's law that is at least 53 requests/s on 4 vCPU, or roughly 25 on the 2 vCPU VPS if it scales linearly — about 7× headroom. The one path to watch is `/aadhaar/extract` at 1.4 s p95: if many households upload card photos on the camp morning instead of scanning the QR, those uploads queue on 2 vCPU. That load is on patient phones, not on the desks.

## Gaps found

- The runbook sets up `--kiosk-printing` and an A4 printer only on registration laptops (`docs/ops/camp-day.md:8`). Clinical laptops print A6 Tokens (`FulfilmentStation.js:190`) and have no printer or kiosk step in the runbook.
- The model assumes the doctors keep up. The app does not see the consultation, so doctor count, not desk count, may set the real ceiling.
