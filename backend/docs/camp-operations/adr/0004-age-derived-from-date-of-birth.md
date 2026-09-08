# Age is derived from date of birth wherever both are captured

Decision accepted 8 September 2026.

`/register` and `/self-register` already derived age from `dob` when the submitter left age blank, and `/aadhaar/decode` derived it for Secure QR cards. Two places did not. `aadhaar_document.transcription` dropped any age it had once it recognised a full `DOB:` line, keeping only the year-of-birth case. `AadhaarReviewForm` left its required Age field empty, so a card whose date of birth OCR read correctly still could not be confirmed until someone retyped the age by hand.

Age is now derived from the date of birth in both. `transcription` sets `age` alongside `dob`; `AadhaarReviewForm` fills Age from an initial `dob` and recomputes it whenever the reviewer corrects the date, accepting `YYYY-MM-DD` and a bare `YYYY` as the server does.

Age stays editable. OCR misreads dates, and the operator must be able to override rather than fight the field.

Deriving only on the server at registration time was rejected: `/self-register` requires age and date of birth to agree, so a reviewer who typed an age the card contradicted got a 400 at the end of the flow instead of a filled field at the start.

Client and server compute the age independently — the browser in local time, the server in IST. They agree in India, which is where the camps run.
