# Aadhaar mobile scanning: reliability research

Research date: 2026-09-05. Design input, not an implementation audit or device certification. No patient data was accessed. Recommendations below require product decisions and acceptance tests before release.

## 1. Separate QR decoding from identity verification

**Verified fact:** UIDAI describes Secure QR as digitally signed data containing demographic information and a photograph; its reader verifies the digital signature. UIDAI's published guidance identifies its own scanners for this purpose. Reading QR text alone does not establish this verification. [UIDAI Aadhaar services FAQ](https://www.uidai.gov.in/en/contact-support/have-any-question/921-english-uk/faqs/aadhaar-online-services.html), [UIDAI QR scanning circular, 22 March 2023](https://www.uidai.gov.in/images/Circular_regarding_dos_and_donts_of_the__tamper_proof_QR_code_scanning_by_residents__dated_22032023.pdf).

**Recommendation:** Distinguish `captured`, `signature_verified`, and `desk_rechecked` in the design. Do not label OCR, legacy unsigned QR, client-supplied success flags, or manually entered details as verified Aadhaar. Verify the Secure QR payload against trusted UIDAI verification material in a trusted implementation; check current UIDAI integration requirements before selecting one. At camp-day recheck, compare the person and presented document with the record. Treat unsupported QR formats as an explicit fallback state. This research does not establish that the current app implements signature verification.

## 2. Preserve a decoder fallback

**Verified fact:** MDN marks `BarcodeDetector` experimental and not Baseline because some widely used browsers do not support it; it exposes supported-format detection. [MDN BarcodeDetector](https://developer.mozilla.org/en-US/docs/Web/API/BarcodeDetector).

**Recommendation:** Feature-detect native QR support and retain a tested software decoder path; inspect installed dependencies before choosing one. Lazy-load decoding code when scanning opens. Check Secure QR payload handling end to end rather than assuming every generic QR decoder provides a usable Aadhaar payload. Native support alone cannot justify an all-device reliability promise.

## 3. Make camera failures actionable

**Verified fact:** `getUserMedia` needs a secure context and permission. Permission requests can remain unanswered. Missing cameras, device errors and mandatory constraints can cause different failures; ideal constraints are preferences. MDN advises stopping the current track when changing cameras in cases that require releasing it. [MDN getUserMedia](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia).

**Recommendation:** Use HTTPS, request video only after a clear user action, prefer the rear camera without requiring one, and provide camera switching and permission recovery instructions. Release tracks on exit. Give permission denial, unavailable camera and unreadable QR distinct messages. Avoid an endless spinner for an unanswered permission prompt.

## 4. Define three attempts as a workflow rule

**Evidence:** Camera access can fail before any image is available; this differs from a completed scan that cannot decode a QR. [MDN getUserMedia](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia).

**Recommendation:** Count three completed, bounded capture attempts with a visible result, not three failed video frames. Track fallback reason and require camp-day recheck for manual registrations. A counter cannot prove genuine scanning because client events can be fabricated. Protect verification and scoring server-side. **Subsequent confirmed product rule:** denied permission requires enablement guidance and retry and must not itself unlock demographic manual entry or count as an unreadable attempt. The audited unavailable-hardware fallback is separate. The implementation spec defines the session boundary and recovery cases.

## 5. Define measured acceptance, not perfection

**Evidence:** Limited decoder support and camera permission/hardware failure states prevent a defensible universal guarantee. [MDN BarcodeDetector](https://developer.mozilla.org/en-US/docs/Web/API/BarcodeDetector), [MDN getUserMedia](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia).

**Recommendation:** Before production, define supported device/browser combinations and record camera-start latency, successful capture rate, decode latency and fallback rate using synthetic/non-patient fixtures. Include low-end Android, iPhone Safari, damaged or reflective prints, denied permissions, camera switching and tab resume in a later authorized device validation plan. Keep scanner telemetry free of images, QR payloads and patient details. Add the Hindi reminder: “शिविर के दिन अपना आधार कार्ड साथ लाएँ।” This note contains no device test results; browser/computer testing is forbidden in the current repository workflow.
