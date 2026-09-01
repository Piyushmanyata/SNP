# Camp lifecycle: pre-registration, Arrival, per-patient SMS, four Fulfilment lines

## Problem Statement

The trust runs free eye camps for roughly fifteen thousand patients, staffed by about a hundred volunteers and team leads who are not technical. Today the app assumes a patient registers and is seen on the same day, at the same desk, in one sitting. That is not how the camp actually runs.

Registration now opens one to two months before a camp. A patient who registers in advance has a booking, not a presence, and the app has no way to express that difference — the only marker between `registered` and `seen` is whether a prescription was printed. Counting who turned up means counting prints, which double-counts reprints and misses anyone whose Print window was closed.

A patient who registered in advance arrives on camp day carrying an Aadhaar card that nobody has re-checked. If the original registration was a Manual entry, the stored name and age may be wrong, and there is no reviewed path to correct them — the current overwrite is silent, and re-scanning a patient who already has Aadhaar on file is rejected as a duplicate.

Patients are told nothing. They receive no confirmation that they registered, and the day-before reminder does not tell them their registration number, so at the desk they cannot identify themselves except by name.

The public login screen advertises the product instead of telling anyone how full the camp is. Volunteers see a live list of every registered patient, which they do not need and which exposes patient names on a shared screen.

After the doctor, patients split across four physical desks, but the app only records power for spectacles that are deferred. The seventy to eighty percent of patients who receive ready-made Fixed-power specs walk away with no record of what the doctor prescribed. There are two separate exports, neither of which contains a full patient record, so nobody can answer a basic question about the camp in a spreadsheet.

The prescription is a fixed printed form the trust has used for years, yet an admin can edit its header, subtitle, footer, and layout blocks behind a draft-and-publish workflow. Every one of those fields is a way for the printed prescription to come out wrong on a camp morning.

Finally, Live scan — the primary way an Aadhaar Secure QR gets into the system — is capped at 720p, never asks for continuous focus, and can trap a volunteer forever: on a phone whose camera never detects anything, the Failure counter never increments and the typed fallback never appears. And the LAN deployment shape it is tested on cannot run a camera at all, because a browser will not grant camera access over plain HTTP.

## Solution

Split the patient lifecycle into a booking and a presence, tell every patient their own registration number by SMS, put a single scan box at the door that figures out what the volunteer meant, record clinical detail on all four Fulfilment lines, and collapse the reporting and prescription surfaces down to one of each.

**Registration becomes a booking.** A patient registers weeks ahead, from a volunteer's phone or by self-register, and immediately receives a Devanagari SMS confirming their `reg_no`, camp day, and venue. Nothing prints. The day before their camp day they receive a second SMS with the same details.

**Arrival becomes a presence.** The lifecycle is `registered -> arrived -> seen`. On camp day the volunteer scans the patient's Aadhaar Secure QR at a single scan box, and the app decides what that means. If the card matches a registration that already has Aadhaar on file, the patient is checked in. If it matches a Manual entry, the volunteer sees Mismatch review — card values beside stored values — and confirming applies the Aadhaar overwrite and checks them in. If nothing matches, the app does not register anyone: it offers a name or phone search, and creating a new registration takes a deliberate second action. A patient who arrives on the wrong camp day is checked in on the day they came. Only after Arrival does the prescription print.

**Volunteers stop browsing patients.** The live patient list is removed. Marking a patient Seen requires finding that one patient first, by scanning the QR on their prescription, or typing their `reg_no`, or searching their name.

**Four Fulfilment lines, all recorded.** Medicine, Fixed-power specs, Spectacles to be made, and OT are four desks and four item types. The clinical desk operator records the prescribed power for Fixed-power specs as well as for Spectacles to be made, so every patient has a clinical record. Deferring to a Specs collection day or an OT Schedule Day prints an A6 Token and sends an SMS on the spot; the day before that appointment, a third SMS goes out.

**One number on the door, one export, one prescription.** The public login screen leads with registrations against total camp seats, refreshing on its own. Every camp day must have a real seat limit. Reporting collapses to a single wide CSV, one row per patient, containing everything. The prescription layout moves into code, leaving only sponsor logos editable.

**The scanner stops failing silently.** Live scan asks for 1080p and continuous focus, and prefers a full-sensor still where the browser offers one. After twenty seconds with no Detect at all, a Scan stall reveals torch, photo upload, and manual entry together, so a bad camera can no longer trap a volunteer.

**Deployment moves to a cloud host over HTTPS**, because a browser will not start a camera without it.

## User Stories

### Public occupancy

1. As a member of the public, I want the login screen to lead with how many people have registered against the camp's total seats, so that I can tell at a glance whether it is worth travelling.
2. As a member of the public, I want that count to refresh on its own without me reloading, so that the number I act on is current.
3. As a member of the public, I want no patient names or details on that screen, so that attending a free eye camp is not a public disclosure.
4. As an admin, I want the public headline to sum the seat limits of the camp's days, so that the total reflects real planned capacity rather than an arbitrary figure.
5. As an admin, I want the marketing copy replaced by the occupancy figure, so that the first thing anyone sees is operationally useful.

### Pre-registration and self-register

6. As a volunteer, I want to register a patient one to two months before the camp, so that we can spread intake instead of absorbing everyone on the day.
7. As a volunteer, I want a pre-registration to print nothing, so that we do not hand out prescriptions weeks before a doctor has seen anyone.
8. As a patient, I want to self-register from my own phone by scanning my Aadhaar Secure QR, so that I do not need to find a volunteer.
9. As a patient self-registering, I want no way to type my details by hand, so that the record of me is what my card says.
10. As a patient, I want to give a household phone number that other members of my family also use, so that one phone can cover several of us.
11. As a team lead, I want the system to refuse a second registration for the same person in the same camp with no override, so that duplicates cannot be argued into existence at the desk.
12. As a team lead, I want that duplicate check to use Aadhaar last-4 with name, Aadhaar last-4 with date of birth, name with age and household phone, or a known Person, so that it catches duplicates even when one of the registrations was typed.
13. As a volunteer, I want a camp day to stop accepting new registrations once it reaches its seat limit, so that we do not book more people into a day than the venue can hold.
14. As an admin, I want every camp day to require a seat limit greater than zero, so that the public total is always meaningful.

### SMS

15. As a patient, I want an SMS in Hindi the moment I am registered, so that I know my registration succeeded.
16. As a patient, I want that SMS to tell me my registration number, so that I can identify myself at the desk without spelling my name.
17. As a patient, I want that SMS to tell me the camp date and venue, so that I know where and when to go.
18. As a patient, I want a second SMS the day before my camp day, so that I do not forget.
19. As a patient sharing a household phone with two relatives, I want three separate messages with three different registration numbers, so that each of us knows our own number.
20. As a patient, I want every message in Devanagari script, so that I can read it.
21. As a patient, I want the messages short, so that they are readable on a basic handset.
22. As a patient deferred for Spectacles to be made, I want an SMS at the clinical desk at the moment I am deferred, so that I have the collection date even if I lose the paper Token.
23. As a patient deferred for OT, I want an SMS at the clinical desk at the moment I am deferred, so that I have the surgery date in writing.
24. As a patient with a Specs collection day appointment, I want a reminder the day before, so that I turn up to collect.
25. As a patient with an OT Schedule Day appointment, I want a reminder the day before, so that I turn up for surgery.
26. As an admin, I want each of the six message types to be its own approved DLT template, so that sending is compliant.
27. As an admin, I want a send recorded once per patient per message type per event date, so that a repeated cron run does not message anyone twice.
28. As an admin, I want patients with a missing or invalid phone number skipped rather than the whole run failing, so that one bad record does not stop the batch.
29. As an admin, I want a cancelled Token to exclude that patient from the corresponding reminder, so that we do not tell someone to collect spectacles that were re-deferred elsewhere.

### Camp-day Arrival

30. As a volunteer, I want one scan box on the desk rather than a mode I have to choose first, so that I am not switching settings during a four-hundred-patient morning.
31. As a volunteer, I want scanning a patient who already has Aadhaar on file to check them in, so that the natural action at the door is the right one.
32. As a volunteer, I want scanning a patient who was a Manual entry to show me the card values beside the stored values, so that I can see exactly what is about to change.
33. As a team lead, I want confirming Mismatch review to overwrite the stored name, age, gender, date of birth, Aadhaar last-4, and address with the card values, so that the card is the authority on identity.
34. As a team lead, I want Mismatch review to keep the household phone, the camp day, and the `reg_no`, so that confirming does not detach the patient from their booking or their SMS history.
35. As a team lead, I want no way to keep the stored values and no way to edit the card values in Mismatch review, so that the outcome is not negotiable.
36. As a volunteer, I want a scan that matches nothing to refuse to register anyone automatically, so that a mis-scan cannot silently create a duplicate patient.
37. As a volunteer, I want a scan that matches nothing to offer me a name or phone search first, so that I find the existing booking rather than creating a second one.
38. As a volunteer, I want registering a new patient on camp day to take a deliberate separate action, so that walk-ins are possible but never accidental.
39. As a volunteer, I want a walk-in to register and arrive in one action, so that someone who never pre-registered is not slower to process than someone who did.
40. As a volunteer, I want a patient booked for one camp day who arrives on another to be checked in on the day they came, so that nobody who travelled to the camp is turned away.
41. As an admin, I want that day change recorded, so that I can see afterwards how much of the day's load was unplanned.
42. As an admin, I want arrivals on a day to be allowed to exceed that day's seat limit, so that the limit governs booking rather than the door.
43. As a volunteer, I want the prescription to print only after Arrival, so that a booking never produces paper.
44. As a volunteer, I want a patient to reach Seen only through Arrival, so that the Seen count means people who were physically present.
45. As an admin, I want a registration with no Arrival to be visible as a no-show, so that I can measure attrition between booking and camp day.

### Live scan on poor hardware

46. As a volunteer with an old Android phone, I want Live scan to request 1080p rather than 720p, so that the dense Aadhaar Secure QR has enough pixels per module to decode.
47. As a volunteer, I want the camera to request continuous focus, so that a card held at arm's length is actually in focus.
48. As a volunteer, I want the app to use a full-sensor still where the browser offers one, so that decoding is not limited to the downscaled preview.
49. As a volunteer, I want twenty seconds of scanning with no Detect at all to reveal torch, photo upload, and manual entry together, so that a camera that never detects cannot trap me.
50. As a volunteer, I want a Scan stall to count the same as two Failures, so that there is one rule for when the typed form appears.
51. As a team lead, I want manual entry to remain unavailable until either two Failures or a Scan stall, so that nobody skips scanning out of habit.
52. As a team lead, I want a Manual entry marked on the registration, so that I know which records were typed and may need repair on camp day.
53. As a volunteer, I want a USB wedge scanner to keep working exactly as it does now, so that desks with hardware are unaffected by camera changes.
54. As a volunteer, I want photo upload to remain available, so that a still image of the QR is a fallback when the live camera cannot lock.

### Doctor and Fulfilment lines

55. As an admin, I want the live patient list removed from the desk, so that patient names are not displayed on a shared screen to people who do not need them.
56. As a volunteer, I want to mark a patient Seen by scanning the QR on their printed prescription, so that the common case is one action.
57. As a volunteer, I want to mark a patient Seen by typing their registration number, so that a damaged or unreadable QR does not block me.
58. As a volunteer, I want to mark a patient Seen by searching their name, so that a patient who lost their prescription can still be processed.
59. As a clinical desk operator, I want four Fulfilment lines — medicine, Fixed-power specs, Spectacles to be made, and OT — so that the screen matches the four physical desks.
60. As a clinical desk operator, I want to record the power the doctor prescribed when I hand over Fixed-power specs, so that the seventy to eighty percent of patients who get ready-made spectacles still have a clinical record.
61. As a clinical desk operator, I want Fixed-power specs to print no Token and send no SMS, so that the highest-volume line is the fastest.
62. As a clinical desk operator, I want to record full measurements for Spectacles to be made, including each eye's power and any bifocal addition, so that the workshop can make the right lenses.
63. As a clinical desk operator, I want deferring Spectacles to be made to assign a Specs collection day, so that the patient has a date to return.
64. As a clinical desk operator, I want deferring OT to assign an OT Schedule Day, so that the surgery is scheduled before the patient leaves.
65. As a clinical desk operator, I want the day picker to pre-select the earliest day with a free seat, so that the common case is one tap.
66. As a clinical desk operator, I want to change that to any other day that has a free seat, so that I can ask the patient which day they are free.
67. As a clinical desk operator, I want full days shown as full and unselectable, so that I do not offer a patient a date we cannot honour.
68. As a clinical desk operator, I want a hard refusal when every day of a type is full, together with a clear instruction to call the admin, so that we never overbook a surgeon.
69. As an admin, I want to add an OT Schedule Day or a Specs collection day from my own device, so that I can unblock a clinical desk quickly.
70. As a patient, I want an A6 paper Token when I am deferred, so that I have something physical to bring back.
71. As a patient re-deferred to a different day, I want my previous Token cancelled, so that only one appointment is live for me.
72. As a clinical desk operator, I want a patient to be able to go to more than one line, so that someone needing both medicine and surgery is fully recorded.

### Reporting

73. As an admin, I want exactly one export button, so that there is no question about which report to run.
74. As an admin, I want one row per patient, so that the row count is the patient count and I can filter in a spreadsheet without deduplicating.
75. As an admin, I want the export to include name, age, gender, household phone, address, Aadhaar last-4, and registration number, so that I have the full identity record.
76. As an admin, I want the export to include whether the record was a Manual entry, so that I can audit data quality.
77. As an admin, I want the export to include the camp day, registration time, arrival time, and seen time, so that I can measure the funnel and count no-shows.
78. As an admin, I want the export to include diagnosis, blood pressure, and blood sugar, so that clinical outcomes are in the same file.
79. As an admin, I want the export to include each eye's prescribed power and bifocal addition, so that spectacle data is analysable.
80. As an admin, I want the export to include the status of all four Fulfilment lines in their own columns, so that I can count how many patients received each.
81. As an admin, I want the export to include the assigned OT Schedule Day and Specs collection day with venue, so that I can plan follow-up logistics.
82. As an admin, I want the export restricted to admins, so that a wide file of patient data is not downloadable by every volunteer.

### Prescription

83. As an admin, I want the printed prescription to reproduce the trust's existing form exactly, so that it looks like what patients and doctors already expect.
84. As an admin, I want the only editable part to be the sponsor logos, so that the one thing that changes between camps is the one thing I can change.
85. As an admin, I want to upload, reorder, and delete sponsor logos on one screen with the change live immediately, so that there is no draft-and-publish step to forget.
86. As an admin, I want no way to edit the header, subtitle, footer, or layout from the UI or the API, so that the prescription cannot come out wrong on a camp morning.

### Deployment

87. As an admin, I want the app served over HTTPS on a real domain, so that volunteers' phone cameras will start at all.
88. As an admin, I want a production configuration separate from the development one, with no reload, no bind mounts, no default admin password, and secrets from the environment, so that the deployed system is not the dev stack.
89. As an admin, I want the built frontend served as static files, so that the camp is not depending on a development server.

## Implementation Decisions

### Registration lifecycle

- The registration record gains an `arrived_at` timestamp and its status vocabulary extends to `registered -> arrived -> seen`. This is one record, not two collections; pre-registration and desk registration produce the same shape.
- `arrived_at` is set only by a camp-day Lock that resolves to that registration. It is never inferred from print state.
- Printing a prescription requires `arrived_at` to be set. The existing Print window rule is unchanged and continues to apply on top of this.
- Marking Seen requires `arrived_at` to be set. The existing print-before-seen rule is unchanged.
- When an Arrival resolves to a registration booked on a different camp day of the same camp, the registration's camp day is updated to the day of arrival and the change is recorded on the record. This does not consume or release a camp-day seat.

### Desk scan resolution

- One endpoint resolves a Lock payload against the active camp and returns a discriminated outcome rather than a boolean. The four outcomes are: matched with Aadhaar already on file, matched on a Manual entry with a field-level diff, no match, and ambiguous match.
- Matched with Aadhaar on file stamps Arrival and returns the patient for printing. This replaces the previous behaviour of rejecting an already-scanned match as a duplicate.
- Matched on a Manual entry returns the card values and the stored values as a field-level diff and does not mutate anything. A second, explicit confirmation endpoint applies the Aadhaar overwrite and stamps Arrival in one operation.
- The overwrite writes name, age, gender, date of birth, Aadhaar last-4, and address from the card; it preserves household phone, camp day, `reg_no`, and all lifecycle timestamps; it clears the Manual entry mark and attaches the Person.
- No match returns no match. It does not create a registration. Registration remains the existing create endpoint, called deliberately by the client.
- Ambiguous match — more than one Manual entry matching — continues to refuse and list the candidates, as today.
- Duplicate in camp detection is unchanged in rules and remains a hard refusal on the create path with no override.

### Camp-day capacity

- Camp day creation and update reject a seat limit of zero or less. Existing days with a zero limit require a one-time backfill to a real number before the public headline is correct.
- Camp-day capacity is enforced on registration only. The Arrival path does not check it.
- The public active-camp endpoint returns camp-level totals — total seats summed across days, and total registrations — in addition to the existing per-day breakdown, so the login screen can lead with one figure without a second request.
- OT Schedule Day and Specs collection day seat consumption is unchanged: an atomic conditional increment that refuses when the day is full. When no day of the required type has a free seat, the deferral is refused with a message naming the admin action needed.

### SMS

- The DLT send function takes `reg_no`, event date, and venue as template variables, not venue alone. Six template identifiers are configured, one per message type.
- The send ledger is keyed on patient, message type, and event date. It is no longer keyed on phone number, so household deduplication is removed.
- Registration confirmation is sent on the registration create path, from both the volunteer and self-register routes. A send failure must not fail the registration; the registration is the durable outcome and the message is best-effort with a ledger row recording the attempt.
- OT Token SMS and Specs Token SMS are sent on the deferral path at the moment the Token is created, under the same best-effort rule.
- The three day-before reminders continue to run from the existing cron endpoint under the existing shared-secret check, and continue to skip missing or invalid numbers and cancelled Tokens.
- Message copy is Devanagari and must fit the approved templates. Two UCS-2 segments is the working budget per message.

### Fulfilment

- The four item types are `medicine`, `specs`, `ot`, and the distinction between Fixed-power specs and Spectacles to be made remains a status on the `specs` item type — `fulfilled` and `deferred` respectively — rather than a fifth item type. The clinical screen presents them as four lines; the stored model stays three item types and their statuses.
- Specs measurements remain on the transcription, not on the fulfilment. Recording power for Fixed-power specs is therefore a matter of requiring the measurement fields on the issue path, not a schema change.
- Measurements are required before a `specs` fulfilment can be recorded in either status. Medicine and OT lines are unaffected.

### Desk patient list

- The list of all registered patients is removed from the desk. The endpoint that backed it is removed if nothing else consumes it; if it is still used by an admin surface, it becomes admin-only.
- Marking Seen is driven by an existing lookup that already accepts a patient QR value, a `reg_no`, or a name. No new lookup mechanism is introduced.

### Live scan

- The camera constraint ladder requests 1920x1080 as the ideal before falling back through the existing attempts, and adds a continuous focus mode hint. The ladder remains a list of progressively weaker constraint sets so that a device that cannot satisfy the first still gets a stream.
- Where the browser exposes a still-image capture path on the video track, a full-sensor still is preferred over a preview frame for the decode attempt, falling back to the current preview-frame path.
- The live scan engine gains a Scan stall: twenty seconds elapsed with zero Detects since the scan started. A Scan stall is equivalent to two Failures for the purpose of revealing fallbacks, and reveals torch, photo upload, and manual entry together in one panel.
- Guide ROI, Soft Hold, Freeze, and the payload-ignore window are unchanged.

### Prescription template

- Header title, subtitle, footer, and block layout become constants in the print component. The template document retains only the sponsor logo list.
- The draft, publish, and restore-defaults endpoints and the template version field are removed. Saving logos writes the live record directly.
- Existing logo size and MIME validation is retained unchanged.

### Reporting

- The two existing exports are replaced by one admin-only endpoint producing a single CSV, one row per patient, scoped to a camp with the active camp as the default.
- Columns cover identity, Manual entry mark, lifecycle timestamps including `arrived_at`, clinical values, per-eye measurements, the status of each of the four lines, and the assigned clinical day and venue for each deferral.
- Patients with no Arrival appear with an empty arrival column rather than being excluded, so no-shows are countable.

### Deployment

- A production compose configuration is added alongside the development one: built frontend served statically, application server without reload, no source bind mounts, no default credentials, secrets supplied by the environment.
- A reverse proxy terminates TLS for a real domain with automatic certificate issuance and renewal.
- The browser-derived API origin and the private-range CORS regex remain for local development and are not the production path.

## Testing Decisions

A good test here asserts externally observable behaviour: the HTTP status and body a client receives, the arguments a send function was called with, or what a rendered screen shows a volunteer. It does not assert internal call sequences, private helper behaviour, or document shapes that no client reads. Tests are named for the rule they defend, not the function they call.

Four seams, all of which already exist. No new seam is introduced.

**In-process application seam — preferred for all backend work.** The application is constructed against a mock database with the outbound SMS function replaced by a recorder, and driven through the framework's test client. Prior art is the reminders test module and the adversarial challenger module. Everything server-side belongs here: Arrival transitions and their gates, the four scan-resolution outcomes, Mismatch review returning a diff without mutating, the confirmation applying the overwrite while preserving `reg_no` and phone, wrong-day check-in, camp-day capacity rejecting registration but not Arrival, deferral refusal when every clinical day is full, per-patient SMS payloads and their variables, ledger idempotency across repeated runs, template lockdown returning the fixed layout, and the export's exact CSV header and row content.

Note that the existing reminders test asserting a household of four produces one camp reminder **inverts** under the new send policy and must become an assertion that it produces four, each with a distinct registration number. The test module's assertion on approved Devanagari copy extends from three message types to six.

**Live-server integration seam — retained, not grown.** Tests that require genuine database semantics stay where they are and new tests are added here only when the behaviour cannot be observed with a mock: unique index enforcement, and the atomic conditional seat increment under concurrency. Prior art is the main backend test module and the index test module.

**Rendered-screen seam for the frontend.** Pages are rendered with the API module mocked and assertions are made on what a volunteer sees and can do. Prior art is the desk, clinical, admin dashboard, and fulfilment station test modules. This covers the single scan box presenting each of the four outcomes, Mismatch review showing both value sets with no edit affordance, the absence of the patient list, marking Seen through each of the three lookup routes, the four-line clinical screen requiring measurements before a specs line can be recorded, the day picker pre-selecting the earliest free day and disabling full ones, and the login screen leading with the occupancy figure.

**Scan engine seam.** The live scan engine already receives its detectors, decoder, and callbacks as injected functions. Scan stall is tested by injecting a detector that always returns no result and advancing fake timers past the threshold, asserting the fallbacks are revealed and that the engine treats the stall as equivalent to two Failures. No camera, no browser media APIs.

**Explicitly not covered by any seam.** Whether a real device honours the requested resolution, focus mode, or still-capture path is negotiated by the browser and the hardware. The constraint-ladder builder is a pure function and its output is asserted, but the effect on decode rates must be verified in the field on the oldest and worst phone available before the camp. This is a known gap, not an oversight.

## Out of Scope

- Any offline or on-site deployment mode. Camp-day registration depends on venue connectivity, mitigated with a mobile router and a spare SIM rather than in the application.
- Any synchronisation between environments or databases.
- Recording a clinical deferral without an assigned day, and any admin waiting-list or later-assignment screen. When every clinical day is full the operator calls the admin, who adds a day.
- Changing the Duplicate in camp matching rules. They are carried over unchanged.
- Any override of a Duplicate in camp refusal.
- Any patient-facing login. Patients never authenticate; self-register remains unauthenticated and Aadhaar-only.
- Any typed path on self-register.
- English or any non-Devanagari SMS copy.
- Any change to the A6 Token paper format.
- Any queue position, waiting time, or called-next display for patients or volunteers.
- Backfilling registration confirmation SMS to patients who registered before this ships.
- Editing the prescription layout from any interface. Changing it is a code change and a deploy.

## Further Notes

**The six DLT template approvals are the critical path and are external to this repository.** They must be applied for and approved by the telecom operator before pre-registration opens, and none of the SMS work can be verified end to end until they exist. Start that process before any code is written. The templates are: registration confirmation, camp reminder, OT Token, OT reminder, Specs Token, Specs reminder — each taking registration number, date, and venue.

**A domain and certificate are a prerequisite, not a hardening task.** A browser will not start a camera over plain HTTP on anything other than loopback, so Live scan cannot be tested on a real phone until HTTPS is in place. Provision the domain early.

**One accepted risk, recorded so it is not a surprise.** When every OT Schedule Day is full and no admin is reachable, the clinical desk cannot record that the patient needs surgery, and that clinical fact is lost. This was chosen deliberately over recording an unscheduled deferral, on the grounds that never overbooking a surgeon matters more. If it bites in practice, the unscheduled-deferral design is the documented alternative.

**Camp days with a zero seat limit need a one-time backfill.** Until every day of the active camp has a real limit, the public total will understate capacity.

**Volume expectation for SMS.** Per-patient sending multiplies volume by mean household size relative to the previous policy, and four new send points are added. At fifteen thousand patients the camp messages alone are on the order of sixty thousand Devanagari segments. Confirm the sending budget before the camp rather than discovering it mid-camp.

**Sequencing suggestion.** The SMS grain change and the Arrival state are independent of each other and can proceed in parallel. Scan resolution depends on Arrival. The four-line clinical screen and the export both depend on measurements being recorded on the issue path, so do that first. The prescription lockdown, the desk list removal, the public headline, and the camera constraint changes are independent of everything else and can land at any time.

**Relevant decisions.** ADR 0012 Arrival as a distinct state, ADR 0013 per-patient SMS with registration number, ADR 0014 camp seats plan footfall while clinical seats block, ADR 0015 prescription layout in code, ADR 0016 cloud-only deployment over HTTPS, and the amendment appended to ADR 0011 covering Scan stall and camp-day scan intent.
