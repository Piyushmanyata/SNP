import io
import json
import csv
import os
import re
import subprocess
import sys
from datetime import date, datetime
from contextlib import ExitStack

from aadhaar import decode_aadhaar
from helpers import age_from_dob

MAX_PIXELS = 24_000_000


class DocumentError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


def transcription(image) -> dict:
    output = io.BytesIO()
    image.save(output, format='PNG')
    try:
        result = subprocess.run(
            ['tesseract', 'stdin', 'stdout', '-l', 'eng+hin', '--psm', '3', 'tsv'],
            input=output.getvalue(), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=20, check=False, env={**os.environ, 'OMP_THREAD_LIMIT': '1'},
        )
    except FileNotFoundError:
        raise DocumentError(503, 'OCR_UNAVAILABLE', 'Text reader is unavailable. Enter details manually or ask the desk.')
    except subprocess.TimeoutExpired:
        raise DocumentError(504, 'OCR_TIMEOUT', 'Reading the document took too long. Try a cropped photo or enter details manually.')
    if result.returncode:
        raise DocumentError(503, 'OCR_UNAVAILABLE', 'Text reader could not start. Enter details manually or ask the desk.')
    if len(result.stdout) > 2 * 1024 * 1024:
        raise DocumentError(413, 'DOCUMENT_TOO_LARGE', 'This document contains too much text. Crop the Aadhaar card and retry.')
    grouped: dict[tuple[str | None, ...], list[str]] = {}
    for row in csv.DictReader(io.StringIO(result.stdout.decode('utf-8', errors='replace')), delimiter='\t'):
        if row.get('level') != '5' or float(row.get('conf') or '-1') < 50:
            continue
        key = tuple(row.get(part) for part in ('page_num', 'block_num', 'par_num', 'line_num'))
        grouped.setdefault(key, []).append(row.get('text', ''))
    lines = [' '.join(words).strip() for words in grouped.values()]
    data = {}
    for index, line in enumerate(lines):
        name = re.search(r'^(?:Name|नाम)\s*[:：]\s*(.+)$', line, re.I)
        if name and len(name[1]) <= 120 and not any(char.isdigit() for char in name[1]):
            data['full_name'] = name[1].strip()
        dob = re.search(r'(?:DOB|D\.O\.B\.?|Date of Birth|जन्म\s*तिथि|जन्मतिथि)\s*[:：/\s]*([0-9]{2}[/-][0-9]{2}[/-][0-9]{4})', line, re.I)
        birth_year = re.search(r'(?:Year\s+of\s+Birth|YOB|जन्म\s*(?:का\s*)?वर्ष)\s*[:：/\s]*([0-9]{4})(?![0-9])', line, re.I)
        if dob:
            try:
                birth_date = datetime.strptime(dob[1].replace('-', '/'), '%d/%m/%Y').date()
                if date(1900, 1, 1) <= birth_date <= date.today():
                    data['dob'] = birth_date.isoformat()
                    data['age'] = age_from_dob(data['dob'])
            except ValueError:
                pass
        elif birth_year and 'dob' not in data:
            age = age_from_dob(f'{birth_year[1]}-01-01')
            if age is not None and 0 <= age <= 130:
                data['dob'] = birth_year[1]
                data['age'] = age
        if dob or birth_year:
            if 'full_name' not in data and index:
                candidate = lines[index - 1]
                if (2 <= len(candidate) <= 120 and any(c.isalpha() for c in candidate)
                        and all(c.isalpha() or c in " .'-" or '\u0900' <= c <= '\u097f' for c in candidate)
                        and not re.search(r'government|india|aadhaar|भारत|सरकार|आधार', candidate, re.I)):
                    data['full_name'] = candidate
        for pattern, gender in ((r'\bFEMALE\b|महिला', 'F'), (r'\bMALE\b|पुरुष', 'M'), (r'\bTRANSGENDER\b|उभयलिंगी', 'O')):
            if re.search(pattern, line, re.I):
                data['gender'] = gender
                break
        number = re.fullmatch(r'(?:[0-9Xx*]{4}\s+){2}([0-9]{4})', line)
        if number:
            data['aadhaar_last4'] = number[1]
        address = re.search(r'^(?:Address|पता)\s*[:：]\s*(.*)$', line, re.I)
        if address:
            parts = [address[1].strip()]
            for following in lines[index + 1:index + 6]:
                if re.search(r'\b[0-9]{6}\b', ' '.join(parts)) or re.search(r'\b(?:VID|UID|DOB|www|help)\b|[0-9Xx*]{4}\s+[0-9Xx*]{4}', following, re.I):
                    break
                parts.append(following)
            value = ' '.join(parts).strip()
            value = re.sub(r'(?<![0-9])(?:[0-9][ -]*){11}[0-9](?![0-9])', '', value).strip()
            if value and len(value) <= 500:
                data['address'] = value
    return data


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
        data = {}
        for image in images:
            for field, value in transcription(image).items():
                if field not in data:
                    data[field] = value
    return {'outcome': 'review', 'data': data, 'message': 'Check and correct every suggested detail before registering. Missing details can be entered manually.'}


def main():
    try:
        if os.name == 'posix':
            import resource

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
        result = {'error': 'OCR_UNAVAILABLE', 'status': 503, 'message': 'Document reader is unavailable. Enter details manually or ask the desk.'}
    except Exception:
        result = {'error': 'UNREADABLE_DOCUMENT', 'status': 422, 'message': 'This document could not be read. Try another photo or enter details manually.'}
    sys.stdout.write(json.dumps(result))


if __name__ == '__main__':
    main()
