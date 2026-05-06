"""Unit tests for the journal user-model portrait builder (ADR-079).

Validates the standalone ``build_journal_user_model_block`` function that
diffuses the compiled portrait into every flow where LIA speaks to the user.

Coverage targets:
- Two formats (full / brief) returning the right portrait field.
- Graceful degradation: feature flag off, user toggle off, missing user,
  empty portrait, runtime error.
- Output shape: well-formed ``<UserModelContext>`` block with the
  anti-duplication directive.
- Prometheus metric increment on the success path.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.journals.portrait_builder import build_journal_user_model_block

pytestmark = pytest.mark.unit


# -----------------------------------------------------------------------------
# Test helpers — emulate the SQLAlchemy result.one_or_none() return shape.
# -----------------------------------------------------------------------------


def _make_db_context(row: tuple[bool, str | None, str | None] | None) -> Any:
    """Return an asynccontextmanager that yields a session whose ``execute``
    produces a result with ``one_or_none()`` returning ``row``.

    Args:
        row: ``(journals_enabled, portrait_full, portrait_brief)`` tuple,
            or ``None`` when the user query yields no rows.
    """

    @asynccontextmanager
    async def _ctx():
        result_obj = MagicMock(name="Result")
        result_obj.one_or_none.return_value = row

        session = MagicMock(name="AsyncSession")

        async def _execute(_stmt: Any) -> Any:
            return result_obj

        session.execute = _execute
        yield session

    return _ctx


def _patch_settings(*, system_enabled: bool):
    return patch(
        "src.domains.journals.portrait_builder.settings",
        MagicMock(journals_enabled=system_enabled),
    )


def _patch_db_context(row: tuple[bool, str | None, str | None] | None):
    return patch(
        "src.domains.journals.portrait_builder.get_db_context",
        new=_make_db_context(row)(),
    )


def _patch_db_context_factory(row: tuple[bool, str | None, str | None] | None):
    """Patch ``get_db_context`` with a factory that produces a fresh context per call."""
    return patch(
        "src.domains.journals.portrait_builder.get_db_context",
        new=_make_db_context(row),
    )


# -----------------------------------------------------------------------------
# Feature-flag short-circuits
# -----------------------------------------------------------------------------


class TestPortraitBuilderFeatureFlags:
    """The builder must short-circuit cleanly when journals are disabled."""

    @pytest.mark.asyncio
    async def test_returns_empty_when_system_flag_off(self) -> None:
        with _patch_settings(system_enabled=False):
            result = await build_journal_user_model_block(uuid4(), format="brief")
        assert result == ""

    @pytest.mark.asyncio
    async def test_returns_empty_when_user_toggle_off(self) -> None:
        # System enabled, but user toggled journals off → no diffusion.
        with (
            _patch_settings(system_enabled=True),
            _patch_db_context_factory((False, "ignored", "ignored")),
        ):
            result = await build_journal_user_model_block(uuid4(), format="brief")
        assert result == ""

    @pytest.mark.asyncio
    async def test_returns_empty_when_user_not_found(self) -> None:
        with (
            _patch_settings(system_enabled=True),
            _patch_db_context_factory(None),
        ):
            result = await build_journal_user_model_block(uuid4(), format="brief")
        assert result == ""


# -----------------------------------------------------------------------------
# Graceful degradation on missing portrait
# -----------------------------------------------------------------------------


class TestPortraitBuilderGracefulDegradation:
    """Empty / NULL portraits must yield ``""`` so callers stay simple."""

    @pytest.mark.asyncio
    async def test_returns_empty_when_portrait_is_none(self) -> None:
        with (
            _patch_settings(system_enabled=True),
            _patch_db_context_factory((True, None, None)),
        ):
            result = await build_journal_user_model_block(uuid4(), format="full")
        assert result == ""

    @pytest.mark.asyncio
    async def test_returns_empty_when_portrait_is_blank(self) -> None:
        with (
            _patch_settings(system_enabled=True),
            _patch_db_context_factory((True, "   \n  ", "   ")),
        ):
            result = await build_journal_user_model_block(uuid4(), format="full")
        assert result == ""


# -----------------------------------------------------------------------------
# Format selection (full vs brief) and output shape
# -----------------------------------------------------------------------------


class TestPortraitBuilderFormatSelection:
    """The ``format`` argument controls which column is read."""

    @pytest.mark.asyncio
    async def test_full_format_returns_full_portrait(self) -> None:
        with (
            _patch_settings(system_enabled=True),
            _patch_db_context_factory((True, "FULL_PORTRAIT_BODY", "BRIEF_PORTRAIT_BODY")),
        ):
            result = await build_journal_user_model_block(uuid4(), format="full")
        assert "FULL_PORTRAIT_BODY" in result
        assert "BRIEF_PORTRAIT_BODY" not in result

    @pytest.mark.asyncio
    async def test_brief_format_returns_brief_portrait(self) -> None:
        with (
            _patch_settings(system_enabled=True),
            _patch_db_context_factory((True, "FULL_PORTRAIT_BODY", "BRIEF_PORTRAIT_BODY")),
        ):
            result = await build_journal_user_model_block(uuid4(), format="brief")
        assert "BRIEF_PORTRAIT_BODY" in result
        assert "FULL_PORTRAIT_BODY" not in result

    @pytest.mark.asyncio
    async def test_block_is_well_formed(self) -> None:
        """Output is a complete <UserModelContext> block with the discipline directive."""
        with (
            _patch_settings(system_enabled=True),
            _patch_db_context_factory((True, "PORTRAIT", "PORTRAIT_BRIEF")),
        ):
            result = await build_journal_user_model_block(uuid4(), format="full")
        assert result.startswith("<UserModelContext>")
        assert result.endswith("</UserModelContext>")
        # Discipline anti-doublon — must instruct the LLM not to duplicate
        # facts already injected by the psychological profile.
        assert "psychological profile" in result.lower()
        assert "silently" in result.lower()


# -----------------------------------------------------------------------------
# Metric instrumentation
# -----------------------------------------------------------------------------


class TestPortraitBuilderMetrics:
    """The success path must increment the diffusion counter."""

    @pytest.mark.asyncio
    async def test_success_increments_counter(self) -> None:
        counter_mock = MagicMock(name="Counter")
        counter_mock.labels.return_value = counter_mock

        with (
            _patch_settings(system_enabled=True),
            _patch_db_context_factory((True, "PORTRAIT", "PORTRAIT_BRIEF")),
            patch(
                "src.domains.journals.portrait_builder.journal_portrait_present_total",
                counter_mock,
            ),
        ):
            await build_journal_user_model_block(uuid4(), format="brief", flow="response")

        counter_mock.labels.assert_called_once_with(flow="response", format="brief")
        counter_mock.inc.assert_called_once()

    @pytest.mark.asyncio
    async def test_metric_failure_never_breaks_injection(self) -> None:
        """If the metrics client errors out, the prompt block must still be returned."""
        counter_mock = MagicMock(name="Counter")
        counter_mock.labels.side_effect = RuntimeError("metrics unavailable")

        with (
            _patch_settings(system_enabled=True),
            _patch_db_context_factory((True, "PORTRAIT", "PORTRAIT_BRIEF")),
            patch(
                "src.domains.journals.portrait_builder.journal_portrait_present_total",
                counter_mock,
            ),
        ):
            result = await build_journal_user_model_block(uuid4(), format="full", flow="planner")

        assert result.startswith("<UserModelContext>")
        assert "PORTRAIT" in result


# -----------------------------------------------------------------------------
# UUID input flexibility
# -----------------------------------------------------------------------------


class TestPortraitBuilderInputs:
    """Builder accepts both UUID instance and string for backward compat."""

    @pytest.mark.asyncio
    async def test_accepts_str_user_id(self) -> None:
        uid = uuid4()
        with (
            _patch_settings(system_enabled=True),
            _patch_db_context_factory((True, "PORTRAIT", "PORTRAIT_BRIEF")),
        ):
            result = await build_journal_user_model_block(str(uid), format="brief")
        assert "PORTRAIT_BRIEF" in result

    @pytest.mark.asyncio
    async def test_accepts_uuid_instance(self) -> None:
        uid = uuid4()
        with (
            _patch_settings(system_enabled=True),
            _patch_db_context_factory((True, "PORTRAIT", "PORTRAIT_BRIEF")),
        ):
            result = await build_journal_user_model_block(uid, format="full")
        assert "PORTRAIT" in result
