"""Print an Aadhaar Secure QR payload the desk can paste, or write it as a QR image the patient page can upload."""

import argparse
from xml.etree.ElementTree import Element, tostring


def payload(name: str, dob: str, last4: str, gender: str = "F", address: str = "12 Station Road Sikar") -> str:
    uid = f"{'12345678'}{last4}"
    return tostring(Element(
        "PrintLetterBarcodeData", name=name, gender=gender, dob=dob, uid=uid, street=address,
    ), encoding="unicode")


def write_png(text: str, path: str) -> None:
    import zxingcpp
    from PIL import Image

    barcode = zxingcpp.create_barcode(text, zxingcpp.BarcodeFormat.QRCode)
    Image.fromarray(zxingcpp.write_barcode_to_image(barcode, scale=8)).save(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--dob", required=True)
    parser.add_argument("--last4", required=True)
    parser.add_argument("--gender", default="F")
    parser.add_argument("--address", default="12 Station Road Sikar")
    parser.add_argument("--png")
    args = parser.parse_args()
    text = payload(args.name, args.dob, args.last4, args.gender, args.address)
    if args.png:
        write_png(text, args.png)
        print(args.png)
    else:
        print(text)


if __name__ == "__main__":
    main()
