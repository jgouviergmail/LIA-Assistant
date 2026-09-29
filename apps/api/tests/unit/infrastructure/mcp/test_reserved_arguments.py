"""Third-party parameter names must survive Pydantic and LangChain unchanged."""

import warnings
from typing import Any

import pytest

from src.infrastructure.mcp.tool_adapter import MCPToolAdapter

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "field", ["json", "schema", "model_dump", "model_config", "model_validate_json"]
)
async def test_reserved_argument_reaches_the_server_by_its_original_name(field: str) -> None:
    properties = {field: {"type": "string"}, "mcp_arg_0": {"type": "integer"}}
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        tool = MCPToolAdapter.from_mcp_tool(
            "proof",
            "read",
            "Read proof data",
            {"type": "object", "properties": properties, "required": list(properties)},
        )
    assert tool.args_schema is not None
    assert set(tool.tool_call_schema["properties"]) == set(properties)
    seen: list[dict[str, Any]] = []

    async def boundary(**kwargs: Any) -> str:
        seen.append(kwargs)
        return "ok"

    from src.domains.agents.effects.runtime import EFFECT_GATED_NAME_ATTR

    setattr(boundary, EFFECT_GATED_NAME_ATTR, tool.name)
    tool._gated_call = boundary
    arguments = {field: "payload", "mcp_arg_0": 7}
    assert await tool.ainvoke(arguments) == "ok"
    assert await tool.coroutine(**arguments) == "ok"
    from langchain_core.utils.function_calling import convert_to_openai_tool

    from src.domains.agents.tools.mcp_react_tools import _MCPReActWrapper

    wrapped = _MCPReActWrapper(tool)
    assert set(convert_to_openai_tool(wrapped)["function"]["parameters"]["properties"]) == set(
        properties
    )
    assert await wrapped.ainvoke(arguments) == "ok"
    from src.domains.agents.tools.react_tool_wrapper import ReactToolWrapper

    generic = ReactToolWrapper(tool)
    assert set(convert_to_openai_tool(generic)["function"]["parameters"]["properties"]) == set(
        properties
    )
    assert await generic.ainvoke(arguments) == "ok"
    assert seen == [arguments] * 4
