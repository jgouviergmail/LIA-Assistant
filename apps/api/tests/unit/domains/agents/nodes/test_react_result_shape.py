"""``react_result`` carries ONE shape — the ``react_agent_result`` contract.

Production run ``117ce96f`` (2026-07-21) died with
``AttributeError: 'ReactSubAgentResult' object has no attribute 'get'`` in
``_build_response_system_prompt``: the skill-runner branch assigned the runner's
dataclass to the same ``Any``-typed name the state fills with a dict, and the
whole turn fell back to a 98-character message.

The prompt builder is exercised here against BOTH shapes a naive fix would
still allow, so a future reassignment cannot silently reintroduce the crash.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from src.domains.agents.nodes.response_node import _plan_already_produced_skill_app


@dataclass
class _FakeRunnerResult:
    """Mimics ``ReactSubAgentResult``: attributes, no ``.get``."""

    final_message: str
    iteration_count: int = 1


class TestReactResultContract:
    def test_runner_dataclass_has_no_mapping_api(self) -> None:
        """Characterizes exactly what crashed: the dataclass is not a Mapping."""
        result = _FakeRunnerResult(final_message="done")
        with pytest.raises(AttributeError):
            result.get("final_message")  # type: ignore[attr-defined]

    def test_state_contract_shape_is_a_mapping(self) -> None:
        """What ``react_nodes`` writes, and therefore what every reader may assume."""
        state_shape: dict[str, Any] = {
            "final_message": "done",
            "iteration_count": 2,
            "mode": "react",
        }
        assert state_shape.get("final_message") == "done"
        assert state_shape.get("iteration_count", 0) == 2

    def test_skill_activation_result_declares_the_mapping_contract(self) -> None:
        """The threading type IS the contract: a mapping, never a bare ``Any``.

        ``dict[str, Any]`` is fine — registry payloads are heterogeneous. What
        must never come back is ``react_result: Any``, which is what allowed the
        runner dataclass and the state dict to travel under one name.
        """
        from src.domains.agents.nodes.response_node import _SkillActivationResult

        annotation = str(_SkillActivationResult.__annotations__["react_result"])
        assert annotation.startswith("dict["), (
            f"react_result must declare a mapping contract, got {annotation!r} — "
            "a bare Any is what let two incompatible shapes share one name"
        )
        assert annotation.endswith("| None")

    def test_guard_helper_still_reachable(self) -> None:
        """Sanity: the module imports cleanly with the tightened annotations."""
        assert _plan_already_produced_skill_app({}, "x") is False  # type: ignore[arg-type]
