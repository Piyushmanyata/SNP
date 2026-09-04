# First-camp readiness: backups, Volunteer roster, USB imager desk, Trivial diff, keyboard Doctor's Rx, Camp-day board

Decisions behind this spec: ADR 0023 (USB imager is the primary desk capture), ADR 0024 (Desk accounts for auth, roster names for attribution). Glossary: `CONTEXT.md`. Read both before starting. Every term in **bold** below is a glossary term; use it verbatim in code, tests and copy.

This spec is written for an implementing agent that must not improvise. Where it says "exactly", do exactly that. Where a file path is named, change that file and no other. Where an alternative is tempting, the **Do not** lists say why it was rejected. If something in this spec is impossible as written, stop and say so on the issue rather than inventing a workaround.

## Problem Statement

The trust's first camp targets five thousand patients a day for three days across ten **Registration desks**, run by about a hundred volunteers who are not technical. No camp has run yet. The app as it stands has six gaps that would each stop a desk or lose a day's data:

1. There is no backup. One MongoDB on one VPS holds every registration, and nothing copies it anywhere. A disk failure on day two loses days one and two.
2. Every volunteer needs their own password. A hundred passwords on paper, and a logout and login at every shift change at the busiest desk in the building. A volunteer locked out at nine in the morning stops a desk. But the trust gives prizes to the best volunteers, so registrations must still be counted per person.
3. The desk was built around the volunteer's phone camera. The trust has decided a **Registration desk** is a laptop with a **USB imager**. The imager types the card payload as keystrokes, and today the only place those keystrokes can land is a textarea hidden behind a "USB / paste" mode button that the volunteer has to click into for every patient.
4. Most pre-registrations will be typed by volunteers weeks ahead (**Manual entries**). On camp day a **Lock** that matches one of these shows **Mismatch review** whenever any stored field differs from the card, and a typed name almost never matches the card byte for byte. That is a screen to read and confirm for most patients, which the one-patient-a-minute desk budget cannot absorb.
5. Eight to sixteen transcribers at **Doctor's Rx** will type roughly four thousand paper prescriptions a day. The transcription form's field order does not follow the paper, nothing is focused after lookup, and saving needs the mouse.
6. Team leads have no way to see the room. The admin dashboard shows camp totals; nobody can see that desk 7 has gone quiet, that transcription is four hundred patients behind the doctors, or that the next OT day is nearly full.

## Solution

1. **Backups.** The production compose gains a `backup` service that dumps the database on an interval into a volume and prunes old dumps, and a `backup-sync` service that copies that volume off the box with rclone. A restore drill is documented as exact commands.
2. **Volunteer roster and On-desk volunteer.** Admin keeps a **Volunteer roster** of names per camp, no passwords. A **Desk account** (an existing `volunteer` or `clinical_desk_operator` login) is signed in once in the morning. When a volunteer sits down they pick their name; the pick rides on every posting as a header, is stored on each record, and feeds the leaderboard. A desk with nobody picked is refused. Team leads and admins keep personal accounts and never see the picker.
3. **Wedge burst.** The desk, the pre-registration modal and the clinical page listen at document level for a **Wedge burst**: a run of fast keystrokes ending in Enter. The burst is scrubbed out of whatever field had focus and handed to the same code the camera hands a payload to. No mode button, no textarea. The camera stays as the fallback behind a collapsed section.
4. **Trivial diff.** Scan resolution compares the card to the stored Manual entry with rules for case, spacing, initials order, age within one year, empty stored fields, and address. If every difference is trivial, the **Aadhaar overwrite** and **Arrival** happen in the same request with no screen. Only a material difference reaches Mismatch review.
5. **Keyboard Doctor's Rx.** The transcription form follows the paper's order, focuses the first field after a lookup, saves on Enter, and returns focus to the lookup box ready for the next burst.
6. **Camp-day board.** One read-only page for team leads and admins, polling every fifteen seconds: per-desk arrivals in the last fifteen and sixty minutes with quiet desks highlighted, the **Transcription backlog**, each **Fulfilment line's** count today, seats left on the next OT and Specs days, and SMS failures today.

## User Stories

### Backups
1. As an admin, I want the database dumped every hour while a camp runs, so that a failure loses at most an hour.
2. As an admin, I want each dump copied off the VPS automatically, so that losing the VPS does not lose the dumps.
3. As an admin, I want old dumps pruned after a fixed number of days, so that the disk does not fill.
4. As an admin, I want the exact restore commands written down and rehearsed once before camp, so that a restore under pressure is a copy-paste, not a search.
5. As an admin, I want production deployment to refuse to start without an off-box destination configured, so that nobody deploys without backups by accident.

### Volunteer roster and On-desk volunteer
6. As an admin, I want to paste a list of volunteer names, one per line, and have them added to the active camp's roster, so that a hundred names take one action.
7. As an admin, I want a duplicate name in the same camp to be skipped and reported, not duplicated, so that the list stays clean.
8. As an admin, I want to disable and re-enable a roster name, so that a volunteer who leaves stops appearing in the picker.
9. As a volunteer sitting down at a Registration desk, I want to pick my name from a list before I can do anything, so that my work is counted.
10. As a volunteer, I want a search box above the list, so that I find my name in a hundred without scrolling.
11. As a volunteer, I want every name to be a button at least 44 pixels tall, so that I can hit it on a laptop trackpad.
12. As a volunteer, I want my name shown in the header once picked, so that I know whose name the desk is on.
13. As a volunteer handing over, I want a "Hand over" button that clears my name and shows the picker to the next person, so that a shift change is one click.
14. As a team lead, I want the desk to refuse to register, arrive, print, mark seen or post a Fulfilment line when nobody is picked, so that no work is ever unattributed.
15. As a team lead or admin signed in as myself, I want no picker and no refusal, so that my own account attributes my own work.
16. As a clinical operator at Doctor's Rx or a Fulfilment line, I want the same picker and the same refusal, so that clinical work is attributed the same way.
17. As an admin, I want the leaderboard to count by roster name, so that prizes go to people, not to shared desk logins.
18. As an admin, I want the leaderboard to show registrations and arrivals per name, so that both pre-registration typing and camp-day desk work count.
19. As an admin, I want a roster name that was disabled to still appear on the leaderboard with its counts, so that a volunteer who left mid-camp keeps their score.
20. As a developer, I want the roster to be per camp, so that next year's roster starts clean.
21. As an admin, I want a pick that names a disabled or foreign-camp roster entry refused, so that stale sessions cannot post under a dead name.
22. As a volunteer, I want my picked name to survive a page refresh but not a logout, so that a refresh does not force a re-pick and a logout does.

### Wedge burst
23. As a volunteer at a Registration desk on a camp day, I want to scan a card with the USB imager and see the outcome with no click before or after, so that the desk runs at one patient a minute.
24. As a volunteer, I want the burst to work whichever field has focus, so that a scan after typing a phone number does not end up in the phone field.
25. As a volunteer, I want the characters that leaked into a focused field before the burst was recognised removed from that field, so that the phone field does not contain half an Aadhaar payload.
26. As a volunteer, I want a burst that Decode says is not a card to count as a Failure, so that two bad scans reveal Manual entry as they do for the camera.
27. As a volunteer, I want the same card scanned twice within three seconds to be ignored the second time, so that a double trigger on the imager does not double-post.
28. As a volunteer, I want the phone camera available under a collapsed "Use phone camera" section on the desk, so that the fallback exists without taking space.
29. As a volunteer in the pre-registration modal, I want a wedge burst to fill the form from the card exactly as a camera Lock does, so that pre-registration desks can also use the imager.
30. As a clinical operator, I want a wedge burst of the prescription QR on the clinical page to run the lookup, so that I do not click the lookup box first.
31. As a volunteer, I want normal typing never mistaken for a burst, so that typing a name and pressing Enter does not fire a scan.
32. As a volunteer, I want the desk to show "Ready for USB scan", "Decoding…" and the outcome in one place, so that I know whether the last scan was taken.
33. As a developer, I want the burst detector to be one hook with one algorithm used in all three places, so that there is one thing to fix.

### Trivial diff
34. As a volunteer, I want a Lock that matches a Manual entry whose only differences are letter case, spacing or punctuation in the name to check the patient in with no screen, so that "ramesh kumar" versus "Ramesh Kumar" costs nothing.
35. As a volunteer, I want the name tokens in a different order ("Kumar Ramesh") treated the same way, so that initials-first typing is not a mismatch.
36. As a volunteer, I want an age within one year of the card's age treated as trivial, so that a birthday between pre-registration and camp day is not a mismatch.
37. As a volunteer, I want any field the registration never had (empty gender, DOB, last-4, address) treated as trivial, so that a sparse Manual entry checks in silently.
38. As a volunteer, I want address differences always treated as trivial, so that a typed village name never blocks a check-in over the card's full postal address.
39. As a volunteer, I want a different last-4, a different DOB, an age two or more years apart, a different gender, or a materially different name to still show Mismatch review, so that the wrong person is never silently overwritten.
40. As a volunteer, I want the silent check-in to apply the full Aadhaar overwrite (name, age, gender, DOB, last-4, address from the card) exactly as confirming Mismatch review does, so that the card becomes the source of identity either way.
41. As a volunteer, I want the desk banner to say the card details were updated when a Trivial diff was applied, so that I know the record changed.
42. As an admin, I want the export to show the card values after a silent overwrite, so that the export reflects identity as verified.

### Keyboard Doctor's Rx
43. As a transcriber, I want the form fields in the order they appear on the paper (diagnosis, blood sugar, BP, remarks, OT eye and procedure, then the glasses grid RE sph/cyl/axis, LE sph/cyl/axis, add), so that my eyes and hands move down the page together.
44. As a transcriber, I want the blood sugar field focused as soon as a lookup succeeds on the Doctor's Rx line, so that I start typing without a click.
45. As a transcriber, I want Tab to move through every field in that order and Enter in any field to save, so that a prescription is typed without touching the mouse.
46. As a transcriber, I want the save to clear the patient and put focus back in the lookup box, so that the next wedge burst starts the next patient.
47. As a transcriber, I want the banner after save to show the reg number I just saved, so that I can match it to the paper I am putting down.
48. As a transcriber, I want the diagnosis chips reachable by Tab and toggled by Space or Enter without submitting the form, so that chips do not break the keyboard flow.
49. As a transcriber, I want Enter in the lookup box to run the lookup, so that a typed reg number works like a burst.
50. As a Fulfilment line operator, I want none of this to change what my line shows, so that only Doctor's Rx gets the keyboard flow.

### Camp-day board
51. As a team lead, I want a Board page showing every Registration desk with arrivals in the last fifteen minutes and last sixty minutes, so that I can see where the queue is moving.
52. As a team lead, I want a desk with zero arrivals in the last fifteen minutes highlighted, so that a stalled desk is obvious across the room.
53. As a team lead, I want the Transcription backlog as one large number, so that I know whether the specs desk is about to stall.
54. As a team lead, I want each Fulfilment line's count for today, so that I can move people between lines.
55. As a team lead, I want seats left on the next OT Schedule Day and the next Specs collection day, so that I know when to ask the admin for another day.
56. As a team lead, I want SMS failures today as a number, so that I know if patients are not being told.
57. As a team lead, I want the page to refresh itself every fifteen seconds with no button, so that I can leave it open on a laptop.
58. As a team lead, I want no patient names and no actions on the board, so that it can sit on a screen in the room.
59. As a volunteer, I want no link to the board, so that desks stay uncluttered.
60. As an admin, I want the same board, so that I can watch from anywhere.

## Implementation Decisions

Repository facts the agent must not rediscover: backend is FastAPI in `backend/`, one router per file, `get_db()` from `db.py`, auth dependencies in `security.py` (`require_admin`, `require_staff`, `require_clinical`, `require_any`, `get_current_user`), IST helpers in `helpers.py`, serializers in `serializers.py`. Frontend is CRA React in `frontend/src`, axios instance in `lib/api.js` (default export), pages in `pages/`, shared UI in `components/ui.js` (`Button`, `Card`, `Input`, `Field`, `Alert`, `Modal`, `Stat`, `Badge`, `ErrorCard`), session-storage pattern in `lib/operatorLines.js`. Roles: `admin`, `team_lead`, `volunteer`, `clinical_desk_operator`. The demo Aadhaar payload format accepted by `decode_aadhaar` is `AADHAAR|<name>|<M/F>|<YYYY-MM-DD>|<12 digits>|<address>`; use it in every test.

Do the milestones in order. Each milestone is one PR. Do not start a milestone before the previous one is merged.

### M1 — Backups (compose and docs only, no application code)

Files: `docker-compose.prod.yml`, new `ops/backup.sh`, new `docs/ops/backups.md`, `.env.example`.

- Add a service `backup` to `docker-compose.prod.yml`:
  - `image: mongo:7` (the image ships `mongodump` and `mongorestore`; do not install anything).
  - `restart: unless-stopped`, `depends_on: mongo: condition: service_healthy`.
  - `environment`: `DB_NAME: ${DB_NAME:?set DB_NAME}`, `BACKUP_INTERVAL_SECONDS: ${BACKUP_INTERVAL_SECONDS:-3600}`, `BACKUP_KEEP_DAYS: ${BACKUP_KEEP_DAYS:-14}`.
  - `volumes`: `backups:/backups` and `./ops/backup.sh:/backup.sh:ro`.
  - `command: sh /backup.sh`.
- `ops/backup.sh` is exactly this loop, nothing more: forever, compute `ts=$(date -u +%Y%m%dT%H%M%SZ)`, run `mongodump --uri mongodb://mongo:27017 --db "$DB_NAME" --gzip --archive="/backups/${DB_NAME}-${ts}.archive.gz"`, then `find /backups -name "${DB_NAME}-*.archive.gz" -mmin +$((BACKUP_KEEP_DAYS * 1440)) -delete`, then `sleep "$BACKUP_INTERVAL_SECONDS"`. Use `set -u` but not `set -e`: a failed dump must not kill the loop; print the failure and continue.
- Add a service `backup-sync`:
  - `image: rclone/rclone:1`, `restart: unless-stopped`, `depends_on: [backup]`.
  - `env_file: ./backup.env` (holds the `RCLONE_CONFIG_OFFBOX_*` variables that define a remote named `offbox`; rclone reads remotes from environment variables of that shape, so no config file is mounted).
  - `environment`: `BACKUP_REMOTE: ${BACKUP_REMOTE:?set BACKUP_REMOTE, e.g. offbox:snp-backups}`, `BACKUP_INTERVAL_SECONDS: ${BACKUP_INTERVAL_SECONDS:-3600}`.
  - `volumes`: `backups:/backups:ro`.
  - `entrypoint: sh`, `command: -c 'while true; do rclone copy /backups "$BACKUP_REMOTE" --min-age 60s; sleep "$BACKUP_INTERVAL_SECONDS"; done'`. `copy`, not `sync`: pruning on the box must never delete off-box copies.
- Add `backups:` to the top-level `volumes:`.
- Add `BACKUP_REMOTE`, `BACKUP_INTERVAL_SECONDS`, `BACKUP_KEEP_DAYS` to `.env.example` with one-line comments, and add a `backup.env.example` at the repo root showing the five `RCLONE_CONFIG_OFFBOX_*` keys for an S3-compatible bucket (`TYPE=s3`, `PROVIDER`, `ACCESS_KEY_ID`, `SECRET_ACCESS_KEY`, `ENDPOINT`) with placeholder values.
- `docs/ops/backups.md` contains: what runs and when; the interval to use during camp (3600) and how to change it; and the restore drill as exact commands: list dumps (`docker compose -f docker-compose.prod.yml exec backup ls -1 /backups`), restore one into a side database (`mongorestore --uri mongodb://mongo:27017 --gzip --archive=/backups/<file> --nsFrom "<DB_NAME>.*" --nsTo "<DB_NAME>_drill.*"` run via `exec backup`), verify (`mongosh` count of `patients` in `<DB_NAME>_drill` via `exec mongo`), and drop the side database. State that the drill must be run once before camp and the date recorded at the bottom of the doc.

**Do not**: add a backup endpoint to the API; write backup logic in Python; use `rclone sync`; back up to a path on the same VPS only; add a third service.

### M2 — Volunteer roster, On-desk volunteer, leaderboard by roster

Backend files: new `backend/routes_roster.py`, `backend/models.py`, `backend/db.py`, `backend/server.py` (include the router), `backend/routes_registration.py`, `backend/routes_desk.py`, `backend/routes_clinical.py`, `backend/routes_reports.py`.

- Collection `roster`, document shape: `{_id, camp_id: ObjectId, name: str, name_normalized: str, created_at, created_by: str, disabled_at: datetime|None}`. Unique index on `(camp_id, name_normalized)` added in `db.init_indexes()` next to the existing ones. `name_normalized` is `helpers.normalize_name(name)`.
- `models.py`: `class RosterBulkBody(BaseModel): camp_id: str; names: List[str]`.
- `routes_roster.py`, prefix `/api/roster`:
  - `POST ""` body `RosterBulkBody`, `require_admin`. Trim each name, drop empties, normalize, insert each that does not already exist in that camp. Response `{"entries": [ser_roster(e) for created], "skipped": [names already present]}`. Empty `names` is a 400 `"No names given"`.
  - `GET ""` query `camp_id` optional, `include_disabled` optional bool, `require_any`. Without `camp_id` use the active camp; no active camp returns `{"entries": []}`. Excludes `disabled_at != None` unless `include_disabled=true`. Sorted by `name`. Response `{"entries": [...]}`.
  - `PATCH "/{entry_id}/disable"` and `PATCH "/{entry_id}/enable"`, `require_admin`, 404 when missing, response `{"ok": true}`.
  - `ser_roster(e)` → `{"id", "camp_id", "name", "disabled_at" (iso or null)}`.
  - A dependency in the same file:
    ```
    async def on_desk_volunteer(request: Request, actor: dict = Depends(get_current_user)) -> Optional[dict]
    ```
    Reads header `X-Roster-Id`. If `actor["role"]` is `admin` or `team_lead`: return the roster entry if the header names a valid one, else `None`; never refuse. If the role is `volunteer` or `clinical_desk_operator`: missing header → 428 `{"code": "ROSTER_REQUIRED", "message": "Pick your name before posting."}`; header that is not a valid ObjectId, or names no entry, or names a disabled entry, or names an entry whose `camp_id` is not the active camp → 428 `{"code": "ROSTER_INVALID", "message": "That roster name is not valid for this camp. Pick again."}`. Valid → return the entry document. 428 is deliberate: it is not 401 (the login is fine) and not 403 (the role is fine).
- Attribution. Add `roster: Optional[dict] = Depends(on_desk_volunteer)` as a parameter to exactly these endpoints and write `str(roster["_id"]) if roster else None` into exactly these fields:
  - `routes_registration.desk_register` → `patients.created_roster_id` (thread it through `_create_registration` and `_build_patient_document` as a new keyword `roster_id`; `self_register` passes `None`).
  - `routes_desk.scan`, `scan_confirm`, `arrive` → `patients.arrived_roster_id`, set inside `_stamp_arrival` (add a `roster_id` parameter), only when it actually stamps.
  - `routes_desk.print_prescription` → `patients.printed_roster_id`, set only on the first print alongside `printed_at`.
  - `routes_desk.mark_seen` → `patients.seen_roster_id`. `undo_seen` clears it to `None` alongside `seen_by`.
  - `routes_clinical.create_transcription` → `transcriptions.roster_id` on insert only.
  - `routes_clinical.record_fulfilment` → `fulfilments.roster_id` via a new `roster_id` parameter on `_build_fulfilment_doc`.
  - `routes_clinical.add_correction` → `corrections.roster_id`.
  The existing `created_by`, `arrived_by`, `seen_by`, `checked_in_by` fields stay exactly as they are; they now identify the Desk account.
- `routes_reports.leaderboard` is rewritten. Response shape becomes `{"volunteers": [{"name", "registrations", "arrivals", "points"}]}` with `points = registrations + arrivals`, sorted by `points` descending then `name`. `registrations` = count of `patients` in the active camp with `created_roster_id == entry id`. `arrivals` = count with `arrived_roster_id == entry id`. Include every roster entry of the active camp, disabled ones too. Remove `team_leads` from the response entirely. Use `count_documents` per entry, not `aggregate` (the test mock's aggregate is limited and a hundred counts is cheap).
- `serializers.ser_patient` gains `created_roster_id`, `arrived_roster_id`, `seen_roster_id` (strings or null).

Frontend files: new `frontend/src/lib/roster.js`, new `frontend/src/components/RosterPicker.js`, `frontend/src/lib/api.js`, `frontend/src/context/AuthContext.js`, `frontend/src/components/Layout.js`, `frontend/src/pages/Desk.js`, `frontend/src/pages/Clinical.js`, `frontend/src/pages/AdminDashboard.js`.

- `lib/roster.js`, mirroring `lib/operatorLines.js` exactly in style: `ROSTER_STORAGE_KEY = "snp.roster"`; `readRoster()` → `{id, name}` or `null` from `sessionStorage` (JSON); `writeRoster({id, name})`; `clearRoster()`; `needsRoster(user)` → `true` when `user.role` is `volunteer` or `clinical_desk_operator`, else `false`.
- `lib/api.js`: add one request interceptor on the existing `api` instance: if `readRoster()` returns an entry, set header `X-Roster-Id` to its `id`. Nothing else changes in this file.
- `AuthContext.js`: call `clearRoster()` in `login` and `logout` next to the existing `clearSessionLine()` calls.
- `RosterPicker.js`: props `{ open, onPicked }`. When `open`, renders a `Modal` (from `ui.js`) that cannot be dismissed (no close button, `onClose` is a no-op), title "Who is at this desk?", an `Input` with `data-testid="roster-search"` filtering case-insensitively on substring, and one `Button` per entry from `GET /roster` with `data-testid="roster-pick-<id>"`, full width, `size="lg"`. Clicking writes `writeRoster({id, name})` and calls `onPicked(entry)`. If the fetch fails, an `Alert` with the error and a retry `Button`. If the list is empty, the text "No roster for this camp yet. Ask an admin."
- `Layout.js`: when `needsRoster(user)` and `readRoster()` is set, show the roster name in the header next to the role badge with `data-testid="roster-name"`, and a button "Hand over" with `data-testid="roster-handover"` (44 px minimum) that calls `clearRoster()` and then calls a `onHandOver` prop if given. `Layout` gets a new optional prop `onHandOver`.
- `Desk.js` and `Clinical.js`: each holds `const [roster, setRoster] = useState(readRoster())`. Render `<RosterPicker open={needsRoster(user) && !roster} onPicked={setRoster} />` at the top of the page and pass `onHandOver={() => setRoster(null)}` to `Layout`. Nothing on the page is disabled while the picker is open; the modal covers it. A 428 from any request (check `errorPayload(err)?.code` is `ROSTER_REQUIRED` or `ROSTER_INVALID`) calls `clearRoster()` and `setRoster(null)`, which re-opens the picker.
- `AdminDashboard.js`: new tab `{ id: "roster", label: "Roster", icon: Users }` after "Staff". The `Roster` component: a textarea `data-testid="roster-names-input"` ("One name per line"), a `Button` "Add names" `data-testid="roster-add-button"` posting `{camp_id: active camp id, names: lines}` and showing "Added N, skipped M" in an `Alert`; below it the full list (`include_disabled=true`) with each row showing the name and a Disable/Enable `Button` (`data-testid="roster-disable-<id>"` / `roster-enable-<id>`). `Leaderboards` renders one `Board` titled "Volunteers" whose rows show `name`, and `registrations`, `arrivals`, `points` as three badges; the "Team Leads" board is removed.

**Do not**: add a PIN, password or any verification to the pick; put the roster id in a cookie or the JWT; make the header optional for desk roles; keep the team-lead rollup; create roster entries from staff accounts; add a roster to self-register.

### M3 — Desk accounts (no code)

A Desk account is an ordinary `volunteer` or `clinical_desk_operator` staff account created by an admin, named for the desk ("Desk 1" … "Desk 10", "Rx 1" …), signed in once in the morning by a team lead. Nothing in the code changes. Add a section "Camp-day accounts" to `docs/ops/backups.md`'s sibling, new `docs/ops/camp-day.md`, stating: create the ten desk and the line accounts before camp; team leads sign each laptop in; the access token lasts twelve hours so a laptop signed in at 07:00 needs a fresh login at 19:00; volunteers never receive a password.

### M4 — Wedge burst

Frontend files: new `frontend/src/components/aadhaar/useWedgeBurst.js`, `frontend/src/components/aadhaar/index.js` (export it), `frontend/src/pages/Desk.js`, `frontend/src/pages/Clinical.js`.

- `useWedgeBurst({ enabled, minLength = 20, onBurst })`. One `useEffect` that, when `enabled`, adds a `keydown` listener on `document` in the capture phase and removes it on cleanup. The listener holds `buf`, `lastAt`, `gaps` in a `useRef`. Algorithm, exactly:
  1. `now = performance.now()`.
  2. If `event.key.length === 1` (a printable character): if `now - lastAt > 500` then reset `buf = ""`, `gaps = []`; if `buf.length > 0` push `now - lastAt` onto `gaps`; append `event.key` to `buf`; set `lastAt = now`; return without preventing default.
  3. If `event.key` is `"Enter"` or `"Tab"`: take `candidate = buf`, `g = gaps`; reset `buf = ""`, `gaps = []`. It is a burst when `candidate.length >= minLength` and `g.length > 0` and the average of `g` is `<= 50` milliseconds. If not a burst, return without preventing default. If a burst: `event.preventDefault()`, `event.stopPropagation()`, call `scrubActiveInput(candidate)`, then `onBurst(candidate)`.
  4. Any other key: ignore.
  `scrubActiveInput(text)`: `el = document.activeElement`; if `el` is an `INPUT` or `TEXTAREA` and `el.value.endsWith(text)`, set the value to `el.value.slice(0, -text.length)` through the native value setter (`Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set`, or the textarea equivalent) and dispatch a bubbling `input` event, so React's controlled state updates. Export `scrubActiveInput` for its unit test.
  Rationale the agent must keep: a human types slower than 50 ms per key, an imager faster; the 500 ms idle reset means a pause splits two runs; scrubbing on the terminator, not per key, is what lets the first characters of a burst land harmlessly.
- `Desk.js`:
  - In `Desk()`, call `useWedgeBurst({ enabled: campDayMode && !showReg && !noCamp, onBurst })` where `onBurst(payload)`: if `payload === lastBurstRef.current.payload && Date.now() - lastBurstRef.current.at < 3000` return; else record it and call `onScanned(null, payload)`.
  - `onScanned` currently sets `doorForm` from its first argument; keep that, and additionally, after `/desk/scan` returns, if `data.card` exists set `doorForm` from `data.card` the same way (so bursts fill the manual form too).
  - In `onScanned`'s catch, if `errorPayload(err)?.code === "NOT_A_CARD"`, call `onDoorFailure("garbage")` so a bad burst counts as a Failure.
  - `DoorScanCard` on a camp day (`collapsed` false): replace the always-visible `AadhaarScanner` with a panel `data-testid="wedge-panel"` showing `Badge` text "Ready for USB scan" when idle, "Decoding…" while the scan request is in flight (add a `scanning` boolean state set around the `/desk/scan` call), then the existing `ScanOutcome` below. Under it a `<details data-testid="camera-fallback">` with summary "Use phone camera" containing the existing `AadhaarScanner` with the same props. In pre-registration mode (`collapsed` true) leave `DoorScanCard` as it is today.
  - `RegisterModal`: call `useWedgeBurst({ enabled: open, onBurst })` where `onBurst(payload)` posts `{payload}` to `/aadhaar/decode`; the response is `{"outcome": "card" | "garbage" | "not-aadhaar", "data": {...}}` and on `card` the `data` object carries `full_name`, `gender`, `dob`, `age`, `aadhaar_last4`, `address`; on `outcome === "card"` call `onScan(data.data)`; on any other outcome call `onFailure(data.outcome)`.
  - Banner after a burst-driven `arrived` outcome: if the response has `"overwritten": true` (M5) say `Checked in #N — Name (card details updated)`, else the existing text.
- `Clinical.js`: refactor `doLookup` into `lookupValue(value)` that does the request with the given value, and `doLookup(e)` that calls `lookupValue(lookup.trim())`. Call `useWedgeBurst({ enabled: !picking, onBurst: (v) => { setLookup(v); lookupValue(v); } })`.

**Do not**: keep a "USB / paste" mode as the primary desk path (it stays inside the collapsed camera fallback untouched); add a hidden always-focused input; steal focus; detect bursts on `keypress` or `input` events; use a fixed character count instead of timing; add a library.

### M5 — Trivial diff

Backend file: `backend/routes_desk.py` only. Glossary: **Trivial diff**.

- Replace `_diff(card, stored)` with `_material_diff(card, stored) -> List[Dict]` that returns only material differences, using these rules per field of `OVERWRITTEN_FIELDS`:
  - Any field where `stored.get(field)` is `None` or `""`: trivial.
  - `address`: always trivial.
  - `full_name`: trivial when `normalize_name(card) == normalize_name(stored)` or when `sorted(normalize_name(card).split()) == sorted(normalize_name(stored).split())`. Otherwise material.
  - `age`: trivial when both are integers and `abs(card - stored) <= 1`. Otherwise material.
  - `gender`: trivial when the first character upper-cased is equal (`"m"`, `"M"`, `"Male"` are all `M`). Otherwise material.
  - `dob`, `aadhaar_last4`: trivial only when equal as strings after `strip()`. Otherwise material.
  Each returned item keeps the shape `{"field", "card", "stored"}`.
- Extract from `scan_confirm` the block that applies the overwrite (the `update_one` with `OVERWRITTEN_FIELDS`, `full_name_normalized`, `aadhaar_scanned`, `person_id`, `manual_entry`, `manual_exception`, and the `DuplicateKeyError` handling) into `async def _apply_overwrite(db, patient, card) -> dict` returning the re-read patient. `scan_confirm` calls it.
- In `scan()`, the `len(manual_hits) == 1` branch becomes: `diff = _material_diff(card, manual_hits[0])`; if `diff` is empty: `patient = await _apply_overwrite(db, manual_hits[0], card)`, `arrived = await _stamp_arrival(...)`, return `{"outcome": "arrived", "registration": ser_patient(arrived), "overwritten": True}`. Otherwise return the existing `mismatch_review` response with `"diff": diff`.
- `scan_confirm` keeps working exactly as before for the material case; it does not check `_material_diff`.

**Do not**: add fuzzy string distance; make address material; auto-confirm when two Manual entries match (that stays `ambiguous`); change `_duplicate_hits`; touch the frontend beyond the banner text in M4.

### M6 — Keyboard Doctor's Rx

Frontend files: `frontend/src/components/clinical/PrescriptionForm.js`, `frontend/src/components/clinical/SpecsMeasurementsGrid.js`, `frontend/src/pages/Clinical.js`, `frontend/src/components/clinical/ClinicalLookupForm.js`.

- `PrescriptionForm` becomes a `<form onSubmit={(e) => { e.preventDefault(); if (!locked && !busy) saveRx(); }}>` wrapping the existing `Card` content. Field order in the DOM, top to bottom, exactly: diagnosis chips, other diagnosis, blood sugar, blood pressure, remarks, OT eye, OT procedure, then `SpecsMeasurementsGrid`. The save `Button` gets `type="submit"`. Diagnosis chip buttons keep `type="button"` (they already have it) so Space/Enter on a chip toggles it and does not submit.
- Blood sugar `Input` gets a `ref` prop passed down from `Clinical` (`firstFieldRef`) and `data-testid` stays `sugar-input`. Add `autoComplete="off"` to every `Input` in the form.
- `SpecsMeasurementsGrid` inputs get `inputMode="decimal"` and `autoComplete="off"`; order of `SPECS_FIELDS` is unchanged (`r_sph, r_cyl, r_axis, l_sph, l_cyl, l_axis, add`), which is the paper's RE-then-LE order.
- `Clinical.js`: after a successful `lookupValue` on `line === "rx"`, `firstFieldRef.current?.focus()` inside a `setTimeout(…, 0)`. After a successful `saveRx` on `line === "rx"`: set banner to `Saved #<reg_no>`, `setData(null)`, `setRx(emptyRx)`, `setLookup("")`, and focus the lookup input through a `lookupRef` passed to `ClinicalLookupForm`. On any other line `saveRx` behaves as today (reload).
- `ClinicalLookupForm` accepts an `inputRef` prop and puts it on its `Input`.

**Do not**: add hotkeys for chips; add a numeric keypad component; change what is saved or the transcription API; change the Fulfilment line screens.

### M7 — Camp-day board

Backend files: `backend/routes_reports.py`, `backend/helpers.py`, `backend/tests/test_adversarial_challenger.py` (mock only).

- `helpers.ist_day_bounds(day_str: str) -> tuple[datetime, datetime]`: the UTC datetimes for 00:00 and 24:00 IST of that calendar day.
- Extend the test mock's `MockCollection._matches` (in `test_adversarial_challenger.py`) so that when a query value is a dict, every operator in it is applied: `$gte`, `$gt`, `$lte`, `$lt` compare with the document value (a missing document value never matches), `$ne` matches when the document value differs, `$in` matches when the document value is in the list, `$nin` the reverse. The existing `_id`, `$expr` and `seats_taken` branches stay untouched above the new general branch. No production code may rely on any operator the mock does not implement.
- `GET /api/board`, dependency `require_roles("admin", "team_lead")` (define `require_lead = require_roles("admin", "team_lead")` in `security.py` next to the others). Response:
  ```
  {
    "camp": {"id", "name"} | null,
    "day": {"id", "day_date"} | null,
    "arrived_today": int, "seen_today": int,
    "transcription_backlog": int,
    "desks": [{"account_id", "name", "last_15m", "last_60m", "last_arrival_at" (iso|null), "quiet": bool}],
    "lines": {"medicine": int, "specs_fixed": int, "specs_made": int, "ot": int},
    "next_ot_day": {"day_date", "seats_left"} | null,
    "next_specs_day": {"day_date", "seats_left"} | null,
    "sms_failed_today": int
  }
  ```
  Computation, with `start, end = ist_day_bounds(today_ist_str())` and `now = now_utc()`:
  - `camp` is the active camp; none → every count 0, `desks` empty, days null.
  - `arrived_today` = `patients.count_documents({"camp_id", "arrived_at": {"$gte": start, "$lt": end}})`; `seen_today` the same on `seen_at`.
  - `transcription_backlog` = ids of patients with `seen_at` in today's bounds minus ids present in `transcriptions` for those patients (fetch the patient ids, then `transcriptions.find({"patient_id": {"$in": ids}})`, subtract).
  - `desks`: every user with `role == "volunteer"` and `disabled_at == None`, sorted by name. For each, `last_60m` = count of patients with `arrived_by == str(user _id)` and `arrived_at >= now - 60 min`; `last_15m` the same with 15 min; `last_arrival_at` = the max `arrived_at` today for that account or null; `quiet = last_15m == 0`.
  - `lines`: count of `fulfilments` with `created_at` in today's bounds, grouped by `item_type`, each of the four keys present even when 0.
  - `next_ot_day`: the `ot_schedule_days` document of this camp with `day_date >= today_ist_str()` and the smallest `day_date`; `seats_left = seat_limit - seats_taken`. Same for the `specs_collection_days` collection. Both collections have `camp_id`, `day_date`, `seat_limit`, `seats_taken`. Corrections live in the `corrections` collection.
  - `sms_failed_today` = `reminder_ledger.count_documents({"status": "failed", "created_at": {"$gte": start, "$lt": end}})`.
  No patient names anywhere in the response.

Frontend files: new `frontend/src/pages/Board.js`, `frontend/src/App.js`, `frontend/src/components/Layout.js`, `frontend/src/constants/roles.js`.

- `roles.js`: `export const LEAD_ROLES = Object.freeze([ROLES.ADMIN, ROLES.TEAM_LEAD]);`
- `App.js`: route `/board` wrapped in `<Protected roles={LEAD_ROLES}>`.
- `Layout.js`: when `user.role` is in `LEAD_ROLES`, a header link "Board" to `/board` with `data-testid="board-link"`; nothing for other roles.
- `Board.js`: `Layout title="Camp-day board"`. Fetch `/board` on mount and every 15 seconds with `setInterval`, cleared on unmount. Show an `ErrorCard` on failure and keep polling. Layout top to bottom: a `Stat` row (`arrived_today`, `seen_today`, `transcription_backlog` with `tone="amber"` when > 0 and `data-testid="board-backlog"`, `sms_failed_today`); a desk table `data-testid="board-desks"` with one row per desk showing name, last 15 min, last 60 min, and the row given an amber background and `data-quiet="true"` when `quiet`; a `Stat` row for the four lines using the `OPERATOR_LINES` labels; a `Stat` for each next day showing `seats_left` or "No day scheduled". No buttons other than the header.

**Do not**: add alerts, sounds or push; add actions; show patient names; use websockets; poll faster than 15 seconds; use `aggregate` in the board endpoint.

## Testing Decisions

A good test asserts what an actor sees: an HTTP status and body, a document written, or what the page renders and sends. It does not assert React state names or private helper internals, except `_material_diff` and `scrubActiveInput`, which are pure functions worth testing directly.

Two seams, both existing. No third.

1. **In-process backend tests (pytest, `backend/tests/`, driven by `MockDB` from `test_adversarial_challenger.py` with routers called directly, in the style of `test_camp_lifecycle.py` and `test_operator_line.py`).** This is the primary seam and the one CI runs. New files, one per milestone: `test_roster.py` (M2), `test_trivial_diff.py` (M5), `test_board.py` (M7). Add each new file to the pytest list in `.github/workflows/ci.yml`. Prior art to copy: `_mock(monkeypatch)` and `_seed_camp` from `test_camp_lifecycle.py`; `_patch_db` and `_client` from `test_operator_line.py` for tests that need `TestClient` (the `X-Roster-Id` header and the 428 must be tested through `TestClient`, because a header is what the dependency reads). Where a router module is new (`routes_roster`), add it to the modules `_patch_db` patches. Must prove: bulk add creates and skips; disabled entries hidden without `include_disabled`; a `volunteer` request without the header is 428 `ROSTER_REQUIRED`; with a disabled id is 428 `ROSTER_INVALID`; a `team_lead` without the header is not refused; `desk_register` writes `created_roster_id`; `scan` writes `arrived_roster_id`; leaderboard counts registrations and arrivals per name including a disabled name and has no `team_leads` key; each Trivial diff rule in both directions (one test per bullet in M5, trivial case checks in silently with the card values written and `overwritten: true`, material case returns `mismatch_review`); `ambiguous` unchanged; board counts with two desk accounts, one quiet; backlog counts seen-without-transcription; lines counts by `item_type`; no key in the board response contains a patient name; the mock operator extension itself (`$gte`, `$in`, `$ne`) with three small direct tests so a mock bug does not masquerade as a green board.
2. **Jest page tests (`frontend/src/**/*.test.js`, in the style of `Desk.test.js`: mock `../lib/api`, mock `Layout`, render with `MemoryRouter`).** Only for what the API cannot see. Must prove: `useWedgeBurst` fires `onBurst` for 40 characters typed with 10 ms gaps then Enter, does not fire for 40 characters at 120 ms gaps, does not fire for 10 fast characters, resets after a 600 ms pause, and prevents default on the terminating Enter (use `jest.useFakeTimers` and mock `performance.now`); `scrubActiveInput` removes the trailing text from a focused input and fires `input`; the desk on a camp day shows `wedge-panel` and hides the scanner behind `camera-fallback`; a burst posts `/desk/scan` and a `NOT_A_CARD` 400 increments the Failure count so two of them show `door-manual-form`; a 428 re-opens the picker; `RosterPicker` filters and writes session storage; `Layout` shows `roster-name` and `roster-handover` only for desk roles; `PrescriptionForm` DOM order matches M6 and Enter in the BP field calls `saveRx`; after save on the `rx` line the lookup input has focus; `Board` renders quiet rows with `data-quiet="true"` and polls again after 15 s.

M1 and M3 have no automated test. Say so in the PR and paste the `docker compose -f docker-compose.prod.yml config` output tail showing both services.

Run before every PR: `pytest` on the CI file list, `flake8 --select=F,E9 backend/*.py`, `npm run lint`, `npm test`, `npm run build` in `frontend/`.

## Out of Scope

- Any change to Live scan, the Guide ROI, the focus ladder, torch, photo upload, or the low-end phone camera path (fallback work, after camp one)
- The self-register page
- An on-site server, LAN TLS, or offline mode
- Serial or HID-POS scanners over WebSerial
- Printing changes (the desk laptop prints through the browser as today)
- PIN or password for roster names; verifying a pick
- Alerts, notifications or sounds on the board
- Changing the SMS templates or sending path
- The HTTPS development work already in the working tree (`Caddyfile.dev`, `docker-compose.https.yml`, `docs/dev-https.md`); leave those files alone
- Closing GitHub issues #11 and #14 (a person does that)
- Backfills for old data
- Renaming `created_by` / `arrived_by` / `seen_by`

## Further Notes

Glossary terms to use in code, tests and copy: Registration desk, USB imager, Wedge burst, Desk account, Volunteer roster, On-desk volunteer, Trivial diff, Mismatch review, Aadhaar overwrite, Arrival, Doctor's Rx, Fulfilment line, Camp-day board, Transcription backlog. Avoid: reg station, USB wedge (as a mode name), volunteer login, fuzzy match, dashboard (for the board), live feed.

Hardware gate, outside this spec but before M4 is useful in the field: the chosen imager Locks a real PVC Aadhaar Secure QR, and a full payload types into Notepad on the desk laptop in under five seconds with no dropped characters. If the second check fails, reopen ADR 0023 rather than loosening the 50 ms gap in `useWedgeBurst`.

Test seams for this spec: (1) in-process pytest with `MockDB`, (2) Jest page tests. If a seam is wrong, say so on this issue before implementation.
