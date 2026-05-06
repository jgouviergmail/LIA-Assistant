"""Unit tests for the deferred self-evaluation section (ADR-079, T → T+1).

Validates ``_build_previous_turn_directives_section`` — the helper that
injects last turn's directives into the current extraction prompt so the
LLM can compare them with the user's reaction and signal an
``evidence_outcome``.

Three things must hold:

1. **Skip gracefully** when there is nothing to evaluate (empty list, malformed
   IDs, conversation reset).
2. **Cross-user isolation**: only entries belonging to the current user are
   loaded — never leak another user's directives via a stolen UUID.
3. **Section shape**: when entries exist, the rendered block contains the
   header, the discipline instructions (``evidence`` / ``contradiction``),
   and the visible epistemic metrics (`conf=...`, `ev=.../co=...`).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.journals.extraction_service import (
    _build_previous_turn_directives_section,
)
from src.domains.journals.models import (
    JournalEntry,
    JournalEntryConfidence,
    JournalEntryLevel,
)

pytestmark = pytest.mark.unit


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


def _make_entry(
    *,
    user_id: Any,
    entry_id: Any | None = None,
    theme: str = "user_observations",
    title: str = "Prefer concise replies",
    content: str = "WHEN the user asks a quick question → DO answer in one paragraph.",
    confidence: str = JournalEntryConfidence.MEDIUM.value,
    evidence_count: int = 0,
    contradiction_count: int = 0,
    search_hints: list[str] | None = None,
) -> JournalEntry:
    """Build a hydrated in-memory JournalEntry usable by the helper."""
    entry = JournalEntry(
        user_id=user_id,
        theme=theme,
        title=title,
        content=content,
        mood="reflective",
        status="active",
        source="conversation",
        char_count=len(content),
        level=JournalEntryLevel.L1.value,
        confidence=confidence,
        evidence_count=evidence_count,
        contradiction_count=contradiction_count,
        search_hints=search_hints,
    )
    entry.id = entry_id or uuid4()
    return entry


def _make_db_context_with_repo(repo_mock: MagicMock) -> Any:
    """Patch get_db_context so it yields a session whose service.repo is mocked."""

    @asynccontextmanager
    async def _ctx():
        session = MagicMock(name="AsyncSession")
        yield session

    return _ctx


def _patch_get_db_context():
    """Patch the resolver of ``get_db_context`` *inside* the helper.

    The helper imports it lazily via
    ``from src.infrastructure.database import get_db_context``, so we patch
    that target.
    """

    @asynccontextmanager
    async def _ctx():
        yield MagicMock(name="AsyncSession")

    return patch(
        "src.infrastructure.database.get_db_context",
        new=_ctx,
    )


def _patch_service_factory(get_by_id_results: list[JournalEntry | None]):
    """Patch JournalService so each ``repo.get_by_id`` call returns the next mock entry."""
    repo_mock = MagicMock()
    repo_mock.get_by_id = AsyncMock(side_effect=list(get_by_id_results))

    service_instance = MagicMock()
    service_instance.repo = repo_mock

    return patch(
        "src.domains.journals.service.JournalService",
        return_value=service_instance,
    )


# -----------------------------------------------------------------------------
# Skip paths
# -----------------------------------------------------------------------------


class TestSelfEvaluationSkipPaths:
    """The helper must short-circuit cleanly on every empty input."""

    @pytest.mark.asyncio
    async def test_empty_id_list_returns_empty_string(self) -> None:
        result = await _build_previous_turn_directives_section(
            user_id=str(uuid4()),
            previous_turn_injected_ids=[],
        )
        assert result == ""

    @pytest.mark.asyncio
    async def test_all_malformed_ids_returns_empty_string(self) -> None:
        """Garbage IDs are silently dropped (UUID parse fails) — no crash, no section."""
        with (
            _patch_get_db_context(),
            _patch_service_factory(get_by_id_results=[]),
        ):
            result = await _build_previous_turn_directives_section(
                user_id=str(uuid4()),
                previous_turn_injected_ids=["not-a-uuid", "garbage", "0000"],
            )
        assert result == ""

    @pytest.mark.asyncio
    async def test_all_ids_unknown_returns_empty_string(self) -> None:
        """Conversation reset / aged-out IDs simply skip the section."""
        with (
            _patch_get_db_context(),
            _patch_service_factory(get_by_id_results=[None, None]),
        ):
            result = await _build_previous_turn_directives_section(
                user_id=str(uuid4()),
                previous_turn_injected_ids=[str(uuid4()), str(uuid4())],
            )
        assert result == ""


# -----------------------------------------------------------------------------
# Cross-user isolation
# -----------------------------------------------------------------------------


class TestSelfEvaluationIsolation:
    """The helper must drop any entry that does not belong to the requested user."""

    @pytest.mark.asyncio
    async def test_other_user_entry_is_filtered_out(self) -> None:
        legit_user = uuid4()
        other_user = uuid4()
        entry_id = uuid4()

        # Repo returns an entry that belongs to a *different* user — must be dropped.
        foreign_entry = _make_entry(user_id=other_user, entry_id=entry_id)

        with (
            _patch_get_db_context(),
            _patch_service_factory(get_by_id_results=[foreign_entry]),
        ):
            result = await _build_previous_turn_directives_section(
                user_id=str(legit_user),
                previous_turn_injected_ids=[str(entry_id)],
            )
        assert result == ""

    @pytest.mark.asyncio
    async def test_legit_entry_is_kept(self) -> None:
        legit_user = uuid4()
        entry_id = uuid4()
        legit_entry = _make_entry(user_id=legit_user, entry_id=entry_id)

        with (
            _patch_get_db_context(),
            _patch_service_factory(get_by_id_results=[legit_entry]),
        ):
            result = await _build_previous_turn_directives_section(
                user_id=str(legit_user),
                previous_turn_injected_ids=[str(entry_id)],
            )
        assert "## DIRECTIVES INJECTED AT THE PREVIOUS TURN" in result


# -----------------------------------------------------------------------------
# Section shape
# -----------------------------------------------------------------------------


class TestSelfEvaluationSectionShape:
    """Ensure the rendered block carries the discipline + visible metrics."""

    @pytest.mark.asyncio
    async def test_section_contains_discipline_directives(self) -> None:
        """Block must instruct the LLM on the evidence/contradiction signal contract."""
        user_id = uuid4()
        entry = _make_entry(user_id=user_id)

        with (
            _patch_get_db_context(),
            _patch_service_factory(get_by_id_results=[entry]),
        ):
            result = await _build_previous_turn_directives_section(
                user_id=str(user_id),
                previous_turn_injected_ids=[str(entry.id)],
            )

        # Header
        assert "## DIRECTIVES INJECTED AT THE PREVIOUS TURN" in result
        # Discipline contract — these strings exist in the helper:
        assert 'evidence_outcome="evidence"' in result
        assert 'evidence_outcome="contradiction"' in result
        # Atomic-counter promise (anti-hallucination layer 4)
        assert "increments the counters atomically" in result

    @pytest.mark.asyncio
    async def test_entry_metrics_are_visible_to_llm(self) -> None:
        """The LLM must see confidence, ev/co counters, theme — these drive the signal."""
        user_id = uuid4()
        entry = _make_entry(
            user_id=user_id,
            confidence=JournalEntryConfidence.HIGH.value,
            evidence_count=3,
            contradiction_count=1,
            search_hints=["concise", "brief", "réponse courte"],
        )

        with (
            _patch_get_db_context(),
            _patch_service_factory(get_by_id_results=[entry]),
        ):
            result = await _build_previous_turn_directives_section(
                user_id=str(user_id),
                previous_turn_injected_ids=[str(entry.id)],
            )

        assert f"id={entry.id}" in result
        assert "conf=high" in result
        assert "ev=3/co=1" in result
        assert "user_observations" in result
        assert "concise" in result  # search hint passthrough
        assert entry.title in result

    @pytest.mark.asyncio
    async def test_multiple_entries_all_rendered(self) -> None:
        user_id = uuid4()
        entry_a = _make_entry(user_id=user_id, title="Directive A")
        entry_b = _make_entry(user_id=user_id, title="Directive B")

        with (
            _patch_get_db_context(),
            _patch_service_factory(get_by_id_results=[entry_a, entry_b]),
        ):
            result = await _build_previous_turn_directives_section(
                user_id=str(user_id),
                previous_turn_injected_ids=[str(entry_a.id), str(entry_b.id)],
            )

        assert "Directive A" in result
        assert "Directive B" in result
