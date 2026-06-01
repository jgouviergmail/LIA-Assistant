"""get_structured_output routes config enrichment by reasoning mode.

On the reasoning-streaming path (``reasoning_emit`` set, consumed via
``astream_events``) it must use the manager-preserving enrichment to avoid the
``on_llm_end`` double-fire; otherwise the standard (flat-list) enrichment.
"""

from typing import Any

import pytest
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from src.infrastructure.llm import structured_output as so


class _Schema(BaseModel):
    x: str


@pytest.mark.asyncio
async def test_reasoning_path_uses_manager_preserving_enrich(monkeypatch: Any) -> None:
    calls: list[str] = []

    monkeypatch.setattr(
        so,
        "enrich_config_preserving_callbacks",
        lambda config, node_name: (calls.append("preserve"), config or {})[1],
    )
    monkeypatch.setattr(
        so,
        "enrich_config_with_node_metadata",
        lambda config, node_name: (calls.append("flat"), config or {})[1],
    )

    async def _fake_native(**_kwargs: Any) -> _Schema:
        return _Schema(x="ok")

    monkeypatch.setattr(so, "_get_native_structured_output", _fake_native)

    result = await so.get_structured_output(
        llm=object(),  # unused: native path is stubbed
        messages=[HumanMessage(content="q")],
        schema=_Schema,
        provider="openai",
        node_name="initiative",
        config={"metadata": {}},
        reasoning_emit=lambda _t: None,
    )

    assert isinstance(result, _Schema)
    assert calls == ["preserve"]


@pytest.mark.asyncio
async def test_non_reasoning_path_uses_standard_enrich(monkeypatch: Any) -> None:
    calls: list[str] = []

    monkeypatch.setattr(
        so,
        "enrich_config_preserving_callbacks",
        lambda config, node_name: (calls.append("preserve"), config or {})[1],
    )
    monkeypatch.setattr(
        so,
        "enrich_config_with_node_metadata",
        lambda config, node_name: (calls.append("flat"), config or {})[1],
    )

    async def _fake_native(**_kwargs: Any) -> _Schema:
        return _Schema(x="ok")

    monkeypatch.setattr(so, "_get_native_structured_output", _fake_native)

    result = await so.get_structured_output(
        llm=object(),
        messages=[HumanMessage(content="q")],
        schema=_Schema,
        provider="openai",
        node_name="planner",
        config={"metadata": {}},
        reasoning_emit=None,
    )

    assert isinstance(result, _Schema)
    assert calls == ["flat"]
