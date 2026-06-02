"""Unit tests for operational injection level routing (systemic refinement).

Verifies that ``build_journal_context`` — the operational injection chokepoint —
excludes L0/L3 by default (only L1/L2 behavioural directives steer behaviour),
honours an explicit ``exclude_levels`` override, and injects entries in full when
``truncate_to_budget=False`` (the count-capped ReAct path, no mid-directive cut).
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.journals.constants import JOURNAL_OPERATIONAL_INJECTION_EXCLUDE_LEVELS


def _make_db(user: SimpleNamespace) -> MagicMock:
    """Build a mock AsyncSession whose User lookup returns ``user``."""
    exec_result = MagicMock()
    exec_result.scalar_one_or_none.return_value = user
    db = MagicMock()
    db.execute = AsyncMock(return_value=exec_result)
    return db


def _entry(content: str, level: str = "L1") -> SimpleNamespace:
    """Build a minimal journal-entry stand-in for context formatting."""
    return SimpleNamespace(
        id=uuid4(),
        content=content,
        title="Title",
        theme="learnings",
        mood="reflective",
        created_at=datetime(2026, 6, 1, tzinfo=UTC),
        search_hints=[],
        char_count=len(content),
        level=level,
    )


def _user() -> SimpleNamespace:
    return SimpleNamespace(
        journals_enabled=True,
        journal_context_max_chars=3000,
        journal_context_max_results=5,
    )


@pytest.mark.unit
class TestOperationalInjectionLevelRouting:
    def test_exclude_levels_constant(self) -> None:
        """L0 (private feedstock) and L3 (carried by portrait) are excluded."""
        assert JOURNAL_OPERATIONAL_INJECTION_EXCLUDE_LEVELS == ["L0", "L3"]

    async def test_default_excludes_l0_and_l3(self) -> None:
        """With no override, the repo search is asked to exclude L0/L3."""
        from src.domains.journals import context_builder

        repo = MagicMock()
        repo.search_by_relevance = AsyncMock(return_value=[(_entry("c1"), 0.9)])
        repo.get_recent_for_user = AsyncMock(return_value=[])

        with (
            patch.object(context_builder, "JournalEntryRepository", return_value=repo),
            patch.object(context_builder, "_fire_and_forget_injection_tracking"),
        ):
            await context_builder.build_journal_context(
                user_id=uuid4(),
                query="q",
                db=_make_db(_user()),
                query_embedding=[0.1] * 1536,
            )

        assert repo.search_by_relevance.await_args.kwargs["exclude_levels"] == ["L0", "L3"]

    async def test_explicit_empty_override_injects_all_levels(self) -> None:
        """An explicit ``exclude_levels=[]`` disables the filter (extraction-style)."""
        from src.domains.journals import context_builder

        repo = MagicMock()
        repo.search_by_relevance = AsyncMock(return_value=[(_entry("c1"), 0.9)])
        repo.get_recent_for_user = AsyncMock(return_value=[])

        with (
            patch.object(context_builder, "JournalEntryRepository", return_value=repo),
            patch.object(context_builder, "_fire_and_forget_injection_tracking"),
        ):
            await context_builder.build_journal_context(
                user_id=uuid4(),
                query="q",
                db=_make_db(_user()),
                query_embedding=[0.1] * 1536,
                exclude_levels=[],
            )

        assert repo.search_by_relevance.await_args.kwargs["exclude_levels"] == []

    async def test_no_truncation_injects_entries_in_full(self) -> None:
        """truncate_to_budget=False injects full entries (count cap only)."""
        from src.domains.journals import context_builder

        user = _user()
        user.journal_context_max_chars = 50  # tiny — would truncate if enabled
        long_a, long_b, long_c = "A" * 200, "B" * 200, "C" * 200
        repo = MagicMock()
        repo.search_by_relevance = AsyncMock(
            return_value=[(_entry(long_a), 0.9), (_entry(long_b), 0.8), (_entry(long_c), 0.7)]
        )
        repo.get_recent_for_user = AsyncMock(return_value=[])

        with (
            patch.object(context_builder, "JournalEntryRepository", return_value=repo),
            patch.object(context_builder, "_fire_and_forget_injection_tracking"),
        ):
            result, _debug, ids = await context_builder.build_journal_context(
                user_id=uuid4(),
                query="q",
                db=_make_db(user),
                query_embedding=[0.1] * 1536,
                max_results_override=3,
                truncate_to_budget=False,
            )

        assert result is not None
        assert long_a in result and long_b in result and long_c in result
        assert "..." not in result
        assert len(ids) == 3
