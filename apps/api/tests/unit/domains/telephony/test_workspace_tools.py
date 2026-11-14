"""LIA's tools in the person's ElevenLabs workspace — verified and repaired before every use.

The one door both voice surfaces go through (the phone's webhook tools, the
live session's client tools): a tool holds LIA's body when everything LIA sent
is served as sent — the vendor adds its own defaults, measured 2026-11-11 —; a
drifted tool is rewritten in place under its id, a lost one re-created in its
position, and a refusal leaves nothing behind. The HTTP side runs on
``httpx.MockTransport`` through the real agents client.
"""

from __future__ import annotations

import asyncio
import copy
import json
from typing import Any

import httpx
import pytest

from src.domains.telephony.client import ElevenLabsAgentsClient, ElevenLabsAgentsError
from src.domains.telephony.workspace_tools import (
    create_tools,
    holds,
    read_workspace_tools,
    repair_set,
)

pytestmark = pytest.mark.unit

#: A client tool as LIA creates it (``client_tool_body``).
SENT: dict[str, Any] = {
    "type": "client",
    "name": "get_events_tool",
    "description": "Reads the agenda.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "What to look for."},
            "order": {"type": "string", "description": "The order.", "enum": ["asc", "desc"]},
        },
        "required": ["query"],
    },
    "expects_response": True,
    "response_timeout_secs": 20,
}

#: The same tool as the workspace served it back on 2026-11-11 (throwaway tool,
#: dev workspace): everything sent, unchanged, plus the vendor's own defaults.
SERVED: dict[str, Any] = {
    **copy.deepcopy(SENT),
    "assignments": [],
    "disable_interruptions": False,
    "dynamic_variables": {"dynamic_variable_placeholders": {}},
    "execution_mode": "immediate",
    "force_pre_tool_speech": False,
    "interruption_mode": "allow",
    "pre_tool_speech": "auto",
    "tool_call_sound": None,
    "tool_call_sound_behavior": "auto",
    "tool_error_handling_mode": "auto",
}
SERVED["parameters"].update({"description": "", "dynamic_variable": "", "is_omitted": False})
for _prop in SERVED["parameters"]["properties"].values():
    _prop.update(
        {
            "allowed_values": None,
            "allowed_values_dynamic_variable": "",
            "constant_value": "",
            "dynamic_variable": "",
            "is_omitted": False,
            "is_system_provided": False,
        }
    )
    _prop.setdefault("enum", None)


def _edited(path: tuple[str, ...], value: object) -> dict[str, Any]:
    """SERVED with one field at ``path`` replaced, as a hand on the portal would."""
    served = copy.deepcopy(SERVED)
    target = served
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    return served


# -- holds: what the workspace serves against what LIA sent ------------------------------


def test_a_tool_served_with_the_vendors_defaults_holds_what_lia_sent() -> None:
    assert holds(SERVED, SENT) is True


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("description",), "Reads the agenda, edited on the portal."),
        (("name",), "get_events_tool_renamed"),
        (("response_timeout_secs",), 120),
        (("expects_response",), False),
        (("parameters", "required"), []),
        (("parameters", "properties", "order", "enum"), ["desc", "asc"]),
        (("parameters", "properties", "query", "type"), "integer"),
    ],
    ids=[
        "description",
        "name",
        "timeout",
        "expects_response",
        "required",
        "enum order",
        "parameter type",
    ],
)
def test_a_field_lia_sent_and_the_workspace_changed_is_drift(
    path: tuple[str, ...], value: object
) -> None:
    assert holds(_edited(path, value), SENT) is False


def test_a_parameter_the_workspace_lost_is_drift() -> None:
    served = copy.deepcopy(SERVED)
    del served["parameters"]["properties"]["order"]
    assert holds(served, SENT) is False


def test_a_boolean_is_never_read_as_a_number() -> None:
    assert holds({"flag": 1}, {"flag": True}) is False
    assert holds({"count": True}, {"count": 1}) is False
    # The same number, an integer or a float, is the same value.
    assert holds({"response_timeout_secs": 20.0}, {"response_timeout_secs": 20}) is True


# -- a fake workspace -------------------------------------------------------------------


class _Workspace:
    """The tools API as a MockTransport handler: create, rewrite (replace), list, delete."""

    def __init__(self) -> None:
        self.tools: dict[str, dict[str, Any]] = {}
        self.calls: list[tuple[str, str, Any]] = []
        self.created = 0
        self.refuse: set[tuple[str, str]] = set()

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        self.calls.append((request.method, request.url.path, body))
        if (request.method, request.url.path) in self.refuse:
            return httpx.Response(422, json={"detail": {"type": "validation_error"}})
        if request.method == "POST" and request.url.path == "/v1/convai/tools":
            self.created += 1
            tool_id = f"tool_new_{self.created}"
            self.tools[tool_id] = copy.deepcopy((body or {})["tool_config"])
            return httpx.Response(200, json={"id": tool_id})
        if request.method == "GET" and request.url.path == "/v1/convai/tools":
            kinds = request.url.params.get_list("types")
            listed = [
                {"id": tool_id, "tool_config": config}
                for tool_id, config in self.tools.items()
                if config.get("type") in kinds
            ]
            return httpx.Response(200, json={"tools": listed, "has_more": False})
        tool_id = request.url.path.rsplit("/", 1)[-1]
        if request.method == "PATCH":
            if tool_id not in self.tools:
                return httpx.Response(404, json={"detail": {"type": "not_found"}})
            self.tools[tool_id] = copy.deepcopy((body or {})["tool_config"])
            return httpx.Response(200, json={"id": tool_id})
        if request.method == "DELETE":
            self.tools.pop(tool_id, None)
            return httpx.Response(204)
        return httpx.Response(404, json={"detail": "unknown"})

    def writes(self) -> list[tuple[str, str, Any]]:
        return [call for call in self.calls if call[0] in {"POST", "PATCH", "DELETE"}]


def _client(workspace: _Workspace) -> ElevenLabsAgentsClient:
    return ElevenLabsAgentsClient("k", transport=httpx.MockTransport(workspace))


def _repaired(surface: str, reason: str) -> float:
    from prometheus_client import REGISTRY

    labels = {"surface": surface, "reason": reason}
    return REGISTRY.get_sample_value("live_agent_tools_repaired_total", labels) or 0.0


def _body(name: str, description: str = "Reads.") -> dict[str, Any]:
    return {"tool_config": {**copy.deepcopy(SENT), "name": name, "description": description}}


# -- read_workspace_tools ----------------------------------------------------------------


async def test_the_workspace_is_read_by_id_for_the_kind_asked() -> None:
    workspace = _Workspace()
    workspace.tools = {
        "c1": {"type": "client", "name": "a"},
        "w1": {"type": "webhook", "name": "b"},
    }
    assert await read_workspace_tools(_client(workspace), "client") == {
        "c1": {"type": "client", "name": "a"}
    }
    assert await read_workspace_tools(_client(workspace), "webhook") == {
        "w1": {"type": "webhook", "name": "b"}
    }


# -- repair_set --------------------------------------------------------------------------


async def test_a_set_the_workspace_holds_as_sent_is_left_alone() -> None:
    workspace = _Workspace()
    bodies = [_body("a"), _body("b")]
    workspace.tools = {"t_a": copy.deepcopy(SERVED) | {"name": "a", "description": "Reads."}}
    workspace.tools["t_b"] = copy.deepcopy(SERVED) | {"name": "b", "description": "Reads."}
    served = await read_workspace_tools(_client(workspace), "client")
    before = (_repaired("live", "drifted"), _repaired("live", "lost"))

    repair = await repair_set(_client(workspace), ["t_a", "t_b"], bodies, served, surface="live")

    assert repair.ids == ("t_a", "t_b")
    assert repair.recreated == () and repair.rewritten == ()
    assert workspace.writes() == []
    assert (_repaired("live", "drifted"), _repaired("live", "lost")) == before


async def test_a_tool_edited_on_the_portal_is_rewritten_in_place_under_its_id() -> None:
    workspace = _Workspace()
    bodies = [_body("a"), _body("b")]
    workspace.tools = {
        "t_a": copy.deepcopy(SERVED) | {"name": "a", "description": "Reads."},
        "t_b": copy.deepcopy(SERVED) | {"name": "b", "description": "Edited by hand."},
    }
    served = await read_workspace_tools(_client(workspace), "client")
    drifted = _repaired("phone", "drifted")

    repair = await repair_set(_client(workspace), ["t_a", "t_b"], bodies, served, surface="phone")

    assert repair.ids == ("t_a", "t_b")
    assert repair.rewritten == ("t_b",) and repair.recreated == ()
    assert workspace.writes() == [("PATCH", "/v1/convai/tools/t_b", bodies[1])]
    assert workspace.tools["t_b"]["description"] == "Reads."
    assert _repaired("phone", "drifted") - drifted == 1.0


async def test_a_tool_the_workspace_lost_is_re_created_in_its_position() -> None:
    workspace = _Workspace()
    bodies = [_body("a"), _body("b"), _body("c")]
    workspace.tools = {
        "t_a": copy.deepcopy(SERVED) | {"name": "a", "description": "Reads."},
        "t_c": copy.deepcopy(SERVED) | {"name": "c", "description": "Reads."},
    }
    served = await read_workspace_tools(_client(workspace), "client")
    lost = _repaired("live", "lost")

    repair = await repair_set(
        _client(workspace), ["t_a", "t_b", "t_c"], bodies, served, surface="live"
    )

    assert repair.ids == ("t_a", "tool_new_1", "t_c")
    assert repair.recreated == ("tool_new_1",) and repair.rewritten == ()
    assert workspace.writes() == [("POST", "/v1/convai/tools", bodies[1])]
    assert _repaired("live", "lost") - lost == 1.0


async def test_a_refused_rewrite_removes_what_the_repair_created_and_is_raised() -> None:
    """The caller stores the repaired ids only once the repair returned: a tool
    created for a lost one would otherwise be named by nothing."""
    workspace = _Workspace()
    bodies = [_body("a"), _body("b")]
    workspace.tools = {"t_b": copy.deepcopy(SERVED) | {"name": "b", "description": "Edited."}}
    workspace.refuse.add(("PATCH", "/v1/convai/tools/t_b"))
    served = await read_workspace_tools(_client(workspace), "client")

    with pytest.raises(ElevenLabsAgentsError):
        await repair_set(_client(workspace), ["t_a", "t_b"], bodies, served, surface="live")

    assert "tool_new_1" not in workspace.tools
    assert ("DELETE", "/v1/convai/tools/tool_new_1", None) in workspace.calls


async def test_a_lost_connection_while_creating_is_raised_as_itself_and_rolled_back() -> None:
    """A transport failure is not a refusal, but it leaves the same debris: what was
    created is removed, and the caller sees the failure itself, never a group."""
    workspace = _Workspace()
    attempts = 0

    def _handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        if request.method == "POST":
            attempts += 1
            if attempts == 2:
                raise httpx.ConnectError("down", request=request)
        return workspace(request)

    client = ElevenLabsAgentsClient("k", transport=httpx.MockTransport(_handler))
    with pytest.raises(httpx.ConnectError):
        await create_tools(client, [_body("a"), _body("b")])
    assert workspace.tools == {}


async def test_a_refusal_cancels_the_creations_still_running_before_the_rollback() -> None:
    """Measured 2026-09-19 on dev: `gather` raised on the third refusal while fifty
    creations went on; the rollback iterated a dict they kept filling and every
    tool created after it was an orphan. With a TaskGroup the siblings are
    cancelled first: nothing is created after the rollback ran.

    Sequenced by events, never by the clock: the refusal lands once "a" was
    created and "b" to "d" are mid-flight, and their creations can only finish
    if nobody cancels them.
    """
    from src.core.constants import TELEPHONY_LIVE_TOOL_PROVISIONING_CONCURRENCY

    siblings = ("b", "c", "d")
    bodies = [{"tool_config": {"name": n}} for n in ("a", "refused", *siblings)]
    # Every creation must be in flight at once for "mid-flight" to mean anything.
    assert len(bodies) <= TELEPHONY_LIVE_TOOL_PROVISIONING_CONCURRENCY
    events: list[str] = []
    a_created = asyncio.Event()
    in_flight: set[str] = set()
    siblings_in_flight = asyncio.Event()
    released = asyncio.Event()  # set only after the call returned: a late creation shows

    class _SequencedClient(ElevenLabsAgentsClient):
        async def create_tool(self, body: dict[str, Any]) -> str:
            name = body["tool_config"]["name"]
            if name == "a":
                events.append("created:a")
                a_created.set()
                return "id_a"
            if name == "refused":
                await a_created.wait()
                await siblings_in_flight.wait()
                raise ElevenLabsAgentsError(422, "no")
            in_flight.add(name)
            if in_flight == set(siblings):
                siblings_in_flight.set()
            try:
                await released.wait()
            except asyncio.CancelledError:
                events.append(f"cancelled:{name}")
                raise
            events.append(f"created:{name}")
            return f"id_{name}"

        async def delete_tool(self, tool_id: str) -> None:
            events.append(f"deleted:{tool_id}")

    async with asyncio.timeout(10):  # a hang guard, never an oracle
        with pytest.raises(ElevenLabsAgentsError):
            await create_tools(_SequencedClient("test-key"), bodies)
        released.set()
        for _ in range(10):  # let any sibling still running land, if one survived
            await asyncio.sleep(0)

    # "a" was created before the refusal and rolled back; the siblings were
    # cancelled before the rollback, and none was created after it.
    assert events[0] == "created:a"
    assert sorted(events[1:-1]) == [f"cancelled:{name}" for name in siblings]
    assert events[-1] == "deleted:id_a"
