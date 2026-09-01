# Desk scan-first registration, public occupancy, and SNP Rx header

## Problem Statement

Opening New Registration shows the scanner, the full patient form, and a volunteer checkbox that pretends two scans failed. People type patients without scanning, duplicates slip through “Register anyway”, and there is no later path to put a real Aadhaar Lock onto that same `reg_no`.

Printing still secretly requires the camp day’s calendar date to be today, even when the admin has opened the Print window. The login page tells staff and patients nothing about how full each camp day is. The default prescription has no Sikar Nagarik Parishad / Sikar Zilla Welfare Trust header — the paper in `EYE CLINIC.jpg` is what the camp actually uses.

## Solution

The desk popup is capture-first. Live scan, photo upload, and USB wedge stay. After two Failures the typed form appears and the row is a Manual entry — no audited reason, no admin. On camp day that is still allowed. A later Lock in the same popup that matches exactly one Manual entry is an Aadhaar overwrite of that `reg_no`, not a second registration.

Duplicate in camp is hard: no “Register anyway”. Public occupancy on the login page shows counts for the active camp only. Camp-day capacity blocks a new registration when the limit is greater than zero and the day is full. Print window is admin Open/Close only — no calendar check. The default Rx template takes header, logos, address, and Rupa footer from the sample; the editor and clinical blocks stay.

## User Stories

1. As a volunteer, I want New Registration to open on the Aadhaar capture UI only, so that I am not invited to type a patient before trying the card.
2. As a volunteer, I want live scan, photo upload, and USB wedge still on that first screen, so that I can use whichever capture mode works on this desk phone.
3. As a volunteer, I want the typed form hidden until two Failures, so that Manual entry is the exception, not the default.
4. As a volunteer, I want pointing the camera at empty space not to count as a Failure, so that the form does not appear after a few seconds of searching.
5. As a volunteer, I want each Decode of `garbage` or `not-aadhaar` from live scan, photo upload, or USB wedge to count as one Failure, so that a real bad card or unreadable QR unlocks typing.
6. As a volunteer, I want closing the popup to reset the Failure count, so that a new attempt starts clean.
7. As a volunteer, I want the scanner to stay after the typed form appears, so that a successful Lock in the same session still fills the card instead of staying Manual entry.
8. As a volunteer, I want to type name, age, gender, address, household phone, and camp day after two Failures, so that the patient can still be registered when capture fails.
9. As a volunteer, I want that row marked as Manual entry with no reason field, so that I am not doing an audit.
10. As a volunteer, I want Manual entry allowed on camp day, so that a card that will not Lock does not stop the queue.
11. As a patient on self-register, I want to still be required to Lock, so that the public page cannot mint typed junk rows.
12. As a volunteer, I want household phone still required on Manual entry, so that the household can be reached.
13. As a volunteer, I want age still required when the row is not scanned, so that the desk record is usable.
14. As a volunteer, I want a Duplicate in camp to refuse a new `reg_no` and show the existing one, so that I print for them instead of creating a second person.
15. As a volunteer, I want no “Register anyway” action, so that caution is not optional.
16. As a volunteer, I want the same Person already in this camp to block a new registration, so that one Aadhaar cannot own two `reg_no`s.
17. As a volunteer, I want last-4 + normalized name already in this camp to block, so that a second scan of the same card cannot double-register.
18. As a volunteer, I want last-4 + date of birth already in this camp to block, so that a spelling drift between Manual entry and later Lock still collides.
19. As a volunteer, I want normalized name + age + household phone already in this camp to block, so that two Manual entries of the same person cannot both land.
20. As a volunteer, I do not want household phone alone to block, so that siblings in one household can all register.
21. As a volunteer, I do not want name + age without phone to hard-block, so that two unrelated people with a common name and age are not stuck.
22. As a volunteer, I want a Lock that matches exactly one Manual entry to update that `reg_no` in place, so that the patient keeps their number and the card becomes the source of identity.
23. As a volunteer, I want that Aadhaar overwrite to write name, age, gender, DOB, last-4, and address from the card, so that typed mistakes are replaced.
24. As a volunteer, I want household phone, camp day, and `reg_no` to stay on Aadhaar overwrite, so that the household number and the paper identity do not jump.
25. As a volunteer, I want the Manual entry mark cleared after Aadhaar overwrite, so that the row is a scanned registration.
26. As a volunteer, I want Aadhaar overwrite to attach the Person and set scanned, so that later duplicate checks use the Aadhaar key.
27. As a volunteer, I want a Lock that matches an already-scanned Person to 409 with that `reg_no`, so that I do not overwrite the wrong row.
28. As a volunteer, I want a Lock that matches two Manual entries to refuse and list them, so that the desk does not guess.
29. As a volunteer, I want a Lock that matches none to create a new registration, so that a first-time scan still works.
30. As a volunteer, I want Aadhaar overwrite not to consume a second camp-day seat, so that a rescan does not look like a new patient on the board.
31. As a volunteer, I want Aadhaar overwrite not to auto-reprint, so that print remains a deliberate desk action.
32. As a volunteer, I want New Registration with a full camp day (limit greater than zero, registered at limit) to 409, so that we do not overbook that day.
33. As a volunteer, I want camp-day limit zero to stay unlimited, so that days without a cap keep working as they do on the admin day row.
34. As a patient on self-register, I want the same Camp-day capacity rule, so that the public path cannot fill a day past the board.
35. As anyone on the login page, I want Public occupancy under the patient self-registration link, so that I can see how full the live camp is without signing in.
36. As anyone on the login page, I want one row per camp day of the active camp: registered, seat limit, remaining, so that the numbers are unambiguous.
37. As anyone on the login page, I want remaining to be limit minus registered, or unlimited when limit is zero, so that the board matches Camp-day capacity.
38. As anyone on the login page, I do not want names, last-4, or phone on that board, so that the unauthenticated page stays free of PHI.
39. As anyone on the login page, I want those counts to refresh on a short poll, so that the board moves as the desk registers.
40. As anyone on the login page, I do not want inactive camps listed, so that only the live event is public.
41. As an admin, I want Print window Open/Close on the camp-day row exactly as today, so that I do not learn a new control.
42. As an admin, I want printing to work whenever Print window is open, regardless of calendar date, so that a Docker or field clock does not block paper.
43. As an admin, I want printing to 409 whenever Print window is closed, so that closed means closed.
44. As a volunteer, I want that print 409 to keep the existing closed-window code, so that the desk message stays familiar.
45. As an admin, I want the default Rx template to show Sikar Nagarik Parishad and Sikar Zilla Welfare Trust names in English and Hindi, so that the paper matches the sample.
46. As an admin, I want both organisation logos on that default header, so that the paper matches the sample.
47. As an admin, I want the Sikar Bhawan address, phone, and email on the default subtitle, so that the paper matches the sample.
48. As an admin, I want Rupa Foundation as the default footer sponsor, so that the paper matches the sample.
49. As an admin, I want the Rx Template tab to still edit title, subtitle, footer, logos, and blocks, so that a camp can still change the paper.
50. As a clinician, I want diagnosis, medicines, and glasses to still come from clinical blocks, so that the prescription is filled by the desk, not drawn as a photograph.
51. As an admin, I want already-published templates left alone, so that a live paper layout is not silently replaced.
52. As an admin, I want Restore defaults to pick up the new SNP header, so that I can opt a camp into the sample without a manual logo upload.
53. As a developer testing on Docker Compose, I want these behaviours visible on the local site, so that I can verify without a hosted deploy.

## Implementation Decisions

- Capture UI on New Registration is the existing scanner (live scan, photo upload, USB wedge). The patient form, camp-day picker, and submit control are not shown until two Failures or a Lock. After a Lock, scanned fields fill as they do today and submit is available. After two Failures, the typed form appears and the scanner remains.
- A Failure is a Decode outcome of `garbage` or `not-aadhaar` from any capture mode. Empty-frame Detect misses are not Failures. The same-payload ignore used by live scan still applies, so one bad QR is one Failure, not a loop. The counter lives in the open popup only.
- Manual entry is a mark on the registration (boolean or the existing manual structure without a required reason). No audited reason. No admin switch. Any staff who can register at the desk may submit Manual entry. Self-register continues to require a Lock and has no typed path.
- Duplicate in camp is enforced on desk register and on self-register. Matching any of: existing Person in this camp; last-4 + normalized name; last-4 + DOB; normalized name + age + household phone. Response is 409 with the existing `reg_no`. There is no override flag and no “Register anyway” UI. Phone-only and name+age-without-phone are not hard blocks. Soft name+age duplicate-check that currently feeds “Register anyway” is removed or reduced to a non-override notice that still cannot proceed when a hard key hits.
- Aadhaar overwrite uses the same register endpoint, not a new resource. Request is a Lock (`aadhaar_scanned` with card fields). If Duplicate-in-camp keys match exactly one Manual entry in this camp, update that row in place: write name, age, gender, DOB, last-4, address from the card; keep household phone, camp day, `reg_no`, queue/print/seen; clear the Manual entry mark; set scanned; attach Person. Return that registration; it is not a new seat. If the match is already scanned, 409 with that `reg_no`. If two Manual entries match, 409 listing them. If none match, create as today.
- After overwrite, the unique Person-in-camp index applies because `person_id` is now set. A collision with a different row is the already-scanned 409 path.
- Print window stays a per-camp-day admin boolean with the existing Open/Close control. The print prescription path checks that boolean only. The calendar “today” conjunct is removed. Closed still returns the existing closed-window error code.
- Public occupancy is counts on the existing unauthenticated active-camp projection: per camp day, registered count, seat limit, remaining. No patient fields. Login page renders this under the patient self-registration link and polls on a short interval (a few seconds). Inactive camps are not listed.
- Camp-day capacity: if seat limit is greater than zero and the count of registrations on that camp day is at or above the limit, new registration 409s (desk and self-register). Limit zero is unlimited and remaining displays as unlimited. Aadhaar overwrite does not increment the count.
- Default Rx template content is taken from the sample photograph `EYE CLINIC.jpg` (Sikar Nagarik Parishad / Sikar Zilla Welfare Trust bilingual header, both logos, Sikar Bhawan address/phone/email, free-screening line as appropriate in title/subtitle, Rupa Foundation footer). Logos are baked into the default so local Docker shows them without an admin upload. Clinical blocks and the one-page guard stay. Published templates are not mutated; restore-defaults and new camps see the new default.
- Domain terms in CONTEXT.md already record Manual entry, Aadhaar overwrite, Duplicate in camp, Public occupancy, Camp-day capacity, and Print window. This change also writes two ADRs: Print window without a calendar check; hard Duplicate in camp plus in-place Aadhaar overwrite (rejected: volunteer checkbox, “Register anyway”, a separate bind screen).
- Verify on the existing Docker Compose stack, not a separate dev server.

## Testing Decisions

A good test asserts an actor-visible outcome: HTTP status and body, or what the page shows and sends. It does not assert React state names, Mongo field shapes, or IST helpers.

Two seams, both existing. No third stack.

1. **HTTP API (pytest, same style as the existing registration / camp / print / template API tests).** This is the primary seam. It must prove: Print window open prints on a non-today date and closed still 409s; Duplicate in camp 409s on each hard key and ignores override; Aadhaar overwrite updates one Manual entry in place and 409s on already-scanned or two manuals; Camp-day capacity 409s when full and allows when limit is zero; public active-camp payload has per-day counts and no PHI; self-register without a Lock still 400s; default template (and restore-defaults) carries the SNP header/logos/footer; overwrite does not create a second `reg_no` or consume a second seat.
2. **Jest page tests (same style as the existing desk, admin dashboard, and template editor page tests).** This seam is only for UI the API cannot see: New Registration starts with capture controls and without the typed form or the manual-exception checkbox; two Failure outcomes reveal the form; a Lock before two Failures never reveals a typed path; login page shows occupancy under the patient link with counts not names; admin day row still toggles Print window.

Prior art: desk page tests already open New Registration, stub register and duplicate-check, and drive the manual-exception checkbox (that checkbox goes away). Admin dashboard tests already toggle Print window. Template tests already save logos and restore defaults. Live-scan engine tests already distinguish Decode `card` / `garbage` / `not-aadhaar` — reuse that outcome, do not re-test the detector. There is no login page test today; add one next to the other page tests, same render + stub pattern. Prefer API tests for invariants; keep Jest thin.

## Out of Scope

- Typed path on self-register
- JPEG or photograph used as the printed prescription
- New layout engine or pixel-perfect clone of every checkbox on the sample
- Live name ticker or any patient details on the login page
- A separate “Scan Aadhaar” or bind screen
- Admin approval, audited reason, or an admin Manual window
- Calendar/IST gate on Print window or on Manual entry
- Blocking on household phone alone, or on name + age without phone
- Auto-reprint after Aadhaar overwrite
- Changing OT / Spectacles-to-be-made `seats_taken` (that counter is not camp-day registration)
- Native scanner shell or paid scanning SDK (ADR-0003)
- Mutating already-published Rx templates
- Showing occupancy for inactive camps

## Further Notes

Glossary terms to use in code, tests, and copy: Failure, Lock, Decode, Manual entry, Aadhaar overwrite, Duplicate in camp, Print window, Public occupancy, Camp-day capacity, live scan, photo upload, USB wedge. Avoid: manual exception, register anyway, bind Aadhaar, IST print gate, live feed.

Sample artefact: `EYE CLINIC.jpg` at the repo root (Sikar Nagarik Parishad, Sikar Zilla Welfare Trust, Sikar Bhawan, Rupa Foundation).

Local verification target is Docker Compose.

Test seams for this spec: (1) HTTP API pytest, (2) Jest page tests. If a seam is wrong, say so on this issue before implementation.
