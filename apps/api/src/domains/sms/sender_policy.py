"""Exact sender equivalence; never infer a country or a person's identity."""

import re
import unicodedata

from src.domains.telephony.phone_numbers import normalize_phone

_PHONE = re.compile(r"^\+?[0-9 ().-]+$")


def normalize_sender(sender: str) -> str:
    normalized = unicodedata.normalize("NFKC", sender).strip()
    if _PHONE.fullmatch(normalized):
        digits = normalize_phone(normalized, infer_country=False)
        if digits:
            return "phone:" + digits
    return "label:" + " ".join(normalized.casefold().split())
