import io
import asyncio
import sys
from pathlib import Path
from urllib.parse import quote

backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import pytest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

import routes_registration
import aadhaar_extract


@pytest.fixture(autouse=True)
def reset_requests():
    aadhaar_extract._requests.clear()


def test_extract_rejects_non_documents_without_echoing_content():
    app = FastAPI()
    app.include_router(routes_registration.router)
    with TestClient(app) as client:
        response = client.post('/api/aadhaar/extract', content=b'private-photo-data')
    assert response.status_code == 415
    assert response.json()['detail']['code'] == 'UNSUPPORTED_DOCUMENT'
    assert 'private-photo-data' not in response.text


def test_extract_decodes_a_real_qr_image():
    import zxingcpp

    payload = '<PrintLetterBarcodeData uid="123456781234" name="Test Patient" gender="M" dob="01/01/1980" />'
    barcode = zxingcpp.create_barcode(payload, zxingcpp.BarcodeFormat.QRCode)
    image = Image.fromarray(zxingcpp.write_barcode_to_image(barcode, scale=5))
    output = io.BytesIO()
    image.save(output, format='PNG')
    app = FastAPI()
    app.include_router(routes_registration.router)
    with TestClient(app) as client:
        response = client.post('/api/aadhaar/extract', content=output.getvalue())
    assert response.status_code == 200, response.text
    assert response.json()['outcome'] == 'card'
    assert response.json()['data']['full_name'] == 'Test Patient'
    assert response.json()['data']['aadhaar_last4'] == '1234'
    assert response.json()['payload'] == payload


def test_extract_unreadable_qr_requires_manual_entry():
    output = io.BytesIO()
    Image.new('RGB', (200, 100), 'white').save(output, format='PNG')
    app = FastAPI()
    app.include_router(routes_registration.router)
    with TestClient(app) as client:
        response = client.post('/api/aadhaar/extract', content=output.getvalue())
    assert response.status_code == 422, response.text
    assert response.json()['detail']['code'] == 'QR_NOT_FOUND'
    assert 'manually' in response.json()['detail']['message'].lower()


def test_extract_reads_qr_from_heic_and_pdf():
    import pillow_heif
    import zxingcpp

    pillow_heif.register_heif_opener()
    payload = '<PrintLetterBarcodeData uid="123456781234" name="Test Patient" gender="M" dob="01/01/1980" />'
    barcode = zxingcpp.create_barcode(payload, zxingcpp.BarcodeFormat.QRCode)
    image = Image.fromarray(zxingcpp.write_barcode_to_image(barcode, scale=8)).convert('RGB')
    app = FastAPI()
    app.include_router(routes_registration.router)
    with TestClient(app) as client:
        for format_name in ('HEIF', 'PDF'):
            output = io.BytesIO()
            image.save(output, format=format_name)
            response = client.post('/api/aadhaar/extract', content=output.getvalue())
            assert response.status_code == 200, (format_name, response.text)
            assert response.json()['outcome'] == 'card'


def test_extract_rejects_extra_pdf_pages_and_large_uploads():
    import pypdfium2

    output = io.BytesIO()
    with pypdfium2.PdfDocument.new() as pdf:
        for _ in range(3):
            pdf.new_page(100, 100).close()
        pdf.save(output)
    app = FastAPI()
    app.include_router(routes_registration.router)
    with TestClient(app) as client:
        response = client.post('/api/aadhaar/extract', content=output.getvalue())
        assert response.status_code == 413, response.text
        assert response.json()['detail']['code'] == 'DOCUMENT_TOO_LARGE'
        response = client.post('/api/aadhaar/extract', content=b'%PDF-' + b'0' * aadhaar_extract.MAX_UPLOAD_BYTES)
        assert response.status_code == 413


def test_extract_enforces_public_rate_limit():
    app = FastAPI()
    app.include_router(routes_registration.router)
    with TestClient(app) as client:
        for _ in range(12):
            assert client.post('/api/aadhaar/extract', content=b'no').status_code == 415
        response = client.post('/api/aadhaar/extract', content=b'no')
    assert response.status_code == 429
    assert response.json()['detail']['code'] == 'RATE_LIMITED'


def test_extract_password_protected_pdf_requests_password_and_accepts_encoded_password():
    document = Path(__file__).with_name('fixtures').joinpath('aadhaar-password.pdf').read_bytes()
    app = FastAPI()
    app.include_router(routes_registration.router)
    with TestClient(app) as client:
        for password in ('', 'wrong'):
            response = client.post('/api/aadhaar/extract', content=document, headers={'X-PDF-Password': password})
            assert response.status_code == 422, response.text
            assert response.json()['detail']['code'] == 'PDF_PASSWORD_REQUIRED'
        response = client.post('/api/aadhaar/extract', content=document, headers={'X-PDF-Password': quote('TEST 1234')})
    assert response.status_code == 200, response.text
    assert response.json()['outcome'] == 'card'
    assert 'TEST 1234' not in response.text


def test_extract_deadline_cancels_work_and_releases_capacity(monkeypatch):
    cancelled = []

    async def blocked_worker(*args):
        try:
            await asyncio.sleep(10)
        finally:
            cancelled.append(True)

    monkeypatch.setattr(aadhaar_extract, 'run_worker', blocked_worker)
    monkeypatch.setattr(aadhaar_extract, 'EXTRACT_TIMEOUT_SECONDS', 0.02)
    app = FastAPI()
    app.include_router(routes_registration.router)
    with TestClient(app) as client:
        response = client.post('/api/aadhaar/extract', content=b'%PDF-')
        assert response.status_code == 504
        assert response.json()['detail']['code'] == 'QR_TIMEOUT'
        assert client.post('/api/aadhaar/extract', content=b'no').status_code == 415
    assert cancelled == [True]


def test_extract_disconnect_cancels_qr_reading_and_releases_capacity(monkeypatch):
    from fastapi import Request, HTTPException

    async def run():
        cancelled = []
        messages = iter([
            {'type': 'http.request', 'body': b'%PDF-', 'more_body': False},
            {'type': 'http.disconnect'},
        ])

        async def receive():
            return next(messages, {'type': 'http.disconnect'})

        async def blocked_worker(*args):
            try:
                await asyncio.sleep(10)
            finally:
                cancelled.append(True)

        monkeypatch.setattr(aadhaar_extract, 'run_worker', blocked_worker)
        monkeypatch.setattr(aadhaar_extract, 'EXTRACT_TIMEOUT_SECONDS', 0.2)
        request = Request({'type': 'http', 'headers': [], 'client': ('test-disconnect', 0)}, receive)
        with pytest.raises(HTTPException) as error:
            await aadhaar_extract.extract_document(request)
        assert error.value.status_code == 499
        assert cancelled == [True]
        assert not aadhaar_extract._slots.locked() and aadhaar_extract._slots._value == 2

    asyncio.run(run())
