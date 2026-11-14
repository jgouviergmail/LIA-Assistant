"""A run with something to admit is never « nothing new » — whatever its model declares.

A routine told to notify only of something new relies on the answering model to
declare that it has nothing new. A prompt can tell it that a failed tool is not
« nothing new »; only the code can make sure of it (ADR-303: a failure is said,
never read as success). The seam that already knows what this answer must admit
— a step that failed, a search cut short, a step left unrun — voids the
declaration: the routine notifies, as it always did.

What the PLATFORM is going through is another fact: a degradation the
diagnostics advisor reports is told to the model beside the run's own failures,
and it is not a failure of the run. Measured on dev on 2026-11-12: one open
incident on the instance's disk voided every quiet routine's silence.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.core.config import settings
from src.core.field_names import FIELD_ERROR, FIELD_ERROR_CODE, FIELD_SUCCESS
from src.domains.agents.services import nothing_new
from src.domains.agents.services.nothing_new import (
    attach_nothing_new_to_done,
    quiet_run_scope,
    take_nothing_new,
)
from src.domains.agents.services.runtime_failure_directive import build_run_honesty_block
from src.domains.diagnostics import failure_context
from src.domains.diagnostics.advisor import CapabilityDegradation

pytestmark = pytest.mark.unit

_DECLARED = "Nothing new this morning.\n<lia_nothing_new/>"

_FAILED_STEP = {
    "step_1": {
        FIELD_SUCCESS: False,
        FIELD_ERROR: "the mailbox did not answer",
        FIELD_ERROR_CODE: "EXTERNAL_API_ERROR",
    }
}


@pytest.fixture(autouse=True)
def _no_declaration_left_behind() -> None:
    nothing_new._declared.clear()


@pytest.fixture
def platform(monkeypatch: pytest.MonkeyPatch) -> list[CapabilityDegradation]:
    """What the diagnostics advisor reports; the test fills it, nothing by default."""
    degradations: list[CapabilityDegradation] = []

    async def active() -> list[CapabilityDegradation]:
        return degradations

    monkeypatch.setattr(settings, "diagnostics_enabled", True)
    monkeypatch.setattr(failure_context, "get_active_degradations", active)
    return degradations


def _degraded(platform: list[CapabilityDegradation]) -> None:
    platform.append(
        CapabilityDegradation(
            capability="platform",
            status="critical",
            reason="open_incident:DiskSpaceCritical",
            alternative=None,
        )
    )


def _declares(run_id: str) -> bool:
    """Whether a run's « nothing new » reached its ``done`` chunk."""
    take_nothing_new(_DECLARED, run_id)
    metadata: dict[str, Any] = {}
    attach_nothing_new_to_done(metadata, run_id)
    return metadata.get("nothing_new") is True


async def test_a_run_that_went_clean_may_declare_nothing_new(
    platform: list[CapabilityDegradation],
) -> None:
    with quiet_run_scope(True):
        assert await build_run_honesty_block({"messages": []}) == ""

        assert _declares("clean") is True


async def test_a_platform_degradation_is_told_but_is_no_failure_of_the_run(
    platform: list[CapabilityDegradation],
) -> None:
    _degraded(platform)
    with quiet_run_scope(True):
        # The model still hears what the platform is going through…
        assert "DiskSpaceCritical" in await build_run_honesty_block({"messages": []})

        # …and a run whose own steps all answered may still have nothing new.
        assert _declares("degraded") is True


async def test_a_failure_beside_a_degradation_still_voids_the_declaration(
    platform: list[CapabilityDegradation],
) -> None:
    _degraded(platform)
    with quiet_run_scope(True):
        await build_run_honesty_block({"messages": [], "completed_steps": _FAILED_STEP})

        assert _declares("both") is False


@pytest.mark.parametrize(
    "state",
    [
        pytest.param(
            {"messages": [], "completed_steps": _FAILED_STEP},
            id="a step that failed",
        ),
        pytest.param(
            {
                "messages": [],
                "react_agent_result": {"truncation": {"reason": "max_iterations", "iterations": 6}},
            },
            id="a search cut short",
        ),
        pytest.param(
            {"messages": [], "held_plan": {"not_run": {"step_2": "its act was not confirmed"}}},
            id="a step left unrun",
        ),
    ],
)
async def test_what_the_answer_must_admit_voids_the_declaration(state: dict[str, Any]) -> None:
    with quiet_run_scope(True):
        assert await build_run_honesty_block(state) != ""

        assert _declares("admits") is False


async def test_one_run_s_admission_is_not_the_next_one_s() -> None:
    failed = {"messages": [], "held_plan": {"not_run": {"step_2": "never ran"}}}
    with quiet_run_scope(True):
        await build_run_honesty_block(failed)
    with quiet_run_scope(True):
        await build_run_honesty_block({"messages": []})

        assert _declares("next") is True
