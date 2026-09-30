"""The response node never re-runs a skill the ReAct loop already activated (ADR-327).

Measured on dev 2026-09-30: « create a skill converting Celsius to Fahrenheit »
— the ReAct loop activated the skill-generator, ran its validation script and
PROPOSED the skill; the response node then found the same skill detected,
saw it needs a runner (it ships scripts) and ran the runner AGAIN: 27 more
seconds of model calls and a SECOND card of the same name, which the person
could only refuse as stale once the first was installed. In ReAct the loop IS
the runner: what it activated this turn is recorded in the state and the
response node reads it, as it reads the plan's own widget (B1).
"""

from __future__ import annotations

from typing import Any

import pytest

from src.domains.agents.nodes.react_result_reading import activated_skill_of
from src.domains.agents.nodes.response_node import _loop_already_activated
from src.domains.agents.tools.output import UnifiedToolOutput

pytestmark = pytest.mark.unit


class TestWhatAnActivationLooksLike:
    def test_an_activation_names_its_skill(self) -> None:
        own = UnifiedToolOutput.action_success(
            message="…", metadata={"skill_name": "pdf", "activation": "dedicated_tool"}
        )
        third_party = UnifiedToolOutput.data_success(
            message="…", metadata={"skill_name": "web", "activation": "isolated_runner"}
        )
        assert activated_skill_of(own) == "pdf"
        assert activated_skill_of(third_party) == "web"

    def test_anything_else_is_no_activation(self) -> None:
        assert activated_skill_of(UnifiedToolOutput.data_success(message="x")) is None
        assert activated_skill_of({"success": True, "data": "ok"}) is None
        assert activated_skill_of("plain text") is None
        assert (
            activated_skill_of(UnifiedToolOutput.failure(message="no", error_code="NOT_FOUND"))
            is None
        )

    def test_a_refused_activation_is_no_activation(self) -> None:
        refused = UnifiedToolOutput.failure(
            message="disabled",
            error_code="FEATURE_DISABLED",
            metadata={"skill_name": "pdf", "activation": "dedicated_tool"},
        )
        assert activated_skill_of(refused) is None


class TestTheResponseNodeReadsIt:
    def test_the_loops_activation_skips_the_runner(self) -> None:
        state: dict[str, Any] = {"react_activated_skills": ["skill-generator"]}
        assert _loop_already_activated(state, "skill-generator") is True

    def test_another_skill_never_fires_the_guard(self) -> None:
        state: dict[str, Any] = {"react_activated_skills": ["pdf"]}
        assert _loop_already_activated(state, "skill-generator") is False

    def test_an_empty_or_missing_record_is_no_activation(self) -> None:
        assert _loop_already_activated({}, "pdf") is False
        assert _loop_already_activated({"react_activated_skills": None}, "pdf") is False
        assert _loop_already_activated({"react_activated_skills": []}, "pdf") is False
