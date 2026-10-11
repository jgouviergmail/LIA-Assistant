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
        source="conversation",
        confidence="medium",
        evidence_count=0,
        contradiction_count=0,
        revision=1,
    )


def _user() -> SimpleNamespace:
    return SimpleNamespace(
        journals_enabled=True,
        journal_context_max_chars=3000,
        journal_context_max_results=5,
        is_active=True,
        deleted_at=None,
    )


@pytest.fixture(autouse=True)
def _offline_injection_dependencies():
    """Exercise rendering and policy without consulting operator/Redis stores."""
    from src.domains.journals import context_builder

    with (
        patch.object(context_builder, "is_capability_enabled", AsyncMock(return_value=True)),
        patch.object(context_builder, "effective_threshold", AsyncMock(return_value=0.63)),
        patch.object(context_builder, "observe_score", AsyncMock()),
    ):
        yield


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
            patch.object(context_builder, "track_injected_entries"),
        ):
            await context_builder.build_journal_context(
                user_id=uuid4(),
                query="q",
                db=_make_db(_user()),
                query_embedding=[0.1] * 1536,
            )

        assert repo.search_by_relevance.await_args.kwargs["exclude_levels"] == ["L0", "L3"]
        assert repo.search_by_relevance.await_args.kwargs["operational_only"] is True

    async def test_explicit_empty_override_injects_all_levels(self) -> None:
        """An explicit ``exclude_levels=[]`` disables the filter (extraction-style)."""
        from src.domains.journals import context_builder

        repo = MagicMock()
        repo.search_by_relevance = AsyncMock(return_value=[(_entry("c1"), 0.9)])
        repo.get_recent_for_user = AsyncMock(return_value=[])

        with (
            patch.object(context_builder, "JournalEntryRepository", return_value=repo),
            patch.object(context_builder, "track_injected_entries"),
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
            patch.object(context_builder, "track_injected_entries"),
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

    async def test_operator_off_opens_neither_user_nor_semantic_search(self) -> None:
        from src.domains.journals import context_builder

        db = _make_db(_user())
        with patch.object(context_builder, "is_capability_enabled", AsyncMock(return_value=False)):
            assert await context_builder.build_journal_context(uuid4(), "q", db) == (None, None, [])
        db.execute.assert_not_awaited()

    @pytest.mark.parametrize("budget", [200, 500, 600, 700])
    async def test_insufficient_budget_omits_the_whole_directive(self, budget: int) -> None:
        from src.domains.journals import context_builder

        user = _user()
        user.journal_context_max_chars = budget
        content = "WHEN preparing a report, " + "verify facts; " * 20 + "DO ask before publishing."
        repo = MagicMock(search_by_relevance=AsyncMock(return_value=[(_entry(content), 0.9)]))
        with (
            patch.object(context_builder, "JournalEntryRepository", return_value=repo),
            patch.object(context_builder, "track_injected_entries") as track,
        ):
            block, debug, ids = await context_builder.build_journal_context(
                uuid4(),
                "report",
                _make_db(user),
                query_embedding=[0.1] * 1536,
                include_debug=True,
            )
        assert block is None and ids == []
        assert debug["entries_injected"] == 0
        assert debug["total_chars_injected"] == 0
        track.assert_not_called()

    async def test_exact_rendered_boundary_keeps_full_action_and_revision(self) -> None:
        from src.domains.journals import context_builder

        user = _user()
        item = _entry("WHEN producing a report DO cite the source.")
        item.revision = 7
        repo = MagicMock(search_by_relevance=AsyncMock(return_value=[(item, 0.9)]))
        with (
            patch.object(context_builder, "JournalEntryRepository", return_value=repo),
            patch.object(context_builder, "track_injected_entries"),
        ):
            whole, _, _ = await context_builder.build_journal_context(
                uuid4(),
                "report",
                _make_db(user),
                query_embedding=[0.1] * 1536,
            )
            user.journal_context_max_chars = len(whole)
            block, _, ids = await context_builder.build_journal_context(
                uuid4(),
                "report",
                _make_db(user),
                query_embedding=[0.1] * 1536,
            )
            user.journal_context_max_chars -= 1
            absent, _, absent_ids = await context_builder.build_journal_context(
                uuid4(),
                "report",
                _make_db(user),
                query_embedding=[0.1] * 1536,
            )
        assert block == whole and item.content in block
        assert "confidence=medium" in block and "revision=7" in block
        assert ids == [str(item.id)]
        assert absent is None and absent_ids == []

    async def test_incompatible_shared_vector_is_recomputed_by_journal_model(self) -> None:
        from src.core.config import settings
        from src.domains.journals import context_builder

        shared, correct = [0.1] * 1536, [0.2] * 1536
        repo = MagicMock(search_by_relevance=AsyncMock(return_value=[]))
        embedding = MagicMock(aembed_query=AsyncMock(return_value=correct))
        with (
            patch.object(settings, "memory_embedding_model", "models/gemini-embedding-2"),
            patch.object(settings, "journal_embedding_model", "models/gemini-embedding-001"),
            patch.object(context_builder, "JournalEntryRepository", return_value=repo),
            patch("src.domains.journals.embedding.get_journal_embeddings", return_value=embedding),
        ):
            await context_builder.build_journal_context(
                uuid4(),
                "report",
                _make_db(_user()),
                query_embedding=shared,
            )
        embedding.aembed_query.assert_awaited_once_with("report")
        assert repo.search_by_relevance.await_args.kwargs["query_embedding"] is correct
