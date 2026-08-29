"""Every post-response extraction decision must be countable (L1).

Before this counter, the only way to know whether a turn fed long-term memory,
interests or the journal was to read the code: each skip was logged at debug
level and nothing aggregated them. Two production defects (channels never
feeding journals, HITL draft turns extracting nothing) stayed invisible for
exactly that reason.

These tests pin the (kind, outcome) contract per branch. They are deliberately
delta-based: Prometheus counters are process-global, so an absolute value would
couple this module to test ordering.
"""

from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID

import pytest
from langchain_core.messages import HumanMessage

from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.nodes.post_response_extractions import (
    KIND_INTERESTS,
    KIND_JOURNAL,
    KIND_MEMORY,
    KIND_OPEN_LOOPS,
    KIND_PSYCHE,
    KIND_RECURRENCE,
    OUTCOME_AUTOMATED_SOURCE,
    OUTCOME_FEATURE_DISABLED,
    OUTCOME_NO_USER,
    OUTCOME_NOT_APPLICABLE,
    OUTCOME_SCHEDULED,
    OUTCOME_TRIVIAL,
    OUTCOME_USER_DISABLED,
    _schedule_post_response_extractions,
)
from src.infrastructure.observability.metrics_extractions import (
    post_response_extraction_scheduled_total,
)
from tests.helpers.runtime_context import installed_runtime_context, make_runtime_context

USER_ID = "11111111-1111-1111-1111-111111111111"


def _counter(kind: str, outcome: str) -> float:
    """Current value of one (kind, outcome) series."""
    return float(
        post_response_extraction_scheduled_total.labels(kind=kind, outcome=outcome)._value.get()
    )


def _state(*, intent: str = "action", primary: str = "email"):
    return {
        "messages": [HumanMessage(content="je déménage à Lyon en septembre")],
        "query_intelligence": {
            "intent": intent,
            "primary_domain": primary,
            "secondary_domains": [],
        },
        "user_timezone": "Europe/Paris",
    }


def _config(
    *,
    automated: bool = False,
    memory: bool = True,
    journals: bool = True,
    psyche: bool = True,
    user_id: str | None = USER_ID,
) -> LiaRuntimeContext | None:
    """The run context the scheduler reads (ADR-231), not a configurable bag.

    user_id=None returns None: identity is a mandatory field of the context,
    so "the turn has no acting user" is now expressible only as "there is no run
    context" — which is exactly what the no-user branches guard against.
    """
    if user_id is None:
        return None
    return make_runtime_context(
        user_id=UUID(user_id),
        thread_id="thread-1",
        conversation_id="thread-1",
        is_automated_source=automated,
        memory_enabled=memory,
        journals_enabled=journals,
        psyche_enabled=psyche,
    )


def _settings(
    *,
    open_loops: bool = True,
    psyche: bool = True,
    recurrence: bool = True,
):
    return SimpleNamespace(
        open_loops_enabled=open_loops,
        journals_enabled=True,
        psyche_enabled=psyche,
        recurrence_suggestion_enabled=recurrence,
    )


def _run(state, context, settings_ns, *, trivial: bool = False) -> None:
    """Invoke the scheduler with the background tasks neutralized.

    The RunnableConfig carries thread plumbing only; everything the scheduler
    reads about the turn now comes from the installed run context.
    """
    config = {"configurable": {"thread_id": "thread-1"}}

    def _fake_fire_and_forget(coro, *, name="", run_id=None):
        coro.close()  # prevent un-awaited coroutine warnings

    installed = installed_runtime_context(context) if context is not None else nullcontext()
    with (
        installed,
        patch(
            "src.domains.agents.nodes.post_response_extractions.safe_fire_and_forget",
            side_effect=_fake_fire_and_forget,
        ),
        patch(
            "src.domains.agents.nodes.post_response_extractions.settings",
            settings_ns,
        ),
    ):
        _schedule_post_response_extractions(
            state,
            config,
            "run-1",
            user_msg_is_trivial=trivial,
            personality_instruction=None,
            user_message_embedding=None,
            user_language="fr",
            final_content="Noté !",
            previous_journal_injected_ids=[],
            psyche_appraisal=None,
        )


@pytest.mark.unit
class TestExtractionMetrics:
    """One (kind, outcome) pair per guard branch."""

    def test_nominal_turn_counts_every_kind_as_scheduled(self):
        """A meaningful direct-user turn schedules all six subsystems."""
        kinds = (
            KIND_MEMORY,
            KIND_INTERESTS,
            KIND_OPEN_LOOPS,
            KIND_JOURNAL,
            KIND_PSYCHE,
            KIND_RECURRENCE,
        )
        before = {k: _counter(k, OUTCOME_SCHEDULED) for k in kinds}

        _run(_state(), _config(), _settings())

        for kind in kinds:
            assert _counter(kind, OUTCOME_SCHEDULED) == before[kind] + 1, kind

    def test_automated_source_counts_every_kind_as_such(self):
        """Scheduled actions must never feed the user's long-term state."""
        kinds = (
            KIND_MEMORY,
            KIND_INTERESTS,
            KIND_OPEN_LOOPS,
            KIND_JOURNAL,
            KIND_PSYCHE,
            KIND_RECURRENCE,
        )
        before = {k: _counter(k, OUTCOME_AUTOMATED_SOURCE) for k in kinds}

        _run(_state(), _config(automated=True), _settings())

        for kind in kinds:
            assert _counter(kind, OUTCOME_AUTOMATED_SOURCE) == before[kind] + 1, kind

    def test_trivial_message_counts_every_kind_as_trivial(self):
        """ "ok" / "merci" cost nothing — and that is now visible."""
        kinds = (
            KIND_MEMORY,
            KIND_INTERESTS,
            KIND_OPEN_LOOPS,
            KIND_JOURNAL,
            KIND_PSYCHE,
            KIND_RECURRENCE,
        )
        before = {k: _counter(k, OUTCOME_TRIVIAL) for k in kinds}

        _run(_state(), _config(), _settings(), trivial=True)

        for kind in kinds:
            assert _counter(kind, OUTCOME_TRIVIAL) == before[kind] + 1, kind

    def test_user_disabled_is_distinct_from_feature_disabled(self):
        """The psyche guard is a disjunction: the metric still tells the two apart."""
        before_user = _counter(KIND_PSYCHE, OUTCOME_USER_DISABLED)
        _run(_state(), _config(psyche=False), _settings(psyche=True))
        assert _counter(KIND_PSYCHE, OUTCOME_USER_DISABLED) == before_user + 1

        before_feature = _counter(KIND_PSYCHE, OUTCOME_FEATURE_DISABLED)
        _run(_state(), _config(psyche=True), _settings(psyche=False))
        assert _counter(KIND_PSYCHE, OUTCOME_FEATURE_DISABLED) == before_feature + 1

    def test_memory_and_journal_user_preferences_are_counted(self):
        before_memory = _counter(KIND_MEMORY, OUTCOME_USER_DISABLED)
        before_journal = _counter(KIND_JOURNAL, OUTCOME_USER_DISABLED)

        _run(_state(), _config(memory=False, journals=False), _settings())

        assert _counter(KIND_MEMORY, OUTCOME_USER_DISABLED) == before_memory + 1
        assert _counter(KIND_JOURNAL, OUTCOME_USER_DISABLED) == before_journal + 1

    def test_global_flags_are_counted_as_feature_disabled(self):
        before_loops = _counter(KIND_OPEN_LOOPS, OUTCOME_FEATURE_DISABLED)
        before_recurrence = _counter(KIND_RECURRENCE, OUTCOME_FEATURE_DISABLED)

        _run(_state(), _config(), _settings(open_loops=False, recurrence=False))

        assert _counter(KIND_OPEN_LOOPS, OUTCOME_FEATURE_DISABLED) == before_loops + 1
        assert _counter(KIND_RECURRENCE, OUTCOME_FEATURE_DISABLED) == before_recurrence + 1

    def test_missing_user_is_counted(self):
        """No run context at all — the kinds gated on identity alone say so.

        Since ADR-231, identity and the user's preferences travel on the SAME
        typed context, so "no acting user" and "no preferences" are one state:
        journal and psyche default to OFF with no context, so they hit their
        preference gate first and report ``user_disabled``; memory defaults to ON
        and reaches the identity check, as do the kinds gated on a global setting
        only. The outcome a dashboard reads must be the one the code can actually
        emit, so each kind is asserted on the branch it really takes.
        """
        kinds = (KIND_MEMORY, KIND_INTERESTS, KIND_OPEN_LOOPS)
        before = {k: _counter(k, OUTCOME_NO_USER) for k in kinds}
        before_disabled = {
            k: _counter(k, OUTCOME_USER_DISABLED) for k in (KIND_JOURNAL, KIND_PSYCHE)
        }

        _run(_state(), _config(user_id=None), _settings())

        for kind in kinds:
            assert _counter(kind, OUTCOME_NO_USER) == before[kind] + 1, kind
        for kind, was in before_disabled.items():
            assert _counter(kind, OUTCOME_USER_DISABLED) == was + 1, kind

    def test_non_actionable_query_is_not_applicable_for_recurrence(self):
        """Only actionable domain queries can recur into automations."""
        before = _counter(KIND_RECURRENCE, OUTCOME_NOT_APPLICABLE)

        _run(_state(intent="conversation"), _config(), _settings())

        assert _counter(KIND_RECURRENCE, OUTCOME_NOT_APPLICABLE) == before + 1

    def test_metric_failure_never_breaks_the_scheduler(self):
        """Observability is best-effort: a broken counter must not break a turn."""
        with patch(
            "src.domains.agents.nodes.post_response_extractions."
            "post_response_extraction_scheduled_total"
        ) as broken:
            broken.labels.side_effect = RuntimeError("registry exploded")
            _run(_state(), _config(), _settings())  # must not raise
