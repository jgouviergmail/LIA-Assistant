"""Unit tests for the open-loop extractor (P5, Lot 2).

The LLM is mocked (structured output); the tests pin the application rules:
guards, per-user cap, conversational closure, tolerant parsing.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.domains.agents.services.open_loop_extractor import (
    OpenLoopExtraction,
    OpenLoopItem,
    apply_extraction,
    extract_open_loops_background,
)


def _existing_loop(subject: str = "rappeler le plombier"):
    return SimpleNamespace(id=uuid4(), subject=subject, direction="user_owes")


def _repo(existing=None):
    repo = MagicMock()
    repo.list_open_for_user = AsyncMock(return_value=existing or [])
    repo.close_loop = AsyncMock(return_value=True)
    repo.create = AsyncMock()
    return repo


@pytest.mark.unit
class TestOpenLoopItemSchema:
    """Structured-output schema tolerance."""

    def test_defaults(self):
        item = OpenLoopItem(action="open", subject="envoyer le devis à Marie")
        assert item.direction == "user_owes"
        assert item.counterparty is None
        assert item.due_hint_iso is None
        assert item.loop_id is None

    def test_rejects_unknown_action(self):
        with pytest.raises(ValueError):
            OpenLoopItem(action="delete", subject="x")

    def test_rejects_unknown_direction(self):
        with pytest.raises(ValueError):
            OpenLoopItem(action="open", subject="x", direction="mutual")


@pytest.mark.unit
class TestApplyExtraction:
    """Application rules over a mocked repository."""

    async def test_open_creates_loop_with_parsed_due_hint(self):
        repo = _repo()
        settings = SimpleNamespace(
            open_loops_max_open_per_user=30, open_loops_extraction_max_items=5
        )

        stats = await apply_extraction(
            OpenLoopExtraction(
                items=[
                    OpenLoopItem(
                        action="open",
                        subject="envoyer le devis à Marie",
                        counterparty="Marie",
                        direction="user_owes",
                        due_hint_iso="2026-07-25T18:00:00+02:00",
                    )
                ]
            ),
            repo=repo,
            user_id=uuid4(),
            session_id="thread-1",
            settings=settings,
        )

        assert stats == {"opened": 1, "closed": 0, "skipped": 0}
        repo.create.assert_awaited_once()
        payload = repo.create.await_args.args[0]
        assert payload["subject"] == "envoyer le devis à Marie"
        assert payload["counterparty"] == "Marie"
        assert payload["due_hint"] is not None
        assert payload["source_ref"] == "thread-1"

    async def test_naive_due_hint_is_coerced_to_aware_utc(self):
        """LLMs often emit offset-less ISO ('2026-07-25T18:00:00'). The column
        is timestamptz and the whole codebase is aware-UTC: a naive datetime
        must never reach the repository (systemic rule)."""
        from datetime import UTC

        repo = _repo()
        settings = SimpleNamespace(
            open_loops_max_open_per_user=30, open_loops_extraction_max_items=5
        )

        await apply_extraction(
            OpenLoopExtraction(
                items=[OpenLoopItem(action="open", subject="x", due_hint_iso="2026-07-25T18:00:00")]
            ),
            repo=repo,
            user_id=uuid4(),
            session_id="t",
            settings=settings,
        )

        due = repo.create.await_args.args[0]["due_hint"]
        assert due is not None
        assert due.tzinfo is UTC

    async def test_unparseable_due_hint_degrades_to_none(self):
        repo = _repo()
        settings = SimpleNamespace(
            open_loops_max_open_per_user=30, open_loops_extraction_max_items=5
        )

        await apply_extraction(
            OpenLoopExtraction(
                items=[OpenLoopItem(action="open", subject="x", due_hint_iso="vendredi prochain")]
            ),
            repo=repo,
            user_id=uuid4(),
            session_id="t",
            settings=settings,
        )

        assert repo.create.await_args.args[0]["due_hint"] is None

    async def test_close_targets_existing_loop(self):
        loop = _existing_loop()
        repo = _repo(existing=[loop])
        settings = SimpleNamespace(
            open_loops_max_open_per_user=30, open_loops_extraction_max_items=5
        )
        user_id = uuid4()

        stats = await apply_extraction(
            OpenLoopExtraction(
                items=[OpenLoopItem(action="close", subject="plombier", loop_id=str(loop.id))]
            ),
            repo=repo,
            user_id=user_id,
            session_id="t",
            settings=settings,
        )

        assert stats["closed"] == 1
        repo.close_loop.assert_awaited_once_with(loop.id, user_id, reason="conversational")

    async def test_close_with_unknown_or_invalid_id_is_skipped(self):
        repo = _repo(existing=[_existing_loop()])
        settings = SimpleNamespace(
            open_loops_max_open_per_user=30, open_loops_extraction_max_items=5
        )

        stats = await apply_extraction(
            OpenLoopExtraction(
                items=[
                    OpenLoopItem(action="close", subject="x", loop_id="not-a-uuid"),
                    OpenLoopItem(action="close", subject="y", loop_id=str(uuid4())),
                ]
            ),
            repo=repo,
            user_id=uuid4(),
            session_id="t",
            settings=settings,
        )

        assert stats["closed"] == 0
        assert stats["skipped"] == 2
        repo.close_loop.assert_not_awaited()

    async def test_open_refused_beyond_per_user_cap(self):
        existing = [_existing_loop(f"loop {i}") for i in range(2)]
        repo = _repo(existing=existing)
        settings = SimpleNamespace(
            open_loops_max_open_per_user=2, open_loops_extraction_max_items=5
        )

        stats = await apply_extraction(
            OpenLoopExtraction(items=[OpenLoopItem(action="open", subject="one more")]),
            repo=repo,
            user_id=uuid4(),
            session_id="t",
            settings=settings,
        )

        assert stats == {"opened": 0, "closed": 0, "skipped": 1}
        repo.create.assert_not_awaited()

    async def test_duplicate_subject_is_skipped(self):
        repo = _repo(existing=[_existing_loop("Rappeler le plombier")])
        settings = SimpleNamespace(
            open_loops_max_open_per_user=30, open_loops_extraction_max_items=5
        )

        stats = await apply_extraction(
            OpenLoopExtraction(items=[OpenLoopItem(action="open", subject="rappeler le plombier")]),
            repo=repo,
            user_id=uuid4(),
            session_id="t",
            settings=settings,
        )

        assert stats["skipped"] == 1
        repo.create.assert_not_awaited()

    async def test_items_capped_to_extraction_max(self):
        repo = _repo()
        settings = SimpleNamespace(
            open_loops_max_open_per_user=30, open_loops_extraction_max_items=2
        )

        stats = await apply_extraction(
            OpenLoopExtraction(
                items=[OpenLoopItem(action="open", subject=f"subject {i}") for i in range(5)]
            ),
            repo=repo,
            user_id=uuid4(),
            session_id="t",
            settings=settings,
        )

        assert stats["opened"] == 2
        assert repo.create.await_count == 2


@pytest.mark.unit
class TestExtractionEntryGuards:
    """The background entry short-circuits without I/O when gated."""

    async def test_flag_off_skips_everything(self):
        with (
            patch(
                "src.domains.agents.services.open_loop_extractor.settings",
                SimpleNamespace(open_loops_enabled=False),
            ),
            patch(
                "src.domains.agents.services.open_loop_extractor._run_extraction",
                AsyncMock(),
            ) as run_mock,
        ):
            await extract_open_loops_background(
                user_id=str(uuid4()),
                messages=[HumanMessage(content="je dois rappeler le plombier")],
                session_id="t",
                run_id="r",
            )

        run_mock.assert_not_awaited()

    async def test_empty_messages_skip(self):
        with (
            patch(
                "src.domains.agents.services.open_loop_extractor.settings",
                SimpleNamespace(open_loops_enabled=True),
            ),
            patch(
                "src.domains.agents.services.open_loop_extractor._run_extraction",
                AsyncMock(),
            ) as run_mock,
        ):
            await extract_open_loops_background(
                user_id=str(uuid4()), messages=[], session_id="t", run_id="r"
            )

        run_mock.assert_not_awaited()

    async def test_extraction_failure_never_raises(self):
        with (
            patch(
                "src.domains.agents.services.open_loop_extractor.settings",
                SimpleNamespace(open_loops_enabled=True),
            ),
            patch(
                "src.domains.agents.services.open_loop_extractor._run_extraction",
                AsyncMock(side_effect=RuntimeError("llm down")),
            ),
        ):
            # Must swallow (background fire-and-forget contract)
            await extract_open_loops_background(
                user_id=str(uuid4()),
                messages=[
                    HumanMessage(content="je dois rappeler le plombier"),
                    AIMessage(content="Noté !"),
                ],
                session_id="t",
                run_id="r",
            )


@pytest.mark.unit
class TestExtractionTokenTracking:
    """Every LLM call must be billed (G-1): tokens persist via track_proactive_tokens."""

    async def test_run_extraction_tracks_tokens(self):
        from contextlib import asynccontextmanager

        from src.domains.agents.services.open_loop_extractor import _run_extraction

        repo = MagicMock()
        repo.list_open_for_user = AsyncMock(return_value=[])

        @asynccontextmanager
        async def _db_ctx():
            session = MagicMock()
            session.commit = AsyncMock()
            yield session

        track_mock = AsyncMock()
        with (
            patch("src.infrastructure.database.session.get_db_context", new=_db_ctx),
            patch(
                "src.domains.open_loops.repository.OpenLoopRepository",
                return_value=repo,
            ),
            patch(
                "src.domains.agents.services.open_loop_extractor.settings",
                SimpleNamespace(
                    open_loops_enabled=True,
                    open_loops_max_open_per_user=30,
                    open_loops_extraction_max_items=5,
                ),
            ),
            patch(
                "src.domains.agents.prompts.prompt_loader.load_prompt",
                return_value="prompt {current_datetime} {max_items}",
            ),
            patch("src.infrastructure.llm.get_llm", return_value=MagicMock()),
            patch(
                "src.core.llm_config_helper.get_llm_config_for_agent",
                return_value=SimpleNamespace(provider="openai", model="m"),
            ),
            patch(
                "src.infrastructure.llm.structured_output.get_structured_output",
                AsyncMock(return_value=OpenLoopExtraction(items=[])),
            ),
            patch(
                "src.infrastructure.proactive.tracking.track_proactive_tokens",
                track_mock,
            ),
        ):
            await _run_extraction(
                str(uuid4()),
                [HumanMessage(content="je dois rappeler le plombier")],
                "thread-1",
                "run-1",
            )

        track_mock.assert_awaited_once()
        assert track_mock.await_args.kwargs["task_type"] == "open_loop_extraction"


@pytest.mark.unit
class TestExtractionDebugCache:
    """Debug-panel cache (same pop-once pattern as journals/extraction_service):
    the SSE generator pops the result after await_run_id_tasks and emits it
    as a debug_metrics_update chunk."""

    def test_store_and_pop_roundtrip(self):
        from src.domains.agents.services.open_loop_extractor import (
            _store_extraction_debug,
            pop_extraction_debug,
        )

        payload = {"items_parsed": 1, "opened": 1, "closed": 0, "skipped": 0, "items": []}
        _store_extraction_debug("run-dbg-1", payload)

        assert pop_extraction_debug("run-dbg-1") == payload
        # Pop-once contract: a second pop returns None
        assert pop_extraction_debug("run-dbg-1") is None

    def test_pop_evicts_stale_entries(self):
        import src.domains.agents.services.open_loop_extractor as mod

        mod._store_extraction_debug("run-stale", {"items_parsed": 0})
        with patch.object(mod._time, "monotonic", return_value=mod._time.monotonic() + 10_000):
            assert mod.pop_extraction_debug("run-stale") is None

    async def test_run_extraction_stores_debug(self):
        from contextlib import asynccontextmanager

        from src.domains.agents.services.open_loop_extractor import (
            _run_extraction,
            pop_extraction_debug,
        )

        repo = MagicMock()
        repo.list_open_for_user = AsyncMock(return_value=[])
        repo.create = AsyncMock()

        @asynccontextmanager
        async def _db_ctx():
            session = MagicMock()
            session.commit = AsyncMock()
            yield session

        extraction = OpenLoopExtraction(
            items=[OpenLoopItem(action="open", subject="envoyer le devis à Marie")]
        )
        with (
            patch("src.infrastructure.database.session.get_db_context", new=_db_ctx),
            patch(
                "src.domains.open_loops.repository.OpenLoopRepository",
                return_value=repo,
            ),
            patch(
                "src.domains.agents.services.open_loop_extractor.settings",
                SimpleNamespace(
                    open_loops_enabled=True,
                    open_loops_max_open_per_user=30,
                    open_loops_extraction_max_items=5,
                ),
            ),
            patch(
                "src.domains.agents.prompts.prompt_loader.load_prompt",
                return_value="prompt {current_datetime} {max_items}",
            ),
            patch("src.infrastructure.llm.get_llm", return_value=MagicMock()),
            patch(
                "src.core.llm_config_helper.get_llm_config_for_agent",
                return_value=SimpleNamespace(provider="openai", model="m"),
            ),
            patch(
                "src.infrastructure.llm.structured_output.get_structured_output",
                AsyncMock(return_value=extraction),
            ),
            patch(
                "src.infrastructure.proactive.tracking.track_proactive_tokens",
                AsyncMock(),
            ),
        ):
            await _run_extraction(
                str(uuid4()),
                [HumanMessage(content="je dois envoyer le devis à Marie")],
                "thread-1",
                "run-dbg-2",
            )

        dbg = pop_extraction_debug("run-dbg-2")
        assert dbg is not None
        assert dbg["items_parsed"] == 1
        assert dbg["opened"] == 1
        assert dbg["items"][0]["subject"] == "envoyer le devis à Marie"
        assert dbg["items"][0]["direction"] == "user_owes"

    def test_store_evicts_stale_entries_without_any_pop(self):
        """When the debug panel is never enabled, nothing ever pops: the
        STORE side must run the TTL eviction too, or the cache grows for
        the whole process lifetime (one entry per turn)."""
        import src.domains.agents.services.open_loop_extractor as mod

        mod._store_extraction_debug("run-old", {"items_parsed": 0})
        with patch.object(mod._time, "monotonic", return_value=mod._time.monotonic() + 10_000):
            mod._store_extraction_debug("run-new", {"items_parsed": 1})
            assert "run-old" not in mod._extraction_debug_results
            assert mod.pop_extraction_debug("run-new") == {"items_parsed": 1}
