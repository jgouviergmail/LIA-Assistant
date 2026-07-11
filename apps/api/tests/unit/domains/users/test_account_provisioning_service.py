"""
Unit tests for AccountProvisioningService (users domain).

Verifies the behavior-preserving extraction of the new-user provisioning
cascade from the auth service (ADR-126): skill states + usage limits,
with caller-controlled transaction topology (``commit_per_step``).
"""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.core.config import settings
from src.domains.users.account_provisioning_service import AccountProvisioningService


@pytest.fixture
def mock_db() -> AsyncMock:
    """Create a mock async database session."""
    db = AsyncMock()
    db.commit = AsyncMock()
    return db


@pytest.fixture
def service(mock_db: AsyncMock) -> AccountProvisioningService:
    """Create the provisioning service on the mocked session."""
    return AccountProvisioningService(mock_db)


class TestProvisionNewUser:
    """Tests for AccountProvisioningService.provision_new_user."""

    async def test_provisions_skills_and_limits_when_flag_enabled(
        self,
        service: AccountProvisioningService,
        mock_db: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Both steps run (skills then limits) when usage limits are enabled."""
        monkeypatch.setattr(settings, "usage_limits_enabled", True, raising=False)
        user_id = uuid4()

        with (
            patch("src.domains.skills.preference_service.SkillPreferenceService") as skill_cls,
            patch("src.domains.usage_limits.service.UsageLimitService") as limit_cls,
        ):
            skill_cls.return_value.ensure_user_skills = AsyncMock(return_value=3)
            limit_cls.return_value.create_default_limits = AsyncMock()

            await service.provision_new_user(user_id, commit_per_step=False)

            skill_cls.assert_called_once_with(mock_db)
            skill_cls.return_value.ensure_user_skills.assert_awaited_once_with(user_id)
            limit_cls.assert_called_once_with(mock_db)
            limit_cls.return_value.create_default_limits.assert_awaited_once_with(user_id)

    async def test_usage_limits_skipped_when_flag_disabled(
        self,
        service: AccountProvisioningService,
        mock_db: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """The usage-limits step is gated by the feature flag."""
        monkeypatch.setattr(settings, "usage_limits_enabled", False, raising=False)
        user_id = uuid4()

        with (
            patch("src.domains.skills.preference_service.SkillPreferenceService") as skill_cls,
            patch("src.domains.usage_limits.service.UsageLimitService") as limit_cls,
        ):
            skill_cls.return_value.ensure_user_skills = AsyncMock(return_value=0)

            await service.provision_new_user(user_id, commit_per_step=True)

            skill_cls.return_value.ensure_user_skills.assert_awaited_once_with(user_id)
            limit_cls.assert_not_called()
            # Only the skills step commits when limits are disabled
            assert mock_db.commit.await_count == 1

    async def test_commit_per_step_true_commits_after_each_step(
        self,
        service: AccountProvisioningService,
        mock_db: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Registration flow topology: one commit after each step."""
        monkeypatch.setattr(settings, "usage_limits_enabled", True, raising=False)

        with (
            patch("src.domains.skills.preference_service.SkillPreferenceService") as skill_cls,
            patch("src.domains.usage_limits.service.UsageLimitService") as limit_cls,
        ):
            skill_cls.return_value.ensure_user_skills = AsyncMock(return_value=1)
            limit_cls.return_value.create_default_limits = AsyncMock()

            await service.provision_new_user(uuid4(), commit_per_step=True)

            assert mock_db.commit.await_count == 2

    async def test_commit_per_step_false_never_commits(
        self,
        service: AccountProvisioningService,
        mock_db: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """OAuth flow topology: the caller owns the single final commit."""
        monkeypatch.setattr(settings, "usage_limits_enabled", True, raising=False)

        with (
            patch("src.domains.skills.preference_service.SkillPreferenceService") as skill_cls,
            patch("src.domains.usage_limits.service.UsageLimitService") as limit_cls,
        ):
            skill_cls.return_value.ensure_user_skills = AsyncMock(return_value=1)
            limit_cls.return_value.create_default_limits = AsyncMock()

            await service.provision_new_user(uuid4(), commit_per_step=False)

            mock_db.commit.assert_not_awaited()

    async def test_default_is_no_commit(
        self,
        service: AccountProvisioningService,
        mock_db: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Omitting commit_per_step must be the safe (no-commit) topology."""
        monkeypatch.setattr(settings, "usage_limits_enabled", False, raising=False)

        with patch("src.domains.skills.preference_service.SkillPreferenceService") as skill_cls:
            skill_cls.return_value.ensure_user_skills = AsyncMock(return_value=0)

            await service.provision_new_user(uuid4())

            mock_db.commit.assert_not_awaited()
