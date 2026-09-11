# ADR 0034: The door is one scan and a print, and Arrival is not a step

**Amends ADR 0033 and ADR 0023.**

## Context

ADR 0033 removed the door re-scan for a patient whose Lock was already on file and gave the desk a "Check in & print" button. That was the right rule with the wrong shape. Three things followed from leaving Arrival visible.

**The word contradicted the glossary.** `CONTEXT.md` has listed `check-in` under _Avoid_ for **Arrival** since the term was written. The desk nevertheless rendered "Check in & print", "Scan their card at the door to check in", "Checked in #101", "Confirm card and check in" and "Register and check in". The one place the vocabulary mattered — the screen a volunteer reads on a camp morning — used the banned word five times.

**Two buttons meant one decision the volunteer should not have to make.** `PatientRow` showed "Print" when `arrived_at` was set and "Check in & print" when it was not. The two do the same thing to the same patient standing in front of the same volunteer; which one appeared depended on a timestamp nobody at the door can see.

**The door had three ways in and a hidden fourth.** The camp-day card carried a "Ready for USB scan" status line driven by an invisible global `keydown` listener, a collapsed `<details>` labelled "Use phone camera or upload photo / PDF" hiding the actual scanner, and an always-visible "Enter details manually" toggle. Below it a separate card offered *two more* inputs: "Scan prescription QR or type Reg #" and "Name search (lost paper/number)". A volunteer with a patient in front of them had five surfaces and no obvious first move. The scanner's viewfinder box — the one affordance that tells a patient where to hold the card — was two layers down.

The invisible listener is the worst of these. It worked, and nothing on screen said so. `useWedgeBurst` buffered keystrokes globally, matched a burst by timing, and `scrubActiveInput` erased any character that leaked into a focused field. When it failed there was nothing to look at; when it succeeded the volunteer could not tell whether the card or luck had done it.

## Decision

- **Arrival keeps its meaning and loses its step.** `arrived_at` still exists, is still stamped once, still moves a patient booked on another day onto the operating day, still feeds the arrivals board, and still gates clinical commit. It is no longer anything a volunteer does: `print` stamps it on the way to the sheet when it is not already set. `/desk/arrive/{id}` is unchanged and still serves the door walk-in.
- **One Print button.** `PatientRow` renders `print-button-{reg_no}` whenever printing is permitted, arrived or not. `checkin-print-button-{reg_no}` is gone.
- **The word "check in" is deleted from the desk.** The banner is `Arrived: #101 — Name`, the badge is `Arrived`, the mismatch control is "Confirm card", the walk-in control is "Register", and an unscanned Manual entry reads "Scan their Aadhaar at the door to print".
- **The door card is the scanner.** `DoorScanCard` renders `AadhaarScanner` directly. The "Ready for USB scan" panel, the `<details>` camera fallback, and the door's `useWedgeBurst` listener are deleted. The three controls the scanner already owns — Scan with camera, Upload photo / PDF, USB / paste — are the whole door. A `door-scan-status` line appears only while a scan is resolving.
- **USB is chosen, not ambient.** The volunteer presses USB / paste and watches the payload arrive in the textarea. This costs one press per patient and buys a door where nothing happens invisibly. `RegisterModal` keeps its own `useWedgeBurst`, unchanged: registration is a seated task at a desk, not a queue at a door.
- **One field finds one patient.** The two forms collapse into `desk-find-input`, placeholder "Registration number or name". All digits or an `snp:` payload goes to `/desk/lookup`; anything else goes to `/patients/search`.
- **One scanner reads both codes.** `AadhaarScanner` takes an `onPatientCode` callback and matches `^snp:[a-z0-9-]+$` before decoding. A patient code goes to `/desk/lookup`; everything else goes to `/aadhaar/decode` as before. The prefix is ours and an Aadhaar Secure QR cannot collide with it.
- **`variant="outline"` gets a real boundary** — `border-2 border-slate-800` instead of `border border-slate-300`. Most door controls use it, and a one-pixel light-grey edge on a white card is not a button in daylight.

## Consequences

A USB scan costs one press it did not cost before. That is the price of the door telling the truth about what it is doing, and it is paid once per patient by a volunteer who is already holding the card.

ADR 0023's "USB imager is the primary desk capture" now holds for registration only. At the door the three capture routes are peers and the volunteer picks one. The imager is not slower than it was; it is no longer automatic.

`doorFailures` and its handlers are deleted from `Desk`. Nothing at the door counts Failures any more — see ADR 0035 — so the counter, `onDoorFailure`, and the no-op `onDoorStall` were dead the moment the gate changed.

Anything outside this repository keying on `checkin-print-button-*`, `wedge-panel`, `camera-fallback`, `desk-lookup-input`, `desk-lookup-button`, `desk-name-search-input`, `desk-name-search-button` or `door-manual-toggle` on the desk page breaks. Inside it, every reference was updated.

The merged find field guesses at intent from the input's shape. A patient whose name is entirely digits would be searched for as a registration number. No such name exists.

## Rejected alternatives

- **Delete `arrived_at` entirely** — the literal reading of "remove check in", and the smallest conceptual model. Rejected because Arrival is load-bearing in three places that have nothing to do with the door: a prescription would print for a patient who never came, a patient booked Tuesday who arrives Wednesday would stay on Tuesday's day, and the team lead's throughput board would have nothing to count.
- **Stamp Arrival at registration** — collapses two events into one and removes the concept cleanly. Rejected because a self-registered patient would be marked present days before they travel.
- **Keep the invisible wedge listener and add a visible box it fills** — zero presses and visible. Rejected because the mode would still change by itself, which is the behaviour a volunteer cannot predict and therefore cannot trust.
- **Keep both the ambient listener and the explicit box** — fastest at the door. Rejected as the current confusing state plus one more control.
- **Force a scan for everyone at the door, removing name and number lookup** — one uniform action. Rejected for ADR 0033's reason, and because it strands a patient whose phone is dead and who left the card at home.
- **Type-ahead search instead of submit-on-Enter** — feels fastest. Rejected: a request per keystroke against the patient list on a camp-morning connection, to save one key.
- **Rename the concept in code as well as on screen (`arrived_at` → something else)** — total consistency. Rejected as a rename of a stored field across six modules and an index, for no reader who is not already reading the glossary.
