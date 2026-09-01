# SNP Camps

Field medical camp operations: desk registration, presence, clinical fulfilment.

## Language

**Aadhaar Secure QR**:
The dense UIDAI Secure QR printed on a PVC Aadhaar card. This is the primary artefact the desk camera must read.
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

**Desk camera**:
The volunteer-held phone camera at the registration desk. Primary capture device for Aadhaar Secure QR.
_Avoid_: patient camera, self-register camera

**Desk phone**:
A volunteer's own Android or iPhone used at the registration desk. Both platforms must read Aadhaar Secure QR.
_Avoid_: camp-issued device, patient phone

**Live scan**:
Reading Aadhaar Secure QR through the desk-camera viewfinder.
_Avoid_: scan (also used for photo upload and USB wedge)

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

**USB wedge**:
A hardware scanner that types the QR payload into the page.
_Avoid_: USB scanner as a synonym for desk camera

**OT Schedule Day**:
An admin-created day, unique per camp and date, on which deferred OT patients are assigned. It has a venue and a finite seat limit.
_Avoid_: OT slot, surgery day, OT appointment

**Spectacles to be made**:
The clinical fulfilment outcome for spectacles that cannot be issued at camp and must be collected later. Deferral assigns the patient to a Specs collection day.
_Avoid_: to-be specs, TBD specs, specs order, glasses order

**Specs collection day**:
An admin-created day, unique per camp and date, on which patients deferred for Spectacles to be made are assigned. Same shape as an OT Schedule Day: venue and finite seat limit.
_Avoid_: specs slot, collection appointment, specs schedule

**Token**:
The paper printed when OT or Spectacles to be made is deferred. Hindi and English labels; name and venue as stored. The patient brings it to the OT Schedule Day or Specs collection day. A new deferral of the same type cancels the previous Token.
_Avoid_: slip, deferred slip, thermal slip, queue ticket, final token

**Print window**:
Admin-declared open/closed state on a camp day. Open: printing is enabled. Closed: printing is disabled. Not derived from the calendar.
_Avoid_: IST print gate, today-only print

**Manual entry**:
A desk registration typed after two Failures. Marked on the registration. Not an admin approval and not an audited reason. Self-register has no typed path.
_Avoid_: manual exception, manual window, manual audit

**Aadhaar overwrite**:
A Lock from New Registration that matches exactly one Manual entry updates that registration in place. Name, age, gender, DOB, last-4, and address come from the card. Household phone, camp day, and reg_no stay. The Manual entry mark clears. Not a second registration.
_Avoid_: merge, bind Aadhaar, rescan button

**Duplicate in camp**:
A second registration in the same camp for the same person. Blocked when Person, last-4+name, last-4+DOB, or name+age+household phone already exists in that camp. There is no override.
_Avoid_: register anyway, likely duplicate

**Public occupancy**:
Counts on the unauthenticated login page for the active camp: per camp day, registered, seat limit, remaining. No patient details.
_Avoid_: live feed, registration ticker, public patient list

**Camp-day capacity**:
When a camp day's seat limit is greater than zero, that day refuses a new registration once the registered count reaches the limit. Limit zero is unlimited.
_Avoid_: seats_taken (that counter is OT and Spectacles to be made only)

**Camp reminder**:
The Devanagari SMS sent the calendar day before a camp day, one per unique household number among patients registered for that day. Date and venue only; no patient names.
_Avoid_: camp SMS, registration reminder

**OT reminder**:
The Devanagari SMS sent the calendar day before an OT Schedule Day, one per unique household number among patients with an OT Token for that day. Date and venue only; no patient names.
_Avoid_: OT SMS, surgery SMS, follow-up reminder

**Specs reminder**:
The Devanagari SMS sent the calendar day before a Specs collection day, one per unique household number among patients with a Spectacles-to-be-made Token for that day. Date and venue only; no patient names.
_Avoid_: specs SMS, glasses SMS, follow-up reminder
