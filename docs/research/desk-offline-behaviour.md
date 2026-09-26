# What each desk does today when the venue's internet drops

Issue: #74. Policy lives in #77. This note records current behaviour only, read from the code at `dc404f6`.

## Shared facts (every screen)

| Fact | Evidence |
|---|---|
| One shared axios client. 30 s timeout. No automatic retry; the only interceptor handles 401. | `frontend/src/lib/api.js:25-36` |
| No offline or online detection anywhere in `frontend/src` (no `navigator.onLine`, no `online`/`offline` listeners). The operator learns of an outage only when a request fails. | search of `frontend/src`, non-test files |
| On a network failure or timeout there is no `response`, so the operator sees axios's raw English text: `Network Error` or `timeout of 30000ms exceeded`. | `frontend/src/lib/api.js:40` (`formatApiError` falls back to `err.message`) |
| The only automatic retry in the app: `/auth/me` at start-up retries forever with backoff capped at 15 s. A staff device that opens the app while offline stays on the loading state until the network returns. | `frontend/src/context/AuthContext.js:38-57` |
| Decode (Aadhaar QR) is a server call, so Scan at the door and pre-registration scans cannot work offline. The photo path has a 35 s timeout. | `frontend/src/components/aadhaar/useAadhaarDecode.js:52`, `:177-184`; `frontend/src/pages/Desk.js:794` |
| A timeout does not mean the write failed. The server may have committed; every risk below is about what the retry does then. | — |

## Per-screen behaviour

| Screen / action | Operator sees on offline, slow or timeout | Retry idempotent? | In-flight print / Paper check | Failure hidden? |
|---|---|---|---|---|
| Desk load and 30 s refresh | Error text via `setLoadErr`; the desk stays and keeps the last good camp, day and print-window state. | Read only. | — | No. But print-window and operating day are stale until a refresh succeeds (`Desk.js:147-148`, `:152-155`). |
| Scan at the door (`/desk/scan`) | Rethrown to the scan handler (`Desk.js:192-197`). | Yes. Arrival stamps only where `arrived_at` is null (`routes_desk.py:133`); the card overwrite only where `printed_at` is null (`routes_desk.py:154`). | — | No. |
| Confirm mismatch (`/desk/scan/confirm`) | Error text (`Desk.js:215-216`). | Yes, same Arrival guard. | — | No. |
| Walk-in at the door (register then Arrival) | Error text (`Desk.js:408-411`). | Yes. The request id and the created patient id are kept across retries (`Desk.js:374-377`, `:398`); `/register` replays by `registration_request_id` (`routes_registration.py:368-371`, unique index `db.py:68`); SMS goes only when `created` (`routes_registration.py:521`). | — | No. |
| Manual entry at the door | Error text (`Desk.js:436-438`). | Yes. `doorReqId` is regenerated only on success or `REGISTRATION_REQUEST_CONFLICT` (`Desk.js:435-437`). | — | No. |
| Pre-registration modal | Error text (`Desk.js:848-855`). | Yes. `reqId` survives a failed save; it is reset on a new scan or reset (`Desk.js:741`, `:782`, `:854`). | — | No. |
| Print Prescription: fetch | Error text (`Desk.js:292-293`). Needs the server to stamp Arrival and return the prescription first (`Desk.js:287-288`). Offline means nothing prints. | Yes. Arrival is conditional; `GET /desk/print` has no side effect (`routes_desk.py:342-353`). | Print is in the page (`lib/printJob.js:19-35`). Once the prescription is in hand the paper prints with no network. | Partly. Logos are fetched at print time and silently dropped after 3 s (`Desk.js:59-64`, `printJob.js:5`); the paper prints without logos and nothing says so at print time. |
| Paper check (`POST /desk/print`) | The error stays inside the Paper check dialog; the operator can retry (`Desk.js:317-318`). | Yes. `printed_at` is set only where null, and a patient already printed passes the refusal check (`routes_desk.py:283-284`, `:299-315`). | **Data-loss risk:** paper exists but no record. If the first attempt never reached the server and the admin closes the print window before the retry, the retry is refused `PRINT_WINDOW_CLOSED` (`routes_desk.py:285-286`). If the operator dismisses the dialog, `printed_at` stays empty (`Desk.js:322-326`), and the clinical desk refuses the patient until printed (`routes_clinical.py:302`). | No, the dialog shows the error. |
| Clinical wizard: step save (`/clinical/transcription`) | Error text, the step does not advance (`Clinical.js:243-246`). | No operation id. Guarded by `expected_draft_version` (`Clinical.js:237`). | — | **Misleading.** If the save committed but the response was lost, the retry sends a stale version and gets `DRAFT_VERSION_CONFLICT`, worded "Another operator saved this prescription; reload before saving." (`routes_clinical.py:242-246`; `Clinical.js:244`). No data is lost: the server holds the draft. |
| Clinical wizard: complete | Error text (`Clinical.js:286-288`). | Yes. The operation id is kept while the request is unchanged (`Clinical.js:263-266`); the server replays it (`routes_clinical.py:319-334`). | — | No. |
| Undo completion, Correction | Error text. | Yes. Undo keeps its id while the reason is unchanged (`Clinical.js:470`, `:521`); Correction keys its id to the request (`CorrectionModal.js:85-88`). | — | No. |
| Fulfilment line | Error text (`FulfilmentStation.js:284-285`). | Yes. The operation id is kept until success (`FulfilmentStation.js:274-276`); a replay with a changed payload is refused, not double-recorded (`clinical_state.py:162`). | A Token that fails to print after a saved line says so: "Saved. The Token did not print … Use Reprint Token." (`FulfilmentStation.js:278-281`). | No. |
| Admin: lists and dashboards | `ErrorCard` with Retry (`components/ui.js:118-127`). | Read only. | — | No. |
| Admin: create camp | Error text. | **Duplicate risk.** The backend replays on `setup_request_id` (`routes_camps.py:101-113`), but the admin screen never sends it (`AdminDashboard.js:209-210`). A retry after a lost response creates a second inactive camp. | — | No, but the duplicate is silent. |
| Admin: camp day, OT day, specs day, catalogue, staff create | Error text. | No request id; unique indexes stop duplicates (`db.py:62`, `:109-110`, `:91-92`, `:52`). A retry after a lost response is refused as a duplicate even though the first write succeeded. | — | Misleading refusal. |
| Admin: activate, deactivate, door manual, print window | Error text. | Yes. They set state (`routes_camps.py:223`, `:234`; `AdminDashboard.js:229-250`, `:363`). | — | No. |
| Self-register (patient phone) | Error text (`SelfRegister.js:85-86`). Loading the camp shows `loadErr` (`SelfRegister.js:66`). | Yes. `reqId` is created at scan and kept until "register another" (`SelfRegister.js:41`, `:96`); the server replays it (`routes_registration.py:368-371`). Each retry counts against the per-network rate limit (`routes_registration.py:531`). | — | No. |
| Login page camp occupancy | Nothing. The 30 s poll swallows errors and shows the last value (`Login.js:27-32`). | Read only. | — | **Yes, stale.** |
| Board | Marks itself `stale` and shows the error (`Board.js:30-33`). | Read only. | — | No. |

## Issue #50 follow-up: "some screens conceal a network outage"

Fixed for every write path above: each one shows an error. Two network failures are still swallowed, and neither is a write:

- `Login.js:29`: the occupancy poll shows stale numbers with no marker.
- `Desk.js:62`: logos silently dropped from a printed prescription.

## Risk summary

- **Data loss (record, not paper):** a printed paper can end up with no `printed_at` when the Paper check write fails and the window closes or the dialog is dismissed. `Desk.js:317-326`, `routes_desk.py:285-286`.
- **Duplicate:** a retried admin "create camp" creates a second camp. `AdminDashboard.js:210`, `routes_camps.py:101-113`.
- **Misleading:** a lost draft-save response reads as another operator's edit (`routes_clinical.py:242-246`). A lost admin create reads as a duplicate refusal. Offline errors show raw axios text (`api.js:40`). A staff device opened offline stays on the loading state (`AuthContext.js:56`).
- **No duplicate risk found** for registration, Arrival, Paper check, completion, correction, undo, fulfilment or self-register.
