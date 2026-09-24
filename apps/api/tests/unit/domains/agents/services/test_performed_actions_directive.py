"""A ReAct turn's acts are stated to the response model as its own (ADR-263 §23).

Measured 2026-09-23 on the failing turn's own prompt, with the real response
model: nothing stated, 6 answers out of 6 denied an image that had been
generated; the act written as a data line, 3 out of 100 invented a second
image and the person still met a denial; the act in this directive, 0 and 0
out of 100.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.agents.services.performed_actions_directive import (
    build_performed_actions_block,
)

pytestmark = [pytest.mark.unit]

_PERFORMED = "src.domains.agents.effects.turn_summary.performed_effects"


def _effect(status: str, target: str) -> dict[str, Any]:
    """One entry of ``performed_effects``, as the register reads it back."""
    return {
        "label_key": "effects.labels.generate_image",
        "values": {"target": target},
        "status": status,
        "tool_name": "generate_image",
    }


def _react_state() -> dict[str, Any]:
    """A turn the ReAct loop ran, whatever its answer — here, none (a budget exit)."""
    return {"react_agent_result": {"final_message": "", "iteration_count": 2}}


class TestTheDirectiveStatesTheLoopSActs:
    async def test_only_the_succeeded_acts_are_stated(self) -> None:
        read = AsyncMock(return_value=[_effect("succeeded", "un chat"), _effect("failed", "x")])
        with patch(_PERFORMED, read):
            block = await build_performed_actions_block(_react_state(), "run-1", "fr")

        read.assert_awaited_once_with("run-1")
        # A failure is the honesty directive's to state, once (ADR-303).
        assert "- Image générée : un chat\n" in block
        assert "- Image générée : x" not in block

    async def test_the_block_is_the_versioned_file_filled(self) -> None:
        """No inline prose (ADR-284): the block IS the file, filled."""
        template = load_prompt("response_directive_performed_actions")
        with patch(_PERFORMED, AsyncMock(return_value=[_effect("succeeded", "a cat")])):
            block = await build_performed_actions_block(_react_state(), "run-1", "en")

        assert block == template.format(performed_actions="- Generated an image: a cat")

    async def test_every_act_is_one_line(self) -> None:
        effects = [_effect("succeeded", "a cat"), _effect("succeeded", "a dog")]
        with patch(_PERFORMED, AsyncMock(return_value=effects)):
            block = await build_performed_actions_block(_react_state(), "run-1", "en")

        assert "- Generated an image: a cat\n- Generated an image: a dog\n" in block


class TestNothingIsStatedWhenNothingWasDone:
    async def test_a_turn_with_no_succeeded_act_gets_no_directive(self) -> None:
        with patch(_PERFORMED, AsyncMock(return_value=[_effect("failed", "x")])):
            assert await build_performed_actions_block(_react_state(), "run-1", "fr") == ""

    async def test_a_pipeline_turn_reads_no_register(self) -> None:
        """The pipeline's summary already carries each tool's own confirmation."""
        read = AsyncMock(return_value=[_effect("succeeded", "un chat")])
        with patch(_PERFORMED, read):
            assert await build_performed_actions_block({}, "run-1", "fr") == ""

        read.assert_not_awaited()

    async def test_a_run_nobody_named_reads_nothing(self) -> None:
        """The node passes ``run_id_of(config)``, empty when absent — never the
        ``"unknown"`` logging placeholder, under which the register may file rows."""
        assert await build_performed_actions_block(_react_state(), "", "fr") == ""
