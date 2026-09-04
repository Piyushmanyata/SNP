# SNP Camps

Field medical camp operations: desk registration, presence, clinical fulfilment.

## Language

**Aadhaar Secure QR**:
The dense UIDAI Secure QR printed on a PVC Aadhaar card. This is the primary artefact the Registration desk must read.
_Avoid_: Aadhaar QR (ambiguous — also used for e-Aadhaar, mAadhaar, and older XML QRs)

**e-Aadhaar QR**:
The QR on an e-Aadhaar PDF or printout. Fallback artefact, not the optimisation target.
_Avoid_: Aadhaar QR

**mAadhaar QR**:
The QR shown on the mAadhaar app screen. Fallback artefact, not the optimisation target.
_Avoid_: Aadhaar QR

**XML QR**:
The older Aadhaar card QR that encodes XML attributes. Fallback artefact, not the optimisation target.
_Avoid_: Aadhaar QR

**Registration desk**:
One laptop, one USB imager, one volunteer seat. Ten per camp day; pairs share one A4 printer. The USB imager is the primary capture device for Aadhaar Secure QR; the desk camera is the fallback.
_Avoid_: reg station, station, desk (alone, when the clinical desks could be meant)

**USB imager**:
The 2D barcode scanner on a Registration desk that reads Aadhaar Secure QR and types the payload into the page as keystrokes. Primary capture device at the desk.
_Avoid_: USB scanner (also used for 1D scanners that cannot read Secure QR), barcode gun

**Desk account**:
The login a Registration desk or a Fulfilment line desk uses for the day. One per desk, signed in once in the morning by a team lead, shared by every volunteer who sits there. Not a person. Team leads and admins sign in as themselves.
_Avoid_: volunteer login, shared password, kiosk account

**Volunteer roster**:
The admin-kept list of volunteer names for a camp. A roster entry is a person, not a login; it has no password and no PIN.
_Avoid_: staff list (that is the accounts), user list

**On-desk volunteer**:
The roster name a volunteer picks when they sit at a desk. It rides on every registration and clinical posting made at that desk until they hand over or a team lead clears it. A desk with no On-desk volunteer refuses to post. Honesty-based: nothing verifies the pick. The leaderboard counts by this name.
_Avoid_: current user, operator (that is a clinical account), logged-in volunteer

**Desk camera**:
The volunteer-held phone camera at a Registration desk. Fallback capture device for Aadhaar Secure QR when the USB imager cannot read the card. Primary capture at the door and for self-register.
_Avoid_: patient camera, self-register camera

**Desk phone**:
A volunteer's own Android or iPhone used at a Registration desk for the fallback ladder. Both platforms must read Aadhaar Secure QR.
_Avoid_: camp-issued device, patient phone

**Live scan**:
Reading Aadhaar Secure QR through the desk-camera viewfinder.
_Avoid_: scan (also used for photo upload and the USB imager)

**Guide ROI**:
The centered square on the live-scan preview, about 90% of the video's short edge, where the volunteer holds Aadhaar Secure QR. The first detect looks here at native pixels; a miss uses the full frame next. It is a place to look, not a smaller image.
_Avoid_: qrbox (the old crop that also downscaled)

**Detect**:
The camera found a QR payload. Detect is not Lock.
_Avoid_: Lock, scan, capture

**Soft Hold**:
Live scan pauses the detector while Decode runs on the Detect payload.
_Avoid_: Freeze, pause camera

**Decode**:
The server job (`POST /aadhaar/decode`) that classifies a QR payload as `card`, `garbage`, or `not-aadhaar`. There is no client Aadhaar sniff. Decode happens during Soft Hold, not after Lock.
_Avoid_: parse, client validation

**Lock**:
Decode returned `card`. Live-scan success. Not a saved registration, not a camera Detect.
_Avoid_: scan success, Detect, capture

**Failure**:
Decode returned `garbage` or `not-aadhaar`. Live scan resumes. The same payload is ignored briefly so the camera does not POST it in a loop.
_Avoid_: camera error, Lock

**Freeze**:
On Lock, live scan stops the detector and holds the preview.
_Avoid_: Soft Hold, stop camera (unless the stream is actually torn down)

**Photo upload**:
The volunteer gives the app a still image of the QR; the app reads the QR from the file.
_Avoid_: scan, gallery scan

**Wedge burst**:
The keystroke stream a USB imager emits for one card: the whole payload followed by a terminator. On a camp day the Registration desk listens for it wherever focus is, with no mode to select and no field to click; the terminator fires Decode.
_Avoid_: USB wedge (the old name for the fallback textarea), paste mode, manual USB mode

**OT Schedule Day**:
An admin-created day, unique per camp and date, on which deferred OT patients are assigned. It has a venue and a finite seat limit.
_Avoid_: OT slot, surgery day, OT appointment

**Doctor's Rx**:
The desk where a patient's paper prescription is transcribed. The only place a transcription can be edited, and the only clinical posting that is not a Fulfilment line. Every line desk reads what it wrote.
_Avoid_: transcription desk, doctor's desk, clinical desk (that is the whole area)

**Operator line**:
Where a clinical operator is posted: Doctor's Rx, or one of the four Fulfilment lines. An admin sets it on the account and the operator may override it for their own session. It is a posting, not a permission — nothing is refused because of it.
_Avoid_: role, station, desk assignment

**Fulfilment line**:
One of the four things a patient can be sent to after Seen: medicine, Fixed-power specs, Spectacles to be made, OT. Each is a physical desk at the camp, its own item type, and its own record. A patient may go to more than one, except that the two specs lines are mutually exclusive. A line is recorded or it is absent, and absent means not needed.
_Avoid_: station, queue, counter, three lines, not required (never a recorded outcome)

**Fixed-power specs**:
The clinical fulfilment outcome for ready-made spectacles handed over at camp. The power comes from Doctor's Rx; the desk reads it and cannot change it. No Token, no SMS, no collection day. The common case, about 70-80% of patients.
_Avoid_: ready specs, stock specs, issued specs

**Spectacles to be made**:
The clinical fulfilment outcome for spectacles that cannot be issued at camp and must be collected later. Deferral assigns the patient to a Specs collection day. A patient already issued Fixed-power specs cannot also be deferred here, and the reverse.
_Avoid_: to-be specs, TBD specs, specs order, glasses order

**Specs collection day**:
An admin-created day, unique per camp and date, on which patients deferred for Spectacles to be made are assigned. Same shape as an OT Schedule Day: venue and finite seat limit.
_Avoid_: specs slot, collection appointment, specs schedule

**Token**:
The paper printed when OT or Spectacles to be made is deferred. Hindi and English labels; name and venue as stored. The patient brings it to the OT Schedule Day or Specs collection day. A new deferral of the same type cancels the previous Token.
_Avoid_: slip, deferred slip, thermal slip, queue ticket, final token

**Reference prescription**:
The trust's own printed eye-camp form, photographed in the repository root. It is the authority for every string and every band of the printed prescription, including its two original misspellings.
_Avoid_: template, Rx template, sample prescription

**Sponsor logo**:
An image of the camp's sponsor, printed in the prescription footer under "Sponsorer :". The only stored template data and the only part of the printed form an admin can change.
_Avoid_: logo (the trust's own emblems are fixed masthead artwork, not sponsor logos), header image

**Print window**:
Admin-declared open/closed state on a camp day. Open: printing is enabled. Closed: printing is disabled. Not derived from the calendar. Today's camp day's Print window also chooses the Desk mode.
_Avoid_: IST print gate, today-only print

**Desk mode**:
Which of two layouts the registration desk shows, chosen by today's camp day and its Print window. Open is camp-day mode: Scan at the door first, Pre-registration hidden. Closed, or no camp day today, is pre-registration mode: Pre-registration first, Scan at the door last.
_Avoid_: camp mode, desk state, kiosk mode

**Manual entry**:
A desk registration typed after two Failures, or after a Scan stall. Marked on the registration. Not an admin approval and not an audited reason. Self-register has no typed path.
_Avoid_: manual exception, manual window, manual audit

**Scan stall**:
Twenty seconds of live scan with no Detect at all. Counts the same as two Failures, because a camera that never detects would otherwise trap the volunteer forever. Reveals torch, photo upload, and manual entry together.
_Avoid_: scan timeout, camera failure, give up

**Arrival**:
The patient is physically at the camp on a camp day. Stamped by a desk Lock that matches their registration in this camp, or by the registration that creates a walk-in. Registration is a booking; Arrival is presence. Stamped once: a second Lock does not re-stamp it or move the patient again. A registration reaches Seen only through Arrival. Print Prescription is gated on Arrival, not on Registration. The desk offers no way to check a patient in from a name or number lookup.
_Avoid_: check-in, presence, attendance, walk-in (a walk-in registers and arrives in one action)

**Door walk-in**:
A registration created at the door from the card a Scan at the door has already decoded, needing only the household phone typed. Registers and stamps Arrival in one action, and is a scanned registration, not a Manual entry.
_Avoid_: rescan, second scan, walk-in registration (also used for the typed path)

**Aadhaar overwrite**:
A Lock that matches exactly one Manual entry updates that registration in place. Name, age, gender, DOB, last-4, and address come from the card. Household phone, camp day, and reg_no stay. The Manual entry mark clears. Not a second registration. On a camp day the overwrite is not silent: it goes through Mismatch review first.
_Avoid_: merge, bind Aadhaar, rescan button

**Mismatch review**:
The camp-day screen shown when a Lock matches a registration whose stored fields differ materially from the card. Card values and stored values side by side; a volunteer or team lead confirms. Confirming applies the Aadhaar overwrite and stamps Arrival. There is no way to keep the stored values and no way to edit the card values. A Trivial diff never reaches this screen.
_Avoid_: conflict resolution, merge screen, override prompt

**Trivial diff**:
A difference between a stored registration and the card that a Lock resolves on its own by applying the Aadhaar overwrite and stamping Arrival with no screen: letter case, spacing and punctuation, initials order in the name, age within one year, any field the registration never had, and the address (never an identity field). Anything else is material and goes to Mismatch review.
_Avoid_: fuzzy match, close enough, auto-merge

**Duplicate in camp**:
A second registration in the same camp for the same person. Blocked when Person, last-4+name, last-4+DOB, or name+age+household phone already exists in that camp. There is no override.
_Avoid_: register anyway, likely duplicate

**Public occupancy**:
The headline on the unauthenticated login page for the active camp: total seats across the camp's days, and registrations so far. Refreshes on its own. No patient details, no per-patient anything.
_Avoid_: live feed, registration ticker, public patient list

**Camp-day capacity**:
Every camp day has a seat limit greater than zero; there is no unlimited day. The limit counts bookings, which Arrival never moves: a patient booked for one camp day who arrives on another is checked in on the day they came without consuming a seat there or releasing one on the day they left. Camp-day capacity is a planning number for footfall. OT Schedule Day and Specs collection day seats are surgical and workshop capacity, and those stay a hard block.
_Avoid_: seats_taken (that counter is OT and Spectacles to be made only), unlimited day

**Camp-day board**:
The read-only page a team lead watches during a camp day. Per Registration desk, Arrivals in the last fifteen minutes and the last hour, with a desk that has gone quiet highlighted; the transcription backlog; each Fulfilment line's count today; seats left on the next OT Schedule Day and Specs collection day; SMS failures. Counts only, refreshes on its own, no actions and no patient names.
_Avoid_: dashboard (that is the admin area), live feed, monitor, alerts (the board pushes nothing)

**Transcription backlog**:
Patients who have reached Seen today and have no transcription yet at Doctor's Rx. The number that says whether the specs desk is about to stall.
_Avoid_: pending Rx, queue at Doctor's Rx (a physical queue is not the backlog)

**Camp records export**:
The single admin-only CSV for a camp, one row per patient including no-shows. Carries identity (name, age, gender, household phone, address, Aadhaar last-4, reg_no), the Manual entry mark, the registration / arrival / seen timestamps, diagnosis, BP and blood sugar, each eye's power, the status of each of the four Fulfilment lines with blank meaning the patient was never recorded at that desk, and the assigned clinical day and venue for each deferral. It is a wide file of patient data and is not downloadable by a volunteer.
_Avoid_: camp records, clinical audit, the reports (there is exactly one export)

Every SMS below is Devanagari, per patient, and carries that patient's reg_no. A household number covering three patients receives three messages. Each is its own DLT template.

**Registration confirmation**:
Sent when a registration is created, whether by self-register or by a volunteer. Confirms the patient is registered and states reg_no, camp day date, and venue.
_Avoid_: welcome SMS, enrolment SMS, receipt

**Camp reminder**:
Sent the calendar day before a camp day, to each patient registered for that day. reg_no, date, and venue.
_Avoid_: camp SMS, registration reminder

**OT Token SMS**:
Sent at the OT desk the moment OT is deferred, alongside the printed Token. reg_no, OT Schedule Day date, and venue.
_Avoid_: surgery SMS, token confirmation

**OT reminder**:
Sent the calendar day before an OT Schedule Day, to each patient with an OT Token for that day. reg_no, date, and venue.
_Avoid_: OT SMS, surgery SMS, follow-up reminder

**Specs Token SMS**:
Sent at the specs desk the moment Spectacles to be made is deferred, alongside the printed Token. reg_no, Specs collection day date, and venue.
_Avoid_: glasses SMS, token confirmation

**Specs reminder**:
Sent the calendar day before a Specs collection day, to each patient with a Spectacles-to-be-made Token for that day. reg_no, date, and venue.
_Avoid_: specs SMS, glasses SMS, follow-up reminder
