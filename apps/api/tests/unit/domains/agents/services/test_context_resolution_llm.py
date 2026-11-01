"""Tests for LLM-first context reference resolution.

Tests the _resolve_llm_detected_reference() method in ContextResolutionService
which uses LLM-detected context references instead of regex-based detection.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.agents.constants import (
    STATE_KEY_AGENT_RESULTS,
    STATE_KEY_LAST_LIST_DOMAIN,
    STATE_KEY_LAST_LIST_TURN_ID,
    TURN_TYPE_ACTION,
    TURN_TYPE_REFERENCE,
)
from src.domains.agents.services.context_resolution_service import (
    ContextResolutionService,
)
from src.domains.agents.services.query_analyzer_service import ContextReferenceOutput

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def context_service(monkeypatch: pytest.MonkeyPatch) -> ContextResolutionService:
    """Resolve references without a persistent TCM session in these routing tests."""
    monkeypatch.setattr(
        "src.domains.agents.services.context_resolution_service.get_tcm_session",
        AsyncMock(return_value=None),
    )
    return ContextResolutionService()


@pytest.fixture
def mock_config() -> MagicMock:
    """Create a mock RunnableConfig."""
    config = MagicMock()
    config.get.return_value = {"langgraph_user_id": "test_user", "thread_id": "test_thread"}
    return config


@pytest.fixture
def sample_items() -> list[dict]:
    """Create sample items for resolution."""
    return [
        {"id": "item_1", "name": "First Item", "index": 1},
        {"id": "item_2", "name": "Second Item", "index": 2},
        {"id": "item_3", "name": "Third Item", "index": 3},
        {"id": "item_4", "name": "Fourth Item", "index": 4},
        {"id": "item_5", "name": "Fifth Item", "index": 5},
    ]


@pytest.fixture
def base_state() -> dict:
    """Create a base conversation state."""
    return {
        STATE_KEY_LAST_LIST_TURN_ID: 1,
        STATE_KEY_LAST_LIST_DOMAIN: "contacts",
        STATE_KEY_AGENT_RESULTS: {},
    }


def _make_ref(
    *,
    has_reference: bool = False,
    reference_type: str = "none",
    ordinal_positions: list[int] | None = None,
    reference_domain: str = "",
) -> ContextReferenceOutput:
    """Helper to create ContextReferenceOutput instances."""
    return ContextReferenceOutput(
        has_reference=has_reference,
        reference_type=reference_type,
        ordinal_positions=ordinal_positions or [],
        reference_domain=reference_domain,
    )


# =============================================================================
# TEST: resolve_context() — top-level routing
# =============================================================================


class TestADescribedItemIsResolvedAgainstWhatWasShown:
    """ADR-367: a descriptive reference never reaches the ordinal resolver."""

    @staticmethod
    def _state(*senders: str) -> dict:
        registry = {
            f"e{i}": {
                "id": f"e{i}",
                "type": "EMAIL",
                "payload": {"id": f"e{i}", "from": sender, "subject": "S", "to": ""},
                "meta": {"source": "gmail", "domain": "emails", "turn_id": 1},
            }
            for i, sender in enumerate(senders, 1)
        }
        # The answer of turn 1 showed every one of them.
        shown = [{"turn_id": 1, "ids": list(registry)}]
        return {"current_turn_id": 2, "registry": registry, "shown_items": shown}

    @staticmethod
    def _ref(descriptor: str) -> ContextReferenceOutput:
        return ContextReferenceOutput(
            has_reference=True,
            reference_type="descriptive",
            descriptor=descriptor,
            reference_domain="email",
        )

    @pytest.fixture(autouse=True)
    def _followed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.domains.agents.services import descriptive_reference
        from src.domains.agents.tools import emails_tools  # noqa: F401 — registers "emails"

        monkeypatch.setattr(descriptive_reference, "turn_follows_the_conversation", lambda: True)

    @pytest.mark.asyncio
    async def test_one_fitting_item_makes_a_reference_turn(
        self, context_service: ContextResolutionService, mock_config: MagicMock
    ) -> None:
        result, turn_type = await context_service.resolve_context(
            query="reply to Marc's email",
            state=self._state("Marc <m@example.com>", "Ana <a@example.com>"),
            config=mock_config,
            run_id="test_run",
            context_reference=self._ref("Marc"),
        )

        assert [item["id"] for item in result.items] == ["e1"]
        assert turn_type == TURN_TYPE_REFERENCE
        assert result.method == "descriptive"

    @pytest.mark.asyncio
    async def test_several_fitting_items_stay_an_action_carrying_candidates(
        self, context_service: ContextResolutionService, mock_config: MagicMock
    ) -> None:
        result, turn_type = await context_service.resolve_context(
            query="reply to Marc's email",
            state=self._state("Marc <m@example.com>", "Marc <m@example.com>"),
            config=mock_config,
            run_id="test_run",
            context_reference=self._ref("Marc"),
        )

        assert result.items == []
        assert [item["id"] for item in result.candidates] == ["e1", "e2"]
        assert turn_type == TURN_TYPE_ACTION

    @pytest.mark.asyncio
    async def test_a_description_the_analyzer_says_designates_nothing_is_not_resolved(
        self, context_service: ContextResolutionService, mock_config: MagicMock
    ) -> None:
        # « find Marc's emails from last week » is a NEW search: a shown email
        # from Marc must not stand in for it, whatever type the model wrote.
        reference = self._ref("Marc").model_copy(update={"has_reference": False})
        result, turn_type = await context_service.resolve_context(
            query="find Marc's emails from last week",
            state=self._state("Marc <m@example.com>"),
            config=mock_config,
            run_id="test_run",
            context_reference=reference,
        )

        assert result.items == [] and result.candidates == []
        assert result.method == "none"
        assert turn_type == TURN_TYPE_ACTION


class TestResolveContextRouting:
    """Test the top-level routing in resolve_context()."""

    @pytest.mark.asyncio
    async def test_no_reference_returns_empty(
        self, context_service: ContextResolutionService, mock_config: MagicMock, base_state: dict
    ) -> None:
        """has_reference=False should return empty ResolvedContext with ACTION turn type."""
        ref = _make_ref(has_reference=False)

        result, turn_type = await context_service.resolve_context(
            query="what's the weather?",
            state=base_state,
            config=mock_config,
            run_id="test_run",
            context_reference=ref,
        )

        assert result.items == []
        assert result.method == "none"
        assert result.confidence == 1.0
        assert turn_type == TURN_TYPE_ACTION

    @pytest.mark.asyncio
    async def test_has_reference_returns_reference_turn_type(
        self,
        context_service: ContextResolutionService,
        mock_config: MagicMock,
        base_state: dict,
        sample_items: list[dict],
    ) -> None:
        """has_reference=True should return REFERENCE turn type."""
        ref = _make_ref(
            has_reference=True,
            reference_type="ordinal",
            ordinal_positions=[1],
            reference_domain="contact",
        )

        with patch.object(
            context_service,
            "_get_items_from_tool_context_manager",
            new_callable=AsyncMock,
            return_value=sample_items,
        ):
            result, turn_type = await context_service.resolve_context(
                query="detail du premier",
                state=base_state,
                config=mock_config,
                run_id="test_run",
                context_reference=ref,
            )

        assert turn_type == TURN_TYPE_REFERENCE
        assert result.method == "llm_detected"

    @pytest.mark.asyncio
    async def test_feature_disabled_returns_disabled(
        self, mock_config: MagicMock, base_state: dict
    ) -> None:
        """When feature is disabled, should return disabled method."""
        with patch(
            "src.domains.agents.services.context_resolution_service.settings"
        ) as mock_settings:
            mock_settings.context_reference_resolution_enabled = False
            service = ContextResolutionService(settings=mock_settings)

            ref = _make_ref(has_reference=True, reference_type="ordinal", ordinal_positions=[1])

            result, turn_type = await service.resolve_context(
                query="detail du premier",
                state=base_state,
                config=mock_config,
                run_id="test_run",
                context_reference=ref,
            )

        assert result.method == "disabled"
        assert turn_type == TURN_TYPE_ACTION


# =============================================================================
# TEST: _resolve_llm_detected_reference() — ordinal resolution
# =============================================================================


class TestOrdinalResolution:
    """Test ordinal reference resolution (the first, the 2nd, the last)."""

    @pytest.mark.asyncio
    async def test_ordinal_position_2(
        self,
        context_service: ContextResolutionService,
        mock_config: MagicMock,
        base_state: dict,
        sample_items: list[dict],
    ) -> None:
        """Position 2 should resolve to the second item (0-indexed: 1)."""
        ref = _make_ref(
            has_reference=True,
            reference_type="ordinal",
            ordinal_positions=[2],
            reference_domain="contact",
        )

        with patch.object(
            context_service,
            "_get_items_from_tool_context_manager",
            new_callable=AsyncMock,
            return_value=sample_items,
        ):
            result = await context_service._resolve_llm_detected_reference(
                ref, base_state, mock_config, "test_run"
            )

        assert len(result.items) == 1
        assert result.items[0]["id"] == "item_2"
        assert result.confidence == 1.0
        assert result.source_domain == "contact"

    @pytest.mark.asyncio
    async def test_ordinal_last(
        self,
        context_service: ContextResolutionService,
        mock_config: MagicMock,
        base_state: dict,
        sample_items: list[dict],
    ) -> None:
        """Position -1 should resolve to the last item."""
        ref = _make_ref(
            has_reference=True,
            reference_type="ordinal",
            ordinal_positions=[-1],
            reference_domain="email",
        )

        with patch.object(
            context_service,
            "_get_items_from_tool_context_manager",
            new_callable=AsyncMock,
            return_value=sample_items,
        ):
            result = await context_service._resolve_llm_detected_reference(
                ref, base_state, mock_config, "test_run"
            )

        assert len(result.items) == 1
        assert result.items[0]["id"] == "item_5"
        assert result.confidence == 1.0

    @pytest.mark.asyncio
    async def test_ordinal_first(
        self,
        context_service: ContextResolutionService,
        mock_config: MagicMock,
        base_state: dict,
        sample_items: list[dict],
    ) -> None:
        """Position 1 should resolve to the first item."""
        ref = _make_ref(
            has_reference=True,
            reference_type="ordinal",
            ordinal_positions=[1],
            reference_domain="contact",
        )

        with patch.object(
            context_service,
            "_get_items_from_tool_context_manager",
            new_callable=AsyncMock,
            return_value=sample_items,
        ):
            result = await context_service._resolve_llm_detected_reference(
                ref, base_state, mock_config, "test_run"
            )

        assert len(result.items) == 1
        assert result.items[0]["id"] == "item_1"

    @pytest.mark.asyncio
    async def test_multi_ordinal(
        self,
        context_service: ContextResolutionService,
        mock_config: MagicMock,
        base_state: dict,
        sample_items: list[dict],
    ) -> None:
        """Multiple positions [1, 3] should resolve to 2 items."""
        ref = _make_ref(
            has_reference=True,
            reference_type="ordinal",
            ordinal_positions=[1, 3],
            reference_domain="contact",
        )

        with patch.object(
            context_service,
            "_get_items_from_tool_context_manager",
            new_callable=AsyncMock,
            return_value=sample_items,
        ):
            result = await context_service._resolve_llm_detected_reference(
                ref, base_state, mock_config, "test_run"
            )

        assert len(result.items) == 2
        assert result.items[0]["id"] == "item_1"
        assert result.items[1]["id"] == "item_3"
        assert result.confidence == 1.0

    @pytest.mark.asyncio
    async def test_ordinal_partial_out_of_bounds(
        self,
        context_service: ContextResolutionService,
        mock_config: MagicMock,
        base_state: dict,
        sample_items: list[dict],
    ) -> None:
        """[1, 10] with 5 items: first resolves, 10th is out of bounds."""
        ref = _make_ref(
            has_reference=True,
            reference_type="ordinal",
            ordinal_positions=[1, 10],
            reference_domain="contact",
        )

        with patch.object(
            context_service,
            "_get_items_from_tool_context_manager",
            new_callable=AsyncMock,
            return_value=sample_items,
        ):
            result = await context_service._resolve_llm_detected_reference(
                ref, base_state, mock_config, "test_run"
            )

        assert len(result.items) == 1
        assert result.items[0]["id"] == "item_1"
        assert result.confidence == 0.5  # 1 resolved out of 2

    @pytest.mark.asyncio
    async def test_ordinal_fully_out_of_bounds(
        self,
        context_service: ContextResolutionService,
        mock_config: MagicMock,
        base_state: dict,
        sample_items: list[dict],
    ) -> None:
        """Position 10 with 5 items should return empty."""
        ref = _make_ref(
            has_reference=True,
            reference_type="ordinal",
            ordinal_positions=[10],
            reference_domain="contact",
        )

        with patch.object(
            context_service,
            "_get_items_from_tool_context_manager",
            new_callable=AsyncMock,
            return_value=sample_items,
        ):
            result = await context_service._resolve_llm_detected_reference(
                ref, base_state, mock_config, "test_run"
            )

        assert len(result.items) == 0
        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_ordinal_position_zero_skipped(
        self,
        context_service: ContextResolutionService,
        mock_config: MagicMock,
        base_state: dict,
        sample_items: list[dict],
    ) -> None:
        """Position 0 is invalid in 1-based indexing and should be skipped."""
        ref = _make_ref(
            has_reference=True,
            reference_type="ordinal",
            ordinal_positions=[0],
            reference_domain="contact",
        )

        with patch.object(
            context_service,
            "_get_items_from_tool_context_manager",
            new_callable=AsyncMock,
            return_value=sample_items,
        ):
            result = await context_service._resolve_llm_detected_reference(
                ref, base_state, mock_config, "test_run"
            )

        assert len(result.items) == 0

    @pytest.mark.asyncio
    async def test_ordinal_empty_positions(
        self,
        context_service: ContextResolutionService,
        mock_config: MagicMock,
        base_state: dict,
        sample_items: list[dict],
    ) -> None:
        """Empty ordinal_positions with type=ordinal should return empty."""
        ref = _make_ref(
            has_reference=True,
            reference_type="ordinal",
            ordinal_positions=[],
            reference_domain="contact",
        )

        with patch.object(
            context_service,
            "_get_items_from_tool_context_manager",
            new_callable=AsyncMock,
            return_value=sample_items,
        ):
            result = await context_service._resolve_llm_detected_reference(
                ref, base_state, mock_config, "test_run"
            )

        assert len(result.items) == 0
        assert result.confidence == 0.0


# =============================================================================
# TEST: _resolve_llm_detected_reference() — demonstrative/pronoun resolution
# =============================================================================


class TestDemonstrativeResolution:
    """Test demonstrative and pronoun reference resolution."""

    @pytest.mark.asyncio
    async def test_demonstrative_with_current_item(
        self,
        context_service: ContextResolutionService,
        mock_config: MagicMock,
        base_state: dict,
        sample_items: list[dict],
    ) -> None:
        """Demonstrative should resolve to current_item from TCM when available."""
        current_item = {"id": "current_123", "name": "Current Contact", "index": 2}
        ref = _make_ref(
            has_reference=True,
            reference_type="demonstrative",
            reference_domain="email",
        )

        with (
            patch.object(
                context_service,
                "_get_items_from_tool_context_manager",
                new_callable=AsyncMock,
                return_value=sample_items,
            ),
            patch.object(
                context_service,
                "_get_current_item_from_tool_context_manager",
                new_callable=AsyncMock,
                return_value=current_item,
            ),
        ):
            result = await context_service._resolve_llm_detected_reference(
                ref, base_state, mock_config, "test_run"
            )

        assert len(result.items) == 1
        assert result.items[0]["id"] == "current_123"
        assert result.confidence == 0.95  # context_current_item_confidence default

    @pytest.mark.asyncio
    async def test_demonstrative_fallback_to_first_item(
        self,
        context_service: ContextResolutionService,
        mock_config: MagicMock,
        base_state: dict,
        sample_items: list[dict],
    ) -> None:
        """Demonstrative without current_item should fallback to first item."""
        ref = _make_ref(
            has_reference=True,
            reference_type="demonstrative",
            reference_domain="email",
        )

        with (
            patch.object(
                context_service,
                "_get_items_from_tool_context_manager",
                new_callable=AsyncMock,
                return_value=sample_items,
            ),
            patch.object(
                context_service,
                "_get_current_item_from_tool_context_manager",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            result = await context_service._resolve_llm_detected_reference(
                ref, base_state, mock_config, "test_run"
            )

        assert len(result.items) == 1
        assert result.items[0]["id"] == "item_1"
        assert result.confidence == 0.8  # context_demonstrative_confidence default

    @pytest.mark.asyncio
    async def test_pronoun_same_as_demonstrative(
        self,
        context_service: ContextResolutionService,
        mock_config: MagicMock,
        base_state: dict,
        sample_items: list[dict],
    ) -> None:
        """Pronoun type should behave identically to demonstrative."""
        ref = _make_ref(
            has_reference=True,
            reference_type="pronoun",
            reference_domain="contact",
        )

        with (
            patch.object(
                context_service,
                "_get_items_from_tool_context_manager",
                new_callable=AsyncMock,
                return_value=sample_items,
            ),
            patch.object(
                context_service,
                "_get_current_item_from_tool_context_manager",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            result = await context_service._resolve_llm_detected_reference(
                ref, base_state, mock_config, "test_run"
            )

        assert len(result.items) == 1
        assert result.items[0]["id"] == "item_1"


# =============================================================================
# TEST: Domain resolution and normalization
# =============================================================================


class TestDomainResolution:
    """Test domain resolution and normalization logic."""

    @pytest.mark.asyncio
    async def test_empty_domain_fallback_to_last_list_domain(
        self,
        context_service: ContextResolutionService,
        mock_config: MagicMock,
        sample_items: list[dict],
    ) -> None:
        """Empty reference_domain should fallback to STATE_KEY_LAST_LIST_DOMAIN."""
        state = {
            STATE_KEY_LAST_LIST_TURN_ID: 1,
            STATE_KEY_LAST_LIST_DOMAIN: "events",  # Plural from task_orchestrator
            STATE_KEY_AGENT_RESULTS: {},
        }
        ref = _make_ref(
            has_reference=True,
            reference_type="ordinal",
            ordinal_positions=[1],
            reference_domain="",  # Empty — should fallback
        )

        with patch.object(
            context_service,
            "_get_items_from_tool_context_manager",
            new_callable=AsyncMock,
            return_value=sample_items,
        ):
            result = await context_service._resolve_llm_detected_reference(
                ref, state, mock_config, "test_run"
            )

        assert len(result.items) == 1
        # source_domain should be normalized to singular
        assert result.source_domain == "event"

    @pytest.mark.asyncio
    async def test_domain_translation_calendar_to_events(
        self,
        context_service: ContextResolutionService,
        mock_config: MagicMock,
        base_state: dict,
        sample_items: list[dict],
    ) -> None:
        """Domain 'calendar' should be translated to 'events' for TCM lookup."""
        ref = _make_ref(
            has_reference=True,
            reference_type="ordinal",
            ordinal_positions=[1],
            reference_domain="calendar",
        )

        with patch.object(
            context_service,
            "_get_items_from_tool_context_manager",
            new_callable=AsyncMock,
            return_value=sample_items,
        ) as mock_tcm:
            result = await context_service._resolve_llm_detected_reference(
                ref, base_state, mock_config, "test_run"
            )

        # TCM should have been called with "events" (translated from "calendar")
        mock_tcm.assert_called_once_with(mock_config, "events", "test_run")
        assert result.source_domain == "calendar"

    @pytest.mark.asyncio
    async def test_no_domain_no_fallback_returns_empty(
        self,
        context_service: ContextResolutionService,
        mock_config: MagicMock,
    ) -> None:
        """No domain from LLM and no last_list_domain should return empty."""
        state: dict = {
            STATE_KEY_LAST_LIST_TURN_ID: None,
            STATE_KEY_AGENT_RESULTS: {},
        }
        ref = _make_ref(
            has_reference=True,
            reference_type="ordinal",
            ordinal_positions=[1],
            reference_domain="",
        )

        result = await context_service._resolve_llm_detected_reference(
            ref, state, mock_config, "test_run"
        )

        assert result.items == []
        assert result.confidence == 0.0
        assert result.source_domain is None

    @pytest.mark.asyncio
    async def test_source_domain_stored_singular(
        self,
        context_service: ContextResolutionService,
        mock_config: MagicMock,
        base_state: dict,
        sample_items: list[dict],
    ) -> None:
        """source_domain in ResolvedContext should be singular (from LLM)."""
        ref = _make_ref(
            has_reference=True,
            reference_type="ordinal",
            ordinal_positions=[1],
            reference_domain="contact",
        )

        with patch.object(
            context_service,
            "_get_items_from_tool_context_manager",
            new_callable=AsyncMock,
            return_value=sample_items,
        ):
            result = await context_service._resolve_llm_detected_reference(
                ref, base_state, mock_config, "test_run"
            )

        assert result.source_domain == "contact"  # Singular, not "contacts"


# =============================================================================
# TEST: Edge cases and LLM output validation
# =============================================================================


class TestEdgeCases:
    """Test edge cases and defensive handling of LLM output."""

    @pytest.mark.asyncio
    async def test_type_none_with_has_reference_true(
        self,
        context_service: ContextResolutionService,
        mock_config: MagicMock,
        base_state: dict,
        sample_items: list[dict],
    ) -> None:
        """Contradiction: has_reference=True + type=none should return empty."""
        ref = _make_ref(
            has_reference=True,
            reference_type="none",
            reference_domain="contact",
        )

        with patch.object(
            context_service,
            "_get_items_from_tool_context_manager",
            new_callable=AsyncMock,
            return_value=sample_items,
        ):
            result = await context_service._resolve_llm_detected_reference(
                ref, base_state, mock_config, "test_run"
            )

        assert result.items == []
        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_unknown_reference_type_fallback_demonstrative(
        self,
        context_service: ContextResolutionService,
        mock_config: MagicMock,
        base_state: dict,
        sample_items: list[dict],
    ) -> None:
        """Unknown reference_type should be treated as demonstrative."""
        ref = _make_ref(
            has_reference=True,
            reference_type="weird_type",
            reference_domain="contact",
        )

        with (
            patch.object(
                context_service,
                "_get_items_from_tool_context_manager",
                new_callable=AsyncMock,
                return_value=sample_items,
            ),
            patch.object(
                context_service,
                "_get_current_item_from_tool_context_manager",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            result = await context_service._resolve_llm_detected_reference(
                ref, base_state, mock_config, "test_run"
            )

        # Should fallback to first item (demonstrative behavior)
        assert len(result.items) == 1
        assert result.items[0]["id"] == "item_1"

    @pytest.mark.asyncio
    async def test_tcm_empty_fallback_to_agent_results(
        self,
        context_service: ContextResolutionService,
        mock_config: MagicMock,
        sample_items: list[dict],
    ) -> None:
        """When TCM is empty, should fallback to agent_results."""
        state = {
            STATE_KEY_LAST_LIST_TURN_ID: 1,
            STATE_KEY_LAST_LIST_DOMAIN: "contacts",
            STATE_KEY_AGENT_RESULTS: {
                "1:plan_executor": {"contacts": sample_items},
            },
        }
        ref = _make_ref(
            has_reference=True,
            reference_type="ordinal",
            ordinal_positions=[1],
            reference_domain="contact",
        )

        with patch.object(
            context_service,
            "_get_items_from_tool_context_manager",
            new_callable=AsyncMock,
            return_value=[],  # TCM empty
        ):
            result = await context_service._resolve_llm_detected_reference(
                ref, state, mock_config, "test_run"
            )

        assert len(result.items) == 1

    @pytest.mark.asyncio
    async def test_all_sources_empty_returns_empty(
        self,
        context_service: ContextResolutionService,
        mock_config: MagicMock,
    ) -> None:
        """When all sources are empty, should return empty ResolvedContext."""
        state: dict = {
            STATE_KEY_LAST_LIST_TURN_ID: None,
            STATE_KEY_LAST_LIST_DOMAIN: "contacts",
            STATE_KEY_AGENT_RESULTS: {},
        }
        ref = _make_ref(
            has_reference=True,
            reference_type="ordinal",
            ordinal_positions=[1],
            reference_domain="contact",
        )

        with patch.object(
            context_service,
            "_get_items_from_tool_context_manager",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await context_service._resolve_llm_detected_reference(
                ref, state, mock_config, "test_run"
            )

        assert result.items == []
        assert result.confidence == 0.0
        assert result.method == "llm_detected"


class TestAnOrdinalCountsInWhatWasShown:
    """ADR-367 amendment: « the second » counts in the list the person SAW.

    « Show Marc's e-mails and reply to the first » — the lookup both showed its
    list and fed the reply, and the context list kept the lookup. Read there,
    the next « the second » named an item of a list nobody was shown.
    """

    @staticmethod
    def _shown_state() -> dict:
        registry = {
            key: {
                "id": key,
                "type": "EMAIL",
                "payload": {"id": key, "subject": key.upper()},
                "meta": {"source": "gmail", "domain": "emails", "turn_id": 1},
            }
            for key in ("m1", "m2", "x")
        }
        return {
            "current_turn_id": 2,
            "registry": registry,
            "shown_items": [{"turn_id": 1, "ids": ["m1", "m2"]}],
            STATE_KEY_LAST_LIST_TURN_ID: 1,
            STATE_KEY_AGENT_RESULTS: {},
        }

    @pytest.mark.asyncio
    async def test_the_shown_list_wins_over_the_context_list(
        self, context_service: ContextResolutionService, mock_config: MagicMock
    ) -> None:
        stale_lookup = [{"id": "x", "index": 1}, {"id": "y", "index": 2}]
        ref = _make_ref(
            has_reference=True,
            reference_type="ordinal",
            ordinal_positions=[2],
            reference_domain="email",
        )
        with patch.object(
            context_service,
            "_get_items_from_tool_context_manager",
            new_callable=AsyncMock,
            return_value=stale_lookup,
        ) as context_list:
            result = await context_service._resolve_llm_detected_reference(
                ref, self._shown_state(), mock_config, "test_run"
            )

        assert [item["id"] for item in result.items] == ["m2"]
        assert result.source_turn_id == 1
        context_list.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_list_nobody_showed_lately_is_read_on_the_context_list(
        self, context_service: ContextResolutionService, mock_config: MagicMock
    ) -> None:
        state = {**self._shown_state(), "shown_items": []}
        ref = _make_ref(
            has_reference=True,
            reference_type="ordinal",
            ordinal_positions=[2],
            reference_domain="email",
        )
        with patch.object(
            context_service,
            "_get_items_from_tool_context_manager",
            new_callable=AsyncMock,
            return_value=[{"id": "x", "index": 1}, {"id": "y", "index": 2}],
        ):
            result = await context_service._resolve_llm_detected_reference(
                ref, state, mock_config, "test_run"
            )

        assert [item["id"] for item in result.items] == ["y"]


# =============================================================================
# TEST: ContextReferenceOutput model
# =============================================================================


class TestContextReferenceOutputModel:
    """Test ContextReferenceOutput Pydantic model."""

    def test_default_values(self) -> None:
        """Default instance should have has_reference=False."""
        ref = ContextReferenceOutput()
        assert ref.has_reference is False
        assert ref.reference_type == "none"
        assert ref.ordinal_positions == []
        assert ref.reference_domain == ""

    def test_serialization(self) -> None:
        """Model should serialize to dict correctly."""
        ref = ContextReferenceOutput(
            has_reference=True,
            reference_type="ordinal",
            ordinal_positions=[1, 3],
            reference_domain="contact",
        )
        data = ref.model_dump()
        assert data["has_reference"] is True
        assert data["ordinal_positions"] == [1, 3]
        assert data["reference_domain"] == "contact"

    def test_json_schema_compatible(self) -> None:
        """JSON schema should be valid and not have additionalProperties."""
        schema = ContextReferenceOutput.model_json_schema()
        assert "properties" in schema
        assert "has_reference" in schema["properties"]
        assert "ordinal_positions" in schema["properties"]
        assert {"descriptor", "selection"} <= set(schema["properties"])

    def test_a_description_defaults_to_one_item(self) -> None:
        ref = ContextReferenceOutput()
        assert ref.descriptor == ""
        assert ref.selection == "one"

    @pytest.mark.parametrize(
        ("raw", "read"),
        [
            ("latest", "latest"),
            ("LATEST", "latest"),
            ("one", "one"),
            ("all", "one"),
            ("", "one"),
            (None, "one"),
            ("newest", "one"),
        ],
    )
    def test_a_selection_outside_the_vocabulary_reads_as_one(self, raw: object, read: str) -> None:
        # Reads are forgiving: an unknown word is never a failed analysis.
        assert ContextReferenceOutput.model_validate({"selection": raw}).selection == read
