"""Signed account identity is required before linking several connectors."""

import base64
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwt

from src.domains.connectors.oauth_identity import verify_provider_identity

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PUBLIC = KEY.public_key().public_numbers()


def _b64(value: int) -> str:
    return (
        base64.urlsafe_b64encode(value.to_bytes((value.bit_length() + 7) // 8, "big"))
        .rstrip(b"=")
        .decode()
    )


JWK = {
    "kty": "RSA",
    "kid": "test-key",
    "use": "sig",
    "alg": "RS256",
    "n": _b64(PUBLIC.n),
    "e": _b64(PUBLIC.e),
}


def _token(**changes: object) -> str:
    claims: dict[str, object] = {
        "iss": "https://accounts.google.com",
        "aud": "lia-client",
        "sub": "google-subject",
        "email": "person@example.com",
        "nonce": "one-flow-nonce",
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    claims.update(changes)
    return jwt.encode(claims, KEY, algorithm="RS256", headers={"kid": "test-key"})


def test_verified_google_subject_is_account_key_not_mutable_email() -> None:
    account = verify_provider_identity(
        "google",
        _token(),
        {"keys": [JWK]},
        client_id="lia-client",
        nonce="one-flow-nonce",
        access_token="issued-access",
    )
    assert account.subject == "google-subject"
    assert account.email == "person@example.com"


def test_google_identity_validates_at_hash_against_exchanged_access_token() -> None:
    token = jwt.encode(
        {
            "iss": "https://accounts.google.com",
            "aud": "lia-client",
            "sub": "google-subject",
            "nonce": "one-flow-nonce",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        KEY,
        algorithm="RS256",
        headers={"kid": "test-key"},
        access_token="issued-access",
    )

    account = verify_provider_identity(
        "google",
        token,
        {"keys": [JWK]},
        client_id="lia-client",
        nonce="one-flow-nonce",
        access_token="issued-access",
    )
    assert account.subject == "google-subject"

    with pytest.raises(ValueError, match="Invalid provider identity token"):
        verify_provider_identity(
            "google",
            token,
            {"keys": [JWK]},
            client_id="lia-client",
            nonce="one-flow-nonce",
            access_token="another-access",
        )


def test_microsoft_identity_validates_at_hash_against_exchanged_access_token() -> None:
    tenant = str(uuid4())
    issuer = f"https://login.microsoftonline.com/{tenant}/v2.0"
    token = jwt.encode(
        {
            "iss": issuer,
            "aud": "lia-client",
            "tid": tenant,
            "oid": str(uuid4()),
            "nonce": "one-flow-nonce",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        KEY,
        algorithm="RS256",
        headers={"kid": "test-key"},
        access_token="issued-access",
    )
    keys = {"keys": [{**JWK, "issuer": issuer}]}

    account = verify_provider_identity(
        "microsoft",
        token,
        keys,
        client_id="lia-client",
        nonce="one-flow-nonce",
        access_token="issued-access",
    )
    assert account.subject.startswith(f"{tenant}:")

    with pytest.raises(ValueError, match="Invalid provider identity token"):
        verify_provider_identity(
            "microsoft",
            token,
            keys,
            client_id="lia-client",
            nonce="one-flow-nonce",
            access_token="another-access",
        )


@pytest.mark.parametrize(
    "changes,nonce",
    [
        ({"aud": "attacker-client"}, "one-flow-nonce"),
        ({"aud": ["lia-client", "attacker-client"], "azp": "attacker-client"}, "one-flow-nonce"),
        ({"aud": ["lia-client", "attacker-client"]}, "one-flow-nonce"),
        ({"iss": "https://attacker.example"}, "one-flow-nonce"),
        ({"exp": datetime.now(UTC) - timedelta(minutes=1)}, "one-flow-nonce"),
        ({}, "another-flow"),
    ],
)
def test_google_rejects_wrong_audience_issuer_expiry_or_nonce(
    changes: dict[str, object], nonce: str
) -> None:
    with pytest.raises(ValueError):
        verify_provider_identity(
            "google",
            _token(**changes),
            {"keys": [JWK]},
            client_id="lia-client",
            nonce=nonce,
            access_token="issued-access",
        )


def test_microsoft_account_key_contains_tenant_and_object_id() -> None:
    tenant = str(uuid4())
    object_id = str(uuid4())
    issuer = f"https://login.microsoftonline.com/{tenant}/v2.0"
    token = _token(iss=issuer, tid=tenant, oid=object_id, preferred_username="member@example.com")
    account = verify_provider_identity(
        "microsoft",
        token,
        {"keys": [{**JWK, "issuer": issuer}]},
        client_id="lia-client",
        nonce="one-flow-nonce",
        access_token="issued-access",
    )
    assert account.subject == f"{tenant}:{object_id}"
    assert account.email == "member@example.com"


def test_microsoft_rejects_key_from_another_tenant() -> None:
    tenant = str(uuid4())
    token = _token(
        iss=f"https://login.microsoftonline.com/{tenant}/v2.0",
        tid=tenant,
        oid=str(uuid4()),
    )
    with pytest.raises(ValueError):
        verify_provider_identity(
            "microsoft",
            token,
            {"keys": [{**JWK, "issuer": "https://login.microsoftonline.com/other/v2.0"}]},
            client_id="lia-client",
            nonce="one-flow-nonce",
            access_token="issued-access",
        )


def test_microsoft_selects_matching_tenant_key_when_kid_is_shared() -> None:
    tenant = str(uuid4())
    issuer = f"https://login.microsoftonline.com/{tenant}/v2.0"
    token = _token(iss=issuer, tid=tenant, oid=str(uuid4()))
    account = verify_provider_identity(
        "microsoft",
        token,
        {
            "keys": [
                {**JWK, "issuer": "https://login.microsoftonline.com/other/v2.0"},
                {**JWK, "issuer": issuer},
            ]
        },
        client_id="lia-client",
        nonce="one-flow-nonce",
        access_token="issued-access",
    )
    assert account.subject.startswith(f"{tenant}:")
