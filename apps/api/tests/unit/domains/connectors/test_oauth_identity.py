"""Signed account identity is required before linking several connectors."""

import base64
import hashlib
import hmac
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from src.domains.connectors.oauth_identity import verify_provider_identity

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PUBLIC = KEY.public_key().public_numbers()
PUBLIC_PEM = KEY.public_key().public_bytes(
    serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
)


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


def _at_hash(access_token: str) -> str:
    """OIDC Core 3.1.3.6, computed here so the tokens never depend on the verifier's library."""
    digest = hashlib.sha256(access_token.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest[: len(digest) // 2]).rstrip(b"=").decode("ascii")


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
    return jwt.encode(
        {k: v for k, v in claims.items() if v is not None},
        KEY,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )


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
    token = _token(email=None, iat=None, at_hash=_at_hash("issued-access"))

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
    token = _token(
        iss=issuer,
        tid=tenant,
        oid=str(uuid4()),
        sub=None,
        email=None,
        iat=None,
        at_hash=_at_hash("issued-access"),
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


# --------------------------------------------------------------------------- characterisation
#
# The seventeen cases of the JWT parity probe (dependency programme, lot 5): what the
# verifier decides, written down before the library under it changed. One row changed
# on purpose with the move to PyJWT: an identity token with no audience is refused —
# OpenID Connect requires `aud`, and python-jose skipped the check when it was absent.
# Decision D3 keeps the rest: a provider clock ahead of ours (`iat` in the future)
# never fails a connector link; `nbf` and `exp` hold at zero leeway.


def _unsigned(alg: str, signature: bytes, payload: dict[str, object]) -> str:
    def part(data: dict[str, object]) -> bytes:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=")

    signing_input = part({"alg": alg, "typ": "JWT", "kid": "test-key"}) + b"." + part(payload)
    return (signing_input + b"." + base64.urlsafe_b64encode(signature).rstrip(b"=")).decode()


def _forged_with_public_key(payload: dict[str, object]) -> str:
    """HS256 signed with the RSA public key as the secret: the algorithm-confusion attack."""
    unsigned = _unsigned("HS256", b"", payload).rsplit(".", 1)[0].encode()
    signature = hmac.new(PUBLIC_PEM, unsigned, hashlib.sha256).digest()
    return (unsigned + b"." + base64.urlsafe_b64encode(signature).rstrip(b"=")).decode()


def _now() -> int:
    """Read when the token is BUILT: a time read at import drifts under a long xdist run."""
    return int(datetime.now(UTC).timestamp())


def _claims(**changes: object) -> dict[str, object]:
    now = _now()
    claims: dict[str, object] = {
        "iss": "https://accounts.google.com",
        "aud": "lia-client",
        "sub": "google-subject",
        "iat": now,
        "exp": now + 600,
        "nonce": "one-flow-nonce",
        "at_hash": _at_hash("issued-access"),
        "email": "person@example.com",
    }
    claims.update(changes)
    return {k: v for k, v in claims.items() if v is not None}


def _signed(*, key: rsa.RSAPrivateKey = KEY, **changes: object) -> str:
    return jwt.encode(_claims(**changes), key, algorithm="RS256", headers={"kid": "test-key"})


CASES: list[tuple[str, Callable[[], str], bool]] = [
    ("valid", lambda: _signed(), True),
    ("at_hash wrong", lambda: _signed(at_hash="AAAAAAAAAAAAAAAAAAAAAA"), False),
    ("at_hash absent", lambda: _signed(at_hash=None), True),
    ("aud wrong", lambda: _signed(aud="someone-else"), False),
    ("aud absent", lambda: _signed(aud=None), False),  # the row changed on purpose
    ("aud list incl. client", lambda: _signed(aud=["lia-client", "other"], azp="lia-client"), True),
    ("iss wrong", lambda: _signed(iss="https://evil.example"), False),
    ("iss absent", lambda: _signed(iss=None), False),
    ("expired 5s ago", lambda: _signed(exp=_now() - 5), False),
    ("iat 30s in the future", lambda: _signed(iat=_now() + 30), True),  # D3: parity
    ("nbf 30s in the future", lambda: _signed(nbf=_now() + 30), False),
    ("iat absent", lambda: _signed(iat=None), True),
    ("sub not a string", lambda: _signed(sub=12345), False),
    ("signed by another key", lambda: _signed(key=OTHER_KEY), False),
    ("HS256 with the public key as secret", lambda: _forged_with_public_key(_claims()), False),
    ("alg none", lambda: _unsigned("none", b"", _claims()), False),
    ("garbage", lambda: "not.a.jwt", False),
]


@pytest.mark.parametrize(("case", "build", "accepted"), CASES, ids=[c[0] for c in CASES])
def test_the_verifier_decides_each_case_as_written_down(
    case: str, build: Callable[[], str], accepted: bool
) -> None:
    token = build()

    def verify() -> object:
        return verify_provider_identity(
            "google",
            token,
            {"keys": [JWK]},
            client_id="lia-client",
            nonce="one-flow-nonce",
            access_token="issued-access",
        )

    if accepted:
        assert verify() is not None, case
    else:
        with pytest.raises(ValueError):
            verify()
