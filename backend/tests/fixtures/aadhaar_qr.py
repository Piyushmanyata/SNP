"""Print an Aadhaar Secure QR payload the desk and self-register screens can paste."""

import argparse
from xml.etree.ElementTree import Element, tostring


def payload(name: str, dob: str, last4: str, gender: str = "F", address: str = "12 Station Road Sikar") -> str:
    uid = f"{'12345678'}{last4}"
    return tostring(Element(
        "PrintLetterBarcodeData", name=name, gender=gender, dob=dob, uid=uid, street=address,
    ), encoding="unicode")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--dob", required=True)
    parser.add_argument("--last4", required=True)
    parser.add_argument("--gender", default="F")
    parser.add_argument("--address", default="12 Station Road Sikar")
    args = parser.parse_args()
    print(payload(args.name, args.dob, args.last4, args.gender, args.address))


if __name__ == "__main__":
    main()
