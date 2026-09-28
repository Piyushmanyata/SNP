# ADR 0093: The Print window gates fetching the sheet, not recording paper that exists

## Context

- The Paper check records Print Prescription only after the volunteer confirms the paper is in the patient's hand.
- If that confirmation fails offline for a sheet that printed while the Print window was open, and the window has closed by the retry, the record was refused with `PRINT_WINDOW_CLOSED`.
- The patient then held a prescription the clinical desk refuses, because it was never printed on the record (#89, slice 2; the desk-offline research note).

## Decision

- **The first-print fetch returns a Sheet stamp** alongside the sheet: `<fetched ms>.<HMAC>` over the registration id and fetch time. The key is derived from the existing JWT secret for this one purpose (`security.sign("sheet-stamp", …)`). Nothing is stored, and the fetch still writes nothing and keeps its refusals. The desk's door scan, scan confirm and arrive responses carry it too, because their prescription is the sheet the desk prints.
- **The Paper check sends it back.** "Printed — next patient" posts `{"sheet_stamp": …}`. "Print again" re-fetches, which replaces the stamp.
- **A closed window no longer refuses the record** when all of these hold:
  - the stamp is valid for this registration;
  - it was minted, which the server does only while the window is open;
  - its fetch time is on today's IST date;
  - the patient is arrived, not printed, not Doctor seen and not held for identity.
- Otherwise the existing refusals apply unchanged, in order: `ALREADY_SEEN`, `NOT_ARRIVED`, `PRINT_WINDOW_CLOSED`, `NEEDS_DOOR_SCAN`. A missing or invalid stamp behaves exactly as before, so an old desk tab is safe.
- A printed patient's sheet (a Reprint) carries no stamp.

## Rejected alternatives

- **Storing each fetch.** A write on a read endpoint, a new collection, and a cleanup job, all to say what a signature already says.
- **Dropping the window check on the record.** It would record a print for a sheet fetched after the window closed, which defeats the window.

## Consequences

- A sheet in a patient's hand always has its record once the link returns, until Doctor seen or IST midnight.
- Rotating `JWT_SECRET` invalidates outstanding stamps as well as sessions. That only matters for a sheet whose record is retried across the rotation, after the window closed.
