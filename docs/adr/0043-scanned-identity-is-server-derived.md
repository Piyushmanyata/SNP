# ADR 0043: A scanned identity is whatever the server decoded, on both registration paths

## Context

`POST /api/self-register` re-decoded `qr_payload` on the server and overwrote every identity field from the result, because the caller is an unauthenticated patient phone.

`POST /api/register` did not. It took `aadhaar_scanned` from the request body and stored `full_name`, `age`, `gender`, `dob`, `aadhaar_last4` and `address` exactly as sent. The desk client is staff-authenticated, but the flag is what decides whether a row is identity-backed: it clears `identity_recheck_required`, it is what `_resolve_registration_conflict` uses to overwrite a Manual entry in place (ADR 0011), and it is what lets the sheet print without an admin identity check (ADR 0033). Any signed-in device could set it with no card in the room, and could pair a real last-4 with a different name.

The legacy XML QR reader widened the same hole. `_parse_xml_attributes` fell back to a regex over `key="value"` pairs when the XML would not parse, and no element name, Aadhaar number shape or date was checked. A synthetic `<anything name="Not Aadhaar" .../>`, a truncated card, a UID of five digits or a date of birth in 2099 all decoded as a card.

## Decision

- One helper, `_apply_scanned_identity`, is the only way a registration becomes scanned. Both routes call it. It requires `qr_payload`, decodes it here, and assigns the protected fields from the decode; a request that claims a scan and brings no readable payload is a 400 `AADHAAR_QR_REQUIRED`. Client-sent identity fields are overwritten, not merged, and `manual_entry` / `manual_exception` are cleared by the same assignment.
- The typed path is untouched. A request that does not claim a scan still goes through `_validate_manual_identity` and is still a Manual entry with `identity_recheck_required`.
- `parse_xml_qr` accepts only a `PrintLetterBarcodeData` root, only well-formed XML, a `uid` of exactly 4 or 12 digits, and a date of birth that parses to an age of 0 to 130. The regex attribute fallback is gone. The one retry that escapes a bare `&` stays: real cards carry unescaped ampersands in names and addresses, and it re-parses as XML rather than guessing at attributes.
- Secure QR gains the same upper age bound; it already rejected a missing or future date.
- `routes_desk._resolve` bounds a numeric lookup at 12 digits before `int()`, so a long digit string is a 400 rather than a BSON encoding error surfacing as a 500.

Nothing here verifies the UIDAI signature. Decoding is still a read of what the card carries, as in ADR 0003 and ADR 0017.

## Consequences

The desk client must send the raw payload alongside `aadhaar_scanned`. `frontend/src/pages/Desk.js` does not yet: both `/register` callers post the decoded form fields only, so the scanned desk registration and the door walk-in return `AADHAAR_QR_REQUIRED` until the payload is threaded from `useWedgeBurst`/`onScanned` into the request. Until that is done the desk can register only manually.

Cards whose XML never had a date of birth, or whose `uid` attribute holds something other than the last four or the full number, now read as garbage instead of a card. That is a narrowing of what the fallback reader accepted, not of what UIDAI prints.

## Rejected alternatives

- Trust the desk client because it is authenticated — authentication says who is at the keyboard, not that a card was read. The flag would remain a typed claim, and the Manual-entry overwrite would remain reachable without a card.
- Validate the client's fields against the decode and reject a mismatch — two sources of truth, and a 409 for every harmless spacing difference the desk already resolves. Deriving leaves one source.
- Keep the regex fallback for unparseable XML — it is what lets an arbitrary attacker-shaped string become identity, and a card that will not parse as XML is not a card we can read honestly.
