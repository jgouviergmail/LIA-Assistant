"""Every registered capability is DECLARED somewhere (ADR-263).

Measured 2026-09-04: ``assert_mutation_policy_completeness`` walks the
MANIFESTS, so the 23 registered tools that have no manifest at all are
invisible to it. None of them is a runtime hole today — both execution modes
select their toolset from manifests (``manifests_for_mode``), and the sub-agent
filter refuses anything not declared ``read`` — but the guard cannot say so,
and a mutating tool registered tomorrow without a manifest would be just as
invisible.

This guard's domain is therefore the REGISTRY, not the catalogue: a registered
tool has a manifest, or it is listed below with the reason it does not. The
list is shrink-only — it may lose entries, never gain them.

No boot assert on purpose: a manifest-less tool is unreachable rather than
dangerous, and refusing to start a production instance over a declaration gap
would trade a real outage for a paperwork one.
"""

from __future__ import annotations

import functools
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

pytestmark = [pytest.mark.unit]

#: Registered tools with no manifest, and why. SHRINK-ONLY: removing an entry
#: (by declaring the tool) is progress; adding one needs a reason as good as
#: these, and a reviewer who agrees.
UNDECLARED_TOOLS: dict[str, str] = {
    # Sub-tools of the browser loop: the loop drives them itself, and only
    # ``browser_task_tool`` (declared ``reversible``) is ever planned.
    "browser_click_tool": "browser loop sub-tool, never planned",
    "browser_fill_tool": "browser loop sub-tool, never planned",
    "browser_navigate_tool": "browser loop sub-tool, never planned",
    "browser_press_key_tool": "browser loop sub-tool, never planned",
    "browser_snapshot_tool": "browser loop sub-tool, never planned",
    # Legacy readers superseded by their `search_`/`get_` equivalents in the
    # catalogue. No manifest means no selector can reach them.
    "get_calls_tool": "legacy reader, superseded in the catalogue",
    "get_contact_details_tool": "legacy reader, superseded in the catalogue",
    "get_email_details_tool": "legacy reader, superseded in the catalogue",
    "get_event_details_tool": "legacy reader, superseded in the catalogue",
    "get_file_details_tool": "legacy reader, superseded in the catalogue",
    "get_peer_messages_tool": "legacy reader, superseded in the catalogue",
    "get_place_details_tool": "legacy reader, superseded in the catalogue",
    "get_task_details_tool": "legacy reader, superseded in the catalogue",
    "list_contacts_tool": "legacy reader, superseded in the catalogue",
    "list_files_tool": "legacy reader, superseded in the catalogue",
    "list_places_tool": "legacy reader, superseded in the catalogue",
    "list_tasks_tool": "legacy reader, superseded in the catalogue",
    "search_contacts_tool": "legacy reader, superseded in the catalogue",
    "search_emails_tool": "legacy reader, superseded in the catalogue",
    "search_events_tool": "legacy reader, superseded in the catalogue",
    "search_files_tool": "legacy reader, superseded in the catalogue",
    "search_places_tool": "legacy reader, superseded in the catalogue",
    # Builds a DRAFT rather than deleting: the effect is claimed and recorded
    # by the `file_delete` executor, which the gate wraps.
    "delete_file_tool": "draft builder; the effect is recorded by its executor",
}


#: Measured in a FRESH interpreter: the tool registry is a module-level
#: singleton, and other tests register probe tools into it (the effect-gate
#: suites alone add half a dozen). Reading it in-process would make this guard
#: depend on test ordering — green alone, red in the suite, which is exactly
#: how a guard gets weakened instead of obeyed.
_MEASURE = """
import json
from src.domains.agents.registry import set_global_registry
from src.domains.agents.registry.agent_registry import AgentRegistry
from src.domains.agents.registry.catalogue import ToolManifestNotFound
from src.domains.agents.registry.catalogue_loader import initialize_catalogue
from src.domains.agents.tools import tool_registry

tool_registry.ensure_tools_loaded()
registry = AgentRegistry()
initialize_catalogue(registry)
set_global_registry(registry)

undeclared = []
for name in tool_registry.get_all_tools():
    try:
        registry.get_tool_manifest(name)
    except (ToolManifestNotFound, RuntimeError, AttributeError):
        undeclared.append(name)
print("@@" + json.dumps({"undeclared": sorted(undeclared),
                         "registered": len(tool_registry.get_all_tools())}))
"""


@functools.lru_cache(maxsize=1)
def _measured() -> dict[str, Any]:
    """Run the measurement once, in a subprocess, and cache it."""
    api_root = Path(__file__).resolve().parents[4]
    completed = subprocess.run(  # noqa: S603 - our own interpreter, fixed script
        [sys.executable, "-c", _MEASURE],
        cwd=api_root,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert completed.returncode == 0, (
        "the measurement failed: " + completed.stdout[-2000:] + completed.stderr[-2000:]
    )
    marker = [line for line in completed.stdout.splitlines() if line.startswith("@@")]
    assert marker, "no measurement in output: " + completed.stdout[-2000:]
    measured: dict[str, Any] = json.loads(marker[-1][2:])
    return measured


def _registered_tools_without_manifest() -> set[str]:
    """Registered tool names the catalogue cannot describe, on a fresh boot."""
    return set(_measured()["undeclared"])


class TestEveryRegisteredToolIsDeclared:
    def test_no_undeclared_tool_outside_the_list(self) -> None:
        offenders = sorted(_registered_tools_without_manifest() - set(UNDECLARED_TOOLS))
        assert not offenders, (
            f"{len(offenders)} registered tool(s) have no manifest and no entry in "
            f"UNDECLARED_TOOLS: {offenders}. Declare them in a catalogue manifest "
            "(which gives them a mutation_policy the gate can read), or add them "
            "here with the reason they cannot be reached."
        )

    def test_the_list_only_shrinks(self) -> None:
        """An entry for a tool that now HAS a manifest must be removed."""
        stale = sorted(set(UNDECLARED_TOOLS) - _registered_tools_without_manifest())
        assert not stale, (
            f"{stale} now have a manifest — delete their UNDECLARED_TOOLS entries. "
            "The list may only shrink."
        )

    def test_every_entry_carries_a_reason(self) -> None:
        empty = sorted(name for name, reason in UNDECLARED_TOOLS.items() if not reason.strip())
        assert not empty, f"undeclared without a reason: {empty}"

    def test_the_registry_is_populated(self) -> None:
        """Anti-vacuity: an empty registry would make all of the above pass."""
        assert _measured()["registered"] > 100


class TestWhyThisIsNotYetAHole:
    """The properties that make the undeclared tools unreachable, not unsafe.

    If either of these ever stops holding, the list above becomes a list of
    ungoverned capabilities and the guard must become a boot assert.
    """

    def test_both_execution_modes_select_from_manifests(self) -> None:
        import inspect

        from src.domains.agents.services import react_tool_selector

        source = inspect.getsource(react_tool_selector)
        assert "manifests_for_mode" in source, (
            "ReAct no longer selects its toolset from manifests — an undeclared "
            "tool may now be reachable, so it can no longer be exempt."
        )

    def test_a_sub_agent_refuses_an_undeclared_tool(self) -> None:
        from types import SimpleNamespace

        from src.domains.sub_agents.skill_resolver import resolve_tools_for_subagent

        kept = resolve_tools_for_subagent(
            allowed_tools=[],
            blocked_tools=[],
            all_tools=[SimpleNamespace(name="delete_file_tool")],
            policy_of=lambda _name: None,
        )
        assert kept == [], "an undeclared tool reached a sub-agent"
