# Patient and session safety

The Desk session (`components/desk/deskSession.js`, a pure reducer, and `useDeskSession.js`, its hook) owns the patient on the card. Every new find — a door scan, a Patient code, a typed number or a typed name — starts a new `seq` and clears the banner, error, search rows, found row, scan result and Paper check, so a new patient never inherits the previous patient's paper. Every reply carries the `seq` it started with and is dropped when stale; the hook bumps `seq` on unmount. Confirming identity and registering a walk-in suspend scanning until the mutation finishes.

The Register form (`components/desk/registerForm.js`, a pure reducer with the pure `registrationView`, and `useRegisterForm.js`, its hook) follows the same pattern for New Registration and Manual entry. Its `seq` drops a card read that lands after the operator switched to manual entry, started a new capture, closed the modal or left the page, and `save` reads `canSubmit` from the latest state so two saves in one tick send one request. `useRegisterForm` keeps its effects in this order: context change, open transition, then the `initialPayload` read. A different order drops the card read that opened New Registration as stale.

Every registration id goes through `lib/useRegistrationRequest.js` (ADR 0102): the desk, the Door walk-in, Self-registration and Admin New Camp. The id follows the payload, so a corrected phone after a failed save is a new Registration request. It is cleared by a success or a `REGISTRATION_REQUEST_CONFLICT`, and by `reset()` when the modal opens or a card is read or scanned.

Clinical history responses belong to the lookup that opened them. A new patient lookup or clearing the patient invalidates an outstanding history response.

Prescription route changes hide the previous printable sheet while loading the next patient. The print action must always refer to the patient whose identity appears on the paper.

The print dialog opens only after the server acknowledges the print stamp. A failed request displays a retry message; printing paper without the persisted stamp leaves the clinical prerequisite unsatisfied. Sponsor logo loading remains optional.

Leaving the prescription or changing its patient invalidates pending print callbacks. A delayed stamp response cannot print a different document or change its error state. The Desk button pauses while the print request is pending.

Changing the template camp hides the previous logos until the selected camp loads. Stale fetches and file uploads cannot replace another camp's logos. Editing and camp selection pause during a save so its response cannot overwrite newer changes.

Logout clears local authentication and operator-line selection only after the server confirms success. Network failures keep the operator signed in and show an explicit retry message. Redirecting to login after a failed request would conceal the still-valid server session.

These flows use the existing request sequence and loading-state patterns. Transport cancellation alone cannot prevent an already-completed response from changing patient state.

Regressions live in `deskSession.test.js` and `useDeskSession.test.js` (one event sequence per Desk rule), `registerForm.test.js`, `useRegisterForm.test.js`, `register.test.js` and `useRegistrationRequest.test.js` (the Register form and its request id), `Desk.test.js`, `Clinical.test.js`, `PrintPrescription.test.js`, and `AuthContext.test.js`.

Fatal QR worker errors settle pending detections and terminate the unusable worker. The next frame creates a fresh worker. An undecodable frame returns no QR result and keeps the healthy worker; `wasmDetector.test.js` covers both paths.
