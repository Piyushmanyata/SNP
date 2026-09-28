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

The camp rides out an outage on a second network, not on paper (ADR 0094).

**Before the doors open**

1. Place one 4G/5G hotspot for every six desks, on a carrier different from the venue link, plus two spares: 9 hotspots for 37 desks. Put each within a few metres of its desks, away from metal cupboards.
2. On every laptop, save both the venue Wi-Fi and its group's hotspot, and let Windows join the hotspot automatically when the venue link drops.
3. Test failover: unplug the venue router for one minute. Every desk should keep working, and any desk that shows the amber banner **No connection to the server** must clear it within a minute on the hotspot. Plug the router back in.

**When a desk shows "No connection to the server"**

- The banner appears on every staff screen the moment the device cannot reach the server, and clears by itself on the next request that gets an answer. Nothing already saved is lost.
- **The door holds the queue.** Do not scan, register or print until the banner clears.
- **Clinical desks pause.** Keep the paper and the entries on screen; save when the banner clears.
- **No paper registrations.** Nothing is written down for later entry: a later entry loses the card Lock and the Paper check.
- A Paper check that failed: once the banner clears, press **Printed — next patient** again. It is recorded even if the Print window closed in the meantime, the same day, until the doctor sees the patient.
- **Who to tell:** the Team Lead first, then the Admin. If the whole camp is down for more than ten minutes, the Admin announces the pause to the queue.

## SMS pause

If SMS Health shows a type paused, stop that send. An admin resumes it from the SMS tab after the provider reason is fixed. Rejected rows from before the resume can be tried once.

## Lost PIN

The person's Team Lead or an Admin resets the PIN from Team. The new one-time PIN is shown once. Unlock clears a lockout and keeps the current PIN.

## End of day

Admin → Exports → camp records. The file has one row per patient, including people who did not arrive. Keep that file with the day's papers.
