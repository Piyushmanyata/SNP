# Patient and session safety

Door scans clear the prior result as soon as a new card is submitted. Only the newest scan may update the patient, error, or loading state. Confirming identity and registering a walk-in suspend scanning until the mutation finishes.

Clinical history responses belong to the lookup that opened them. A new patient lookup or clearing the patient invalidates an outstanding history response.

Prescription route changes hide the previous printable sheet while loading the next patient. The print action must always refer to the patient whose identity appears on the paper.

The print dialog opens only after the server acknowledges the print stamp. A failed request displays a retry message; printing paper without the persisted stamp leaves the clinical prerequisite unsatisfied. Sponsor logo loading remains optional.

Leaving the prescription or changing its patient invalidates pending print callbacks. A delayed stamp response cannot print a different document or change its error state. The Desk button pauses while the print request is pending.

Changing the template camp hides the previous logos until the selected camp loads. Stale fetches and file uploads cannot replace another camp's logos. Editing and camp selection pause during a save so its response cannot overwrite newer changes.

Logout clears local authentication and operator-line selection only after the server confirms success. Network failures keep the operator signed in and show an explicit retry message. Redirecting to login after a failed request would conceal the still-valid server session.

These flows use the existing request sequence and loading-state patterns. Transport cancellation alone cannot prevent an already-completed response from changing patient state.

Regressions live in `Desk.test.js`, `Clinical.test.js`, `PrintPrescription.test.js`, and `AuthContext.test.js`.

Fatal QR worker errors settle pending detections and terminate the unusable worker. The next frame creates a fresh worker. An undecodable frame returns no QR result and keeps the healthy worker; `wasmDetector.test.js` covers both paths.
