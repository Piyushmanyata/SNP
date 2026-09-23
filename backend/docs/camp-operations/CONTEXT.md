# Camp operations

Language for the camp workflow design interview.

## Language

**Camp**:
An organised medical event that can span multiple operating dates.
_Avoid_: single-day event

**SMS venue**:
A short, recognisable camp location, at most 40 characters, used in DLT messages while the full venue remains on camp records.
_Avoid_: truncated address

**Camp day**:
One scheduled operating date belonging to a Camp, covering the whole calendar day in Indian Standard Time.
_Avoid_: separate camp

**Registration credit**:
The original registrar's attribution for registering a patient in a Camp, belonging to the registrar's team at registration even if the registrar later changes teams.
_Avoid_: door-scan credit

**Prize point**:
One point earned by the original registrar when their registered patient is confirmed Doctor seen, at most once per patient per Camp.
_Avoid_: arrival point, repeat-visit point

**Doctor seen**:
A clinical desk operator's attestation that a patient's consultation has taken place, committed with completion of the whole paper-prescription transcription after arrival and printing. Draft transcription does not confer Doctor seen.
_Avoid_: arrival, prescription printed

**Manual fallback**:
Patient detail entry after three unsuccessful scan sessions, or an eligible recorded hardware failure, with identity rechecking required at camp. Denied camera permission requires enablement guidance and retry, not manual fallback.
_Avoid_: verified Aadhaar

**Clinical visit**:
The patient's single clinical attendance record for a Camp; subsequent scans reopen it rather than create another visit or reset completed care.
_Avoid_: daily visit

**Doctor Rx**:
An optional transcription position beside a doctor, operated by a clinical desk operator; it records the paper prescription for reuse at fulfilment desks.
_Avoid_: new clinical role, compulsory queue

**Alternative identity check**:
An admin-assisted camp-day identity check, with a recorded reason, for a patient whose Aadhaar is unavailable or unreadable; it permits onward camp flow without claiming verified Aadhaar.
_Avoid_: Aadhaar verification

**Printing availability**:
Whether prescription printing is enabled for a camp day. Volunteers see door scanning when it is enabled, and pre-registration when it is disabled; patient search remains available in both cases.
_Avoid_: camp paused

**Walk-in registration**:
Registration and check-in of a previously unregistered patient within door scanning, with registration credit belonging to the signed-in staff registrar.
_Avoid_: arrival-only credit

**Prescription completion**:
The clinical operator's explicit confirmation that the whole paper prescription has been transcribed, committing the prescription and Doctor seen together. It does not itself issue any treatment.
_Avoid_: draft save, medicine issue

**Paper review**:
A clinical operator's explicit comparison of a fulfilment line's instructions with the physical prescription, tied to the completed prescription revision being used for that issue.
_Avoid_: opening the prescription, automatic approval

**Completion undo**:
A reasoned clinical-operator reversal before any issue or token allocation, retaining history and returning the prescription to draft while removing current Doctor seen and prize eligibility.
_Avoid_: deleting a visit, erasing an issue
