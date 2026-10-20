"""An ingestion credential only grants its explicit resource scope."""

from hashlib import sha256
from uuid import uuid4

import pytest

from src.domains.ingestion.principal import IngestionPrincipal, IngestionScopeDenied
from src.domains.ingestion.token_auth import extract_token, hash_token

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("header", ["Bearer hm_abc", "hm_abc", "  bEaReR hm_abc  "])
def test_legacy_health_credentials_keep_their_wire_shape(header: str) -> None:
    assert extract_token(header, prefix="hm_") == "hm_abc"


@pytest.mark.parametrize("header", [None, "", "Bearer pi_abc", "Basic hm_abc"])
def test_other_credentials_do_not_become_health_tokens(header: str | None) -> None:
    assert extract_token(header, prefix="hm_") is None


def test_hashing_preserves_existing_health_token_identity() -> None:
    assert hash_token("hm_example") == sha256(b"hm_example").hexdigest()


def test_health_authority_never_grants_sms_or_future_resource_access() -> None:
    principal = IngestionPrincipal(
        user_id=uuid4(), token_id=uuid4(), source_id=None, scopes=frozenset({"health:write"})
    )
    principal.require_scope("health:write")
    for scope in ("sms:write", "location:write", "*"):
        with pytest.raises(IngestionScopeDenied):
            principal.require_scope(scope)
