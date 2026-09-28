# Camp day

Each person has their own account and PIN. A Volunteer or Clinical operator uses 4 digits. An Admin or Team Lead uses 6. A new account gets a random one-time PIN, shown once, and must choose their own PIN at first sign-in. There is no shared desk login and no default PIN.

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

## Internet outage

Switch to the second SIM router. If the camp still has no connection, write arrivals on a paper register. When the network returns, enter those patients with **Manual entry**, reason Other, note "network outage". Do not invent a scan.

## SMS pause

If SMS Health shows a type paused, stop that send. An admin resumes it from the SMS tab after the provider reason is fixed. Rejected rows from before the resume can be tried once.

## Lost PIN

The person's Team Lead or an Admin resets the PIN from Team. The new one-time PIN is shown once. Unlock clears a lockout and keeps the current PIN.

## End of day

Admin → Exports → camp records. The file has one row per patient, including people who did not arrive. Keep that file with the day's papers.
