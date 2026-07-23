"""Unit tests for WebAuthnService (passkey ceremonies orchestration).

py_webauthn's ``verify_*`` / ``generate_*`` functions are patched at the
service-module boundary: the library is FIDO-conformance-tested upstream,
our logic under test is the orchestration around it (challenge lifecycle,
persistence, caps, ownership, sign-count bookkeeping, error mapping).
"""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.auth.models import WebAuthnCredential
from src.domains.auth.webauthn_service import WebAuthnService
from src.domains.users.models import User
from src.infrastructure.database.registry import import_all_models

import_all_models()

MODULE = "src.domains.auth.webauthn_service"


def _make_user(user_id: uuid.UUID | None = None) -> User:
    """Minimal active user for ceremony tests."""
    now = datetime.now(UTC)
    return User(
        id=user_id or uuid.uuid4(),
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


def _make_credential_row(
    user_id: uuid.UUID,
    credential_id: str = "Y3JlZC1pZA",
    sign_count: int = 5,
) -> WebAuthnCredential:
    """A persisted passkey row."""
    now = datetime.now(UTC)
    return WebAuthnCredential(
        id=uuid.uuid4(),
        user_id=user_id,
        credential_id=credential_id,
        public_key="cHVibGljLWtleQ",
        sign_count=sign_count,
        backed_up=False,
        created_at=now,
        updated_at=now,
    )


def _service_with_mocks() -> tuple[WebAuthnService, MagicMock, AsyncMock]:
    """Build a service with mocked repository and db session."""
    db = AsyncMock(spec=AsyncSession)
    db.add = MagicMock()
    service = WebAuthnService(db)
    repo = MagicMock()
    repo.list_for_user = AsyncMock(return_value=[])
    repo.get_by_credential_id = AsyncMock(return_value=None)
    repo.get_for_user = AsyncMock(return_value=None)
    service.repository = repo
    return service, repo, db


def _redis_mock(getdel_value: str | None = None) -> AsyncMock:
    redis = AsyncMock()
    redis.set = AsyncMock()
    redis.getdel = AsyncMock(return_value=getdel_value)
    return redis


@pytest.mark.unit
class TestRegistrationOptions:
    """generate_registration_options: challenge + exclusions + cap."""

    async def test_generates_options_and_stores_challenge(self) -> None:
        """Options JSON returned; challenge stored single-use with TTL."""
        service, repo, _db = _service_with_mocks()
        user = _make_user()
        existing = _make_credential_row(user.id)
        repo.list_for_user = AsyncMock(return_value=[existing])
        redis = _redis_mock()

        fake_options = SimpleNamespace(challenge=b"challenge-bytes")
        with (
            patch(f"{MODULE}.get_redis_session", return_value=redis),
            patch(f"{MODULE}.generate_registration_options", return_value=fake_options) as mock_gen,
            patch(f"{MODULE}.options_to_json", return_value='{"rp": "lia"}'),
        ):
            options_json = await service.generate_registration_options(user)

        assert options_json == '{"rp": "lia"}'
        kwargs = mock_gen.call_args.kwargs
        assert kwargs["rp_name"] == settings.webauthn_rp_name
        assert kwargs["user_name"] == user.email
        # A1: discoverable credentials — resident key REQUIRED.
        assert kwargs["authenticator_selection"].resident_key.value == "required"
        # Existing passkeys are excluded from re-registration.
        assert len(kwargs["exclude_credentials"]) == 1
        redis.set.assert_awaited_once()
        set_args, set_kwargs = redis.set.call_args
        assert set_args[0].endswith(str(user.id))
        assert set_kwargs["ex"] == settings.webauthn_challenge_ttl_seconds

    async def test_cap_reached_rejects(self) -> None:
        """A user at the passkey cap cannot start a new enrollment."""
        service, repo, _db = _service_with_mocks()
        user = _make_user()
        repo.list_for_user = AsyncMock(
            return_value=[
                _make_credential_row(user.id, credential_id=f"cred-{i}")
                for i in range(settings.mfa_max_passkeys_per_user)
            ]
        )

        with patch(f"{MODULE}.get_redis_session", return_value=_redis_mock()):
            with pytest.raises(Exception) as exc_info:
                await service.generate_registration_options(user)
        assert exc_info.value.status_code == 400  # type: ignore[union-attr]


@pytest.mark.unit
class TestRegistrationVerify:
    """verify_registration: challenge lifecycle, dedup, persistence."""

    def _verified_registration(self) -> SimpleNamespace:
        from webauthn.helpers.structs import CredentialDeviceType

        return SimpleNamespace(
            credential_id=b"cred-id",
            credential_public_key=b"public-key",
            sign_count=0,
            aaguid="0000-aaguid",
            credential_device_type=CredentialDeviceType.MULTI_DEVICE,
            credential_backed_up=True,
        )

    async def test_happy_path_persists_credential(self) -> None:
        """Valid ceremony: row persisted with base64url material + label."""
        service, repo, db = _service_with_mocks()
        user = _make_user()
        redis = _redis_mock(getdel_value="Y2hhbGxlbmdl")
        credential = {"response": {"transports": ["internal", "hybrid"]}}

        with (
            patch(f"{MODULE}.get_redis_session", return_value=redis),
            patch(
                f"{MODULE}.verify_registration_response",
                return_value=self._verified_registration(),
            ) as mock_verify,
            patch(f"{MODULE}.track_webauthn_ceremony"),
        ):
            row = await service.verify_registration(user, credential, label="iPhone")

        assert mock_verify.call_args.kwargs["require_user_verification"] is True
        assert row.user_id == user.id
        assert row.label == "iPhone"
        assert row.transports == ["internal", "hybrid"]
        assert row.backed_up is True
        db.add.assert_called_once()
        db.commit.assert_awaited()
        redis.getdel.assert_awaited_once()

    async def test_missing_challenge_rejects(self) -> None:
        """No pending challenge (expired or never issued) → 400."""
        service, _repo, _db = _service_with_mocks()
        with patch(f"{MODULE}.get_redis_session", return_value=_redis_mock(None)):
            with pytest.raises(Exception) as exc_info:
                await service.verify_registration(_make_user(), {}, label=None)
        assert exc_info.value.status_code == 400  # type: ignore[union-attr]

    async def test_duplicate_credential_rejects(self) -> None:
        """A credential id already registered cannot be enrolled twice."""
        service, repo, _db = _service_with_mocks()
        user = _make_user()
        repo.get_by_credential_id = AsyncMock(return_value=_make_credential_row(user.id))

        with (
            patch(f"{MODULE}.get_redis_session", return_value=_redis_mock("Y2hhbGxlbmdl")),
            patch(
                f"{MODULE}.verify_registration_response",
                return_value=self._verified_registration(),
            ),
        ):
            with pytest.raises(Exception) as exc_info:
                await service.verify_registration(user, {}, label=None)
        assert exc_info.value.status_code == 400  # type: ignore[union-attr]

    async def test_invalid_ceremony_rejects(self) -> None:
        """py_webauthn rejection maps to 400 without leaking lib internals."""
        from webauthn.helpers.exceptions import InvalidRegistrationResponse

        service, _repo, _db = _service_with_mocks()
        with (
            patch(f"{MODULE}.get_redis_session", return_value=_redis_mock("Y2hhbGxlbmdl")),
            patch(
                f"{MODULE}.verify_registration_response",
                side_effect=InvalidRegistrationResponse("bad attestation"),
            ),
        ):
            with pytest.raises(Exception) as exc_info:
                await service.verify_registration(_make_user(), {}, label=None)
        assert exc_info.value.status_code == 400  # type: ignore[union-attr]

    async def test_label_too_long_rejects(self) -> None:
        """Labels above the cap are rejected before any ceremony work."""
        service, _repo, _db = _service_with_mocks()
        with pytest.raises(Exception) as exc_info:
            await service.verify_registration(_make_user(), {}, label="x" * 65)
        assert exc_info.value.status_code == 400  # type: ignore[union-attr]


@pytest.mark.unit
class TestAuthenticationOptions:
    """generate_authentication_options: anonymous challenge issuance."""

    async def test_returns_challenge_id_and_options(self) -> None:
        """Challenge stored under a fresh uuid4 id, options JSON returned."""
        service, _repo, _db = _service_with_mocks()
        redis = _redis_mock()
        fake_options = SimpleNamespace(challenge=b"auth-challenge")

        with (
            patch(f"{MODULE}.get_redis_session", return_value=redis),
            patch(f"{MODULE}.generate_authentication_options", return_value=fake_options),
            patch(f"{MODULE}.options_to_json", return_value="{}"),
        ):
            challenge_id, options_json = await service.generate_authentication_options()

        uuid.UUID(challenge_id)  # must be a valid uuid4 string
        assert options_json == "{}"
        set_args, set_kwargs = redis.set.call_args
        assert challenge_id in set_args[0]
        assert set_kwargs["ex"] == settings.webauthn_challenge_ttl_seconds


@pytest.mark.unit
class TestAuthenticationVerify:
    """verify_authentication: login ceremony → user resolution."""

    def _verified_authentication(self, new_sign_count: int = 6) -> SimpleNamespace:
        return SimpleNamespace(new_sign_count=new_sign_count)

    def _credential_payload(self, credential_id: str = "Y3JlZC1pZA") -> dict:
        return {"rawId": credential_id, "id": credential_id}

    async def test_happy_path_returns_user_and_updates_counter(self) -> None:
        """Valid assertion: sign_count + last_used_at persisted, user returned."""
        service, repo, db = _service_with_mocks()
        user = _make_user()
        row = _make_credential_row(user.id, sign_count=5)
        repo.get_by_credential_id = AsyncMock(return_value=row)
        redis = _redis_mock(getdel_value="Y2hhbGxlbmdl")

        user_repo = MagicMock()
        user_repo.get_user_minimal_for_session = AsyncMock(return_value=user)

        with (
            patch(f"{MODULE}.get_redis_session", return_value=redis),
            patch(
                f"{MODULE}.verify_authentication_response",
                return_value=self._verified_authentication(new_sign_count=6),
            ) as mock_verify,
            patch(f"{MODULE}.UserRepository", return_value=user_repo),
            patch(f"{MODULE}.track_webauthn_ceremony"),
        ):
            result = await service.verify_authentication(
                "11111111-1111-4111-8111-111111111111", self._credential_payload()
            )

        assert result is user
        assert row.sign_count == 6
        assert row.last_used_at is not None
        assert mock_verify.call_args.kwargs["require_user_verification"] is True
        assert mock_verify.call_args.kwargs["credential_current_sign_count"] == 5
        db.commit.assert_awaited()

    async def test_missing_challenge_rejects_401(self) -> None:
        """Expired/unknown challenge id → generic 401 (no enumeration)."""
        service, _repo, _db = _service_with_mocks()
        with patch(f"{MODULE}.get_redis_session", return_value=_redis_mock(None)):
            with pytest.raises(Exception) as exc_info:
                await service.verify_authentication(str(uuid.uuid4()), self._credential_payload())
        assert exc_info.value.status_code == 401  # type: ignore[union-attr]

    async def test_unknown_credential_rejects_401(self) -> None:
        """Credential id not registered → generic 401 (no enumeration)."""
        service, repo, _db = _service_with_mocks()
        repo.get_by_credential_id = AsyncMock(return_value=None)
        with patch(f"{MODULE}.get_redis_session", return_value=_redis_mock("Y2hhbGxlbmdl")):
            with pytest.raises(Exception) as exc_info:
                await service.verify_authentication(str(uuid.uuid4()), self._credential_payload())
        assert exc_info.value.status_code == 401  # type: ignore[union-attr]

    async def test_invalid_assertion_rejects_401_and_keeps_counter(self) -> None:
        """Lib rejection (incl. sign-count regression) → 401, row untouched."""
        from webauthn.helpers.exceptions import InvalidAuthenticationResponse

        service, repo, db = _service_with_mocks()
        user = _make_user()
        row = _make_credential_row(user.id, sign_count=5)
        repo.get_by_credential_id = AsyncMock(return_value=row)

        with (
            patch(f"{MODULE}.get_redis_session", return_value=_redis_mock("Y2hhbGxlbmdl")),
            patch(
                f"{MODULE}.verify_authentication_response",
                side_effect=InvalidAuthenticationResponse("counter regression"),
            ),
            patch(f"{MODULE}.track_webauthn_ceremony"),
        ):
            with pytest.raises(Exception) as exc_info:
                await service.verify_authentication(str(uuid.uuid4()), self._credential_payload())

        assert exc_info.value.status_code == 401  # type: ignore[union-attr]
        assert row.sign_count == 5
        db.commit.assert_not_awaited()

    async def test_inactive_user_rejects_401(self) -> None:
        """Credential resolves but the account is inactive/deleted → 401."""
        service, repo, _db = _service_with_mocks()
        row = _make_credential_row(uuid.uuid4())
        repo.get_by_credential_id = AsyncMock(return_value=row)
        user_repo = MagicMock()
        user_repo.get_user_minimal_for_session = AsyncMock(return_value=None)

        with (
            patch(f"{MODULE}.get_redis_session", return_value=_redis_mock("Y2hhbGxlbmdl")),
            patch(
                f"{MODULE}.verify_authentication_response",
                return_value=self._verified_authentication(),
            ),
            patch(f"{MODULE}.UserRepository", return_value=user_repo),
            patch(f"{MODULE}.track_webauthn_ceremony"),
        ):
            with pytest.raises(Exception) as exc_info:
                await service.verify_authentication(str(uuid.uuid4()), self._credential_payload())
        assert exc_info.value.status_code == 401  # type: ignore[union-attr]


@pytest.mark.unit
class TestCredentialManagement:
    """list / rename / delete with ownership enforcement."""

    async def test_rename_updates_label(self) -> None:
        """Rename persists the new label on an owned credential."""
        service, repo, db = _service_with_mocks()
        user = _make_user()
        row = _make_credential_row(user.id)
        repo.get_for_user = AsyncMock(return_value=row)

        result = await service.rename_credential(user, row.id, label="PC bureau")

        assert result.label == "PC bureau"
        db.commit.assert_awaited()

    async def test_rename_unowned_rejects_404(self) -> None:
        """Renaming a credential you don't own → 404 (hide existence)."""
        service, repo, _db = _service_with_mocks()
        repo.get_for_user = AsyncMock(return_value=None)

        with pytest.raises(Exception) as exc_info:
            await service.rename_credential(_make_user(), uuid.uuid4(), label="X")
        assert exc_info.value.status_code == 404  # type: ignore[union-attr]

    async def test_delete_removes_owned_credential(self) -> None:
        """Deleting an owned credential removes the row (password still set)."""
        service, repo, db = _service_with_mocks()
        user = _make_user()
        user.hashed_password = "hashed_pw"  # password sign-in remains available
        row = _make_credential_row(user.id)
        repo.get_for_user = AsyncMock(return_value=row)

        await service.delete_credential(user, row.id)

        db.delete.assert_awaited_once_with(row)
        db.commit.assert_awaited()

    async def test_delete_last_passkey_of_passwordless_account_rejects(self) -> None:
        """A8: the last strong method is never revocable (password disabled)."""
        service, repo, db = _service_with_mocks()
        user = _make_user()  # hashed_password=None (passwordless)
        row = _make_credential_row(user.id)
        repo.get_for_user = AsyncMock(return_value=row)
        repo.list_for_user = AsyncMock(return_value=[row])  # the last one

        with pytest.raises(Exception) as exc_info:
            await service.delete_credential(user, row.id)

        assert exc_info.value.status_code == 400  # type: ignore[union-attr]
        db.delete.assert_not_awaited()

    async def test_delete_passwordless_with_two_passkeys_allowed(self) -> None:
        """Passwordless accounts can still prune down to one passkey."""
        service, repo, db = _service_with_mocks()
        user = _make_user()
        row = _make_credential_row(user.id)
        other = _make_credential_row(user.id, credential_id="b3RoZXI")
        repo.get_for_user = AsyncMock(return_value=row)
        repo.list_for_user = AsyncMock(return_value=[row, other])

        await service.delete_credential(user, row.id)

        db.delete.assert_awaited_once_with(row)

    async def test_delete_unowned_rejects_404(self) -> None:
        """Deleting a credential you don't own → 404 (hide existence)."""
        service, repo, _db = _service_with_mocks()
        repo.get_for_user = AsyncMock(return_value=None)

        with pytest.raises(Exception) as exc_info:
            await service.delete_credential(_make_user(), uuid.uuid4())
        assert exc_info.value.status_code == 404  # type: ignore[union-attr]
