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

**Volunteer**:
An authenticated user account with a unique Name and 4-digit PIN assigned to a Team Lead or Admin. Operates registration or fulfilment desks directly.
_Avoid_: Desk account, kiosk account, shared login

**Team**:
The cohort of Volunteers supervised by a specific Team Lead. The Team Lead's leaderboard score is strictly the sum of points earned by their Team.
_Avoid_: sub-camp, brigade, shift group

**PIN**:
The personal number used with a unique Name to sign in: 6 digits for an Admin or Team Lead, 4 for a Volunteer or Clinical operator. It is never one digit repeated or a straight run like 1234. A new or reset account gets a random one-time PIN, shown once to the person who created or reset it, and must choose its own PIN at first sign-in.
_Avoid_: password, secret, OTP, default PIN

**Lockout**:
Five wrong PINs for one Name within 15 minutes lock that Name for 15 minutes. A network where no one has signed in during the last 12 hours gets 50 wrong PINs across all Names in 15 minutes; the venue, where desks sign in, is not limited this way. The Team page shows a locked account and how often it was locked in the last day, from how many networks. The account's Team Lead or an Admin can Unlock it, which keeps the PIN and is recorded.
_Avoid_: ban, block (an Admin disables an account; a lockout lapses by itself)

**Reset PIN**:
The header action beside Logout that lets the signed-in user choose a new PIN after entering their current PIN. Logout ends the session before another person signs in.
_Avoid_: Switch Volunteer, switch person, shared login

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
The keystroke stream a USB imager emits for one card: the whole payload followed by a terminator. Registration listens for it wherever focus is, with no mode to select and no field to click; the terminator fires Decode. At the door, on a laptop, the USB / paste box opens focused, the payload arrives visibly in it, and the box clears for the next patient; a burst that lands in any other field is still read, and that field keeps its value (ADR 0048).
_Avoid_: USB wedge (the old name for the fallback textarea), paste mode, manual USB mode

**OT Schedule Day**:
An admin-created hospital surgery date, unique per camp and date, with a finite seat limit that is always enforced, unlike a camp day's. The admin types the hospital, defaulting to Vimla Ramkrishna Bajaj Eye Hospital, plus an optional short name used in SMS instead of the full address (ADR 0040); camp staff schedule it and print the token. Past dates cannot accept bookings.
_Avoid_: OT slot, surgery day, OT appointment

**Prescription transcription**:
The operator copies the doctor's paper prescription at any Fulfilment line, then issues supplies or schedules hospital treatment or collection at the same desk. It runs as a wizard: one question per screen, the same sequence for every operator, with a step for each prescribed line only and a read-back before commit. Corrections after fulfilment require an audit reason and use their own form, not the wizard.
_Avoid_: Doctor's Rx line, separate transcription desk, prescription form (it is no longer one screen)

**Medicine catalogue**:
The single global list of medicines the trust carries, maintained by an admin. The clinical desk can prescribe nothing else; a medicine the camp does not stock is recorded as not available at the desk. Retiring an entry hides it from operators without touching prescriptions already committed.
_Avoid_: formulary, drug list, stock (nothing is counted)

**Prescribed medicine**:
One medicine on a prescription: a name and nothing else. The dose stays on the paper the patient keeps. The name is copied onto the revision when the prescription is committed, so later catalogue edits cannot rewrite it.
_Avoid_: medication instructions, dosage, prescription line item

**Fixed power catalogue**:
The admin's list of ready-made spectacle powers the camp carries, in dioptres, minus and plus. It is the stock list: a power that is not on it cannot be prescribed or issued.
_Avoid_: power range, lens stock, inventory

**Issued power**:
The fixed power actually handed over, recorded on the fulfilment. It equals the prescribed power unless that power had run out and the desk substituted a neighbouring one. The prescribed power on the revision never moves.
_Avoid_: final power, corrected power, adjusted prescription

**Partially fulfilled**:
The medicine line's status when some prescribed medicines were given and others were not. Derived from the per-medicine outcomes, never chosen by the operator.
_Avoid_: partial, incomplete, half fulfilled

**Operator line**:
The one of four Fulfilment lines the operator chooses for their current session. It selects which fulfilment station opens once a prescription is committed, not permissions and not the transcription sequence — every operator walks the same wizard. Admin assignment is unnecessary.
_Avoid_: role, station, desk assignment

**Fulfilment line**:
One of the four things a patient can be sent to after Seen: medicine, Fixed-power specs, Spectacles to be made, or Hospital. Each has its own item type and record. The Hospital line carries the Hospital outcome; operations do not occur at camp. A prescription names at most one of Fixed-power specs, Spectacles to be made, or IOL surgery; medicine goes with any of them, and a Hospital referral goes with either specs line. A patient who declines IOL surgery and then wants spectacles needs a correction to the prescription. An absent record means not needed.
_Avoid_: station, queue, counter, three lines, Hospital surgery (the line also holds referrals), not required (never a recorded outcome)

**Fixed-power specs**:
The clinical fulfilment outcome for ready-made spectacles handed over at camp. The operator picks the power from the Fixed power catalogue — one tap for both eyes, or one per eye when they differ — and no measurement grid is involved. If that power has run out, the desk may issue a neighbouring one, recorded as the Issued power. No Token, SMS or collection window is required.
_Avoid_: ready specs, stock specs, issued specs

**Spectacles to be made**:
The clinical fulfilment outcome for spectacles that cannot be issued at camp and must be collected later. Deferral assigns the patient to a Specs collection day. Never on the same prescription as Fixed-power specs or IOL surgery. Recording it as cancelled closes its Token. A correction cannot remove or change the order while its Token is active; cancel it first.
_Avoid_: to-be specs, TBD specs, specs order, glasses order

**Specs collection day**:
An admin-created date range, unique per camp and start date, with a venue, on which patients deferred for Spectacles to be made collect them. It has no seat limit. Collection hours are always 10:00 AM–5:00 PM and are not stored.
_Avoid_: specs slot, collection appointment, specs schedule

**Token**:
The short A6 paper printed when IOL surgery or Spectacles to be made is scheduled — never for a Hospital referral or Surgery declined. It contains the patient's name, registration number, date or collection window and venue. Each Token sends its own SMS, so moving a patient A→B→A sends three. An IOL surgery Token is titled as IOL surgery, names the eye, carries BP and blood sugar when recorded, the hospital phone, and the Bring list. Rescheduling cancels the previous Token. A Schedule edit replaces it: the old Token is marked replaced, a new one is printed, and the patient gets one notice by SMS or by phone.
_Avoid_: slip, deferred slip, thermal slip, queue ticket, final token

**Schedule edit**:
A change to an OT Schedule Day or Specs collection day through its Edit. A date or venue change is material: it replaces every active Token on the day and queues one notice per patient. A seat-limit or SMS short-name change is not. Adding a day on a date that already has one is refused.
_Avoid_: re-adding a day, upsert

**Patients to phone**:
The admin list of patients whose Token was replaced by a Schedule edit but whose SMS notice was not sent, failed, or is paused. Someone phones each one and marks the call done.
_Avoid_: manual SMS, call list

**Bring list**:
The one list of what a patient carries on the day of IOL surgery: the prescription, the Token, Aadhaar card, ration card and mobile phone. Printed identically on the prescription and the IOL surgery Token. On the prescription it shares a Hindi and English band with the notice that only cataract (IOL) operations are arranged.
_Avoid_: disclaimer, documents list, voter ID (not required)

**Hospital outcome**:
What the hospital line records for a patient, chosen explicitly by the operator and never inferred from the diagnosis: IOL surgery, Hospital referral, or Surgery declined. The prescription carries the doctor's choice — IOL surgery with its eye, or Hospital referral. Surgery declined is the patient's answer at the hospital station to a prescribed IOL surgery, the alternative to scheduling it. Only a scheduled IOL surgery takes an OT Schedule Day seat, prints a Token and sends an SMS.
_Avoid_: OT status, surgery status, glaucoma rule

**IOL surgery**:
The only operation the trust arranges: cataract surgery with an intraocular lens at the hospital, scheduled onto an OT Schedule Day with a Token. One eye, one seat, one Token. When the paper prescribes both eyes, the eye the doctor marks first is scheduled and the second is noted on the prescription for a later camp.
_Avoid_: OT procedure, cataract operation (the procedure is not free text), surgery (alone)

**Hospital referral**:
The doctor sends the patient to the hospital for care the trust does not arrange — glaucoma, for one. Complete once the prescription is committed; there is nothing to do at the hospital station. No seat, no Token, no SMS.
_Avoid_: glaucoma surgery, referral token, OT referral

**Surgery declined**:
The patient does not want the prescribed IOL surgery, recorded at the hospital station instead of scheduling it. Never follows a Hospital referral. No seat, no Token, no SMS.
_Avoid_: not required, no-show, cancelled

**Displayed date**:
Every date a person reads — on screen, on paper, in an SMS or in the Camp records export — is written DD-MM-YYYY, as 17-09-2026. Only the device's own date picker is exempt.
_Avoid_: ISO date, YYYY-MM-DD (never shown to a person), DD/MM/YYYY

**Clinical find**:
How the clinical desk opens a patient: the Patient code on the prescription, read by the USB imager with no click wherever focus is or by the desk camera, or a registration number or name typed into one field. Scoped to the active camp. A name offers only patients who have arrived and been printed, most recent Arrival first, showing the last four digits of the household phone to tell namesakes apart. It lists 20 and says so when more match. An Aadhaar card is not a way in; the paper is what gets transcribed.
_Avoid_: clinical lookup, Reg # box, patient search

**Reference prescription**:
The trust's own printed eye-camp form, photographed in the repository root. It is the authority for every string and every band of the printed prescription, including its two original misspellings.
_Avoid_: template, Rx template, sample prescription

**Sponsor logo**:
An image of the camp's sponsor, printed in the prescription footer under "Sponsorer :". The only stored template data and the only part of the printed form an admin can change. At most six per camp. Each upload is up to 2 MB and is stored resized to at most 600 px and 150 KB. A desk downloads a camp's logos once and refreshes them after ten minutes. A prescription never waits more than 3 seconds for them: without them it still prints, and the desk says the logos are unavailable.
_Avoid_: logo (the trust's own emblems are fixed masthead artwork, not sponsor logos), header image

**Paper check**:
The dialog that follows every prescription print at the desk. "Printed — next patient" records Print Prescription (`printed_at`), clears the card and returns the cursor to the USB box. "Print again" asks the server for the sheet again and prints it; it is not a Reprint, because nothing reached the patient yet. "Printer problem" and Escape record nothing and keep the patient on the card. A new scan closes the Paper check without recording anything. The browser's print event alone never records a print, because it fires for a cancelled dialog too.
_Avoid_: print confirmation, printed flag, auto-stamp

**Print Prescription**:
The paper in the patient's hand, recorded by the Paper check as `printed_at`. The desk prints in the page, with no navigation. An attempted print that is not confirmed is not Print Prescription. Refused after Doctor seen, and for a Manual entry from Pre-registration until its door Lock or a No-card print.
_Avoid_: print attempt, printed (for a dialog that was cancelled)

**Reprint**:
A fresh copy of the prescription for a patient who already has Print Prescription and has lost the paper. Offered only on a row the desk found from a typed registration number or name, which says when and by whom the first print was made. A door scan or a Patient code read of a printed patient says it is already printed and offers nothing, so a patient who forgets they printed cannot collect a second sheet at another desk. Closes at Doctor seen, like every print.
_Avoid_: duplicate print, Paper check's Print again (a first print not yet recorded)

**Print window**:
Server-derived printing availability for the active camp: automatic on the IST calendar camp day, or one admin-selected day, or off. Manual enable/disable expires at the next IST midnight. A stored per-day boolean is not the authority. Chooses Desk mode via the operating day. While it is closed the desk withdraws Print and says so rather than offering a control that fails; a sheet that has already printed keeps its reprint.
_Avoid_: paused camp, calendar-today-only print, client timer

**Desk mode**:
Camp-day mode when printing is open for the operating day: Scan at the door first, Pre-registration hidden. Pre-registration mode when printing is closed: Pre-registration first, and no Scan at the door, because the door refuses scans while printing is closed. Search stays in both.
_Avoid_: camp mode, desk state, kiosk mode

**Operating day**:
The single camp day currently selected for door check-in and printing. Automatic mode uses today's IST date when that date is in the schedule; manual enable uses the admin-selected day even if it is not today.
_Avoid_: calendar today, booked day (a patient may have booked a different day)

**Manual entry**:
A desk registration typed instead of scanned, for a patient with no Aadhaar card or a card that will not read. Any desk role starts one from the Manual entry button under the scanner, at Pre-registration and, while the Print window is open, at Scan at the door; no count of Failures and no admin switch stands in front of it. The server refuses one without a reason and records who typed it. The reason is one of No Aadhaar card, Card won't scan, Scanner not working, or Other with a written note; No-card print uses the same list. When the card is in hand but will not read, its last-4 is required. Typed at the door, it is arrived when saved and prints at once. Typed at Pre-registration, it still wants its Lock at the door on the camp day: a card that reads applies the Aadhaar overwrite, and a patient with no readable card gets a No-card print. Self-register has no typed path: without a readable QR the public endpoint refuses with `AADHAAR_QR_REQUIRED` and sends the patient to the desk. No client-supplied flag can mint a registration without a Lock: the desk and the public endpoint both re-decode the payload themselves and take name, age, gender, DOB, last-4 and address from that decode, so a registration that claims a scan and carries no payload is refused with `AADHAAR_QR_REQUIRED`. The server, not the request, decides that an unscanned registration is a Manual entry.
_Avoid_: permission fallback, failure unlock, door manual gate and identity hold (both retired), public reviewed details

**No-card print**:
The desk's recorded decision, with a reason, to print a Manual entry from Pre-registration whose patient has come to the door with no readable Aadhaar. Any desk role takes it. It stands in for the door Lock and stamps Arrival like any print. It never marks the Aadhaar as verified.
_Avoid_: identity check (the retired admin step), override, print anyway

**Patient code**:
The unguessable short code that identifies one registration, printed as a QR on the prescription and shown on the self-registration receipt. Scanning it at the door or at the clinical desk finds the patient; it is not identity evidence, never substitutes for a Lock, and never offers a Reprint.
_Avoid_: patient QR (that is the printed symbol, not the code), reg_no (guessable, and unique only within a camp)

**Scan stall**:
Twenty seconds of live scan with no Detect. Does not count as a Failure.
_Avoid_: scan timeout, camera failure, give up

**Arrival**:
The patient is physically at the camp on a camp day. Stamped by a desk Lock that matches their registration in this camp, by the registration that creates a walk-in, or by Print Prescription on a registration whose Lock was already taken at registration. Registration is a booking; Arrival is presence. Stamped once: a second Lock does not re-stamp it or move the patient again. Arrival is never a step the desk performs on its own — it has no button and no screen of its own. Print Prescription is gated on Arrival, not on Registration, and closes at Doctor seen — reprints included, until a clinical undo. Doctor seen is gated on clinical completion after print, not on Arrival alone. A Manual entry from Pre-registration has no Lock and still needs one at the door, or a No-card print; one typed at the door is arrived when saved. A door Lock stamps Arrival only on the same Person's registration.
_Avoid_: check-in, checking in, presence, attendance, walk-in (a walk-in registers and arrives in one action), door re-scan (a Lock is taken once)

**Household phone**:
The one mobile number stored for a registration and used for its SMS. Ten local digits starting 6–9. Input may carry `+91`, `0`, spaces or dashes; the server strips them and refuses anything else. Screens keep what was typed and send the canonical value. One household phone can self-register at most six patients per camp, and receives at most six registration SMS per IST day.
_Avoid_: contact, mobile of the patient (it is the household's)

**Door walk-in**:
A registration created at the door from the card a Scan at the door has already decoded, needing only the household phone typed. The phone field starts empty for every card. Registers and stamps Arrival in one action, and is a scanned registration, not a Manual entry. Walk-in means a staff registration for the Operating day, not for the IST calendar date.
_Avoid_: rescan, second scan, walk-in registration (also used for the typed path)

**Aadhaar overwrite**:
A Lock that matches exactly one Manual entry updates that registration in place. Name, age, gender, DOB, last-4, and address come from the card. Household phone, camp day, and reg_no stay. The Manual entry mark clears. Not a second registration. A material diff goes through Mismatch review first, at the door and at the registration desk. Never after print or Doctor seen (`ALREADY_PRINTED`).
_Avoid_: merge, bind Aadhaar, rescan button

**Mismatch review**:
The screen shown, at the door or at the registration desk, when a Lock matches a registration whose stored fields differ materially from the card. Card values and stored values side by side; a volunteer or team lead confirms. For a Manual entry, confirming applies the Aadhaar overwrite and stamps Arrival. For a registration that was already scanned from another card, confirming stamps Arrival and replaces nothing. There is no way to keep the stored values and no way to edit the card values. A Trivial diff never reaches this screen.
_Avoid_: conflict resolution, merge screen, override prompt

**Trivial diff**:
A difference between a stored registration and the card that a Lock resolves on its own by applying the Aadhaar overwrite and stamping Arrival with no screen: letter case, spacing and punctuation, initials order in the name, age within one year, any field the registration never had, and the address (never an identity field). Anything else is material and goes to Mismatch review.
_Avoid_: fuzzy match, close enough, auto-merge

**Duplicate in camp**:
A second registration in the same camp for the same person. Blocked when Person, last-4 + name (word order ignored), or name + age + household phone already exists in that camp. There is no override. Last-4 + DOB alone is not a duplicate: year-only card DOBs make it collide for different people. Two scanned cards born apart are different people even with the same name and last-4: different birth years, or two full dates that differ. A year-only DOB against a full date in the same year may be one person, so it still goes to Mismatch review (ADR 0083).
_Avoid_: register anyway, likely duplicate

**Lookalike**:
A registration already in the camp whose name matches a Manual entry being saved, word order ignored, with an age within five years of it. The desk shows every Lookalike with its status — booked, printed or Doctor seen — before the entry saves. The volunteer either opens that registration, where the usual print rules apply, or records that the patient is a different person. Never a block, unlike Duplicate in camp: namesakes are common. It exists so a patient already seen cannot come back as a second, typed registration.
_Avoid_: possible duplicate, fuzzy match, similar patient

**Self-registration**:
A booking the patient's household makes on its own phone, before or on a camp day, with no staff involved. Identity comes only from the Aadhaar QR the server decodes, read by the phone camera or found in an uploaded card photo or e-Aadhaar PDF; the Household phone and the camp day are the only things chosen by hand. A card that cannot be read sends the patient to the desk — there is no typed path. It never stamps Arrival: the patient is still scanned at the door. When every remaining camp day is full it closes and says the patient can still come, because the door registers every walk-in.
_Avoid_: patient login, patient sign-in (patients never sign in), online registration

**Public occupancy**:
Seat counts for the active camp shown to anyone, read from the camp-day counters. Staff sign-in shows the camp-wide headline: total seats across the camp's days and registrations so far, refreshed every 30 seconds. Self-registration shows seats left per camp day in its day choice, lists only today and later days, and offers no full day. No patient details, no per-patient anything.
_Avoid_: live feed, registration ticker, public patient list

**Camp-day capacity**:
Every camp day has a seat limit greater than zero. The limit blocks self-registration and pre-registration, and never blocks a walk-in: a patient who has come to the camp is registered whatever the count says, so a camp day's bookings can exceed its limit (ADR 0042). The limit counts bookings, which Arrival never moves: a patient booked for one camp day who arrives on another is checked in on the day they came without consuming a seat there or releasing one on the day they left. Camp-day capacity is a planning number for footfall. An OT Schedule Day has a seat limit and that limit is a hard block. A Specs collection day has no seats.
_Avoid_: seats_taken (that counter is OT and Spectacles to be made only), unlimited day, turning away a walk-in

**Camp-day board**:
The read-only page a team lead watches during a camp day. Per Registration desk, Arrivals in the last fifteen minutes and the last hour, with a desk that has gone quiet highlighted; the transcription backlog; each Fulfilment line's count today; seats left on the next OT Schedule Day; the next Specs collection day with no seat count; SMS failures; one banner when backups are red. Counts only, refreshes on its own, no actions and no patient names. The clock on the page is the server's.
_Avoid_: dashboard (that is the admin area), live feed, monitor, alerts (the board pushes nothing)

**Transcription backlog**:
Arrived and printed patients who do not yet have a completed prescription. Doctor seen is committed with completion, not before it.
_Avoid_: pending Rx after seen, queue at Doctor's Rx (a physical queue is not the backlog)

**Pending**:
Patients in the active camp who arrived on the Operating day and have Print Prescription but are not yet Doctor seen: the people the camp still owes a consultation today. The same patients the Camp-day board counts as the Transcription backlog. Patients who booked but have not arrived, or arrived but have not printed, are not Pending. The count opens the whole list, longest since print first, with each household phone so a lost patient can be found and called. The list is for finding people and offers no reprint; the clinical desk operator does not see it.
_Avoid_: registered minus seen, waiting (ambiguous with the physical queue)

**Doctor seen**:
A clinical desk operator's attestation that consultation is complete, committed with whole-prescription completion after arrival and print. Drafts, reprints and volunteer mark-seen cannot confer it. Undo completion withdraws it, with a reason, only while no line has been issued; the patient returns to Arrived and can print again.
_Avoid_: arrival, prescription printed, independent mark-seen

**Paper review**:
The issuing operator's explicit comparison of a fulfilment line with the physical paper, tied to the exact committed prescription revision and generation.
_Avoid_: opening the prescription, automatic approval

**Camp records export**:
The single admin-only CSV for a camp, one row per patient including no-shows. Carries identity (name, age, gender, household phone, address, Aadhaar last-4, reg_no), the Manual entry mark and its reason, the registration / arrival / seen timestamps, diagnosis, BP and blood sugar, each eye's power, the medicines prescribed and any not given, the prescribed and issued fixed powers, the status of each of the four Fulfilment lines with blank meaning the patient was never recorded at that desk, and the assigned clinical day and venue for each deferral. It is a wide file of patient data and is not downloadable by a volunteer.
_Avoid_: camp records, clinical audit, the reports (there is exactly one export)

**Clinical operation**:
One clinical write — completing a prescription, undoing it, issuing a line, or recording a correction — identified by the operation id the desk sent. The same id and the same payload replay the saved result. A different payload for that id is refused. The write and its ledger intent commit together, or not at all.
_Avoid_: request id (that is the registration idempotency key), correction id

**SMS intent**:
A `reminder_ledger` row written before any send: queued, then pending while the provider has the message, then sent, failed, uncertain, rejected, paused, abandoned or skipped. A restart sends queued rows older than 30 seconds and failed rows whose retry time has passed. A pending row older than five minutes becomes uncertain and is never sent again.
_Avoid_: outbox message, SMS job

**Ops status**:
The record a background service keeps about its own health, one document per service. For backups: when the last backup and the last off-site copy succeeded, the last error message, and the patient count when the dump started. It never holds patient data.
_Avoid_: logs, audit trail, metrics

**System card**:
The admin overview's one-glance health check: green, amber or red. Backups are red when none has succeeded for six hours (or three backup intervals, if longer), and amber when the last one is more than two intervals old, there is no recent off-site copy, or the last pass reported an error. The backup disk is amber under 20% free and red under 10%. A red System card puts one "Backups failing — tell the admin" banner on the Camp-day board.
_Avoid_: status page, health check (that is the readiness route), monitoring

Every SMS below is Devanagari, per patient, and carries that patient's reg_no. A household number covering three patients receives three messages. Each is its own DLT template.

**SMS venue**:
The place name an SMS gives the patient: the short name the admin set on the camp, OT Schedule Day or Specs collection day, else its full venue. It is 3 to 30 characters, carries no link and no phone number, and is never a placeholder such as NA. A schedule whose SMS venue breaks the rule cannot be saved, and no SMS is submitted with one, because the provider charges for a message that fails.
_Avoid_: short venue, venue_sms (the field, not the idea), SMS address

**Delivery report**:
The provider's final word on one submitted SMS: delivered or failed, with the reason and the credit charged. Acceptance at submission is not delivery, and a failed message is still charged.
_Avoid_: DLR (in UI copy), receipt, acknowledgement

**DLT failure**:
A Delivery report that says the operator refused the message against its DLT template — a variable too long, content that does not match the template or header, or a message the operator rejected. It is a fault in what was sent, not in the patient's phone, so it will repeat for every patient until fixed. An absent, switched-off or DND phone is not a DLT failure.
_Avoid_: bounce, delivery failure (includes phones that are simply off)

**SMS pause**:
A message type that has stopped submitting because of a DLT failure. Only an admin resumes it. Pausing one type never stops the others. A registration confirmation or Token SMS that falls due during a pause is not sent later; it is counted as not sent. The day's reminder batch waits instead, and goes out if the type is resumed before the day ends.
_Avoid_: kill switch, disabled template (a template with no flow is unconfigured, not paused)

**Canary**:
The first reminder of a type in the day's reminder batch. The rest of that type wait for its Delivery report, up to ten minutes, so a DLT failure costs one message instead of the whole batch.
_Avoid_: test SMS (that is the operator's consented check), probe

**Registration confirmation**:
Sent when a registration is created for a future camp day, whether by self-register or by a volunteer. Confirms the patient is registered and states reg_no, camp day date, and venue. A desk registration for today is a walk-in who is already at the camp, so it sends nothing (ADR 0041); self-registration always sends.
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
