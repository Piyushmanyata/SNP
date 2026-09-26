import io
import json
import os
import sys
from contextlib import ExitStack

from aadhaar import decode_aadhaar

MAX_PIXELS = 24_000_000


class DocumentError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


def extract(document: bytes, password: str = '') -> dict:
    from PIL import Image, ImageOps
    import zxingcpp

    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    with ExitStack() as stack:
        images = []
        if document.startswith(b'%PDF-'):
            import pypdfium2 as pdfium

            try:
                pdf = stack.enter_context(pdfium.PdfDocument(document, password=password or None))
            except pdfium.PdfiumError as error:
                if error.err_code == 4:
                    raise DocumentError(422, 'PDF_PASSWORD_REQUIRED', 'Enter the correct password to open this Aadhaar PDF.')
                raise
            if not 1 <= len(pdf) <= 2:
                raise DocumentError(413, 'DOCUMENT_TOO_LARGE', 'Upload an Aadhaar PDF with no more than two pages.')
            total_pixels = 0
            for page_index in range(len(pdf)):
                page = pdf[page_index]
                stack.callback(page.close)
                width, height = page.get_size()
                total_pixels += int(width * 3 + 1) * int(height * 3 + 1)
                if total_pixels > MAX_PIXELS:
                    raise DocumentError(413, 'DOCUMENT_TOO_LARGE', 'This PDF has oversized pages. Upload a cropped card photo instead.')
                bitmap = page.render(scale=3)
                stack.callback(bitmap.close)
                images.append(stack.enter_context(bitmap.to_pil().convert('RGB')))
        else:
            if document[4:8] == b'ftyp':
                from pillow_heif import register_heif_opener

                register_heif_opener()
            try:
                original = stack.enter_context(Image.open(io.BytesIO(document)))
            except Image.DecompressionBombError:
                raise DocumentError(413, 'DOCUMENT_TOO_LARGE', 'This photo has too many pixels. Crop the card and retry.')
            if original.width * original.height > MAX_PIXELS:
                raise DocumentError(413, 'DOCUMENT_TOO_LARGE', 'This photo has too many pixels. Crop the card and retry.')
            oriented = stack.enter_context(ImageOps.exif_transpose(original))
            images.append(stack.enter_context(oriented.convert('RGB')))
        for image in images:
            for barcode in zxingcpp.read_barcodes(image, formats=zxingcpp.BarcodeFormats(zxingcpp.BarcodeFormat.QRCode)):
                result = decode_aadhaar(barcode.text)
                if result['outcome'] == 'card':
                    return {**result, 'payload': barcode.text}
    raise DocumentError(422, 'QR_NOT_FOUND', 'No readable Aadhaar QR was found. Try another photo or enter details manually at the desk.')


def main():
    try:
        if os.name == 'posix':
            import resource

            os.nice(10)
            resource.setrlimit(resource.RLIMIT_AS, (1024 * 1024 * 1024, 1024 * 1024 * 1024))
            resource.setrlimit(resource.RLIMIT_CPU, (25, 25))
            resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        header = json.loads(sys.stdin.buffer.readline(4096))
        document = sys.stdin.buffer.read(12 * 1024 * 1024 + 1)
        result = extract(document, header.get('password', ''))
    except DocumentError as error:
        result = {'error': error.code, 'status': error.status, 'message': error.message}
    except ImportError:
        result = {'error': 'QR_UNAVAILABLE', 'status': 503, 'message': 'QR reader is unavailable. Enter details manually or ask the desk.'}
    except Exception:
        result = {'error': 'UNREADABLE_DOCUMENT', 'status': 422, 'message': 'This document could not be read. Try another photo or enter details manually.'}
    sys.stdout.write(json.dumps(result))


if __name__ == '__main__':
    main()
