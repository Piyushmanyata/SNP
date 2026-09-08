# Backend Aadhaar OCR fallback research

Research date: 2026-09-08. Status: implementation reference. See [the implemented interface and limits](aadhaar-document-extraction.md); recognition accuracy and production capacity remain unmeasured.

## Decision and scope

Recommend a bounded Tesseract 5 CPU subprocess with `tessdata_fast` English and Hindi models, feeding normalized image bytes through stdin and receiving TSV through stdout; defer PaddleOCR until a representative evaluation demonstrates a useful accuracy gain. Tesseract supports bilingual `eng+hin` and word-level TSV with boxes and confidence. Its documentation describes `tessdata_fast` as the usual distribution default. This is an implementation simplicity recommendation, not an observed speed or accuracy comparison. [Tesseract command-line guide](https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage.html), [fast model guidance](https://tesseract-ocr.github.io/tessdoc/Data-Files-in-tessdata_fast.html), [stdin/stdout reference](https://github.com/tesseract-ocr/tesseract/blob/main/doc/tesseract.1.asc).

PaddleOCR is a credible alternative with a CPU installation path, but adds an inference engine and OCR package. Its current quick start includes PaddlePaddle and Transformers choices. The additional runtime is why it is deferred here; no claim is made that it is less accurate or slower. [PaddleOCR quick start](https://www.paddleocr.ai/main/en/quick_start.html).

User requirements: OCR runs on the existing backend; uploaded documents and PDF passwords are not retained; extracted details require review by the submitting operator or patient; manual entry is available immediately in staff and public registration. Public transcription/manual submissions still require the existing desk identity recheck. OCR supplies suggestions only. It must not set a Secure QR verification result, auto-register a patient, or fill an uncertain field with invented data. These are product requirements, not claims about an OCR library.

## Input support

| Input | Proposed handling | Evidence |
| --- | --- | --- |
| JPEG / PNG | Decode, correct EXIF orientation, normalize to RGB, preserve readable detail within explicit pixel limits. | [Tesseract supported formats](https://tesseract-ocr.github.io/tessdoc/InputFormats.html), [Pillow EXIF transpose](https://pillow.readthedocs.io/en/stable/reference/ImageOps.html#PIL.ImageOps.exif_transpose) |
| HEIC / HEIF | Decode server-side with Pillow plus `pillow-heif`, then use the same normalized image path. Verify wheels for the deployed Python/platform. | [HEIF Pillow plugin](https://pillow-heif.readthedocs.io/en/stable/pillow-plugin.html), [installation prerequisites](https://pillow-heif.readthedocs.io/en/stable/installation.html) |
| PDF, including password-protected PDF | Included by user decision: accept password transiently, open PDF bytes with `pypdfium2`, render only allowed pages within pixel limits, then attempt QR and reviewed OCR. Tesseract itself cannot read PDF or HEIC. | [PDF byte/password API](https://pypdfium2.readthedocs.io/en/stable/python_api.html#pypdfium2.PdfDocument), [render API](https://pypdfium2.readthedocs.io/en/stable/python_api.html#pypdfium2.PdfPage.render), [Tesseract format limitations](https://tesseract-ocr.github.io/tessdoc/InputFormats.html) |

PDFium calls must be serialized within a process or isolated in separate processes: the official documentation forbids simultaneous calls across threads, even for different documents. Close PDF/page/bitmap handles promptly. [PDFium threading and lifecycle restrictions](https://pypdfium2.readthedocs.io/en/stable/python_api.html#incompatibility-with-threading).

## Deployment and no-retention prerequisites

- Install and pin the Tesseract executable, English/Hindi trained data, and Pillow; add HEIF decoding only with a compatible wheel or verified native libraries. Download models at build time, and check executable/model availability before advertising OCR. These deployment checks are recommendations based on the documented installation requirements. [Tesseract installation](https://tesseract-ocr.github.io/tessdoc/Installation.html), [language availability](https://tesseract-ocr.github.io/tessdoc/Data-Files-in-different-versions.html), [HEIF installation](https://pillow-heif.readthedocs.io/en/stable/installation.html).
- Treat no photo retention as an end-to-end constraint. FastAPI `UploadFile` uses a spooled temporary file that can move to disk. Merely omitting a database write does not prove an in-memory upload path. Choose bounded raw-body streaming or explicitly controlled memory-backed temporary storage, and inspect reverse-proxy buffering, request logging and error monitoring before claiming no disk writes. The buffering fact is documented; the deployment checks are recommendations. [FastAPI file uploads](https://fastapi.tiangolo.com/tutorial/request-files/).
- Use Tesseract stdin/stdout without debug image output; discard original bytes, normalized images and raw OCR text after returning suggestions. Never log photos, passwords or extracted personal details. These are proposed privacy controls. The stdin/stdout mechanism is documented. [Tesseract CLI reference](https://github.com/tesseract-ocr/tesseract/blob/main/doc/tesseract.1.asc).
- Bound bytes, decoded pixels, output size, concurrent jobs and wall time. Use `create_subprocess_exec` with fixed arguments and no shell, drain output with `communicate`, and explicitly kill/reap on timeout or cancellation. The process API has no built-in timeout argument; Python documents using `wait_for`. These limits are design requirements pending host measurements. [Python asyncio subprocess API](https://docs.python.org/3/library/asyncio-subprocess.html).

## Evidence limits and acceptance

No actual Aadhaar corpus, low-end phone measurements, or server OCR speed benchmarks were available for this research. No recognition percentage, timing promise, or all-card/all-phone guarantee is justified. Tesseract documents quality losses from skew, noise, poor scaling and uneven backgrounds; preprocessing needs evaluation against the actual captures. [Tesseract quality guidance](https://tesseract-ocr.github.io/tessdoc/ImproveQuality.html).

Before rollout, evaluate consented, safely handled examples covering English/Hindi, old/new layouts, PVC/laminated cards, masks, blur, glare, rotation, HEIC and weak connectivity. Measure usable field suggestions, operator corrections, failure rate, memory and latency under concurrent camp traffic. Reject unreadable uploads cleanly and keep immediate manual registration usable throughout. These are proposed acceptance criteria, not completed verification.
