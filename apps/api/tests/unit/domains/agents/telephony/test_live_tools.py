"""Live read-only tools on an owner call — the agents half (lot 7, lot 8).

Lot 8 (owner decision 2026-09-16): the allowlist is no longer a hand-typed
tuple of three tools but a RULE over the catalogue — every tool that only
reads, in a domain the phone offers, with the parameters a voice can speak —
plus the native lookups the catalogue has no tool for (the person's
memories). The vendor bodies, the completeness guard, the endpoint and the
person's own domain switches all read the same derived list. Provisioning is
idempotent by fingerprint and never blocks a call; execution runs the
registered tool on a synthetic runtime under a bound, and projects the result
the way the ReAct loop does.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Annotated, Any
from uuid import uuid4

import pytest
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg, tool

import src.domains.agents.telephony.live_tools as mod
from src.core.config import settings
from src.domains.agents.registry.catalogue import ParameterConstraint, ParameterSchema
from src.domains.agents.telephony.live_tools import (
    NATIVE_LOOKUPS,
    LiveToolSpec,
    assert_live_tools_completeness,
    available_live_tools,
    derive_live_tool_specs,
    ensure_vendor_live_tools,
    exposed_parameter_names,
    live_tool_description,
    live_tool_parameters,
    run_live_tool,
    spec_for,
    tool_descriptions,
    vendor_bodies,
)
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.shared.phone_domains import PHONE_DOMAINS
from src.domains.telephony.live_tools import LiveToolBinding, live_tool_token

#: The real availability function, before any fixture replaces it.
_REAL_AVAILABLE = mod.available_live_tools

# ---------------------------------------------------------------------------
# The rule that derives the allowlist
# ---------------------------------------------------------------------------


@dataclass
class _Manifest:
    name: str
    mutation_policy: str | None = None
    tool_category: str | None = None
    parameters: list[ParameterSchema] = field(default_factory=list)
    description: str = "Reads something of the person's."
    execution_modes: frozenset[str] = frozenset({"pipeline", "react"})


def _param(name: str, kind: str = "string", **kw: Any) -> ParameterSchema:
    return ParameterSchema(
        name=name,
        type=kind,
        required=kw.get("required", False),
        description=kw.get("d", name),
        semantic_type=kw.get("semantic_type"),
    )


_DOMAINS = {
    "get_emails_tool": "email",
    "send_email_tool": "email",
    "get_events_tool": "event",
    "resolve_reference": "context",
    "platform_logs_tool": "devops",
    "read_document_tool": "file",
    "local_query_engine_tool": "query",
    "get_route_tool": "route",
    "get_route_matrix_tool": "route",
    "get_tasks_tool": "task",
    "list_hue_lights_tool": "hue",
}


def _domain_of(manifest: Any) -> str:
    return _DOMAINS[manifest.name]


def _catalogue() -> list[_Manifest]:
    return [
        _Manifest(
            "get_emails_tool",
            parameters=[
                _param("query"),
                _param("message_id"),
                _param("message_ids", "array"),
                _param("max_results", "integer"),
                _param("detail"),
                _param("page_token"),
                _param("use_cache", "boolean"),
            ],
        ),
        _Manifest("send_email_tool", tool_category="send", mutation_policy="draft"),
        _Manifest(
            "get_events_tool",
            parameters=[_param("query"), _param("event_ids", "array", semantic_type="event_id")],
        ),
        # A context tool is a `system` category with an explicit read policy:
        # it answers only inside a turn, and a call has none.
        _Manifest("resolve_reference", tool_category="system", mutation_policy="read"),
        _Manifest("platform_logs_tool", mutation_policy="read"),
        # Its only required parameter is an id nobody can say on the phone.
        _Manifest(
            "read_document_tool",
            mutation_policy="read",
            parameters=[_param("file_id", required=True)],
        ),
        _Manifest(
            "local_query_engine_tool",
            tool_category="system",
            mutation_policy="read",
            execution_modes=frozenset({"pipeline"}),
        ),
        _Manifest(
            "get_route_tool",
            parameters=[
                _param("destination", required=True),
                _param("waypoints", "array"),
                _param("avoid_tolls", "boolean"),
            ],
        ),
        _Manifest("get_tasks_tool", parameters=[_param("show_completed", "boolean")]),
        # No voice line in the lines file: described by its own words.
        _Manifest(
            "get_route_matrix_tool",
            description="Durations between several origins and destinations.\n\nMore.",
            parameters=[_param("origins", "array", required=True)],
        ),
    ]


@pytest.mark.unit
def test_the_rule_keeps_every_read_only_tool_of_a_phone_domain_and_nothing_else() -> None:
    """Search tools and explicit ``read`` policies qualify; a tool that acts,
    a `system` tool (it needs a turn), a domain the phone does not offer, a
    pipeline-only tool and a tool whose required parameter is an identifier
    are left out. The native lookups close the list."""
    specs = derive_live_tool_specs(_catalogue(), domain_of=_domain_of)
    names = [s.name for s in specs]
    assert names == [
        "get_emails_tool",
        "get_events_tool",
        "get_route_matrix_tool",
        "get_route_tool",
        "get_tasks_tool",
        *[s.name for s in NATIVE_LOOKUPS],
    ]
    by_name = {s.name: s for s in specs}
    assert by_name["get_emails_tool"].domain == "email"
    # A lookup files under the section named after its domain.
    assert by_name["get_emails_tool"].section == "email"
    assert by_name["get_emails_tool"].parameters == ("query", "max_results", "detail")
    assert by_name["get_route_tool"].parameters == ("destination", "waypoints", "avoid_tolls")
    assert by_name["get_events_tool"].parameters == ("query",)


@pytest.mark.unit
def test_exposed_parameters_hide_identifiers_and_mechanics_but_keep_spoken_arrays() -> None:
    manifest = _Manifest(
        "x",
        parameters=[
            _param("query"),
            _param("calendar_id"),
            _param("resource_names", "array"),
            _param("event_ids", "array", semantic_type="event_id"),
            _param("waypoints", "array"),
            _param("page_token"),
            _param("force_refresh", "boolean"),
            _param("payload", "object"),
            _param("min_rating", "number"),
        ],
    )
    assert exposed_parameter_names(manifest) == ("query", "waypoints", "min_rating")


@pytest.mark.unit
def test_native_lookups_recall_the_person_s_memories() -> None:
    """The catalogue has no memory tool (the chat injects memories itself), so
    the phone gets a native lookup reading through the same builder."""
    (recall,) = NATIVE_LOOKUPS
    assert recall.name == "recall_memories" and recall.native is True
    assert recall.domain == "context" and recall.section == "memories"
    params = live_tool_parameters(recall, None)
    assert [(p.name, p.type, p.required) for p in params] == [("query", "string", True)]
    assert recall.name in tool_descriptions()


@pytest.mark.unit
def test_the_real_catalogue_yields_the_person_s_services() -> None:
    """Measured against the real manifests: the services the owner named
    (mails, calendar, tasks, reminders, weather, contacts, files, places,
    memories) are there, what acts or administers is not, and every entry
    passes the completeness guard."""
    from src.domains.agents.registry.agent_registry import AgentRegistry
    from src.domains.agents.registry.catalogue_loader import initialize_catalogue

    registry = AgentRegistry()
    initialize_catalogue(registry)
    manifests = registry.list_tool_manifests()
    specs = derive_live_tool_specs(manifests, domain_of=lambda m: mod.domain_of(m, registry))
    names = {s.name for s in specs}
    assert {
        "get_emails_tool",
        "get_events_tool",
        "find_availability_tool",
        "get_tasks_tool",
        "list_reminders_tool",
        "get_current_weather_tool",
        "get_weather_forecast_tool",
        "get_contacts_tool",
        "get_person_overview_tool",
        "get_files_tool",
        "search_user_documents_tool",
        "get_places_tool",
        "get_route_tool",
        "get_open_loops_tool",
        "list_tickets_tool",
        "recall_memories",
    } <= names
    for absent in (
        "send_email_tool",
        "create_event_tool",
        "create_reminder_tool",
        "platform_logs_tool",
        "resolve_reference",
        "get_context_list",
        "delegate_to_sub_agent_tool",
        "read_skill_resource",
        "run_python_tool",
        "local_query_engine_tool",
        "read_document_tool",
        "call_me_tool",
    ):
        assert absent not in names, absent
    served = {s.domain for s in specs}
    assert served <= set(PHONE_DOMAINS)
    # Every domain the person can switch is served by a tool — except the
    # telephony calls list, whose tool registers only under the telephony
    # flag (off in the unit environment).
    assert set(PHONE_DOMAINS) - served <= {"telephony"}
    assert_live_tools_completeness(manifests, registry=registry)
    assert len(specs) >= 40


@pytest.mark.unit
def test_completeness_refuses_a_native_lookup_without_a_description_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        mod, "NATIVE_LOOKUPS", (LiveToolSpec("recall_dreams", "context", "memories", (), True),)
    )
    with pytest.raises(RuntimeError, match="recall_dreams"):
        assert_live_tools_completeness(_catalogue())


@pytest.mark.unit
def test_completeness_refuses_a_section_the_surface_does_not_declare(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        mod, "NATIVE_LOOKUPS", (LiveToolSpec("recall_memories", "context", "nowhere", (), True),)
    )
    with pytest.raises(RuntimeError, match="nowhere"):
        assert_live_tools_completeness(_catalogue())


@pytest.mark.unit
def test_completeness_refuses_a_derived_tool_nobody_can_describe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mod, "domain_of", lambda m, _r=None: _DOMAINS[m.name])
    blank = [_Manifest("list_hue_lights_tool", description="   ")]
    with pytest.raises(RuntimeError, match="list_hue_lights_tool"):
        assert_live_tools_completeness(blank)


@pytest.mark.unit
def test_description_prefers_the_voice_line_and_falls_back_to_the_manifest() -> None:
    spoken = LiveToolSpec("get_events_tool", "event", "event", ("query",))
    assert live_tool_description(spoken, _Manifest("get_events_tool", description="x")) == (
        tool_descriptions()["get_events_tool"]
    )
    long_text = "First paragraph of the catalogue.\n\nSecond paragraph the voice never needs."
    plain = LiveToolSpec("get_route_matrix_tool", "route", "route", ())
    assert live_tool_description(
        plain, _Manifest("get_route_matrix_tool", description=long_text)
    ) == ("First paragraph of the catalogue.")
    huge = LiveToolSpec("get_route_matrix_tool", "route", "route", ())
    text = live_tool_description(huge, _Manifest("get_route_matrix_tool", description="w" * 1000))
    assert len(text) == mod.LIVE_TOOL_DESCRIPTION_MAX_CHARS


@pytest.mark.unit
def test_live_tool_parameters_carry_the_bounds_the_tool_enforces() -> None:
    """ADR-184: a bound the validator enforces reaches the producer — here in
    the description, since the vendor schema carries no numeric bounds. An
    array travels with the type of its items (measured 2026-09-16: the vendor
    refuses an array whose items carry no description)."""
    manifest = _Manifest(
        name="get_events_tool",
        parameters=[
            _param("query", d="Free text"),
            ParameterSchema(
                name="max_results",
                type="integer",
                required=False,
                description="Max",
                constraints=[
                    ParameterConstraint(kind="minimum", value=1),
                    ParameterConstraint(kind="maximum", value=25),
                ],
            ),
            ParameterSchema(
                name="scope",
                type="string",
                required=True,
                description="Which",
                constraints=[ParameterConstraint(kind="enum", value=["mine", "all"])],
            ),
            _param("waypoints", "array"),
            _param("event_id"),
        ],
    )
    spec = LiveToolSpec(
        "get_events_tool", "event", "event", ("query", "max_results", "scope", "waypoints")
    )
    params = live_tool_parameters(spec, manifest)
    assert [p.name for p in params] == ["query", "max_results", "scope", "waypoints"]
    assert params[1].description == "Max (1 to 25)"
    assert params[2].enum == ("mine", "all") and params[2].required is True
    assert params[3].type == "array" and params[3].items_type == "string"


@pytest.mark.unit
def test_spec_for_knows_only_the_derived_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod, "_SPECS", derive_live_tool_specs(_catalogue(), domain_of=_domain_of))
    assert spec_for("get_events_tool") is not None
    assert spec_for("recall_memories") is not None
    assert spec_for("send_email_tool") is None
    assert spec_for("") is None


@pytest.mark.unit
async def test_availability_reads_the_flag_the_capabilities_and_the_person_s_switches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    specs = derive_live_tool_specs(_catalogue(), domain_of=_domain_of)
    monkeypatch.setattr(mod, "_SPECS", specs)
    monkeypatch.setattr(settings, "telephony_live_tools_enabled", True)

    async def _hidden(_registry: object) -> set[str]:
        return {"get_tasks_tool"}

    monkeypatch.setattr(mod, "tools_hidden_by_capabilities", _hidden)
    monkeypatch.setattr(mod, "get_global_registry", lambda: object())

    offered = await available_live_tools(disabled_domains=frozenset({"email"}))
    assert [s.name for s in offered] == [
        "get_events_tool",
        "get_route_matrix_tool",
        "get_route_tool",
        "recall_memories",
    ]
    # The person switched the memories off too.
    offered = await available_live_tools(disabled_domains=frozenset({"email", "context"}))
    assert "recall_memories" not in [s.name for s in offered]
    monkeypatch.setattr(settings, "telephony_live_tools_enabled", False)
    assert await available_live_tools() == ()


# ---------------------------------------------------------------------------
# Provisioning, idempotent by fingerprint
# ---------------------------------------------------------------------------


class _Client:
    def __init__(self, fail_create: bool = False) -> None:
        self.created: list[dict] = []
        self.deleted: list[str] = []
        self.fail_create = fail_create
        self.in_flight = 0
        self.max_in_flight = 0

    async def create_tool(self, body: dict) -> str:
        from src.domains.telephony.client import ElevenLabsAgentsError

        if self.fail_create:
            raise ElevenLabsAgentsError(500, "boom")
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        await asyncio.sleep(0)
        self.in_flight -= 1
        self.created.append(body)
        return f"tool_{body['tool_config']['name']}"

    async def delete_tool(self, tool_id: str) -> None:
        self.deleted.append(tool_id)


class _DB:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


def _connector(metadata: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        connector_metadata=metadata if metadata is not None else {"agent_id": "ag"}
    )


@pytest.fixture
def _provisioning(monkeypatch: pytest.MonkeyPatch) -> dict:
    monkeypatch.setattr(settings, "telephony_live_tools_enabled", True)
    monkeypatch.setattr(settings, "api_url", "https://lia-back.example.test")
    manifests = {m.name: m for m in _catalogue()}
    specs = derive_live_tool_specs(manifests.values(), domain_of=_domain_of)
    monkeypatch.setattr(mod, "_SPECS", specs)
    monkeypatch.setattr(mod, "_manifest_of", lambda name: manifests[name])

    async def _available(**_kw: Any) -> tuple[LiveToolSpec, ...]:
        return specs

    monkeypatch.setattr(mod, "available_live_tools", _available)
    return {"manifests": manifests, "specs": specs}


@pytest.mark.unit
async def test_provisioning_creates_the_tools_once_and_stores_ids_and_fingerprint(
    _provisioning: dict,
) -> None:
    client = _Client()
    db = _DB()
    connector = _connector()
    specs = _provisioning["specs"]

    bindings = await ensure_vendor_live_tools(
        db, connector=connector, api_key="k", api_secret="whsec", client_factory=lambda _k: client
    )

    assert [b.name for b in bindings] == [s.name for s in specs]
    assert bindings[0] == LiveToolBinding("get_emails_tool", "tool_get_emails_tool", "email")
    assert len(client.created) == len(specs)
    headers = client.created[0]["tool_config"]["api_schema"]["request_headers"]
    assert headers == {"X-LIA-Tool-Secret": live_tool_token("whsec")}
    assert client.created[0]["tool_config"]["api_schema"]["url"].startswith(
        "https://lia-back.example.test"
    )
    meta = connector.connector_metadata
    assert meta["live_tool_ids"] == {b.name: b.vendor_id for b in bindings}
    assert meta["live_tools_hash"]
    assert meta["agent_id"] == "ag"  # a NEW dict, the old keys kept
    assert db.commits == 1

    # Second call, nothing drifted: no vendor round trip, same bindings.
    again = await ensure_vendor_live_tools(
        db, connector=connector, api_key="k", api_secret="whsec", client_factory=lambda _k: client
    )
    assert again == bindings
    assert len(client.created) == len(specs)
    assert db.commits == 1


@pytest.mark.unit
async def test_provisioning_creates_the_tools_concurrently_but_bounded(
    _provisioning: dict,
) -> None:
    """Fifty tools created one after the other would hold the dial for a
    minute: they are created concurrently, under a bound the vendor tolerates."""
    client = _Client()
    await ensure_vendor_live_tools(
        _DB(),
        connector=_connector(),
        api_key="k",
        api_secret="whsec",
        client_factory=lambda _k: client,
    )
    assert 1 < client.max_in_flight <= mod.LIVE_TOOL_PROVISIONING_CONCURRENCY


@pytest.mark.unit
async def test_provisioning_replaces_the_tools_when_the_fingerprint_drifts(
    _provisioning: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _Client()
    connector = _connector(
        {
            "agent_id": "ag",
            "live_tool_ids": {"get_events_tool": "old_a"},
            "live_tools_hash": "stale",
        }
    )
    await ensure_vendor_live_tools(
        _DB(),
        connector=connector,
        api_key="k",
        api_secret="whsec",
        client_factory=lambda _k: client,
    )
    assert len(client.created) == len(_provisioning["specs"])
    assert client.deleted == ["old_a"]  # the old ones go, forced by the client


@pytest.mark.unit
async def test_provisioning_never_blocks_a_call_on_a_vendor_failure(_provisioning: dict) -> None:
    client = _Client(fail_create=True)
    connector = _connector()
    bindings = await ensure_vendor_live_tools(
        _DB(),
        connector=connector,
        api_key="k",
        api_secret="whsec",
        client_factory=lambda _k: client,
    )
    assert bindings == ()
    assert "live_tool_ids" not in connector.connector_metadata


@pytest.mark.unit
async def test_provisioning_is_inert_when_the_flag_is_off(
    _provisioning: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mod, "available_live_tools", _REAL_AVAILABLE)
    monkeypatch.setattr(settings, "telephony_live_tools_enabled", False)
    client = _Client()
    bindings = await ensure_vendor_live_tools(
        _DB(),
        connector=_connector(),
        api_key="k",
        api_secret="whsec",
        client_factory=lambda _k: client,
    )
    assert bindings == () and client.created == []


@pytest.mark.unit
async def test_provisioning_offers_only_what_the_capabilities_allow(
    _provisioning: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _only_tasks(**_kw: Any) -> tuple[LiveToolSpec, ...]:
        return tuple(s for s in _provisioning["specs"] if s.name == "get_tasks_tool")

    monkeypatch.setattr(mod, "available_live_tools", _only_tasks)
    client = _Client()
    bindings = await ensure_vendor_live_tools(
        _DB(),
        connector=_connector(),
        api_key="k",
        api_secret="whsec",
        client_factory=lambda _k: client,
    )
    assert [b.name for b in bindings] == ["get_tasks_tool"]


@pytest.mark.unit
def test_vendor_bodies_describe_each_tool_and_type_its_arrays(_provisioning: dict) -> None:
    bodies = vendor_bodies(_provisioning["specs"], token="t")
    by_name = {b["tool_config"]["name"]: b for b in bodies}
    assert (
        by_name["get_events_tool"]["tool_config"]["description"]
        == tool_descriptions()["get_events_tool"]
    )
    # No voice line for the matrix tool: the catalogue's own words serve,
    # first paragraph only.
    assert by_name["get_route_matrix_tool"]["tool_config"]["description"] == (
        "Durations between several origins and destinations."
    )
    assert by_name["get_events_tool"]["tool_config"]["response_timeout_secs"] == (
        settings.telephony_live_tool_timeout_seconds
    )
    waypoints = by_name["get_route_tool"]["tool_config"]["api_schema"]["request_body_schema"][
        "properties"
    ]["waypoints"]
    assert waypoints["type"] == "array" and waypoints["items"]["type"] == "string"
    assert waypoints["items"]["description"]
    # The native lookup is provisioned like any other, on its own route.
    recall = by_name["recall_memories"]["tool_config"]
    assert recall["api_schema"]["url"].endswith("/telephony/tools/recall_memories")
    assert recall["api_schema"]["request_body_schema"]["required"] == ["call_id", "query"]


# ---------------------------------------------------------------------------
# Execution on a synthetic runtime
# ---------------------------------------------------------------------------


def _fake_tool(behaviour: str = "ok"):
    @tool
    async def get_events_tool(
        runtime: Annotated[ToolRuntime, InjectedToolArg],
        query: str = "",
        max_results: int = 10,
    ) -> UnifiedToolOutput:
        """Fake agenda."""
        assert runtime.context is not None and runtime.config["configurable"]["thread_id"]
        # A connector tool reads its clients through the dependency container
        # (measured on Docker dev 2026-09-16: without it get_events_tool answers
        # « Tool dependencies not injected »); the container is bound to a live
        # session for the run.
        assert runtime.context.deps is not None and runtime.context.deps.db is not None
        assert runtime.store is not None
        if behaviour == "raise":
            raise RuntimeError("provider down")
        if behaviour == "slow":
            await asyncio.sleep(5)
        if behaviour == "failure":
            return UnifiedToolOutput.failure(message="No calendar connected", error_code="x")
        return UnifiedToolOutput.data_success(
            message=f"{max_results} events for {query!r}",
            structured_data={
                "count": 40,
                "events": [{"title": "Dentist", "start": "10:00"}]
                + [
                    {"title": f"Meeting number {i} with a long description", "start": "11:00"}
                    for i in range(39)
                ],
            },
        )

    return get_events_tool


@pytest.fixture
def _execution(monkeypatch: pytest.MonkeyPatch) -> dict:
    captured: dict = {"consultations": []}

    async def _store() -> object:
        return object()

    def _record(**kwargs: Any) -> None:
        captured["consultations"].append(kwargs)

    @asynccontextmanager
    async def _recorder(*, run_id: str):  # noqa: ANN202
        captured["collector_run_id"] = run_id
        yield []

    class _Db:
        async def __aenter__(self):  # noqa: ANN204
            captured["session_opened"] = True
            return object()

        async def __aexit__(self, *exc):  # noqa: ANN002, ANN204
            captured["session_closed"] = True
            return False

    class _Deps:
        def __init__(self, db_session):  # noqa: ANN001
            self.db = db_session
            captured["deps"] = self

        async def aclose(self) -> None:
            captured["deps_closed"] = True

    class _Tracker:
        def __init__(self, run_id, user_id, session_id, conversation_id, **kw):  # noqa: ANN001
            captured["tracker"] = {
                "run_id": run_id,
                "user_id": user_id,
                "session_id": session_id,
                "conversation_id": conversation_id,
            }

        async def __aenter__(self):  # noqa: ANN204
            captured["tracker_entered"] = True
            return self

        async def __aexit__(self, *exc):  # noqa: ANN002, ANN204
            captured["tracker_exited"] = True
            return False

    class _Callback:
        def __init__(self, tracker, run_id) -> None:  # noqa: ANN001
            captured["callback"] = (tracker, run_id)
            captured["callback_instance"] = self

    monkeypatch.setattr(mod, "get_tool_context_store", _store)
    monkeypatch.setattr(mod, "record_surface_consultations", _record)
    monkeypatch.setattr(mod, "treatment_recorder", _recorder)
    monkeypatch.setattr(mod, "get_db_context", lambda: _Db())
    monkeypatch.setattr(mod, "ToolDependencies", _Deps)
    monkeypatch.setattr(mod, "TrackingContext", _Tracker)
    monkeypatch.setattr(mod, "TokenTrackingCallback", _Callback)
    monkeypatch.setattr(mod, "_SPECS", derive_live_tool_specs(_catalogue(), domain_of=_domain_of))
    monkeypatch.setattr(settings, "telephony_live_tool_timeout_seconds", 5)
    return captured


async def _run(spec_name: str = "get_events_tool", **args: Any) -> str:
    spec = spec_for(spec_name)
    assert spec is not None
    return await run_live_tool(
        spec,
        args,
        user_id=uuid4(),
        language="fr",
        timezone="Europe/Paris",
        display_name="Alex",
        call_id=uuid4(),
    )


@pytest.mark.unit
async def test_run_validates_args_through_the_tool_schema_and_projects_the_result(
    _execution: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mod, "get_tool", lambda _n: _fake_tool())
    monkeypatch.setattr(settings, "telephony_live_tool_result_max_tokens", 4000)
    text = await _run(query="dentist", max_results="5", invented="x")
    assert text.startswith("5 events for 'dentist'")
    assert "Dentist" in text and "Meeting number 38" in text
    assert "shown" not in text
    # The dependency container and its session live for the run, then close —
    # the clients it cached hold sockets (ADR-283's owner rule).
    assert _execution["session_opened"] and _execution["session_closed"]
    assert _execution["deps_closed"] is True
    # The consultation is filed on the phone_call surface, under the section
    # named after the tool's domain, inside a collector opened for the call
    # (no turn is running).
    (row,) = _execution["consultations"]
    assert row["surface"] == "phone_call"
    assert row["opened"] == ["event"] and row["failed"] == []
    assert _execution["collector_run_id"] == row["run_id"]


def _heavy_tool():
    """Four real-shaped calendar events, each ~1 000 characters raw."""
    raw = {
        "id": "_64p36cpn6h0j6b9g60o30b9k6kq3ab9p6ss32b9n60qj6dho8gs3ee1j8s",
        "summary": "Dentist",
        "start": {"dateTime": "2026-09-20T14:00:00+02:00", "formatted": "dimanche 20 à 14:00"},
        "end": {"dateTime": "2026-09-20T15:00:00+02:00", "formatted": "dimanche 20 à 15:00"},
        "htmlLink": "https://www.google.com/calendar/event?eid=" + "x" * 80,
        "attendees": [
            {"email": f"p{i}@example.com", "responseStatus": "accepted"} for i in range(6)
        ],
        "reminders": {"useDefault": True, "overrides": [{"method": "popup", "minutes": 10}]},
        "iCalUID": "abc@google.com",
        "etag": '"3456"',
        "creator": {"email": "me@example.com"},
        "organizer": {"email": "me@example.com"},
        "description": "Bring the X-ray results. " * 8,
    }

    @tool
    async def get_events_tool(
        runtime: Annotated[ToolRuntime, InjectedToolArg], query: str = ""
    ) -> UnifiedToolOutput:
        """Fake agenda, heavy."""
        return UnifiedToolOutput.data_success(
            message="4 events",
            structured_data={
                "count": 4,
                "events": [dict(raw, summary=f"Event {i}") for i in range(4)],
            },
        )

    return get_events_tool


@pytest.mark.unit
async def test_run_reads_every_item_out_in_words_a_voice_can_say(
    _execution: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Measured on production 2026-09-16: four weekend events, ONE reached the
    voice agent — the raw event JSON ate the budget. Projected for a voice,
    all four fit under the default budget and no identifier or link is read."""
    monkeypatch.setattr(mod, "get_tool", lambda _n: _heavy_tool())
    text = await _run(query="weekend")
    assert all(f"Event {i}" in text for i in range(4))
    assert "shown" not in text
    for forbidden in ("htmlLink", "iCalUID", "etag", "_64p36", "responseStatus", "dateTime"):
        assert forbidden not in text, forbidden
    assert "dimanche 20 à 14:00" in text


@pytest.mark.unit
async def test_run_spends_under_the_call_s_own_run_id(
    _execution: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Lot 8: a lookup that spends (an e-mail digest, an embedding search)
    records under ONE run id shared by everything the call costs — the
    tracker is opened around the run, and the runtime config carries its
    callback so the tool's own model calls reach it (ADR-287's lesson: a
    structured door handed no config builds a fresh one nobody tracks)."""
    from src.domains.telephony.spend import phone_call_run_id

    seen: dict[str, Any] = {}

    @tool
    async def get_events_tool(
        runtime: Annotated[ToolRuntime, InjectedToolArg], query: str = ""
    ) -> UnifiedToolOutput:
        """Fake agenda reading its config."""
        seen["callbacks"] = runtime.config.get("callbacks")
        seen["node"] = (runtime.config.get("metadata") or {}).get("langgraph_node")
        return UnifiedToolOutput.data_success(message="ok", structured_data={"events": []})

    monkeypatch.setattr(mod, "get_tool", lambda _n: get_events_tool)
    call_id = uuid4()
    user_id = uuid4()
    await run_live_tool(
        spec_for("get_events_tool"),  # type: ignore[arg-type]
        {"query": "q"},
        user_id=user_id,
        language="fr",
        timezone="Europe/Paris",
        display_name="Alex",
        call_id=call_id,
    )
    tracker = _execution["tracker"]
    assert tracker["run_id"] == phone_call_run_id(call_id)
    assert tracker["user_id"] == user_id
    assert tracker["session_id"] == f"phone_call_{call_id}"
    assert tracker["conversation_id"] is None
    assert _execution["tracker_entered"] and _execution["tracker_exited"]
    callback_tracker, callback_run_id = _execution["callback"]
    assert callback_run_id == phone_call_run_id(call_id)
    assert callback_tracker is _execution.get("tracker_instance", callback_tracker)
    # The callback rides the runtime config (beside the metrics handler the
    # node enrichment adds), so the tool's own model calls reach the tracker.
    assert _execution["callback_instance"] in seen["callbacks"]
    assert seen["node"] == "telephony_live_tool"


@pytest.mark.unit
async def test_run_states_the_cut_when_the_result_exceeds_its_budget(
    _execution: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mod, "get_tool", lambda _n: _fake_tool())
    monkeypatch.setattr(settings, "telephony_live_tool_result_max_tokens", 100)
    text = await _run(query="q")
    assert "Dentist" in text  # the first item always passes whole
    assert "Meeting number 38" not in text
    assert "of 40 items are shown" in text


@pytest.mark.unit
async def test_run_reads_a_tool_refusal_as_a_failed_consultation(
    _execution: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mod, "get_tool", lambda _n: _fake_tool("failure"))
    text = await _run()
    assert "No calendar connected" in text
    (row,) = _execution["consultations"]
    assert row["failed"] == ["event"]


@pytest.mark.unit
async def test_run_turns_an_exception_into_a_spoken_line(
    _execution: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mod, "get_tool", lambda _n: _fake_tool("raise"))
    text = await _run()
    assert "provider down" not in text  # never the raw error
    assert text == mod.result_lines()["failed"].format(tool="get_events_tool")


@pytest.mark.unit
async def test_run_bounds_the_lookup_under_the_vendor_timeout(
    _execution: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mod, "get_tool", lambda _n: _fake_tool("slow"))
    monkeypatch.setattr(settings, "telephony_live_tool_timeout_seconds", 5)
    monkeypatch.setattr(mod, "TELEPHONY_LIVE_TOOL_INNER_MARGIN_SECONDS", 4.8)
    text = await _run()
    assert text == mod.result_lines()["timeout"].format(tool="get_events_tool")


@pytest.mark.unit
async def test_run_refuses_a_tool_the_registry_does_not_hold(
    _execution: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mod, "get_tool", lambda _n: None)
    text = await _run()
    assert text == mod.result_lines()["failed"].format(tool="get_events_tool")


@pytest.mark.unit
async def test_run_serves_a_native_lookup_through_its_own_reader(
    _execution: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The memories lookup calls no registry tool: it reads through the
    chat's own profile builder, for the person, ranked on the question."""
    seen: dict[str, Any] = {}

    async def _profile(user_id: str, query: str, **_kw: Any):  # noqa: ANN202
        seen["user_id"], seen["query"] = user_id, query
        return "- likes tea\n\n- dentist on Mondays\n", None, None

    monkeypatch.setattr(mod, "build_psychological_profile", _profile)
    monkeypatch.setattr(
        mod, "get_tool", lambda _n: pytest.fail("no registry tool for a native lookup")
    )
    text = await _run("recall_memories", query="what do I drink")
    assert text == "- likes tea\n- dentist on Mondays"
    assert seen["query"] == "what do I drink" and seen["user_id"]
    (row,) = _execution["consultations"]
    assert row["opened"] == ["memories"] and row["failed"] == []


@pytest.mark.unit
async def test_run_refuses_a_native_lookup_without_its_required_argument(
    _execution: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mod, "build_psychological_profile", lambda *a, **k: pytest.fail("ran"))
    text = await _run("recall_memories")
    assert text == mod.result_lines()["failed"].format(tool="recall_memories")
