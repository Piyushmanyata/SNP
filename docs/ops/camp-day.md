# Camp day

Each person has their own account and PIN. A Volunteer or Clinical operator uses 4 digits. An Admin or Team Lead uses 6. A new account gets a random one-time PIN, shown once, and must choose their own PIN at first sign-in. There is no shared desk login and no default PIN.

## Before the camp: admin checklist

- **OT Schedule Days:** seats across all OT days total about 10% of expected patients (about 1,500 for 15,000), spread over the OT days.
- **Specs collection days:** sized for about 20% of expected patients (about 3,000).
- **SMS venue names:** each short SMS name is 3–30 characters, with no link or phone number.
- **Sign-ins:** staggered a few desks at a time (see Morning).
- **Schedule-change SMS:** the owner registers the `ot_change` and `specs_change` DLT templates as Service Implicit, with the copy the code sends and the same variable order, adds the two MSG91 flows, and sets `MSG91_TEMPLATE_OT_CHANGE` and `MSG91_TEMPLATE_SPECS_CHANGE` on the VPS. Then send one consented test of each and confirm it arrives. Until then, every patient moved by a Schedule edit is on **Patients to phone**.
- **Hotspots:** bought, charged, and the failover test passed (see Internet outage).

## Kit for 5,000 patients a day

Sized for 5,000 patients a day over 8 hours, with the throughput model the owner confirmed: a door mix of 50% booked, 45% walk-in and 5% no-card; about 40 seconds a patient at the door and 70 seconds at the clinical desk; the peak hour at 1.5 times the average, run at 80% utilisation.

| What | Count |
|---|---|
| Door desks | 14 |
| Clinical desks | 23 |
| Operators | 37, plus about 6 for break relief |
| A4 printers | 16: 14 at the door, 2 spare |
| A6 Token printers | 25: 23 at clinical desks, 2 spare |
| USB imagers | one per door desk, plus 3 spare |
| Laptops | one per desk, plus 2 spare |
| Hotspots on a second carrier | 9: one per six desks, plus 2 spare (see Internet outage) |
| A4 paper | about 11 reams a day |
| A6 Token stock | about 1,500 a day |
| Toner | one spare cartridge per printer model |

Doctors' paper rate may set the real ceiling. If fewer doctors come than planned, close clinical desks to match the doctor count on the day rather than let transcription queue behind paper that is not yet written.

## Spares kit

Keep it in one labelled box at the Team Lead's table: 2 A4 printers, 2 A6 printers, 3 USB imagers, 2 laptops already set up for the camp (Chrome with `--kiosk-printing`, both networks saved), toner for each printer model, and one ream of A4 and one roll of A6 stock.

## Morning

1. Open the admin Overview. The System card should be green: backup, disk, and the reminder heartbeat. SMS Health should show today's sends, not a blank card.
2. On each registration laptop, start Chrome with `--kiosk-printing` and set the A4 printer as the default. Print one test sheet and confirm the whole page is on the paper, including the longest venue.
3. On each clinical laptop, do the same with the A6 Token printer as the default, and print one test Token. A Token prints on the laptop that issues it.
4. Sign each volunteer into their own account, a few desks at a time rather than all at once. The token lasts twelve hours.
5. The door opens when today's camp day is the operating day. Scan one test card, print, and press **Printed — next patient** only when that sheet is in hand.

## During the day

Registration is Scan at the door, then the household phone if there is no booking, then Print, then Paper check. **Print again** prints the same sheet again. **Printer problem** or Escape records nothing. If **Printed — next patient** fails because the connection dropped, press it again when the connection is back: it is recorded even if the print window closed meanwhile, the same day, until the doctor sees the patient.

No card, or a card that will not read: press **Manual entry** under the scanner, pick the reason, type the details and Register. The patient prints straight away. If the desk shows someone already registered with that name, open them if it is the same person. A booked patient who has not arrived prints only after their card is scanned at the door, even if they scanned it when they booked. Finding them by registration number or name shows **Scan the card** and **No-card print**, never Print. Use **No-card print** for a patient with no card; if the card is in hand but will not read, type its last 4 digits.

A door scan of a patient who already printed says so and prints nothing. If they lost the paper, find them by registration number or name and press **Reprint**.

**Pending** at the top of the desk is everyone printed and not yet seen by the doctor, on any camp day. Tap it for the list, longest wait first, with each household phone, to find a patient who has wandered off. A patient who arrived on an earlier camp day shows the day they arrived. The board counts them too, and says how many are from earlier days: send someone to find them first.

A clinical operator copies the paper in the wizard and saves it. That save is what marks the patient Seen. They then issue medicine or schedule Hospital or spectacles at the same desk. A scheduled IOL surgery or spectacles order prints an A6 Token. A Hospital referral or Surgery declined does not.

## A station fails

Nobody needs to call anyone for these. Tell the Team Lead afterwards.

| What failed | What to do |
|---|---|
| **USB imager** | Press **Scan with camera** under Scan at the door and hold the card to the laptop's camera. If that will not read either, register with **Manual entry**, reason **Scanner not working**, and type the card's last 4 digits. Swap in a spare imager when one is free. |
| **A4 printer** | Send the queue to the neighbouring desk. Patients who already arrived are found there by registration number or name, and **Print** prints them. Swap in a spare printer, then print one test sheet before taking patients again. |
| **A6 Token printer** | Carry on issuing: the issue is saved even when the Token does not print. When a printer is back, press **Reprint Token** for each patient issued meanwhile. |
| **Laptop** | Swap in a spare laptop and sign in with your own account. No patient data is kept on a laptop, but your sign-in stays on it for up to twelve hours: if the failed laptop leaves your desk, have your PIN reset from Team, which signs it out. A volunteer asks their own Team Lead; a clinical operator or anyone else asks an Admin. |
| **Desk phone camera** | Use another desk phone. |

## Internet outage

Switch to the second SIM router. If the camp still has no connection, write arrivals on a paper register. When the network returns, enter those patients with **Manual entry**, reason Other, note "network outage". Do not invent a scan.

## SMS pause

If SMS Health shows a type paused, stop that send. An admin resumes it from the SMS tab after the provider reason is fixed. Rejected rows from before the resume can be tried once.

## Lost PIN

The person's Team Lead or an Admin resets the PIN from Team. The new one-time PIN is shown once. Unlock clears a lockout and keeps the current PIN.

## End of day

Admin → Exports → camp records. The file has one row per patient, including people who did not arrive. Keep that file with the day's papers.
