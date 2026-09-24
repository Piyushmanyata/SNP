# Camp-day accounts

A **Desk account** is an ordinary `volunteer` or `clinical_desk_operator` staff account. It is created by an admin, named for the desk, and signed in once in the morning by a team lead. Volunteers never receive a password. Attribution of work is the **On-desk volunteer** pick from the **Volunteer roster**, not the Desk account login.

## Before camp

Create these staff accounts in Admin → Staff:

- Ten **Registration desks**: `Desk 1` … `Desk 10`, role `volunteer`.
- Doctor's Rx and each **Fulfilment line**: `Rx 1` … and the line accounts, role `clinical_desk_operator`, with the matching line set.

Paste the volunteer names into Admin → Roster (one name per line) for the active camp.

## Morning of camp

Team leads sign each laptop in as its Desk account. The access token lasts twelve hours, so a laptop signed in at 07:00 needs a fresh login at 19:00.

When a volunteer sits down they pick their name. Hand over clears the pick for the next person. Team leads and admins keep personal accounts and never see the picker.

## Desk laptops and printers

Each desk prints in the page and never leaves the Desk screen. To remove the print dialog, start Chrome with `--kiosk-printing` and set the desk's A4 printer as the default. The browser still reports when printing ends, so the Paper check opens after each sheet.

After every sheet, the volunteer checks the paper in hand. **Printed — next patient** (Enter) records it. **Reprint** prints again. **Printer problem** or Escape records nothing, so the patient can be printed again once the printer works.

## Moving an OT or Specs day

Edit the day in Admin → OT & Specs; never add a second day on the same date. A date or venue change replaces every patient's Token on that day and sends each patient one SMS saying their old paper is void.

- Check **Patients to phone** at the top of that tab. It lists everyone whose SMS was not sent, failed, or is paused. Phone each one with the new date and venue, then press **Phoned — done**.
- Until MSG91 approves the two change templates (`MSG91_TEMPLATE_OT_CHANGE`, `MSG91_TEMPLATE_SPECS_CHANGE`), every moved patient appears on that list.
- When a patient comes to a station with an old Token, the station says "Print this new Token and take back the old one". A reprint of the old Token is stamped "Replaced — not valid".

