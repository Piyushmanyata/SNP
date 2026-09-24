# ADR 0064: Print in the page, and record the paper in hand

Issue #50, slice S6.

## Context

- The desk left the Desk for `/print/prescription/:id` (a page load), fetched the prescription, and only then fetched the sponsor logos. The logos were base64 images of up to 2 MB each, with no cache, fetched again for every patient. Clicking "Desk" afterwards loaded the page again and refetched everything.
- `POST /desk/print/{id}` stamped `printed_at` **before** `window.print()`. A cancelled dialog or a jammed printer still counted as printed, and Clinical then accepted the patient.
- At 5,000 arrivals a day on 10 desks, each second at the door costs about 1.4 desk-hours.

## Decision

- **Print in the page.** `lib/printJob.printDocument(element, {pageSize})` renders the sheet into one `#print-root` on `<body>`. Its rules hide everything else in print and set `@page { size: A4 | A6; margin: 0 }`. It waits for every image to decode, for at most 3 s, calls `window.print()`, and resolves on `afterprint`. The Desk stays mounted.
- **The door already has the sheet.** `/desk/scan`, `/desk/scan/confirm` and `/desk/arrive` return `prescription` whenever the patient can print, so the door needs no extra request. A found patient, a Reprint and any print after a dismissed Paper check use `GET /desk/print/{id}`, so the server decides again. One rule (`_print_refusal`) decides both the sheet and the stamp: Doctor seen, not arrived, a shut print window, or an identity hold refuses both.
- **`printed_at` means paper in hand.** After `afterprint`, the Paper check asks the volunteer:
  - **Printed — next patient** sends the stamp, clears the card and puts the cursor back in the USB box. A failed stamp shows the error and Retry, and never advances.
  - **Reprint** prints again.
  - **Printer problem** and Escape record nothing.

  A scan or lookup closes an open Paper check and drops a pending one, so the old patient is never stamped. Space does not work on the Paper check buttons, because a USB scan of an XML card types spaces into whichever button has focus. Enter, click and tap still work. One print runs at a time.
- **Logos are small and loaded once.** `lib/logoCache` keeps one fetch per camp. It starts when the Desk loads and refreshes after 10 minutes. A print waits at most 3 s for the fetch, then prints without logos, and the Desk says so. `PUT /templates/logos` refuses more than 6 logos and any non-image, rather than dropping them. Pillow re-encodes each upload to at most 600 px and 150 KB (JPEG quality 85 down to 60; PNG kept when smaller). An already-small PNG or JPEG is kept as sent, so saving again does not degrade it.
- **Tokens use the same path** on A6. The `/print/prescription/:id` and `/print/slip/:id` routes and pages are deleted. `PrescriptionSheet` and `TokenSheet` are plain components under `components/print/`.
- **No migration.** The VPS database is wiped at the release gate, so no stored `printed_at` carries the old meaning.

## Consequences

- One scan, one print and one keystroke per patient. With `--kiosk-printing` there is no print dialog at all (runbook: `docs/ops/camp-day.md`).
- A volunteer who presses Escape out of habit leaves the patient unstamped. The Desk says "Not recorded as printed", and the patient prints again from the card or a lookup.
- The A4 sheet has a fixed 297 mm box. The write area shrinks and the other bands keep their size, so long names, addresses and venues wrap without pushing the Bring list or the sponsors off the page. jsdom cannot measure layout. The real-page height check belongs to the S14 browser suite, and an operator checks real paper at the release gate.

## Rejected alternatives

- **Stamp on `afterprint` with no question.** Browsers fire it for a cancelled dialog too, so it cannot tell paper from an attempt.
- **Keep the separate print page and only add a confirmation.** It keeps the two page loads that dominate the door's time.
- **An iframe for printing.** Same result as `#print-root`, plus cross-document styling and focus problems.
- **Cache logos with HTTP headers.** The response is JSON with embedded images. A module cache controls the refresh interval and works with the `no-store` API.
