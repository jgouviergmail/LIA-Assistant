"""The integration turn boundary preserves collector and runtime ownership."""

from contextlib import nullcontext

import pytest

from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.domains.agents.effects.treatments import (
    collected_treatments,
    is_collecting,
    record_treatment,
    treatment_collector,
)
from tests.helpers.runtime_context import (
    installed_runtime_context as original_runtime_context,
)
from tests.helpers.runtime_context import make_runtime_context
from tests.integration.application_runtime_context import installed_runtime_context

pytestmark = pytest.mark.unit


class _BodyError(RuntimeError):
    """A controlled interruption of the caller's body."""


@pytest.mark.parametrize("raises", [False, True])
def test_opens_and_restores_a_missing_collector_and_the_previous_runtime(raises: bool) -> None:
    previous = make_runtime_context(thread_id="previous-runtime")
    selected = make_runtime_context(thread_id="integration-runtime")
    with original_runtime_context(previous):
        assert not is_collecting()
        with pytest.raises(_BodyError) if raises else nullcontext():
            with installed_runtime_context(selected) as actual:
                assert actual is selected and runtime_context_if_running() is selected
                assert is_collecting()
                record_treatment("native_runtime_probe", "draft", succeeded=True, duration_ms=1)
                assert [
                    (row.tool_name, row.run_id, row.outcome) for row in collected_treatments()
                ] == [("native_runtime_probe", "integration-runtime", "ok")]
                if raises:
                    raise _BodyError("controlled body failure")
        assert not is_collecting()
        assert runtime_context_if_running() is previous


@pytest.mark.parametrize("raises", [False, True])
def test_reuses_and_preserves_the_enclosing_collector(raises: bool) -> None:
    previous = make_runtime_context(thread_id="previous-runtime")
    with original_runtime_context(previous), treatment_collector(run_id="enclosing-run") as rows:
        with pytest.raises(_BodyError) if raises else nullcontext():
            with installed_runtime_context(thread_id="inner-runtime"):
                assert is_collecting()
                record_treatment("native_runtime_probe", "read", succeeded=True, duration_ms=1)
                assert len(rows) == 1 and collected_treatments()[0] is rows[0]
                if raises:
                    raise _BodyError("controlled body failure")
        assert is_collecting()
        assert [(row.tool_name, row.run_id, row.outcome) for row in rows] == [
            ("native_runtime_probe", "enclosing-run", "ok")
        ]
        assert runtime_context_if_running() is previous
    assert not is_collecting()


def test_original_runtime_helper_still_leaves_the_collector_absent() -> None:
    assert not is_collecting()
    with original_runtime_context(thread_id="original-runtime") as context:
        assert runtime_context_if_running() is context
        assert not is_collecting() and collected_treatments() == ()
    assert not is_collecting()
