"""Contract: every registered tool converts to an LLM-facing schema, and none leaks
an injected argument to the model.

Why this exists (audit F9): ``test_tool_registry_smoke`` imports and invokes every
tool, but never converts one to an OpenAI tool schema — and no other file in
``src/`` or ``tests/`` calls ``convert_to_openai_tool`` either. The three tests
using ``bind_tools`` pass through a fake model that ignores its ``tools`` argument.
So two failure modes were invisible to CI:

1. An injected argument (``runtime``, ``config``, ``state``, ``store``,
   ``tool_call_id``) surfacing in the schema sent to the model — wasted tokens and
   an invitation to hallucinate a value for it.
2. A tool that cannot be converted at all. Measured: a bare
   ``runtime: ToolRuntime | None = None`` annotation raises
   ``PydanticInvalidForJsonSchema`` because ``ToolRuntime`` carries a callable
   field, while ``Annotated[ToolRuntime | None, InjectedToolArg] = None`` is fine.
   Such a tool cannot be bound to any model.

This guard is also the non-regression oracle for the runtime-context migration
(ADR-231), which parameterizes every ``ToolRuntime`` annotation in the codebase.
"""

import warnings

import pytest
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool

from src.domains.agents.tools.tool_registry import ensure_tools_loaded, get_all_tools

# Arguments the tool-execution layer injects. None may ever reach the model.
INJECTED_ARGUMENT_NAMES: frozenset[str] = frozenset(
    {"runtime", "config", "state", "store", "tool_call_id"}
)

# Floor for the registry-loaded check. Deliberately well below the measured count
# (105 on 2026-08-19) so removing a tool family does not fail this file for the
# wrong reason, while a registry that failed to load still does.
MIN_EXPECTED_TOOLS = 80


@pytest.fixture(scope="module")
def registered_tools() -> dict[str, BaseTool]:
    """Every auto-registered tool, loaded once for the module."""
    ensure_tools_loaded()
    tools = get_all_tools()
    assert tools, "the tool registry is empty — ensure_tools_loaded() did nothing"
    return tools


def _openai_parameters(tool: BaseTool) -> dict:
    """Convert a tool and return the parameter block the model actually sees."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        schema = convert_to_openai_tool(tool)
    return schema["function"].get("parameters") or {}


@pytest.mark.unit
def test_every_tool_converts_to_an_openai_schema(
    registered_tools: dict[str, BaseTool],
) -> None:
    """A tool that cannot be converted cannot be bound to any model."""
    failures: list[str] = []
    for name, tool in sorted(registered_tools.items()):
        try:
            _openai_parameters(tool)
        except Exception as exc:  # noqa: BLE001 - report every failure at once
            failures.append(f"{name}: {type(exc).__name__}: {exc}")

    assert not failures, (
        "These tools cannot be converted to an OpenAI tool schema, so they cannot "
        "be bound to a model. A bare `runtime: ToolRuntime | None = None` is the "
        "known cause — use `Annotated[ToolRuntime | None, InjectedToolArg] = None`.\n"
        + "\n".join(failures)
    )


@pytest.mark.unit
def test_no_injected_argument_reaches_the_model(
    registered_tools: dict[str, BaseTool],
) -> None:
    """Injected arguments are runtime plumbing; the model must never see them."""
    leaks: list[str] = []
    for name, tool in sorted(registered_tools.items()):
        properties = set(_openai_parameters(tool).get("properties", {}))
        leaked = properties & INJECTED_ARGUMENT_NAMES
        if leaked:
            leaks.append(f"{name}: {sorted(leaked)}")

    assert not leaks, (
        "These tools expose injected arguments to the model. Annotate them with "
        "`InjectedToolArg`, or type the parameter `ToolRuntime` so the tool layer "
        "recognises and strips it.\n" + "\n".join(leaks)
    )


@pytest.mark.unit
def test_the_guard_inspects_a_meaningful_number_of_tools(
    registered_tools: dict[str, BaseTool],
) -> None:
    """A guard that silently inspects nothing is worse than no guard."""
    assert len(registered_tools) >= MIN_EXPECTED_TOOLS, (
        f"only {len(registered_tools)} tools registered — the registry did not load "
        "properly, so the two contract tests above proved nothing"
    )
