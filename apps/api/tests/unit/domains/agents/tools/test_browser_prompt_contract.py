"""The browser's written tool calls use the native schema the model is bound to."""

import ast
import re

import pytest
from langchain_core.tools import BaseTool

from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.agents.tools import browser_tools


def _documented_calls() -> dict[str, set[str]]:
    prompt = load_prompt("browser_agent_prompt", version="v1")
    entries = re.findall(r"^- `(browser_\w+_tool)\(([^)]*)\)`:", prompt, flags=re.MULTILINE)
    assert entries, "the written browser tool inventory must be discoverable"
    return {
        name: {
            argument.split(":", 1)[0].strip() for argument in args.split(",") if argument.strip()
        }
        for name, args in entries
    }


def test_prompt_covers_the_browser_subtools() -> None:
    bound = {
        name
        for name, value in vars(browser_tools).items()
        if isinstance(value, BaseTool) and name != "browser_task_tool"
    }
    assert set(_documented_calls()) == bound


@pytest.mark.parametrize("name, documented", _documented_calls().items())
def test_every_written_argument_is_accepted_by_the_native_tool_schema(
    name: str, documented: set[str]
) -> None:
    tool = getattr(browser_tools, name)
    schema = tool.tool_call_schema
    assert not isinstance(schema, dict)
    assert documented == set(schema.model_fields)


def test_canonical_calls_validate_against_the_bound_tool_schema() -> None:
    prompt = load_prompt("browser_agent_prompt", version="v1")
    examples = re.findall(r"(browser_\w+_tool)\(([^)]*=.*?)\)", prompt)
    assert examples, "canonical tool calls must be exercised"
    for name, arguments in examples:
        call = ast.parse(f"{name}({arguments})", mode="eval").body
        assert isinstance(call, ast.Call)
        values = {arg.arg: ast.literal_eval(arg.value) for arg in call.keywords}
        tool = getattr(browser_tools, name)
        schema = tool.tool_call_schema
        assert not isinstance(schema, dict)
        schema.model_validate(values)
