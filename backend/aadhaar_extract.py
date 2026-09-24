from helpers import api_error
import asyncio
import json
import os
import signal
import sys
import time
from pathlib import Path
from typing import NoReturn
from urllib.parse import unquote

from fastapi import Request

MAX_UPLOAD_BYTES = 12 * 1024 * 1024
EXTRACT_TIMEOUT_SECONDS = 30
_slots = asyncio.Semaphore(2)
_requests: dict[str, list[float]] = {}


def fail(status: int, code: str, message: str) -> NoReturn:
    raise api_error(status, str(code).upper(), message)


async def run_worker(document: bytes, password: str) -> dict:
    process = await asyncio.create_subprocess_exec(
        sys.executable, str(Path(__file__).with_name('aadhaar_document.py')),
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL, start_new_session=os.name == 'posix',
    )
    try:
        output, _ = await process.communicate(json.dumps({'password': password}).encode() + b'\n' + document)
        if process.returncode or len(output) > 128 * 1024:
            fail(503, 'QR_UNAVAILABLE', 'QR reader could not finish. Retry or enter details manually.')
        result = json.loads(output)
        if 'error' in result:
            fail(result['status'], result['error'], result['message'])
        return result
    finally:
        if process.returncode is None:
            if os.name == 'posix':
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            else:
                process.kill()
            await process.wait()


async def wait_for_disconnect(request: Request):
    while True:
        if (await request.receive())['type'] == 'http.disconnect':
            return


async def extract_document(request: Request) -> dict:
    now = time.monotonic()
    for ip in [key for key, attempts in _requests.items() if attempts[-1] < now - 600]:
        del _requests[ip]
    ip = request.client.host if request.client else 'unknown'
    if ip not in _requests and len(_requests) >= 2048:
        fail(429, 'RATE_LIMITED', 'Document reader is busy. Please try again shortly or enter details manually.')
    attempts = [stamp for stamp in _requests.get(ip, []) if stamp > now - 600]
    if len(attempts) >= 12:
        fail(429, 'RATE_LIMITED', 'Too many document attempts. Enter details manually or try again later.')
    _requests[ip] = attempts + [now]
    try:
        async with asyncio.timeout(EXTRACT_TIMEOUT_SECONDS):
            document = bytearray()
            async for chunk in request.stream():
                if len(document) + len(chunk) > MAX_UPLOAD_BYTES:
                    fail(413, 'DOCUMENT_TOO_LARGE', 'Choose a document smaller than 12 MB or enter details manually.')
                document.extend(chunk)
            supported = document.startswith((b'\xff\xd8\xff', b'\x89PNG\r\n\x1a\n', b'%PDF-'))
            supported = supported or (document[4:8] == b'ftyp' and any(
                brand in document[8:64] for brand in (b'heic', b'heix', b'hevc', b'hevx', b'mif1', b'msf1')
            ))
            if not supported:
                fail(415, 'UNSUPPORTED_DOCUMENT', 'Upload a JPEG, PNG, HEIC photo or an Aadhaar PDF, or enter details manually.')
            encoded_password = request.headers.get('x-pdf-password', '')
            if len(encoded_password) > 1024:
                fail(422, 'INVALID_PASSWORD', 'The PDF password is too long.')
            try:
                password = unquote(encoded_password, errors='strict')
            except UnicodeError:
                fail(422, 'INVALID_PASSWORD', 'Enter the PDF password again.')
            if _slots.locked():
                fail(429, 'QR_BUSY', 'Other documents are being read. Please retry shortly or enter details manually.')
            async with _slots:
                reading = asyncio.create_task(run_worker(bytes(document), password))
                disconnected = asyncio.create_task(wait_for_disconnect(request))
                try:
                    done, _ = await asyncio.wait((reading, disconnected), return_when=asyncio.FIRST_COMPLETED)
                    if reading in done:
                        return await reading
                    fail(499, 'REQUEST_CANCELLED', 'Document reading was cancelled.')
                except (OSError, ValueError):
                    fail(503, 'QR_UNAVAILABLE', 'QR reader is unavailable. Enter details manually or ask the desk.')
                finally:
                    reading.cancel()
                    disconnected.cancel()
                    await asyncio.gather(reading, disconnected, return_exceptions=True)
    except TimeoutError:
        fail(504, 'QR_TIMEOUT', 'Reading the QR took too long. Try a cropped photo or enter details manually.')
