"""POST /skills/import-from-url endpoint contract (UXR Lot 10, B12).

The endpoint is a thin composition: hardened fetch → the EXACT same
``SkillImportService.import_upload`` call as the file-upload path (zero
bypass), with the outcome metric incremented on every path.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from src.core.config import settings
from src.domains.skills.router import (
    SkillUrlImportRequest,
    _url_import_rate_limit,
    import_skill_from_url,
)
from src.infrastructure.observability.metrics_registry import skill_url_imports_total

pytestmark = pytest.mark.unit

SKILL_BYTES = b"---\nname: net-skill\ndescription: d\n---\nBody."


def _user() -> MagicMock:
    user = MagicMock()
    user.id = uuid4()
    return user


def _outcome_value(outcome: str) -> float:
    return skill_url_imports_total.labels(outcome=outcome)._value.get()


class TestImportFromUrlEndpoint:
    async def test_pipeline_receives_fetched_bytes_verbatim(self) -> None:
        imported: dict[str, Any] = {"name": "net-skill", "description": "d"}
        svc = MagicMock()
        svc.import_upload = AsyncMock(return_value=imported)
        before = _outcome_value("ok")
        with (
            patch(
                "src.domains.skills.url_import.fetch_skill_from_url",
                AsyncMock(return_value=(SKILL_BYTES, "SKILL.md")),
            ),
            patch("src.domains.skills.import_service.SkillImportService", return_value=svc),
        ):
            user = _user()
            result = await import_skill_from_url(
                body=SkillUrlImportRequest(url="https://example.com/SKILL.md"),
                user=user,
                db=MagicMock(),
            )
        svc.import_upload.assert_awaited_once_with(
            SKILL_BYTES, "SKILL.md", owner_id=user.id, is_system=False
        )
        assert result["name"] == "net-skill"
        assert result["scope"] == "user"
        assert _outcome_value("ok") == before + 1

    async def test_pipeline_rejection_propagates_and_counts(self) -> None:
        svc = MagicMock()
        svc.import_upload = AsyncMock(side_effect=HTTPException(status_code=409, detail="dup"))
        before = _outcome_value("pipeline_rejected")
        with (
            patch(
                "src.domains.skills.url_import.fetch_skill_from_url",
                AsyncMock(return_value=(SKILL_BYTES, "SKILL.md")),
            ),
            patch("src.domains.skills.import_service.SkillImportService", return_value=svc),
        ):
            with pytest.raises(HTTPException) as exc:
                await import_skill_from_url(
                    body=SkillUrlImportRequest(url="https://example.com/SKILL.md"),
                    user=_user(),
                    db=MagicMock(),
                )
        assert exc.value.status_code == 409
        assert _outcome_value("pipeline_rejected") == before + 1

    async def test_blocked_fetch_counts_blocked(self) -> None:
        before = _outcome_value("blocked")
        with patch(
            "src.domains.skills.url_import.fetch_skill_from_url",
            AsyncMock(side_effect=HTTPException(status_code=400, detail="url_blocked: x")),
        ):
            with pytest.raises(HTTPException):
                await import_skill_from_url(
                    body=SkillUrlImportRequest(url="https://127.0.0.1/s.zip"),
                    user=_user(),
                    db=MagicMock(),
                )
        assert _outcome_value("blocked") == before + 1

    async def test_disabled_flag_refuses(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "skills_url_import_enabled", False)
        with pytest.raises(HTTPException) as exc:
            await import_skill_from_url(
                body=SkillUrlImportRequest(url="https://example.com/SKILL.md"),
                user=_user(),
                db=MagicMock(),
            )
        assert exc.value.status_code == 400


class TestUrlImportRateLimit:
    """Per-user sliding window on outbound fetches (settings-driven)."""

    async def test_exhausted_window_is_429(self) -> None:
        limiter = MagicMock()
        limiter.acquire = AsyncMock(return_value=False)
        with patch(
            "src.infrastructure.rate_limiting.redis_limiter.get_rate_limiter",
            AsyncMock(return_value=limiter),
        ):
            with pytest.raises(HTTPException) as exc:
                await _url_import_rate_limit(user=_user())
        assert exc.value.status_code == 429
        # Settings-driven, never hardcoded in the assertion (repo rule).
        limiter.acquire.assert_awaited_once()
        kwargs = limiter.acquire.await_args.kwargs
        assert kwargs["max_calls"] == settings.skills_url_import_rate_max_calls
        assert kwargs["window_seconds"] == settings.skills_url_import_rate_window_seconds

    async def test_within_window_passes(self) -> None:
        limiter = MagicMock()
        limiter.acquire = AsyncMock(return_value=True)
        with patch(
            "src.infrastructure.rate_limiting.redis_limiter.get_rate_limiter",
            AsyncMock(return_value=limiter),
        ):
            await _url_import_rate_limit(user=_user())

    async def test_redis_outage_fails_open(self) -> None:
        """A Redis outage must not take the import feature down (auth policy)."""
        with patch(
            "src.infrastructure.rate_limiting.redis_limiter.get_rate_limiter",
            AsyncMock(side_effect=RuntimeError("redis down")),
        ):
            await _url_import_rate_limit(user=_user())
