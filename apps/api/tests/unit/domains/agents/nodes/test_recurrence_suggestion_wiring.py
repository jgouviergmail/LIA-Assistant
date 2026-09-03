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
from src.domains.agents.nodes.initiative_recurrence import initiative_node
from tests.helpers.runtime_context import installed_runtime_context


def _state():
    return {
        "messages": [HumanMessage(content="fais-moi la revue de presse IA")],
        "user_timezone": "Europe/Paris",
        "user_language": "fr",
        "query_intelligence": {
            "intent": "action",
            "primary_domain": "web_search",
            "secondary_domains": [],
        },
    }


#: The config the node receives carries thread plumbing only (ADR-231).
_CONFIG = {"configurable": {"thread_id": "t1"}}
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

    async def test_core_suggestion_never_overridden(self):
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
        ):
            update = await initiative_node(_state(), _CONFIG)

        assert update[STATE_KEY_INITIATIVE_SUGGESTION] == "core suggestion"
        eval_mock.assert_not_awaited()

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
        state = _state()
        state["query_intelligence"]["intent"] = "conversation"
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

    def test_not_recorded_when_flag_off(self):
        names = self._run(
            state=_state(),
            config=_CONFIG,
            settings=self._extraction_settings(recurrence_suggestion_enabled=False),
        )
        assert not any(n.startswith("recurrence_record_") for n in names)

    def test_not_recorded_for_conversation_intent(self):
        state = _state()
        state["query_intelligence"]["intent"] = "conversation"
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
