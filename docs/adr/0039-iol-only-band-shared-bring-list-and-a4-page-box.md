# ADR 0039: An IOL-only bilingual band, one Bring list, and a declared A4 page box

**Amends ADR 0032 and ADR 0036.**

## Context

The patient keeps two papers that disagree. ADR 0032's English-only disclaimer on the prescription says to bring an Aadhaar card, ration card and mobile phone. The surgery Token says prescription, Token, Aadhaar card, voter ID and mobile number. Neither says the trust arranges only cataract (IOL) operations, so a patient referred for another condition can expect the trust to operate.

The prescription also prints across two pages on some printers. ADR 0036 kept the sheet inside 297mm by construction, but it never declared the paper size. A printer defaulting to Letter, together with the screen backdrop's padding and minimum height still applying in print, pushes the sheet onto a second page.

## Decision

- **One Bring list**: the prescription, the Token, Aadhaar card, ration card and mobile phone. Voter ID is dropped. It is identical on the prescription and the IOL surgery Token.
- The prescription's English-only band is replaced by one bordered band of two lines, Hindi then English:
  - "केवल मोतियाबिंद (IOL) ऑपरेशन की व्यवस्था की जाती है। ऑपरेशन के दिन लाएँ: यह पर्चा, टोकन, आधार कार्ड, राशन कार्ड, मोबाइल फ़ोन।"
  - "Only cataract (IOL) operations are arranged. On the day of the operation bring: this prescription, token, Aadhaar card, ration card, mobile phone."
- The Token is titled "मोतियाबिंद (IOL) ऑपरेशन / IOL Surgery", names the eye, prints BP and blood sugar only when recorded, keeps the help phone, and carries the Bring list in Hindi.
- The page box is declared: print rules set `@page { size: A4; margin: 0 }`, the screen backdrop's padding and minimum height do not apply in print, and the sheet is fixed at 210 × 297mm with overflow hidden. The write area stays the flexible band that absorbs spare height, so the new band takes its height from the doctor's slack, not from the page count.
- Every other band is unchanged: masthead, services band, declaration and the original misspellings. The reference-form snapshot is regenerated deliberately.

## Consequences

The two papers can no longer disagree about what to bring, and the one sentence a Hindi reader most needs on the prescription is now in Hindi. ADR 0032's "translate it if the trust wants it" is taken up for this band only; the rest of the form stays English.

Declaring A4 means a Letter-default printer prints one A4 sheet instead of re-flowing onto two. `overflow: hidden` turns an accidental overflow into clipped content rather than a second page, so a physical print on the camp printer remains the check that nothing is clipped.

## Rejected alternatives

- **Keep the English-only band and fix only the documents list** — smallest change. Rejected because the IOL-only notice is what stops a referred patient expecting an operation, and it has to be readable by the patient.
- **Translate the whole prescription** — most inclusive. Rejected as out of scope and the likeliest to break the one-page fit.
- **Leave the page size to the print dialog** — no CSS. Rejected because volunteers print from whatever the printer defaults to, which is how the two-page print happened.
