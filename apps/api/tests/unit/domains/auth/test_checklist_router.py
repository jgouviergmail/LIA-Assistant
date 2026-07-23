"""PATCH /auth/me/onboarding-checklist (UXR Lot 6, A10).

Pins the stamp-once contract: timestamps are written on true TRANSITIONS
only — a replayed PATCH (retry, second tab) never overwrites history — and
the write is a full NEW-dict replacement (JSONB new-dict rule).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domains.auth.checklist_router import update_onboarding_checklist
from src.domains.auth.schemas import OnboardingChecklistRequest

pytestmark = pytest.mark.unit


def _user(checklist: dict[str, Any] | None) -> MagicMock:
    user = MagicMock()
    user.onboarding_checklist = checklist
    return user


def _db() -> MagicMock:
    db = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


class TestChecklistStampOnce:
    async def test_first_dismiss_stamps_an_iso_utc_timestamp(self) -> None:
        user = _user(None)
        response = await update_onboarding_checklist(
            OnboardingChecklistRequest(dismissed=True), user=user, db=_db()
        )
        stamped = response.onboarding_checklist["dismissed_at"]
        assert stamped.endswith("+00:00")
        assert user.onboarding_checklist == {"dismissed_at": stamped}

    async def test_replayed_dismiss_never_overwrites_history(self) -> None:
        original = {"dismissed_at": "2026-01-01T00:00:00+00:00"}
        user = _user(dict(original))
        db = _db()
        response = await update_onboarding_checklist(
            OnboardingChecklistRequest(dismissed=True), user=user, db=db
        )
        assert response.onboarding_checklist == original
        db.commit.assert_not_awaited()

    async def test_celebrate_after_dismiss_keeps_both(self) -> None:
        user = _user({"dismissed_at": "2026-01-01T00:00:00+00:00"})
        before = user.onboarding_checklist
        response = await update_onboarding_checklist(
            OnboardingChecklistRequest(celebrated=True), user=user, db=_db()
        )
        assert response.onboarding_checklist["dismissed_at"] == "2026-01-01T00:00:00+00:00"
        assert "celebrated_at" in response.onboarding_checklist
        # New-dict rule: the stored value is a NEW object, never a mutation.
        assert user.onboarding_checklist is not before

    async def test_noop_request_writes_nothing(self) -> None:
        db = _db()
        response = await update_onboarding_checklist(
            OnboardingChecklistRequest(), user=_user(None), db=db
        )
        assert response.onboarding_checklist == {}
        db.commit.assert_not_awaited()
