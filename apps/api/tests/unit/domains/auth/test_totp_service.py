"""Unit tests for TOTPService (second factor: enroll/confirm/verify/backup).

Real pyotp codes are used against the real Fernet encryption — the mocked
boundary is the repository (SQL) and Redis (pending tokens). This pins the
actual protocol behavior: window tolerance, same-step anti-replay, backup
code single-use, revealed-once semantics.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import unquote

import pyotp
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import (
    MFA_BACKUP_CODE_HEX_CHARS,
    MFA_BACKUP_CODES_COUNT,
    TOTP_INTERVAL_SECONDS,
)
from src.core.security.utils import decrypt_data, encrypt_data
from src.domains.auth.models import MFABackupCode, UserTOTP
from src.domains.auth.totp_service import TOTPService, hash_backup_code
from src.domains.users.models import User
from src.infrastructure.database.registry import import_all_models

import_all_models()

MODULE = "src.domains.auth.totp_service"


def _make_user() -> User:
    now = datetime.now(UTC)
    return User(
        id=uuid.uuid4(),
        email="totp@example.com",
        is_active=True,
        is_verified=True,
        is_superuser=False,
        language="fr",
        timezone="Europe/Paris",
        created_at=now,
        updated_at=now,
    )


def _totp_row(
    user_id: uuid.UUID,
    secret: str,
    confirmed: bool = True,
    last_used_step: int | None = None,
) -> UserTOTP:
    now = datetime.now(UTC)
    return UserTOTP(
        id=uuid.uuid4(),
        user_id=user_id,
        secret_encrypted=encrypt_data(secret),
        confirmed_at=now if confirmed else None,
        last_used_step=last_used_step,
        created_at=now,
        updated_at=now,
    )


def _service_with_mocks() -> tuple[TOTPService, MagicMock, AsyncMock]:
    db = AsyncMock(spec=AsyncSession)
    db.add = MagicMock()
    service = TOTPService(db)
    repo = MagicMock()
    repo.get_for_user = AsyncMock(return_value=None)
    repo.delete_for_user = AsyncMock()
    repo.delete_codes_for_user = AsyncMock()
    repo.get_unused_code_by_hash = AsyncMock(return_value=None)
    repo.count_unused_codes = AsyncMock(return_value=0)
    service.repository = repo
    return service, repo, db


def _current_code(secret: str) -> str:
    return pyotp.TOTP(secret, interval=TOTP_INTERVAL_SECONDS).now()


@pytest.mark.unit
class TestEnroll:
    """Enrollment drafts: secret + provisioning URI + QR, revealed once."""

    async def test_enroll_returns_secret_uri_and_qr(self) -> None:
        """Fresh enrollment: base32 secret, issuer URI, PNG data-URI QR."""
        service, repo, db = _service_with_mocks()
        user = _make_user()

        secret, uri, qr_data_uri = await service.enroll(user)

        assert pyotp.TOTP(secret).now()  # valid base32 secret
        assert "otpauth://totp/" in uri
        assert user.email in unquote(uri)  # account label is URL-encoded in the URI
        assert qr_data_uri.startswith("data:image/png;base64,")
        added = db.add.call_args.args[0]
        assert isinstance(added, UserTOTP)
        assert added.confirmed_at is None
        # Stored encrypted, never plaintext.
        assert added.secret_encrypted != secret
        assert decrypt_data(added.secret_encrypted) == secret

    async def test_enroll_replaces_unconfirmed_draft(self) -> None:
        """A new enrollment discards a prior unconfirmed draft."""
        service, repo, _db = _service_with_mocks()
        user = _make_user()
        repo.get_for_user = AsyncMock(
            return_value=_totp_row(user.id, pyotp.random_base32(), confirmed=False)
        )

        await service.enroll(user)

        repo.delete_for_user.assert_awaited_once_with(user.id)

    async def test_enroll_rejected_when_already_active(self) -> None:
        """An active (confirmed) TOTP cannot be silently replaced."""
        service, repo, _db = _service_with_mocks()
        user = _make_user()
        repo.get_for_user = AsyncMock(
            return_value=_totp_row(user.id, pyotp.random_base32(), confirmed=True)
        )

        with pytest.raises(Exception) as exc_info:
            await service.enroll(user)
        assert exc_info.value.status_code == 400  # type: ignore[union-attr]


@pytest.mark.unit
class TestConfirm:
    """Possession proof + backup code generation (revealed once)."""

    async def test_confirm_with_valid_code_activates_and_returns_codes(self) -> None:
        """Valid first code: confirmed_at set, 10 hex backup codes returned."""
        service, repo, db = _service_with_mocks()
        user = _make_user()
        secret = pyotp.random_base32()
        row = _totp_row(user.id, secret, confirmed=False)
        repo.get_for_user = AsyncMock(return_value=row)

        codes = await service.confirm(user, _current_code(secret))

        assert row.confirmed_at is not None
        assert len(codes) == MFA_BACKUP_CODES_COUNT
        assert all(len(c) == MFA_BACKUP_CODE_HEX_CHARS for c in codes)
        assert len(set(codes)) == MFA_BACKUP_CODES_COUNT
        # Hashes persisted, raw codes never.
        hashed = [
            call.args[0].code_hash
            for call in db.add.call_args_list
            if isinstance(call.args[0], MFABackupCode)
        ]
        assert len(hashed) == MFA_BACKUP_CODES_COUNT
        assert set(hashed) == {hash_backup_code(c) for c in codes}
        db.commit.assert_awaited()

    async def test_confirm_with_invalid_code_rejects(self) -> None:
        """A wrong code leaves the enrollment unconfirmed."""
        service, repo, _db = _service_with_mocks()
        user = _make_user()
        row = _totp_row(user.id, pyotp.random_base32(), confirmed=False)
        repo.get_for_user = AsyncMock(return_value=row)

        with pytest.raises(Exception) as exc_info:
            await service.confirm(user, "000000")
        assert exc_info.value.status_code == 400  # type: ignore[union-attr]
        assert row.confirmed_at is None

    async def test_confirm_without_enrollment_rejects(self) -> None:
        """No pending draft → 400."""
        service, _repo, _db = _service_with_mocks()
        with pytest.raises(Exception) as exc_info:
            await service.confirm(_make_user(), "123456")
        assert exc_info.value.status_code == 400  # type: ignore[union-attr]


@pytest.mark.unit
class TestVerifyForLogin:
    """Second login step: TOTP with anti-replay, or single-use backup code."""

    async def test_valid_totp_code_accepted_and_step_recorded(self) -> None:
        """A valid current code passes and records its timestep."""
        service, repo, db = _service_with_mocks()
        secret = pyotp.random_base32()
        row = _totp_row(uuid.uuid4(), secret, confirmed=True)
        repo.get_for_user = AsyncMock(return_value=row)

        await service.verify_for_login(row.user_id, _current_code(secret))

        assert row.last_used_step is not None
        db.commit.assert_awaited()

    async def test_same_code_replay_rejected(self) -> None:
        """The same code cannot authenticate twice within its window."""
        service, repo, _db = _service_with_mocks()
        secret = pyotp.random_base32()
        row = _totp_row(uuid.uuid4(), secret, confirmed=True)
        repo.get_for_user = AsyncMock(return_value=row)
        code = _current_code(secret)

        await service.verify_for_login(row.user_id, code)

        with pytest.raises(Exception) as exc_info:
            await service.verify_for_login(row.user_id, code)
        assert exc_info.value.status_code == 401  # type: ignore[union-attr]

    async def test_unconfirmed_totp_rejects(self) -> None:
        """An unconfirmed enrollment can never authenticate."""
        service, repo, _db = _service_with_mocks()
        secret = pyotp.random_base32()
        row = _totp_row(uuid.uuid4(), secret, confirmed=False)
        repo.get_for_user = AsyncMock(return_value=row)

        with pytest.raises(Exception) as exc_info:
            await service.verify_for_login(row.user_id, _current_code(secret))
        assert exc_info.value.status_code == 401  # type: ignore[union-attr]

    async def test_backup_code_consumed_single_use(self) -> None:
        """A valid backup code passes once and is stamped used."""
        service, repo, db = _service_with_mocks()
        secret = pyotp.random_base32()
        row = _totp_row(uuid.uuid4(), secret, confirmed=True)
        repo.get_for_user = AsyncMock(return_value=row)
        raw_code = "a1b2c3d4e5"
        code_row = MFABackupCode(
            id=uuid.uuid4(),
            user_id=row.user_id,
            code_hash=hash_backup_code(raw_code),
            used_at=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        repo.get_unused_code_by_hash = AsyncMock(return_value=code_row)

        await service.verify_for_login(row.user_id, raw_code)

        assert code_row.used_at is not None
        db.commit.assert_awaited()

    async def test_unknown_code_rejects(self) -> None:
        """Neither a valid TOTP nor a known backup code → 401."""
        service, repo, _db = _service_with_mocks()
        row = _totp_row(uuid.uuid4(), pyotp.random_base32(), confirmed=True)
        repo.get_for_user = AsyncMock(return_value=row)

        with pytest.raises(Exception) as exc_info:
            await service.verify_for_login(row.user_id, "ffffffffff")
        assert exc_info.value.status_code == 401  # type: ignore[union-attr]


@pytest.mark.unit
class TestManagement:
    """Disable, regenerate, status."""

    async def test_disable_removes_totp_and_codes(self) -> None:
        """Disable drops the secret row and every backup code."""
        service, repo, db = _service_with_mocks()
        user = _make_user()
        repo.get_for_user = AsyncMock(
            return_value=_totp_row(user.id, pyotp.random_base32(), confirmed=True)
        )

        await service.disable(user)

        repo.delete_for_user.assert_awaited_once_with(user.id)
        repo.delete_codes_for_user.assert_awaited_once_with(user.id)
        db.commit.assert_awaited()

    async def test_disable_without_totp_rejects(self) -> None:
        """Nothing to disable → 400."""
        service, _repo, _db = _service_with_mocks()
        with pytest.raises(Exception) as exc_info:
            await service.disable(_make_user())
        assert exc_info.value.status_code == 400  # type: ignore[union-attr]

    async def test_regenerate_invalidates_old_codes(self) -> None:
        """Regeneration wipes the previous set and returns a fresh one."""
        service, repo, _db = _service_with_mocks()
        user = _make_user()
        repo.get_for_user = AsyncMock(
            return_value=_totp_row(user.id, pyotp.random_base32(), confirmed=True)
        )

        codes = await service.regenerate_backup_codes(user)

        repo.delete_codes_for_user.assert_awaited_once_with(user.id)
        assert len(codes) == MFA_BACKUP_CODES_COUNT

    async def test_status_reports_active_and_remaining_codes(self) -> None:
        """Status mirrors confirmation state + unused backup code count."""
        service, repo, _db = _service_with_mocks()
        user = _make_user()
        repo.get_for_user = AsyncMock(
            return_value=_totp_row(user.id, pyotp.random_base32(), confirmed=True)
        )
        repo.count_unused_codes = AsyncMock(return_value=7)

        status = await service.get_status(user)

        assert status.active is True
        assert status.backup_codes_remaining == 7


@pytest.mark.unit
class TestPendingToken:
    """Two-step login bridge: single-use Redis token."""

    async def test_pending_token_roundtrip_single_use(self) -> None:
        """Create → consume returns the payload; token is GETDEL'd."""
        service, _repo, _db = _service_with_mocks()
        user_id = uuid.uuid4()
        stored: dict[str, str] = {}

        redis = AsyncMock()

        async def fake_set(key: str, value: str, ex: int) -> None:
            stored[key] = value

        async def fake_getdel(key: str) -> str | None:
            return stored.pop(key, None)

        redis.set = AsyncMock(side_effect=fake_set)
        redis.getdel = AsyncMock(side_effect=fake_getdel)

        # Patched where the call LIVES, not where the caller lives: the bridge
        # runs on the shared single-use store, so patching
        # ``totp_service.get_redis_session`` would silently hit a real Redis and
        # leave this test green while measuring nothing (observed 2026-08-24).
        with patch("src.core.single_use_token.get_redis_session", return_value=redis):
            token = await service.create_pending_token(user_id, remember_me=True)
            payload = await service.consume_pending_token(token)
            replay = await service.consume_pending_token(token)

        assert payload is not None
        assert payload.user_id == str(user_id)
        assert payload.remember_me is True
        assert replay is None
