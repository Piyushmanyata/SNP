# ADR 0102: A registration request id belongs to one payload

**Carries ADR 0088, which binds a Clinical operation's id to its payload, to registration on the desk side. Builds on ADR 0063 and ADR 0090.**

## Context

- Four screens sent an idempotency id, each with a private lifecycle:
  - the registration desk kept `reqId` inside `RegisterModal`
  - the Door walk-in kept `walkIn: {key, reqId}` in the Desk session, keyed on the scanned card alone
  - Self-registration kept `reqId` in component state, and stayed on a conflicting id until the card was scanned again
  - the Admin New Camp form kept `setupId` in a ref
- None of them renewed the id when the operator edited the payload. The server replays the row already saved under an id, and `_replay_registration` compares only the camp, the booked day, the normalised name and, for a scanned card, the last-4 and date of birth. A lost reply followed by a corrected phone therefore showed "Registered" while the SMS went to the old number and the correction was dropped.
- `RegisterModal` held twelve `useState` calls, three refs, the stale-scan counter, the submit rules and the error-code routing. Its logic could only be tested by mounting the whole Desk.
- Issue #110 (slice 5) asks for desk registration behind a reducer seam, with one request hook.

## Decision

- `frontend/src/lib/useRegistrationRequest.js` is the one hook, `send(payload, post)` and `reset()`. The same payload sends the same id until success, a `REGISTRATION_REQUEST_CONFLICT` or `reset()`. A different payload mints a new id, and going back to an old payload does not bring the old id back. A late reply clears the id only if it is still the id that call used. Errors reach the caller unchanged.
- The registration desk, the Door walk-in and Self-registration send through it. The key is the person and booking being registered (`registrationBody`). Mismatch review and Different person answer server prompts about the same registration, so they stay out of the key and keep the id of the attempt that raised them.
- `reset()` is called only where the payload can stay equal but the registration is new: the modal opens, a card is read or scanned, Self-registration's Register another or new capture, and Admin New Camp opening. A success already clears the id, so nobody resets after one.
- `RegisterModal`'s state moves behind the same seam as the Desk session:
  - `registerForm.js` is a pure reducer. Its `seq` replaces the stale-scan counter. Age and last-4 are stripped to digits there.
  - `registrationView` holds the submit rules: the effective camp day (today's, else the first, so days that arrive after the modal opened need no event), `canSubmit`, `dirty` and `locked`.
  - `useRegisterForm.js` is the hook. Its `save` reads `canSubmit` from the latest state, so a fast Enter and click send one request.
  - `registrationFailure` in `register.js` routes an error to a Mismatch review, the Lookalikes or a message.
- The Door walk-in's `walkIn` state, `NO_WALK_IN` and the ids on `walkInStarted` and `walkInFailed` are deleted.
- **Admin New Camp uses the hook with a constant key on purpose.** The server already compares the whole camp body per `setup_request_id` and answers `CAMP_REQUEST_CONFLICT` ("close this form and edit the camp"). A payload-keyed id would mint a second id after an edit and create a second camp. The hook renews an id only on `REGISTRATION_REQUEST_CONFLICT`, never on `CAMP_REQUEST_CONFLICT`.
- **Deliberate fix:** a corrected phone, age, name, gender, address, last-4, reason or day after a failed save now sends a new id. The server then answers honestly: a scanned card gets `DUPLICATE_IN_CAMP`, a typed entry gets `LOOKALIKES`. An unchanged retry still replays.

## Consequences

- A fifth registration surface calls `send` and gets the same rule. Its tests are the hook's, not a copy.
- The safe `REGISTRATION_REQUEST_CONFLICT` path is no longer taken on an edit. The correction is not applied, but the volunteer is told the patient exists (scanned) or shown the Lookalike (typed). A volunteer can press Different person and save a second typed row, the choice Lookalike already offers.
- The Door walk-in's id now also changes when the door phone, the card fields or the day change. It used to follow the scanned card alone.
- Self-registration now renews its id after `REGISTRATION_REQUEST_CONFLICT` and after a seat refusal that moves the chosen day, where it used to keep the old id. The first call did not save in either case.
- `useClinicalCommand` still carries its own copy of the same rule ("new id when the payload changes, clear on success and on a reload code"). Folding it onto `useRegistrationRequest` means classifying thrown failures in ADR 0088 territory, so it is a follow-up, not part of this slice.
- Tests move out of the Desk page test into `registerForm.test.js` (rules, no DOM), `useRegisterForm.test.js` (id lifecycle, stale reads, effect order, double submit), `register.test.js` and `useRegistrationRequest.test.js`. `Desk.test.js` keeps the wiring and rendering.
- No backend, SMS, printed output, index or wire change apart from the value of `registration_request_id`.

## Rejected alternatives

- **Make the server strict:** hash the whole registration payload per id, as `clinical_operation` does, and answer `REGISTRATION_REQUEST_CONFLICT` when the same id arrives with a different phone. It is a backend change outside this slice, and it turns a lost reply followed by a corrected phone into a dead end ("Saved earlier. Search for the patient."). The desk would then have to mint a new id anyway. Minting per payload on the client gets the honest answer from the existing Lock rules with no server change.
- **Patch only `RegisterModal`:** renew the id when a field is edited and leave the walk-in key and Self-registration's `reqId`. It keeps three private id lifecycles and fixes one of them.
- **Put `reviewConfirmedId` and `differentPerson` in the key.** A confirmed overwrite would then start a fresh request instead of retrying the attempt the server asked about, and the desk would lose the replay after a lost reply.
