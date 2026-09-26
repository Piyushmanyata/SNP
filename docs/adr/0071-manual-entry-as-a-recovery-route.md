Renumbered from `backend/docs/camp-operations/adr/0003-manual-entry-as-a-recovery-route.md`.

# Manual Aadhaar entry is a recovery route, not a starting option

Historical decision. Its OCR review route was superseded on 23 September 2026 by [0005](0005-qr-only-aadhaar-capture.md). Staff manual entry remains available after unreadable QR capture. Amended by [0084](0084-manual-entry-is-a-desk-decision.md): the desk offers Manual entry at once, with no count of failed reads.

Decision accepted 8 September 2026. Supersedes the "allow immediate manual registration" clause of [0002](0002-reviewed-aadhaar-capture.md) for the public page, and removes the scanner's own manual-entry control everywhere.

`AadhaarScanner` offered "Enter details manually" alongside the camera, upload and USB buttons. The desk pages already own an equivalent toggle, so the desk rendered the scanner's copy suppressed and its own visible — two controls, one label, two meanings. At the desk the toggle also pauses USB wedge capture, because the desk workflow is manual entry first and a card scan afterwards to correct it.

`AadhaarScanner` no longer owns a manual-entry control. `Desk` keeps its toggle unchanged. `SelfRegister` shows "Enter details manually" only after a read attempt has failed, and reveals the same `AadhaarReviewForm` the OCR path uses. The control stays available afterwards as "Edit these details", prefilled from what was entered, because a patient who spots a typo in the preview would otherwise have to fail another read to correct it. A Secure QR scan hides it: locked card identity is not the patient's to overwrite.

Manual entry offered before any attempt trains patients to skip the card, and every skipped card becomes a desk identity recheck. Requiring one attempt first costs an unreadable-QR patient a few seconds and gains a Secure QR lock whenever the card is readable. Leaving the button visible was rejected: it made the cheapest path the one that produces the least verified data.

`onFailure` becomes the scanner's single "this attempt got nowhere" channel. `useAadhaarDecode` now reports every result that is neither `card` nor `review` — transport errors, oversized files and OCR outages included — instead of only `garbage` and `not-aadhaar`, and `AadhaarScanner` reports camera errors and live-scan stalls the same way. Camera denial is the case that matters: it never reaches the decode hook at all, so without this a patient who blocked the camera and has no photo file to upload would reach the public page's only remaining dead end. Both desk handlers already filtered on outcome, so their three-failure counters are unchanged.

The ordinary unreadable-card path needs none of this: `/aadhaar/extract` returns `outcome: review` with whatever OCR found — an empty suggestion set included — so it already ends at an editable form.
