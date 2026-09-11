"""Wiring of the recurrence detector (P12, Lot 3, ADR-140).

Two hooks: the post-response ledger write and the initiative-node wrapper
that merges the deterministic suggestion into the existing directive slot.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from langchain_core.messages import HumanMessage

from src.core.constants import STATE_KEY_INITIATIVE_SUGGESTION
from src.domains.agents.analysis.query_intelligence import QueryIntelligence, UserGoal
from src.domains.agents.domain_schemas import RouterOutput
from src.domains.agents.nodes.initiative_recurrence import initiative_node
from tests.helpers.runtime_context import installed_runtime_context


def _state(intention: str = "action"):
    """The state as the ROUTER actually writes it.

    Built by the real producers — ``QueryIntelligence.to_serializable_dict``
    and ``RouterOutput`` — never by hand: the hand-written shape used here
    until 2026-09-11 carried an ``intent`` key the producer has never
    emitted, so the gate read ``None`` in production while 40 tests stayed
    green (see ``tests/unit/test_qi_attr_contract_guard.py``).
    """
    intelligence = QueryIntelligence(
        original_query="fais-moi la revue de presse IA",
        english_query="do the AI press review",
        # The producer's own vocabulary: search | detail | create | update |
        # delete | send | chat | list — never "action", which belongs to the
        # ROUTER's decision below.
        immediate_intent="search",
        immediate_confidence=0.9,
        user_goal=UserGoal.FIND_INFORMATION,
        goal_reasoning="press review",
        domains=["web_search"],
        primary_domain="web_search",
    )
    return {
        "messages": [HumanMessage(content="fais-moi la revue de presse IA")],
        "user_timezone": "Europe/Paris",
        "user_language": "fr",
        "query_intelligence": intelligence.to_serializable_dict(),
        "routing_history": [
            RouterOutput(
                intention=intention,
                confidence=0.95,
                context_label="general",
                next_node="planner",
                domains=["web_search"],
            )
        ],
    }


#: The config the node receives carries thread plumbing only (ADR-231).
_CONFIG = {"configurable": {"thread_id": "t1"}}


@pytest.fixture(autouse=True)
def _open_learning_gate():
    """The person allows learning and holds no tombstone on the signature —
    the historical premise of every test below — and the operator's habits
    switch is ON. The refusal cases patch their own gate or switch."""
    from src.domains.habits.learning_gate import LearningGate

    with (
        patch(
            "src.domains.habits.capability.habits_capability_enabled",
            AsyncMock(return_value=True),
        ),
        patch(
            "src.domains.habits.learning_gate.read_learning_gate",
            AsyncMock(return_value=LearningGate(allowed=True)),
        ) as gate,
    ):
        yield gate


_USER_ID = UUID("11111111-1111-1111-1111-111111111111")


@pytest.fixture(autouse=True)
def _run_context():
    """Identity and the user's preferences travel on the typed run context."""
    with installed_runtime_context(
        user_id=_USER_ID,
        thread_id="t1",
        conversation_id="t1",
        memory_enabled=False,
        journals_enabled=False,
        psyche_enabled=False,
    ):
        yield


def _settings(**overrides):
    defaults = {
        "initiative_enabled": False,  # core short-circuits to {}
        "recurrence_suggestion_enabled": True,
        "default_language": "fr",
        "recurrence_window_days": 14,
        "recurrence_min_distinct_days": 3,
        "recurrence_suggestion_cooldown_days": 30,
        "recurrence_ledger_max_entries": 20,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.mark.unit
class TestInitiativeRecurrenceWrapper:
    async def test_suggestion_merged_when_core_silent(self):
        with (
            patch(
                "src.domains.agents.nodes.initiative_recurrence.settings",
                _settings(),
            ),
            patch(
                "src.domains.agents.services.recurrence_ledger.evaluate_suggestion",
                AsyncMock(return_value="Veux-tu automatiser cela ?"),
            ) as eval_mock,
            # The identity now travels on the typed run context (ADR-231), so the
            # node needs a real run installed — the bag key alone no longer feeds it.
            installed_runtime_context(user_id=UUID("11111111-1111-1111-1111-111111111111")),
        ):
            update = await initiative_node(_state(), _CONFIG)

        assert update[STATE_KEY_INITIATIVE_SUGGESTION] == "Veux-tu automatiser cela ?"
        # Signature built from QI shape (positional arg 2 is the signature).
        # v2 (ADR-214): domains only — the hour is data, never part of the key.
        signature = eval_mock.await_args.args[1]
        assert signature == "web_search"

    async def test_core_and_recurrence_suggestions_coexist(self):
        """Measured 2026-09-11 (sim C15): the LLM core's « active OpenWeatherMap »
        used to silence the deterministic recurrence suggestion — and its
        promotion — every turn it was offered. Both now travel in the slot."""
        with (
            patch(
                "src.domains.agents.nodes.initiative_recurrence.settings",
                _settings(),
            ),
            patch(
                "src.domains.agents.nodes.initiative_recurrence._initiative_core",
                AsyncMock(return_value={STATE_KEY_INITIATIVE_SUGGESTION: "core suggestion"}),
            ),
            patch(
                "src.domains.agents.services.recurrence_ledger.evaluate_suggestion",
                AsyncMock(return_value="recurrence suggestion"),
            ) as eval_mock,
            installed_runtime_context(user_id=UUID("11111111-1111-1111-1111-111111111111")),
        ):
            update = await initiative_node(_state(), _CONFIG)

        assert update[STATE_KEY_INITIATIVE_SUGGESTION] == (
            "core suggestion\n\nrecurrence suggestion"
        )
        eval_mock.assert_awaited_once()

    async def test_core_suggestion_alone_when_nothing_recurs(self):
        with (
            patch(
                "src.domains.agents.nodes.initiative_recurrence.settings",
                _settings(),
            ),
            patch(
                "src.domains.agents.nodes.initiative_recurrence._initiative_core",
                AsyncMock(return_value={STATE_KEY_INITIATIVE_SUGGESTION: "core suggestion"}),
            ),
            patch(
                "src.domains.agents.services.recurrence_ledger.evaluate_suggestion",
                AsyncMock(return_value=None),
            ),
            installed_runtime_context(user_id=UUID("11111111-1111-1111-1111-111111111111")),
        ):
            update = await initiative_node(_state(), _CONFIG)

        assert update[STATE_KEY_INITIATIVE_SUGGESTION] == "core suggestion"

    async def test_flag_off_leaves_update_untouched(self):
        with (
            patch(
                "src.domains.agents.nodes.initiative_recurrence.settings",
                _settings(recurrence_suggestion_enabled=False),
            ),
            patch(
                "src.domains.agents.services.recurrence_ledger.evaluate_suggestion",
                AsyncMock(return_value="never"),
            ) as eval_mock,
        ):
            update = await initiative_node(_state(), _CONFIG)

        assert STATE_KEY_INITIATIVE_SUGGESTION not in update
        eval_mock.assert_not_awaited()

    async def test_conversation_intent_never_checks(self):
        state = _state(intention="conversation")
        with (
            patch(
                "src.domains.agents.nodes.initiative_recurrence.settings",
                _settings(),
            ),
            patch(
                "src.domains.agents.services.recurrence_ledger.evaluate_suggestion",
                AsyncMock(return_value="never"),
            ) as eval_mock,
        ):
            update = await initiative_node(state, _CONFIG)

        assert STATE_KEY_INITIATIVE_SUGGESTION not in update
        eval_mock.assert_not_awaited()


@pytest.mark.unit
class TestRecurrenceRecordWiring:
    """The post-response 7th block records actionable shapes only."""

    def _run(self, *, state, config, settings):
        from src.domains.agents.nodes.post_response_extractions import (
            _schedule_post_response_extractions,
        )

        captured: list = []

        def _fake_fire_and_forget(coro, *, name="", run_id=None):
            captured.append(name)
            coro.close()

        with (
            patch(
                "src.domains.agents.nodes.post_response_extractions.safe_fire_and_forget",
                side_effect=_fake_fire_and_forget,
            ),
            patch(
                "src.domains.agents.nodes.post_response_extractions.settings",
                settings,
            ),
        ):
            _schedule_post_response_extractions(
                state,
                config,
                "run-1",
                user_msg_is_trivial=False,
                personality_instruction=None,
                user_message_embedding=None,
                user_language="fr",
                final_content="Voilà !",
                previous_journal_injected_ids=[],
                psyche_appraisal=None,
            )
        return captured

    def _extraction_settings(self, **overrides):
        defaults = {
            "habits_enabled": True,
            "recurrence_suggestion_enabled": True,
            "recurrence_window_days": 14,
            "recurrence_ledger_max_entries": 20,
            "open_loops_enabled": False,
            "journals_enabled": False,
            "psyche_enabled": False,
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def test_recorded_for_actionable_query(self):
        names = self._run(state=_state(), config=_CONFIG, settings=self._extraction_settings())
        assert any(n.startswith("recurrence_record_") for n in names)

    def test_not_recorded_when_the_habits_flag_is_off(self):
        """The ledger is habit LEARNING (ADR-214 c): it follows HABITS_ENABLED."""
        names = self._run(
            state=_state(),
            config=_CONFIG,
            settings=self._extraction_settings(habits_enabled=False),
        )
        assert not any(n.startswith("recurrence_record_") for n in names)

    def test_the_chat_suggestion_flag_does_not_govern_the_ledger(self):
        """RECURRENCE_SUGGESTION_ENABLED decides whether LIA OFFERS an
        automation in the answer — never whether the request is learned.
        The previous version of this test passed on a missing attribute."""
        names = self._run(
            state=_state(),
            config=_CONFIG,
            settings=self._extraction_settings(recurrence_suggestion_enabled=False),
        )
        assert any(n.startswith("recurrence_record_") for n in names)

    def test_not_recorded_for_conversation_intent(self):
        state = _state(intention="conversation")
        names = self._run(state=state, config=_CONFIG, settings=self._extraction_settings())
        assert not any(n.startswith("recurrence_record_") for n in names)


@pytest.mark.unit
class TestAutomatedRunGuard:
    """ADR-214 amendment (2026-09-03): the evaluation is guarded like the
    recording. A scheduled run with a LOCKED ledger must neither fire the
    suggestion nor promote a habit — otherwise LIA proposes to automate her
    own automation."""

    async def test_automated_run_never_evaluates(self):
        from src.infrastructure.observability.metrics_agents import (
            recurrence_evaluation_skipped_total,
        )

        before = recurrence_evaluation_skipped_total.labels(reason="automated_source")._value.get()
        with (
            patch("src.domains.agents.nodes.initiative_recurrence.settings", _settings()),
            patch(
                "src.domains.agents.services.recurrence_ledger.evaluate_suggestion",
                AsyncMock(return_value="Veux-tu automatiser cela ?"),
            ) as eval_mock,
            installed_runtime_context(user_id=_USER_ID, is_automated_source=True),
        ):
            update = await initiative_node(_state(), _CONFIG)

        assert STATE_KEY_INITIATIVE_SUGGESTION not in update
        eval_mock.assert_not_awaited()
        after = recurrence_evaluation_skipped_total.labels(reason="automated_source")._value.get()
        assert after == before + 1

    async def test_human_run_with_the_same_ledger_fires(self):
        with (
            patch("src.domains.agents.nodes.initiative_recurrence.settings", _settings()),
            patch(
                "src.domains.agents.services.recurrence_ledger.evaluate_suggestion",
                AsyncMock(return_value="Veux-tu automatiser cela ?"),
            ) as eval_mock,
            installed_runtime_context(user_id=_USER_ID, is_automated_source=False),
        ):
            update = await initiative_node(_state(), _CONFIG)

        assert update[STATE_KEY_INITIATIVE_SUGGESTION] == "Veux-tu automatiser cela ?"
        eval_mock.assert_awaited_once()


@pytest.mark.unit
class TestThePersonsGateOnTheSuggestion:
    """« Apprendre mes habitudes » OFF, a paused or a blocked habit: no
    evaluation, no suggestion, one counted reason (measured violated
    2026-09-11 — sim C5 and the blocked-key reading of ADR-214 decision 3)."""

    @pytest.mark.parametrize(
        ("gate_kwargs", "reason"),
        [
            ({"allowed": False}, "user_disabled"),
            ({"allowed": True, "recurring_status": "paused"}, "paused"),
            ({"allowed": True, "recurring_status": "blocked"}, "blocked"),
        ],
    )
    async def test_refused_gate_skips_the_ledger_evaluation(
        self, gate_kwargs: dict, reason: str
    ) -> None:
        from src.domains.habits.learning_gate import LearningGate
        from src.infrastructure.observability.metrics_agents import (
            recurrence_evaluation_skipped_total,
        )

        before = recurrence_evaluation_skipped_total.labels(reason=reason)._value.get()
        with (
            patch("src.domains.agents.nodes.initiative_recurrence.settings", _settings()),
            patch(
                "src.domains.habits.learning_gate.read_learning_gate",
                AsyncMock(return_value=LearningGate(**gate_kwargs)),
            ) as gate,
            patch(
                "src.domains.agents.services.recurrence_ledger.evaluate_suggestion",
                AsyncMock(return_value="recurrence suggestion"),
            ) as eval_mock,
            installed_runtime_context(user_id=UUID("11111111-1111-1111-1111-111111111111")),
        ):
            update = await initiative_node(_state(), _CONFIG)

        assert STATE_KEY_INITIATIVE_SUGGESTION not in update
        eval_mock.assert_not_awaited()
        gate.assert_awaited_once_with("11111111-1111-1111-1111-111111111111", "web_search")
        after = recurrence_evaluation_skipped_total.labels(reason=reason)._value.get()
        assert after == before + 1

    async def test_the_operator_switch_closes_the_suggestion_at_the_act(self) -> None:
        """ADR-280 amendment: a habits capability switched OFF after boot must
        silence the chat suggestion too — a stale ledger key (35-day TTL)
        would otherwise still lock and speak, and the promotion it triggers
        is refused while the words are not."""
        from src.infrastructure.observability.metrics_agents import (
            recurrence_evaluation_skipped_total,
        )

        before = recurrence_evaluation_skipped_total.labels(reason="feature_disabled")._value.get()
        with (
            patch("src.domains.agents.nodes.initiative_recurrence.settings", _settings()),
            patch(
                "src.domains.habits.capability.habits_capability_enabled",
                AsyncMock(return_value=False),
            ),
            patch(
                "src.domains.agents.services.recurrence_ledger.evaluate_suggestion",
                AsyncMock(return_value="recurrence suggestion"),
            ) as eval_mock,
            installed_runtime_context(user_id=_USER_ID),
        ):
            update = await initiative_node(_state(), _CONFIG)
        assert STATE_KEY_INITIATIVE_SUGGESTION not in update
        eval_mock.assert_not_awaited()
        after = recurrence_evaluation_skipped_total.labels(reason="feature_disabled")._value.get()
        assert after == before + 1

    async def test_an_active_row_still_evaluates(self) -> None:
        from src.domains.habits.learning_gate import LearningGate

        with (
            patch("src.domains.agents.nodes.initiative_recurrence.settings", _settings()),
            patch(
                "src.domains.habits.learning_gate.read_learning_gate",
                AsyncMock(return_value=LearningGate(allowed=True, recurring_status="active")),
            ),
            patch(
                "src.domains.agents.services.recurrence_ledger.evaluate_suggestion",
                AsyncMock(return_value="recurrence suggestion"),
            ) as eval_mock,
            installed_runtime_context(user_id=UUID("11111111-1111-1111-1111-111111111111")),
        ):
            update = await initiative_node(_state(), _CONFIG)
        assert update[STATE_KEY_INITIATIVE_SUGGESTION] == "recurrence suggestion"
        eval_mock.assert_awaited_once()
