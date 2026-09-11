# ADR 0037: The patient code is a short alphanumeric token, and its QR has a quiet zone

## Context

The patient's own QR is the code the camp controls completely — unlike an Aadhaar Secure QR, its content, size and error correction are all ours to choose. It was nevertheless the harder of the two to scan.

`patient_qr` was a UUID4, so the printed payload was `snp:` plus 36 characters: 40 bytes. Lowercase letters and hyphens force QR **byte mode**, which spends 8 bits per character, so the symbol came out at Version 3 — 29×29 modules. It was rendered at `size={68}`, about 18mm on paper: roughly **0.6mm per module**.

Worse, `qrcode.react@4.2.0` defaults `marginSize` to 0 (`lib/index.js:813`, `DEFAULT_MARGIN_SIZE = 0`). The QR specification requires a four-module quiet zone, and the symbol was rendered flush inside a bordered identity box. A reader that cannot find the symbol's edge does not read it slowly; it does not read it at all. Every "the scanner is not picking it up" report at the door is explained by those two facts together.

QR **alphanumeric mode** covers `0-9`, `A-Z`, space and `$%*+-./:` — uppercase only — and packs two characters into 11 bits instead of one into 8. A payload built entirely from that set encodes about twice as densely.

The production database holds test data only and is being wiped as part of this deployment, so no printed sheet and no stored code has to survive the change. That removes the backfill, the dual-resolution window and the new-field-alongside-the-old that a live dataset would have forced.

## Decision

- **`patient_qr` becomes an 8-character code**, not a UUID. `new_patient_code()` draws from **Crockford base32 without `I`, `L`, `O` and `U`** (`0123456789ABCDEFGHJKMNPQRSTVWXYZ`) using `secrets.choice`. 32⁸ ≈ 1.1 × 10¹² — still unguessable, which is the property that matters, because scanning the code is what surfaces a print control.
- **The printed payload is `SNP:` + the code** — uppercase, 12 characters, entirely inside the QR alphanumeric set. That is **Version 1, 21×21**, at error-correction level **Q** (25% recovery; V1-Q holds 16 alphanumeric characters).
- **Both render sites get real geometry**: `size={104}` with `marginSize={4}` on the prescription (≈27mm square, ≈0.95mm modules — a 4× improvement in module area over the old sheet) and `level="Q" marginSize={4}` on the self-registration receipt.
- **No new field, no migration.** `patient_qr` already carries a unique index (`db.py:127`). The generator changes; the storage does not.
- **Parsing is shared and case-insensitive.** `parse_patient_identifier()` in `helpers.py` strips an `snp:`/`SNP:` prefix, strips a `/p/` URL path, and uppercases. `routes_desk._resolve` and `routes_clinical.clinical_lookup` both call it; their two near-identical private copies are deleted. `decode_aadhaar`'s "this is a patient QR" guard is made case-insensitive to match.
- **A collision is left to the unique index.** No retry. At 32⁸ the birthday probability across a 10,000-patient database is about 4.5 × 10⁻⁵, and the index already makes the failure safe rather than silent: the insert raises, the desk re-submits, and `_build_patient_document` mints a fresh code. A second write path inside the registration route's error handler is not worth one avoided error message per twenty thousand camps.

## Consequences

The symbol on the sheet is physically bigger and structurally simpler: 21×21 with a quiet zone instead of 29×29 flush against a border. It should read instantly at arm's length on a phone camera, which is the requirement.

Level Q costs nothing here. V1 holds 16 alphanumeric characters at Q and the payload is 12, so the higher error correction is free — it does not push the symbol to Version 2.

Excluding `I`, `L`, `O` and `U` means a code read aloud over a phone cannot be transcribed into a different valid code. It also means the alphabet is exactly 32 characters, so each character carries exactly 5 bits.

Any sheet printed before this change stops scanning, and any stored UUID stops resolving, because `parse_patient_identifier` uppercases and a UUID is lowercase with hyphens. This is safe **only** because the database is being wiped in the same deployment. A future change to the code format on a live dataset would need the backfill and dual-resolution window this one skips, and must not copy this decision's shortcut.

`new_uuid()` had exactly one caller — this one — so it and its `import uuid` are deleted with it.

`benchmark_dataset.py` seeds `patient_qr` with a UUID5. Those rows are never looked up by code, so they are unaffected, but they no longer resemble production data in that one field.

## Rejected alternatives

- **Keep the UUID and only fix the rendering** — no data change at all, and the quiet zone alone would have fixed most of the failures. Rejected because the payload is the reason the symbol is Version 3; fixing the margin on a 29×29 code at 0.6mm modules leaves the harder half of the problem in place.
- **Encode just the registration number, `SNP:1234`** — no new data, no migration, and the smallest symbol possible. Rejected because `reg_no` is sequential and unique only within a camp: anyone could print `SNP:1235` and present it, and a scanned code is what unlocks a print control.
- **Add a `short_code` field alongside `patient_qr`** — the shape a live dataset would have required, keeping old codes resolving. Rejected as two identifiers for one thing when nothing in the wild needs the old one.
- **Keep honouring old lowercase UUID codes anyway, as insurance** — three lines and harmless. Rejected as speculative: there is nothing to honour, and a resolution path nobody exercises is a path nobody notices breaking.
- **Base58 or full base32 including `I`/`O`** — slightly more entropy per character. Rejected because `O`/`0` and `I`/`1` are exactly the confusions a volunteer reading a code down a phone line makes, and the entropy is already ample.
- **Level H error correction** — maximum damage tolerance for a sheet that gets folded. Rejected because V1-H holds only 10 alphanumeric characters and the payload is 12, so it would push the symbol to Version 2 and shrink the modules to buy resilience the paper does not need.
- **Retrying the insert on a `patient_qr` duplicate key** — guarantees a collision can never surface as an error. Rejected as a defensive layer for a one-in-twenty-thousand-camps event that the unique index already fails safely on.
