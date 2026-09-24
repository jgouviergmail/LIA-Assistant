"""A demonstrator account starts with the demonstration turned on.

``demo_defaults.py`` already opens the instance-level half of the debug panel
(``DEBUG_PANEL_USER_ACCESS_ENABLED``), with a docstring that states the intent
plainly: "off everywhere else because it exposes a run's internals, and exactly
what a visitor should see here — the routing, the plan, the tokens spent".

The other half was missing. The per-account flag is an opt-in whose default is
``False`` (the model documents it as such), so every visitor landed on a debug
panel that displayed and stayed empty, and had to go and find the switch in
their settings. Worse on this instance than anywhere else: its database lives
on tmpfs, so each visitor — and the operator — lost that choice at every
restart.

Owner arbitration 2026-08-07: turn it on by default for demonstrator visitors.
It stays a PREFERENCE, so a visitor can still switch it off, and an operator
can still close the instance-level gate for everybody.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.config import settings
from src.domains.users.demo_account_preferences import (
    DEMO_ACCOUNT_PREFERENCES,
    apply_demo_account_preferences,
)

pytestmark = pytest.mark.unit


class _FakeUser:
    """Stands in for the ORM row: only the preferences matter here."""

    def __init__(self) -> None:
        self.debug_panel_enabled = False


@pytest.fixture
def db_with_user() -> tuple[AsyncMock, _FakeUser]:
    user = _FakeUser()
    db = AsyncMock()
    db.get = AsyncMock(return_value=user)
    return db, user


class TestOnADemonstrator:
    async def test_the_debug_panel_starts_on(
        self, db_with_user: tuple[AsyncMock, _FakeUser], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "demo_mode_enabled", True, raising=False)
        db, user = db_with_user

        applied = await apply_demo_account_preferences(db, uuid4())

        assert applied is True
        assert user.debug_panel_enabled is True

    async def test_every_declared_preference_is_applied(
        self, db_with_user: tuple[AsyncMock, _FakeUser], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The table is the contract: an entry that is never applied is a lie."""
        monkeypatch.setattr(settings, "demo_mode_enabled", True, raising=False)
        db, user = db_with_user

        await apply_demo_account_preferences(db, uuid4())

        for name, value in DEMO_ACCOUNT_PREFERENCES.items():
            assert getattr(user, name) == value

    async def test_it_reads_the_row_rather_than_updating_blind(
        self, db_with_user: tuple[AsyncMock, _FakeUser], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An UPDATE would match nothing on the OAuth path.

        Email/password registration commits before provisioning; the OAuth
        callback does not — it commits once at the end. A statement issued
        against a row that is still pending updates zero rows and says nothing,
        which is precisely how a feature ends up silently inert.
        """
        monkeypatch.setattr(settings, "demo_mode_enabled", True, raising=False)
        db, _ = db_with_user
        user_id = uuid4()

        await apply_demo_account_preferences(db, user_id)

        db.get.assert_awaited_once()
        assert db.get.await_args.args[1] == user_id


class TestEverywhereElse:
    async def test_a_private_instance_is_left_alone(
        self, db_with_user: tuple[AsyncMock, _FakeUser], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The panel exposes a run's internals; only a showcase wants it on."""
        monkeypatch.setattr(settings, "demo_mode_enabled", False, raising=False)
        db, user = db_with_user

        applied = await apply_demo_account_preferences(db, uuid4())

        assert applied is False
        assert user.debug_panel_enabled is False
        db.get.assert_not_awaited()


class TestItNeverBreaksASignUp:
    async def test_an_absent_row_is_reported_not_raised(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "demo_mode_enabled", True, raising=False)
        db = AsyncMock()
        db.get = AsyncMock(return_value=None)

        assert await apply_demo_account_preferences(db, uuid4()) is False

    async def test_a_failing_session_is_swallowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A visitor without a debug panel is disappointed; one who cannot
        sign up sees nothing at all — the same trade-off the shared search key
        already makes."""
        monkeypatch.setattr(settings, "demo_mode_enabled", True, raising=False)
        db = AsyncMock()
        db.get = AsyncMock(side_effect=RuntimeError("connection lost"))

        assert await apply_demo_account_preferences(db, uuid4()) is False


class TestItIsActuallyWired:
    async def test_the_provisioning_cascade_calls_it(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A step nothing calls is a step nobody has."""
        monkeypatch.setattr(settings, "demo_mode_enabled", False, raising=False)
        monkeypatch.setattr(settings, "usage_limits_enabled", False, raising=False)
        from src.domains.users.account_provisioning_service import AccountProvisioningService

        called: list[object] = []

        async def _spy(db: object, user_id: object) -> bool:
            called.append(user_id)
            return False

        monkeypatch.setattr(
            "src.domains.users.demo_account_preferences.apply_demo_account_preferences",
            _spy,
        )
        db = AsyncMock()
        user_id = uuid4()

        with pytest.MonkeyPatch.context() as inner:
            inner.setattr(
                "src.domains.skills.preference_service.SkillPreferenceService",
                lambda _db: AsyncMock(ensure_user_skills=AsyncMock()),
            )
            await AccountProvisioningService(db).provision_new_user(user_id)

        assert called == [user_id]
