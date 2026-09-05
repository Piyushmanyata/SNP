# Clinical monitoring and hospital surgery

## Decision

Operators choose Medicine, Fixed-power specs, Spectacles to be made, or Hospital surgery for their current browser session. The choice starts the prescription form at the relevant fields; it is not a permission or a patient referral. Admin-assigned lines and a separate Doctor's Rx station added handoffs without protecting a clinical invariant, so they are removed from the UI. A fresh session asks the operator again, including accounts with an old line assignment.

## Workflow

1. A volunteer registers the patient, prints the prescription and marks them seen after examination.
2. Any clinical operator looks up the seen patient and copies the doctor's paper prescription. Medicine focuses diagnosis; spectacles focus right-eye power; surgery focuses the operative eye. Other fields remain available.
3. Saving the transcription keeps the patient open and uses the API response directly, avoiding another lookup. Existing prescriptions open as a readable summary. Editing temporarily hides issue controls until the prescription is saved, so an unsaved power change cannot be issued against the old record.
4. Record medicine or spectacles at the selected line, or switch monitoring line to serve the patient's other needs. Both-eye powers remain required for spectacles. After the first item is issued, the prescription locks. At any later line, **Add correction** opens the full current prescription, including diagnosis selections, surgery eye, procedure and notes, and spectacle powers. The operator can complete missing fields or correct transcription in one submission with a mandatory audit reason. Only changed fields are posted, preserving other lines' existing values.
5. Hospital surgery creates a scheduled hospital token. Surgery cannot be marked completed at camp. The hospital is Vimla Ramkrishna Bajaj Eye Hospital, Near Canara Bank, Bilasi Mod, Deoghar 814112 (Jharkhand), phone 9835317006. Camp registration and examination remain at Hansa Garden, Rohini Road in Baghmara, Jasidih, Deoghar 814142.

Monitoring line means the operator's current focus, not an admin assignment or separate doctor queue. The backend remains authoritative for registration, seen status, prescription locking, capacity and fulfilment validation.

## Request safety and navigation

Clinical lookup results are ordered by the latest request. Starting another lookup clears the previous patient's controls, and late responses cannot restore an older patient. Patient switching and line changes are disabled during transcription or fulfilment writes. Correction refreshes use the displayed patient's registration number, not unsent lookup text. The correction form reuses the normal prescription controls, initializes them from the saved transcription, rejects unchanged submissions and blank audit reasons, and disables its fields while saving.

Team Management no longer assigns operator lines. Team leads reach Team Management and Analytics from their registration overview. The shared line helper retains `clearSessionLine` for logout; retired or unknown saved line values return to the picker. `PrescriptionForm` and `SpecsMeasurementsGrid` accept the monitoring field ref; `FulfilmentSection` reports write activity to its parent through `onBusyChange`.

## Verification

Component and public helper tests cover self-selection, retired preferences, each line's autofocus, same-patient transcription and medicine fulfilment, unsaved edits, out-of-order lookups, write controls, powers validation, collection dates, hospital tokens, operator creation and role-specific overview navigation. Browser/device verification is outside this automated check because repository rules prohibit browsers and dev servers.
