"""Tenant/purpose-separated blind lexical index, without embeddings or LLMs."""

import hashlib
import hmac
import re
from uuid import UUID

from src.domains.shared.text_normalization import fold_name

_WORDS = re.compile(r"[^\W_]+", re.UNICODE)
_CJK = re.compile(r"[\u3400-\u9fff\uf900-\ufaff\U00020000-\U000323af]+")


def blind_digest(user_id: UUID, purpose: str, value: str, *, key: bytes) -> str:
    """The stable wrapped tenant key survives an encryption-key rotation."""
    if len(key) != 32:
        raise ValueError("invalid_ingestion_key")
    scoped = f"lia/phone-ingestion/v1:{user_id}:{purpose}:".encode() + value.encode("utf-8")
    return hmac.new(key, scoped, hashlib.sha256).hexdigest()


def tokenize(text: str) -> tuple[str, ...]:
    normalized = fold_name(text)
    terms = set(_WORDS.findall(_CJK.sub(" ", normalized)))
    for match in _CJK.finditer(normalized):
        value = match.group()
        terms.update(value)
        terms.update(value[i : i + 2] for i in range(len(value) - 1))
    return tuple(sorted(terms))


def blind_terms(user_id: UUID, text: str, *, key: bytes) -> tuple[str, ...]:
    return tuple(sorted(blind_digest(user_id, "term", term, key=key) for term in tokenize(text)))
