# ADR 0017: A bounded Secure QR decode on an unauthenticated endpoint

## Context

`POST /api/aadhaar/decode` takes no credentials, by design: patient self-registration decodes a card before anyone is signed in (ADR 0003).

Two costs in that path were unbounded on caller-supplied input.

`_decompress` starts with `int(qr)`. CPython's decimal-to-int conversion is quadratic, and the module raised the interpreter's own guard to 200,000 digits, so a single 200 kB request bought hundreds of milliseconds of CPU on a shared event loop.

It then called `zlib.decompress` with no output limit. A gzip stream of 8 MB of zero bytes is about 2,700 digits — smaller than a real card — and measured at 2 MB of resident output per request. The decompression ratio is the attacker's dial, so a handful of concurrent requests is an out-of-memory, not a slowdown.

A real Secure QR, photo included, runs to roughly 7,000 digits and a few kilobytes inflated. The legitimate input is two orders of magnitude below what the code accepted.

## Decision

- `MAX_SECURE_QR_DIGITS = 16000`, checked before `int()`. The interpreter's own digit guard is set from that constant rather than to a flat 200,000, so one number governs both.
- `MAX_DECOMPRESSED_BYTES = 256 * 1024`, enforced with `zlib.decompressobj().decompress(data, max_length)`. `obj.eof` is the single success condition, which covers both a truncated stream and one that stops at the limit — the two cases the old `zlib.decompress` collapsed into one error.
- `_decompress` is the only gate. `_try_decode_secure_qr` keeps its existing `> 40` digit test and its `except Exception`, so an oversized payload comes back as the ordinary garbage outcome without a second copy of the bound to keep in step.

## Consequences

A card is decoded exactly as before; the shipped fixtures and the live-scan path are unchanged. A payload above the bound returns the ordinary "could not read" outcome rather than consuming the process, so the operator-facing behaviour of a bad scan does not change either.

The limits are constants in `aadhaar.py`, exported and asserted in `backend/tests/test_hardening.py`. If UIDAI grows the payload format, the failure is a decode that stops working, not a silent truncation.

## Rejected alternatives

- Authenticate the endpoint — self-registration has no session to authenticate, so this removes the feature rather than the risk.
- Rate-limit by IP at the proxy — the camp is behind one venue NAT, so the honest traffic shares an address with the abusive traffic. It also leaves the per-request cost unbounded, which is the actual defect.
- Cap only the input length — bounds `int()` but not the expansion ratio; a 7,000-digit payload that inflates to gigabytes stays legal.
