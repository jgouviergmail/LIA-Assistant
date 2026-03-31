"""Unit tests for AccountDeletionService.

Tests the orchestration logic: validation, table purge order, PII scrubbing,
and external service cleanup. Uses mocked DB and services.
"""

import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.auth.models import User
from src.domains.users.account_deletion_service import AccountDeletionService
from src.infrastructure.database.registry import import_all_models

# Ensure all SQLAlchemy models are loaded so relationship() references resolve
import_all_models()


# ==============================================================================
# FACTORY FUNCTIONS
# ==============================================================================


def _make_user(
    *,
    user_id: uuid.UUID | None = None,
    is_active: bool = False,
    is_superuser: bool = False,
    deleted_at: datetime | None = None,
    email: str = "test@example.com",
    full_name: str = "Test User",
) -> User:
    """Create a User ORM instance for testing."""
    now = datetime.now(UTC)
    return User(
        id=user_id or uuid.uuid4(),
        email=email,
        full_name=full_name,
        hashed_password="hashed_pw",
        is_active=is_active,
        is_verified=True,
        is_superuser=is_superuser,
        language="fr",
        timezone="Europe/Paris",
        memory_enabled=True,
        voice_enabled=False,
        theme="system",
        color_theme="default",
        image_generation_enabled=True,
        image_generation_default_quality="low",
        image_generation_default_size="portrait",
        image_generation_output_format="png",
        deleted_at=deleted_at,
        created_at=now,
        updated_at=now,
    )


def _mock_db_with_user(user: User | None) -> AsyncMock:
    """Create a mock AsyncSession that returns the given user on SELECT FOR UPDATE."""
    db = AsyncMock(spec=AsyncSession)
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = user
    db.execute = AsyncMock(return_value=result_mock)
    db.commit = AsyncMock()
    db.add = MagicMock()
    return db


# ==============================================================================
# VALIDATION TESTS
# ==============================================================================


@pytest.mark.unit
class TestAccountDeletionValidation:
    """Tests for _load_and_validate_user preconditions."""

    async def test_rejects_not_found_user(self) -> None:
        """404 when user does not exist."""
        db = _mock_db_with_user(None)
        service = AccountDeletionService(db)

        with pytest.raises(Exception) as exc_info:
            await service._load_and_validate_user(uuid.uuid4())
        assert exc_info.value.status_code == 404  # type: ignore[union-attr]

    async def test_rejects_superuser(self) -> None:
        """409 when user is a superuser."""
        user = _make_user(is_superuser=True)
        db = _mock_db_with_user(user)
        service = AccountDeletionService(db)

        with pytest.raises(Exception) as exc_info:
            await service._load_and_validate_user(user.id)
        assert exc_info.value.status_code == 409  # type: ignore[union-attr]

    async def test_rejects_active_user(self) -> None:
        """409 when user is still active (not deactivated)."""
        user = _make_user(is_active=True)
        db = _mock_db_with_user(user)
        service = AccountDeletionService(db)

        with pytest.raises(Exception) as exc_info:
            await service._load_and_validate_user(user.id)
        assert exc_info.value.status_code == 409  # type: ignore[union-attr]
        assert "deactivated" in str(exc_info.value.detail).lower()  # type: ignore[union-attr]

    async def test_rejects_already_deleted(self) -> None:
        """409 when user is already deleted."""
        user = _make_user(deleted_at=datetime.now(UTC))
        db = _mock_db_with_user(user)
        service = AccountDeletionService(db)

        with pytest.raises(Exception) as exc_info:
            await service._load_and_validate_user(user.id)
        assert exc_info.value.status_code == 409  # type: ignore[union-attr]
        assert "already deleted" in str(exc_info.value.detail).lower()  # type: ignore[union-attr]

    async def test_accepts_deactivated_user(self) -> None:
        """Valid user: deactivated, not superuser, not deleted."""
        user = _make_user(is_active=False, is_superuser=False, deleted_at=None)
        db = _mock_db_with_user(user)
        service = AccountDeletionService(db)

        result = await service._load_and_validate_user(user.id)
        assert result.id == user.id


# ==============================================================================
# PII SCRUBBING TESTS
# ==============================================================================


@pytest.mark.unit
class TestMarkUserDeleted:
    """Tests for _mark_user_deleted PII scrubbing."""

    async def test_sets_deleted_at_and_reason(self) -> None:
        """deleted_at is set to now, deleted_reason is set."""
        user = _make_user()
        db = AsyncMock(spec=AsyncSession)
        service = AccountDeletionService(db)

        await service._mark_user_deleted(user, "Account closed by admin")

        assert user.deleted_at is not None
        assert user.deleted_reason == "Account closed by admin"
        assert user.is_deleted is True

    async def test_preserves_email_and_name(self) -> None:
        """Email and full_name must be preserved for billing contact."""
        user = _make_user(email="billing@test.com", full_name="Billing User")
        db = AsyncMock(spec=AsyncSession)
        service = AccountDeletionService(db)

        await service._mark_user_deleted(user, None)

        assert user.email == "billing@test.com"
        assert user.full_name == "Billing User"

    async def test_scrubs_sensitive_pii(self) -> None:
        """Sensitive PII fields must be set to None."""
        user = _make_user()
        user.hashed_password = "secret_hash"
        user.oauth_provider = "google"
        user.oauth_provider_id = "google_123"
        user.picture_url = "https://example.com/pic.jpg"
        user.home_location_encrypted = "encrypted_location"
        db = AsyncMock(spec=AsyncSession)
        service = AccountDeletionService(db)

        await service._mark_user_deleted(user, None)

        assert user.hashed_password is None
        assert user.oauth_provider is None
        assert user.oauth_provider_id is None
        assert user.picture_url is None
        assert user.home_location_encrypted is None


# ==============================================================================
# FILE CLEANUP TESTS
# ==============================================================================


@pytest.mark.unit
class TestFileCleanup:
    """Tests for physical file cleanup."""

    def test_cleanup_attachment_files_existing_dir(self, tmp_path: Path) -> None:
        """Deletes user attachment directory when it exists."""
        user_id = uuid.uuid4()
        user_dir = tmp_path / str(user_id)
        user_dir.mkdir()
        (user_dir / "test.pdf").write_text("content")

        db = AsyncMock(spec=AsyncSession)
        service = AccountDeletionService(db)

        with patch.object(
            type(service),
            "_cleanup_attachment_files",
            wraps=service._cleanup_attachment_files,
        ):
            with patch("src.domains.users.account_deletion_service.settings") as mock_settings:
                mock_settings.attachments_storage_path = str(tmp_path)
                result = service._cleanup_attachment_files(user_id)

        assert result == 1
        assert not user_dir.exists()

    def test_cleanup_attachment_files_missing_dir(self, tmp_path: Path) -> None:
        """Returns 0 when user directory doesn't exist."""
        db = AsyncMock(spec=AsyncSession)
        service = AccountDeletionService(db)

        with patch("src.domains.users.account_deletion_service.settings") as mock_settings:
            mock_settings.attachments_storage_path = str(tmp_path)
            result = service._cleanup_attachment_files(uuid.uuid4())

        assert result == 0

    def test_cleanup_rag_files_existing_dir(self, tmp_path: Path) -> None:
        """Deletes user RAG upload directory when it exists."""
        user_id = uuid.uuid4()
        space_dir = tmp_path / str(user_id) / "space1"
        space_dir.mkdir(parents=True)
        (space_dir / "doc.pdf").write_text("content")

        db = AsyncMock(spec=AsyncSession)
        service = AccountDeletionService(db)

        with patch("src.domains.users.account_deletion_service.settings") as mock_settings:
            mock_settings.rag_spaces_storage_path = str(tmp_path)
            result = service._cleanup_rag_files(user_id)

        assert result == 1
        assert not (tmp_path / str(user_id)).exists()


# ==============================================================================
# CONNECTOR DEACTIVATION TESTS
# ==============================================================================


@pytest.mark.unit
class TestDeactivateConnectors:
    """Tests for _deactivate_connectors."""

    async def test_deactivate_returns_total_count(self) -> None:
        """Returns sum of OAuth (REVOKED) + non-OAuth (INACTIVE) counts."""
        db = AsyncMock(spec=AsyncSession)

        # Mock two execute calls: first for OAuth update, second for non-OAuth update
        oauth_result = MagicMock()
        oauth_result.rowcount = 3
        non_oauth_result = MagicMock()
        non_oauth_result.rowcount = 2
        db.execute = AsyncMock(side_effect=[oauth_result, non_oauth_result])

        service = AccountDeletionService(db)
        count = await service._deactivate_connectors(uuid.uuid4())

        assert count == 5
        assert db.execute.call_count == 2
