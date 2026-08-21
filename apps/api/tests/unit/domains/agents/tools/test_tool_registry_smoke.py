"""Registry smoke tests: a broken tool module must fail CI (audit wave 2, C9).

Three layers of protection:

1. **Loud imports** — every canonical tool module is imported directly; a
   syntax error / missing dependency / renamed symbol fails CI with the
   original traceback instead of silently removing the whole tool family.
2. **Family completeness** — after ``ensure_tools_loaded()``, each family's
   sentinel tool must be present in the registry.
3. **Invocation smoke** — every registered tool is invoked with synthesized
   minimal arguments, network and DB access blocked. Any outcome is accepted
   (structured error, connection failure, validation error) EXCEPT
   programming errors (TypeError/AttributeError/NameError escaping the tool,
   or classified inside its error payload): those mean the wrapper chain or
   the tool body is broken — the class of bug that shipped as N-140.

Also covers the C9 hardening of ``_import_tool_modules``: import failures
raise outside production and are logged + counted in production.
"""

import asyncio
import importlib
import json
from typing import Any
from unittest.mock import patch

import httpx
import pytest
from langchain_core.tools import BaseTool
from pydantic import BaseModel

from src.core.config import get_settings
from src.domains.agents.tools.tool_registry import (
    ensure_tools_loaded,
    get_all_tools,
)

# Canonical always-on tool modules (mirrors _import_tool_modules) with a
# sentinel tool per family. Feature-flagged modules (skills, sub-agents,
# image generation, devops, health) are appended dynamically below.
ALWAYS_ON_MODULES: dict[str, str] = {
    "src.domains.agents.tools.calendar_tools": "create_event_tool",
    "src.domains.agents.tools.drive_tools": "search_files_tool",
    "src.domains.agents.tools.emails_tools": "send_email_tool",
    "src.domains.agents.tools.google_contacts_tools": "get_contacts_tool",
    "src.domains.agents.tools.labels_tools": "list_labels_tool",
    "src.domains.agents.tools.tasks_tools": "create_task_tool",
    "src.domains.agents.tools.places_tools": "search_places_tool",
    "src.domains.agents.tools.routes_tools": "get_route_tool",
    "src.domains.agents.tools.brave_tools": "brave_search_tool",
    "src.domains.agents.tools.perplexity_tools": "perplexity_search_tool",
    "src.domains.agents.tools.weather_tools": "get_current_weather_tool",
    "src.domains.agents.tools.web_search_tools": "unified_web_search_tool",
    "src.domains.agents.tools.web_fetch_tools": "fetch_web_page_tool",
    "src.domains.agents.tools.wikipedia_tools": "search_wikipedia_tool",
    "src.domains.agents.tools.hue_tools": "list_hue_lights_tool",
    "src.domains.agents.tools.browser_tools": "browser_task_tool",
    "src.domains.agents.tools.context_tools": "resolve_reference",
    "src.domains.agents.tools.reminder_tools": "create_reminder_tool",
    "src.domains.agents.tools.local_query_tool": "local_query_engine_tool",
}

FLAGGED_MODULES: dict[str, tuple[str, str]] = {
    # settings flag -> (module path, sentinel tool)
    "skills_enabled": ("src.domains.skills.tools", "activate_skill_tool"),
    "sub_agents_enabled": (
        "src.domains.agents.tools.sub_agent_tools",
        "delegate_to_sub_agent_tool",
    ),
    "image_generation_enabled": (
        "src.domains.agents.tools.image_generation_tools",
        "generate_image",
    ),
    "document_generation_enabled": (
        "src.domains.agents.tools.document_generation_tools",
        "generate_document",
    ),
    "health_metrics_enabled": (
        "src.domains.agents.tools.health_tools",
        "get_health_overview_tool",
    ),
    "devops_enabled": (
        "src.domains.agents.tools.devops_tools",
        "claude_server_task_tool",
    ),
}

# Programming-error types that must never escape a tool invocation or be
# the classified cause inside its structured error payload.
PROGRAMMING_ERRORS = ("TypeError", "AttributeError", "NameError", "UnboundLocalError")


def _enabled_flagged_modules() -> dict[str, str]:
    settings = get_settings()
    return {
        module: sentinel
        for flag, (module, sentinel) in FLAGGED_MODULES.items()
        if getattr(settings, flag, False)
    }


def _all_expected_modules() -> dict[str, str]:
    return {**ALWAYS_ON_MODULES, **_enabled_flagged_modules()}


def _synthesize_args(schema: type[BaseModel] | None) -> dict[str, Any]:
    """Build minimal dummy arguments for a tool's args schema."""
    if schema is None or not (isinstance(schema, type) and issubclass(schema, BaseModel)):
        return {}
    args: dict[str, Any] = {}
    for name, field in schema.model_fields.items():
        if not field.is_required():
            continue
        annotation = field.annotation
        origin = getattr(annotation, "__origin__", None)
        if annotation is str:
            args[name] = "test"
        elif annotation is int:
            args[name] = 1
        elif annotation is float:
            args[name] = 1.0
        elif annotation is bool:
            args[name] = False
        elif origin is list or annotation is list:
            args[name] = []
        elif origin is dict or annotation is dict:
            args[name] = {}
        else:
            # Optional/unions and exotic types: try a string, pydantic will
            # coerce or reject with a ValidationError (acceptable outcome)
            args[name] = "test"
    return args


class TestToolModulesImportLoudly:
    """Layer 1: every canonical module must import without error."""

    @pytest.mark.parametrize("module_path", sorted(ALWAYS_ON_MODULES))
    def test_always_on_module_imports(self, module_path: str):
        """A broken tool module fails CI with its original traceback."""
        importlib.import_module(module_path)

    def test_enabled_flagged_modules_import(self):
        """Feature-flagged modules must import when their flag is on."""
        for module_path in _enabled_flagged_modules():
            importlib.import_module(module_path)


class TestToolFamiliesRegistered:
    """Layer 2: each family's sentinel tool is present in the registry."""

    def test_every_family_has_its_sentinel_tool(self):
        ensure_tools_loaded()
        registered = set(get_all_tools())
        missing = {
            f"{module} -> {sentinel}"
            for module, sentinel in _all_expected_modules().items()
            if sentinel not in registered
        }
        assert not missing, (
            "Tool families missing from the registry (module import silently "
            f"failed or sentinel renamed): {sorted(missing)}"
        )

    def test_registry_has_no_empty_metadata(self):
        ensure_tools_loaded()
        for name, tool in get_all_tools().items():
            assert isinstance(tool, BaseTool), f"{name} is not a BaseTool"
            assert tool.name, f"{name} has empty .name"
            assert tool.description, f"{name} has empty .description"


class TestToolInvocationSmoke:
    """Layer 3: invoke every registered tool with minimal mocks.

    Network and event-loop sleeps are blocked so external tools fail fast on
    their error path. The contract: NO programming error may escape the tool
    or be the classified cause of its structured error payload.
    """

    @pytest.mark.asyncio
    async def test_every_registered_tool_survives_minimal_invocation(self):
        ensure_tools_loaded()
        tools = get_all_tools()
        assert tools, "Registry is empty"

        config = {"configurable": {"user_id": "00000000-0000-0000-0000-000000000000"}}
        failures: list[str] = []

        async def _blocked_request(*args: Any, **kwargs: Any) -> None:
            raise httpx.ConnectError("network blocked by smoke test")

        real_sleep = asyncio.sleep

        async def _fast_sleep(_delay: float, *args: Any, **kwargs: Any) -> None:
            await real_sleep(0)

        with (
            patch.object(httpx.AsyncClient, "send", _blocked_request),
            patch.object(httpx.Client, "send", side_effect=httpx.ConnectError("blocked")),
            patch("asyncio.sleep", _fast_sleep),
        ):
            for name, tool in sorted(tools.items()):
                args = _synthesize_args(tool.args_schema)
                try:
                    result = await asyncio.wait_for(tool.ainvoke(args, config=config), timeout=15)
                except TimeoutError:
                    # Reached execution and hung on a blocked dependency —
                    # wiring is intact, outcome acceptable for a smoke test
                    continue
                except Exception as e:  # noqa: BLE001 - smoke classifies outcomes
                    if type(e).__name__ in PROGRAMMING_ERRORS:
                        failures.append(f"{name}: {type(e).__name__}: {e}")
                    continue

                # Structured result: reject programming errors classified
                # inside the payload (broken tool body caught by handle_error)
                payload: dict[str, Any] | None = None
                if isinstance(result, dict):
                    payload = result
                elif isinstance(result, str):
                    try:
                        parsed = json.loads(result)
                        payload = parsed if isinstance(parsed, dict) else None
                    except json.JSONDecodeError, ValueError:
                        payload = None
                if payload:
                    error_type = str(
                        payload.get("error_type")
                        or (payload.get("error") or {}).get("error_type", "")
                        if isinstance(payload.get("error"), dict)
                        else payload.get("error_type", "")
                    )
                    if error_type in PROGRAMMING_ERRORS:
                        failures.append(f"{name}: payload error_type={error_type}")

        assert not failures, (
            "Programming errors detected while smoke-invoking registered tools "
            "(broken wrapper chain or tool body):\n" + "\n".join(f"  - {f}" for f in failures)
        )


class TestImportFailuresAreLoud:
    """C9 hardening of _import_tool_modules: never silent."""

    def test_import_failure_raises_outside_production(self, monkeypatch):
        """In dev/test a broken tool module must abort loading (RuntimeError)."""
        from src.domains.agents.tools import tool_registry

        monkeypatch.setattr(
            importlib,
            "import_module",
            lambda path: (_ for _ in ()).throw(ImportError("broken module")),
        )

        with pytest.raises(RuntimeError, match="failed to import"):
            tool_registry._import_tool_modules()

    def test_import_failure_counted_and_swallowed_in_production(self, monkeypatch):
        """In production the failure increments the Prometheus counter and
        loading continues (resilience over crash)."""
        from src.domains.agents.tools import tool_registry
        from src.infrastructure.observability.metrics_agents import (
            tool_module_import_failures,
        )

        class _ProdSettings:
            is_production = True

        monkeypatch.setattr("src.core.config.get_settings", lambda: _ProdSettings())
        monkeypatch.setattr(
            importlib,
            "import_module",
            lambda path: (_ for _ in ()).throw(ImportError("broken module")),
        )

        before = tool_module_import_failures.labels(module="calendar_tools")._value.get()

        # Must NOT raise in production
        tool_registry._import_tool_modules()

        after = tool_module_import_failures.labels(module="calendar_tools")._value.get()
        assert after == before + 1, "tool_module_import_failures_total not incremented"
