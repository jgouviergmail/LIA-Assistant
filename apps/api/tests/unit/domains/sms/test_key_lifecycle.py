"""Rotating encryption must never reset receipt identity or lexical indexes."""

from unittest.mock import patch
from uuid import uuid4

import pytest

from src.core.config import settings
from src.domains.sms.search import blind_digest, blind_terms

pytestmark = pytest.mark.unit


def test_hmac_identity_is_independent_of_the_fernet_wrapping_key() -> None:
    owner, key = uuid4(), b"t" * 32
    assert len(key) == 32
    before = blind_digest(owner, "event", "stable-event", key=key)
    terms = blind_terms(owner, "Bonjour", key=key)
    with patch.object(settings, "fernet_key", "other-wrapping-key"):
        assert blind_digest(owner, "event", "stable-event", key=key) == before
        assert blind_terms(owner, "Bonjour", key=key) == terms
    assert blind_digest(owner, "sender", "stable-event", key=key) != before
