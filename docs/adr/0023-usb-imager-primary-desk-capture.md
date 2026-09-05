# ADR 0023: USB 2D imager is the primary desk capture

Amends ADR 0003, 0004, 0005 and 0017. Those ADRs made the desk phone camera the primary route for Aadhaar Secure QR and tuned Live scan for it. Live scan stays, as the fallback. Decode stays on the server and is unchanged.

## Context

The first camp targets five thousand patients a day for three days across ten Registration desks, about one patient a minute per desk for eight hours. Two desks share one A4 printer. No camp has run yet; the venue network has not been measured.

Live scan on a volunteer's own phone was chosen before those numbers existed. Field trials of dense Secure QR on cheap phones have been unreliable enough that the trust does not want to stake a desk's throughput on it. A phone desk also prints through the mobile print dialog to a shared printer, fifteen to thirty seconds a patient that the one-minute budget cannot afford.

A USB 2D imager on a laptop reads the card in under a second, types the payload as keystrokes, and needs no camera permission, no HTTPS-on-LAN, no focus ladder and no torch. The same laptop drives the printer over USB, so the print dialog is a click, not a phone spool.

## Decision

- A Registration desk is a laptop, a USB 2D imager and a seat. Ten per camp day, pairs sharing a printer.
- The imager is the primary capture. On a camp day the desk listens for the wedge burst with no mode button and no textarea to click; the terminator fires Decode.
- The desk phone camera, photo upload and Manual entry remain the fallback ladder, reached when the imager cannot read a card.
- Two hardware checks gate the purchase: the chosen imager Locks a real PVC Aadhaar Secure QR, and a full payload types into a text field on the desk laptop in under five seconds without dropped characters.

## Consequences

Desk throughput no longer depends on a volunteer's phone camera, its browser, or its lighting. The Live scan work in ADRs 0003 to 0005 becomes fallback code that must keep working but is no longer the thing to optimise for the desk. Self-register and the door still use the phone camera. The trust buys and carries ten imagers and ten laptops. A wedge scanner sends the payload as keystrokes, so the desk must accept a burst of a few thousand digits into whatever has focus without a form swallowing it.

## Rejected alternatives

- Keep the phone camera primary and improve Live scan on low-end phones — still the plan for the fallback and for self-register, but a desk that needs one Lock a minute for eight hours cannot wait on it being proven.
- USB imager on the phone by OTG — saves the laptop, keeps the phone print dialog, which is the other half of the per-patient minute.
- Serial or HID-POS scanner over WebSerial instead of a keyboard wedge — faster and no focus problem, but Chrome-only and a different device class; revisit if the five-second typing check fails.
