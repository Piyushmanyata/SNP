# ADR 0086: The SMS provider is a port with two adapters

## Context

- The SMS module called `msg91` directly: `configured()`, `template_id()` and `send_dlt_sms()`. The reminders route and the SMS status route also asked `msg91` whether it was configured.
- With one adapter the seam was hypothetical. About 13 test files faked the provider by monkeypatching module globals, sometimes the same function under two import paths (`msg91.send_dlt_sms` and `sms.msg91.send_dlt_sms`). A test that patched only one of them could reach the real provider.
- Issue #88 asks for one rule in one module and tests at the interface. #33 kept the MSG91 module and the SMS module separate.

## Decision

- The provider port is `configured()`, `template_id(message_type)` and `send(message_type, mobile, variables)`. `send` returns the provider request id. It raises `Unsent` (retryable; `Throttled` is an `Unsent`) or `Rejected`; any other exception means the outcome is unknown.
- `msg91` stays its own module and is the production adapter, with unchanged behaviour. `send_dlt_sms` is renamed `send`. It keeps its HTTP-level tests, which may fake `http.client.HTTPSConnection` because that is the adapter's own seam.
- `sms.use_provider(adapter)` installs an adapter and returns the one it replaced. `sms` holds `msg91` until something else is installed. `sms.configured()` and `sms.template_id()` are the only way the rest of the backend asks about the provider.
- Tests use the in-memory `Recorder` (`backend/tests/sms_recorder.py`). It records accepted sends and plays scripted outcomes: accept, unsent, throttled, rejected, unknown, or a callable. One autouse fixture, `sms_provider`, installs a fresh recorder for every test. It starts switched off, like a deployment without MSG91, and `switch_on()` or the `recorder()` seed helper turns it on. Tests that exercise the MSG91 adapter install it with `sms.use_provider(msg91)`.

## Consequences

- No test patches `msg91` or `sms` module attributes. A test can never reach MSG91 by accident, because every test starts with the recorder installed.
- A second real vendor would be one more adapter module. None is planned.
- The next slice of #88 (the SMS intent ledger) builds its tests on the recorder's scripted outcomes.

## Rejected alternatives

- **Keep monkeypatching `msg91`.** It costs nothing today, but two import paths must be patched in step, and a missed patch sends a real SMS.
- **Merge `msg91` into `sms`.** Fewer modules, but #33 kept them apart. The HTTP details would then share a file with ledger policy.
- **Install a recorder that is switched on by default.** That matches the port's default, but every test that never asked for SMS would start writing ledger rows. The fixture mirrors production without MSG91 instead.
