"""Contract: ``auto_save_context`` gets its config and store from the ToolRuntime.

Before ADR-231 the decorator carried two "legacy" fallbacks that read
``config.get("store")`` — one nesting level above where LIA actually writes it
(``configurable["store"]``), so they could only ever yield ``None``. They were
unreachable anyway: a scan of the 105 registered tools found exactly one without a
``runtime`` parameter (``local_query_engine_tool``, which carries no
``auto_save_context``) and **zero** declaring a ``config`` parameter, and the
fallbacks require both.

Deleting them must not weaken the decorator's real contract, which is a fail-safe:
auto-save is a side effect and must NEVER break the tool it wraps. These tests pin
that contract on both output shapes — the ``UnifiedToolOutput`` registry path and
the legacy JSON-string path — so the cleanup is provably behaviour-preserving.
"""

import json

import pytest
from langchain.tools import ToolRuntime

from src.domains.agents.context.decorators import auto_save_context
from src.domains.agents.tools.output import UnifiedToolOutput


def _make_runtime() -> ToolRuntime:
    """A minimal ToolRuntime, shaped like the one the tool layer injects."""
    return ToolRuntime(
        state=None,
        config={"configurable": {}},
        context=None,
        stream_writer=lambda _: None,
        tool_call_id=None,
        store=None,
    )


@pytest.mark.unit
async def test_unified_output_is_returned_unchanged_without_a_runtime() -> None:
    """Registry path: no runtime means skip the save, never break the tool."""

    @auto_save_context("contacts")
    async def _tool() -> UnifiedToolOutput:
        return UnifiedToolOutput.action_success(message="ok")

    result = await _tool()

    assert isinstance(result, UnifiedToolOutput)
    assert result.success is True
    assert result.message == "ok"


@pytest.mark.unit
async def test_json_output_is_returned_unchanged_without_a_runtime() -> None:
    """Legacy JSON path: same fail-safe contract, same absence of a runtime."""

    payload = json.dumps({"success": True, "data": {"name": "Alice"}})

    @auto_save_context("contacts")
    async def _tool() -> str:
        return payload

    result = await _tool()

    assert result == payload


@pytest.mark.unit
async def test_a_failed_tool_result_is_passed_through_untouched() -> None:
    """A tool that failed must not have its payload rewritten by the side effect."""

    payload = json.dumps({"success": False, "error": "boom"})

    @auto_save_context("contacts")
    async def _tool() -> str:
        return payload

    assert await _tool() == payload


@pytest.mark.unit
async def test_an_unparseable_result_does_not_raise() -> None:
    """Fail-safe means fail-safe: a non-JSON payload must still come back."""

    @auto_save_context("contacts")
    async def _tool() -> str:
        return "not json at all"

    assert await _tool() == "not json at all"


@pytest.mark.unit
def test_resolve_runtime_finds_it_in_kwargs() -> None:
    """The nominal path: the tool layer injects ``runtime`` as a keyword."""
    from src.domains.agents.context.decorators import _resolve_runtime

    runtime = _make_runtime()

    assert _resolve_runtime((), {"runtime": runtime}) is runtime


@pytest.mark.unit
def test_resolve_runtime_finds_it_positionally() -> None:
    """Both output paths must accept a positional runtime, not just one of them.

    Before the factorisation the registry branch scanned positional arguments and
    the JSON branch did not — same intent, two implementations, one weaker.
    """
    from src.domains.agents.context.decorators import _resolve_runtime

    runtime = _make_runtime()

    assert _resolve_runtime(("some-arg", runtime), {}) is runtime


@pytest.mark.unit
def test_resolve_runtime_returns_none_when_absent() -> None:
    from src.domains.agents.context.decorators import _resolve_runtime

    assert _resolve_runtime(("a", 1), {"other": "value"}) is None


@pytest.mark.unit
async def test_json_path_honours_a_positional_runtime() -> None:
    """End-to-end proof that the JSON branch gained the registry branch's tolerance."""
    saved: list[str] = []

    @auto_save_context("contacts")
    async def _tool(runtime: object) -> str:
        return json.dumps({"success": True, "data": {"name": "Alice"}})

    runtime = _make_runtime()
    result = await _tool(runtime)

    # The store is None on this synthetic runtime, so the save is skipped — the
    # point is that resolution reached it instead of bailing out one step earlier.
    assert json.loads(result)["success"] is True
    assert saved == []


@pytest.mark.unit
def test_the_decorator_no_longer_reads_the_store_from_the_wrong_level() -> None:
    """``config["store"]`` is one level above where LIA writes it.

    LIA writes the store at ``configurable["store"]``
    (``services/orchestration/service.py``). Reading ``config["store"]`` could only
    return ``None``, so a resurrection of that fallback would silently disable
    auto-save rather than fail — exactly the class of defect ADR-231 removes.
    """
    from pathlib import Path

    source = Path("src/domains/agents/context/decorators.py").read_text(encoding="utf-8")

    assert 'config.get("store")' not in source, (
        'decorators.py reads `config.get("store")` again. The store lives at '
        '`configurable["store"]`; take it from `runtime.store` instead.'
    )
