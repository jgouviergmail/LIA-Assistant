"""A passkey ceremony through the REAL py_webauthn and cbor2, end to end.

``test_webauthn_service.py`` patches py_webauthn at the service-module
boundary: the orchestration around the library is its subject. This file is
the other half. A software authenticator — an Ed25519 or a P-256 key, a ``none``
attestation, CBOR written with cbor2 — drives ``WebAuthnService`` through
enrollment and login with nothing of the library mocked, so a release of
webauthn or cbor2 that changes what LIA passes in or reads back
(``credential_public_key``, ``sign_count``, ``new_sign_count``…) fails here,
where a mock agrees with anything. Only storage is faked: a dict for Redis,
the repositories for the database.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import cbor2
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, ed25519
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from sqlalchemy.ext.asyncio import AsyncSession
from webauthn.helpers import bytes_to_base64url

from src.core.exceptions import BaseAPIException
from src.domains.auth.models import WebAuthnCredential
from src.domains.auth.webauthn_service import WebAuthnService
from src.domains.users.models import User
from src.infrastructure.database.registry import import_all_models

import_all_models()

pytestmark = pytest.mark.unit

MODULE = "src.domains.auth.webauthn_service"

# authenticatorData flags (WebAuthn Level 3, section 6.1).
_USER_PRESENT = 0x01
_USER_VERIFIED = 0x04
_ATTESTED_CREDENTIAL = 0x40
# COSE algorithm identifiers (RFC 9053).
_EDDSA = -8
_ES256 = -7


class _FakeRedis:
    """The two calls a ceremony makes: a challenge stored, then taken once."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def set(self, key: str, value: str, ex: int) -> None:
        self.values[key] = value

    async def getdel(self, key: str) -> str | None:
        return self.values.pop(key, None)


class _SoftAuthenticator:
    """A platform authenticator in software: one key, ``none`` attestation.

    webauthn 3.0 asks authenticators for EdDSA first, ES256 next: both are
    what new passkeys will carry.
    """

    def __init__(self, origin: str, algorithm: int = _EDDSA) -> None:
        self.origin = origin
        self.signer: ed25519.Ed25519PrivateKey | ec.EllipticCurvePrivateKey = (
            ed25519.Ed25519PrivateKey.generate()
            if algorithm == _EDDSA
            else ec.generate_private_key(ec.SECP256R1())
        )
        self.credential_id = uuid.uuid4().bytes

    def _client_data(self, kind: str, challenge: str, origin: str) -> bytes:
        payload = {"type": kind, "challenge": challenge, "origin": origin, "crossOrigin": False}
        return json.dumps(payload).encode("utf-8")

    def _cose_public_key(self) -> bytes:
        # COSE_Key (RFC 9053): OKP Ed25519 with EdDSA, or EC2 P-256 with ES256.
        if isinstance(self.signer, ed25519.Ed25519PrivateKey):
            raw = self.signer.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
            return cbor2.dumps({1: 1, 3: _EDDSA, -1: 6, -2: raw})
        numbers = self.signer.public_key().public_numbers()
        return cbor2.dumps(
            {
                1: 2,
                3: _ES256,
                -1: 1,
                -2: numbers.x.to_bytes(32, "big"),
                -3: numbers.y.to_bytes(32, "big"),
            }
        )

    def _sign(self, data: bytes) -> bytes:
        if isinstance(self.signer, ed25519.Ed25519PrivateKey):
            return self.signer.sign(data)
        return self.signer.sign(data, ec.ECDSA(hashes.SHA256()))

    def create(
        self, options: dict[str, Any], *, fmt: object = "none", origin: str | None = None
    ) -> dict[str, Any]:
        """What ``navigator.credentials.create`` returns for these options."""
        credential_data = (
            bytes(16)  # AAGUID of a ``none`` attestation
            + len(self.credential_id).to_bytes(2, "big")
            + self.credential_id
            + self._cose_public_key()
        )
        auth_data = (
            hashlib.sha256(options["rp"]["id"].encode("utf-8")).digest()
            + bytes([_USER_PRESENT | _USER_VERIFIED | _ATTESTED_CREDENTIAL])
            + (0).to_bytes(4, "big")
            + credential_data
        )
        attestation = cbor2.dumps({"fmt": fmt, "attStmt": {}, "authData": auth_data})
        client_data = self._client_data(
            "webauthn.create", options["challenge"], origin or self.origin
        )
        raw_id = bytes_to_base64url(self.credential_id)
        return {
            "id": raw_id,
            "rawId": raw_id,
            "type": "public-key",
            "response": {
                "clientDataJSON": bytes_to_base64url(client_data),
                "attestationObject": bytes_to_base64url(attestation),
                "transports": ["internal"],
            },
            "clientExtensionResults": {},
            "authenticatorAttachment": "platform",
        }

    def get(self, options: dict[str, Any], *, sign_count: int) -> dict[str, Any]:
        """What ``navigator.credentials.get`` returns: an assertion signed with the key."""
        auth_data = (
            hashlib.sha256(options["rpId"].encode("utf-8")).digest()
            + bytes([_USER_PRESENT | _USER_VERIFIED])
            + sign_count.to_bytes(4, "big")
        )
        client_data = self._client_data("webauthn.get", options["challenge"], self.origin)
        signature = self._sign(auth_data + hashlib.sha256(client_data).digest())
        raw_id = bytes_to_base64url(self.credential_id)
        return {
            "id": raw_id,
            "rawId": raw_id,
            "type": "public-key",
            "response": {
                "clientDataJSON": bytes_to_base64url(client_data),
                "authenticatorData": bytes_to_base64url(auth_data),
                "signature": bytes_to_base64url(signature),
            },
            "clientExtensionResults": {},
        }


def _user() -> User:
    now = datetime.now(UTC)
    return User(
        id=uuid.uuid4(),
        email="passkey@example.com",
        full_name="Passkey User",
        hashed_password=None,
        is_active=True,
        is_verified=True,
        is_superuser=False,
        language="fr",
        timezone="Europe/Paris",
        created_at=now,
        updated_at=now,
    )


def _service() -> tuple[WebAuthnService, MagicMock]:
    db = AsyncMock(spec=AsyncSession)
    db.add = MagicMock()
    service = WebAuthnService(db)
    repository = MagicMock()
    repository.list_for_user = AsyncMock(return_value=[])
    repository.get_by_credential_id = AsyncMock(return_value=None)
    service.repository = repository
    return service, repository


async def _enroll(
    service: WebAuthnService, user: User, authenticator: _SoftAuthenticator
) -> WebAuthnCredential:
    options = json.loads(await service.generate_registration_options(user))
    return await service.verify_registration(user, authenticator.create(options), "Laptop")


async def _sign_in(
    service: WebAuthnService, user: User, authenticator: _SoftAuthenticator, *, sign_count: int
) -> User:
    challenge_id, options_json = await service.generate_authentication_options()
    assertion = authenticator.get(json.loads(options_json), sign_count=sign_count)
    accounts = MagicMock(get_user_minimal_for_session=AsyncMock(return_value=user))
    with patch(f"{MODULE}.UserRepository", return_value=accounts):
        return await service.verify_authentication(challenge_id, assertion)


@pytest.fixture
def redis() -> Iterator[_FakeRedis]:
    store = _FakeRedis()
    with patch(f"{MODULE}.get_redis_session", return_value=store):
        yield store


@pytest.mark.parametrize("algorithm", [_EDDSA, _ES256], ids=["EdDSA", "ES256"])
async def test_enrollment_then_login(redis: _FakeRedis, algorithm: int) -> None:
    user = _user()
    service, repository = _service()
    authenticator = _SoftAuthenticator(WebAuthnService._expected_origin(), algorithm)

    row = await _enroll(service, user, authenticator)
    repository.get_by_credential_id = AsyncMock(return_value=row)
    signed_in = await _sign_in(service, user, authenticator, sign_count=1)

    assert row.credential_id == bytes_to_base64url(authenticator.credential_id)
    assert row.transports == ["internal"]
    assert signed_in is user
    assert row.sign_count == 1
    assert redis.values == {}  # every challenge was single-use


async def test_a_replayed_counter_is_refused_as_a_clone(redis: _FakeRedis) -> None:
    user = _user()
    service, repository = _service()
    authenticator = _SoftAuthenticator(WebAuthnService._expected_origin())
    row = await _enroll(service, user, authenticator)
    repository.get_by_credential_id = AsyncMock(return_value=row)
    await _sign_in(service, user, authenticator, sign_count=5)

    with pytest.raises(BaseAPIException) as refused:
        await _sign_in(service, user, authenticator, sign_count=5)

    assert refused.value.status_code == 401
    assert row.sign_count == 5


async def test_a_synced_passkey_that_never_counts_is_not_a_clone(redis: _FakeRedis) -> None:
    """Synced passkeys (a platform keychain, a password manager) report 0 on every
    use — the common case. 0 → 0 is no replay (ADR-143), on the real library too."""
    user = _user()
    service, repository = _service()
    authenticator = _SoftAuthenticator(WebAuthnService._expected_origin())
    row = await _enroll(service, user, authenticator)
    repository.get_by_credential_id = AsyncMock(return_value=row)

    assert await _sign_in(service, user, authenticator, sign_count=0) is user
    assert await _sign_in(service, user, authenticator, sign_count=0) is user
    assert row.sign_count == 0


async def test_a_foreign_origin_is_refused(redis: _FakeRedis) -> None:
    user = _user()
    service, _ = _service()
    authenticator = _SoftAuthenticator(WebAuthnService._expected_origin())
    options = json.loads(await service.generate_registration_options(user))

    with pytest.raises(BaseAPIException) as refused:
        await service.verify_registration(
            user, authenticator.create(options, origin="https://elsewhere.example"), None
        )

    assert refused.value.status_code == 400


async def test_an_attestation_format_that_is_not_a_string_is_refused(redis: _FakeRedis) -> None:
    user = _user()
    service, _ = _service()
    authenticator = _SoftAuthenticator(WebAuthnService._expected_origin())
    options = json.loads(await service.generate_registration_options(user))

    with pytest.raises(BaseAPIException) as refused:
        await service.verify_registration(user, authenticator.create(options, fmt=1), None)

    assert refused.value.status_code == 400
