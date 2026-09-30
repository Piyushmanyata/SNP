"""Desk search: how the registration desk reads one typed line (CONTEXT.md)."""

import re
from typing import Any, Dict, Optional

from helpers import normalize_name, normalize_phone

NAME_INDEX = [("camp_id", 1), ("full_name_normalized", 1)]


def options(match: Dict[str, Any]) -> Dict[str, Any]:
    """A name search reads the name index, so a rare name never walks every registration."""
    return {"hint": NAME_INDEX} if "full_name_normalized" in match else {}


def where(typed: str) -> Optional[Dict[str, Any]]:
    """The patient filter for a typed line: {} for a blank line, None when nothing can match."""
    text = typed.strip()
    if not text:
        return {}
    if any(ch.isalpha() for ch in text):
        name = normalize_name(text)
        return {"full_name_normalized": {"$regex": f"(?:^| ){re.escape(name)}"}} if name else None
    digits = re.sub(r"\D", "", text)
    if not digits:
        return None
    if len(digits) < 10:
        return {"reg_no": int(digits)}
    phone = normalize_phone(digits)
    return {"phone_normalized": phone} if phone else None
