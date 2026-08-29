"""Same contract as ``test_manifest_reference_examples_truthful``, one shape further.

Those tools build their output from an already-parsed provider result, so the
suite can call a builder directly. The tools here build it INSIDE the ``@tool``
body, right after the client answers — there is no seam to feed. Driving the
real coroutine with a mocked client covers strictly more: the whole tool path,
not just its formatting half.

Mocking rather than extracting a seam is deliberate. The seam would have to be
carved into 17 production tools to make them testable, and a refactor of live
code is a worse trade than a double at the network boundary — which is exactly
what a unit test is allowed to replace.

**The doubles sit as low as they can, and are the production types wherever one
exists.** ``WikipediaClient`` is REAL with only its HTTP call answered here, so
the client's own parameter building and ``query.search`` unwrapping run for
real; ``RelationDetail`` and ``Reminder`` are the production schema and model,
so Pydantic and SQLAlchemy reject a renamed field instead of letting this guard
certify a shape nothing produces. A hand-rolled stand-in would have asserted
against a shape invented in this file — the very fiction ADR-194 removed.

Same oracle as its sibling (``reference_harness``): rebuild what
``completed_steps`` holds, then resolve the published paths against it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from langchain.tools import ToolRuntime

from src.domains.agents.registry.catalogue import ToolManifest
from src.domains.agents.tools import (
    relation_read_tools,
    reminder_tools,
    routes_tools,
    wikipedia_tools,
)
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.connectors.clients.wikipedia_client import WikipediaClient
from src.domains.relations.schemas import (
    IdentityConfidence,
    RelationCall,
    RelationDetail,
    RelationOpenLoop,
    RelationPeerMessage,
)
from src.domains.reminders.models import Reminder
from tests.helpers.runtime_context import make_tool_runtime
from tests.unit.domains.agents.registry.reference_harness import (
    completed_step,
    type_mismatches,
    unresolved_reference_examples,
    unresolved_top_level_outputs,
)

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------------
# Provider payloads, in the shape the CLIENT returns them (not the tool's own
# output): `client.search()` yields raw MediaWiki search rows, `get_article()`
# the article record, and so on.
# --------------------------------------------------------------------------
_WIKI_SEARCH_ROWS = [
    {
        "title": "Lyonnaise de banque",
        "pageid": 12345,
        "snippet": 'Une <span class="searchmatch">banque</span> régionale',
    },
    {"title": "Lyon", "pageid": 6789, "snippet": "Ville française"},
]
_WIKI_ARTICLE = {
    "title": "Lyon",
    "pageid": 6789,
    "extract": "Lyon est une commune française située au confluent du Rhône et de la Saône.",
    "fullurl": "https://fr.wikipedia.org/wiki/Lyon",
}
_WIKI_SECTIONS = [
    {"title": "Géographie", "level": 2, "index": "1"},
    {"title": "Histoire", "level": 2, "index": "2"},
]
_WIKI_RELATED = [
    {"title": "Villeurbanne", "pageid": 4242},
    {"title": "Rhône", "pageid": 4243},
]


async def _drive(tool: Any, **kwargs: Any) -> UnifiedToolOutput:
    """Await a decorated tool's real coroutine.

    The single home for the ``no-any-return`` ignore: LangChain's ``@tool``
    decorator erases the return type, and repeating the concession at every
    call site would spread a library limitation across the whole file.

    Args:
        tool: The decorated tool object.
        **kwargs: The tool's own arguments, ``runtime`` included.

    Returns:
        Whatever the tool produced.
    """
    return await tool.coroutine(**kwargs)  # type: ignore[no-any-return]


async def _mediawiki_response(params: dict[str, Any]) -> dict[str, Any]:
    """Answer like the MediaWiki HTTP API, keyed on the action being requested.

    The simulation sits at the HTTP boundary — the only place a unit test is
    entitled to replace — rather than on the client's own methods. Everything
    above it is the REAL client: its parameter building, its
    ``query.search`` / ``query.pages`` unwrapping, its error branches. A double
    placed on ``client.search()`` would have skipped all of that and asserted
    against a shape invented here.

    Args:
        params: The query parameters the client built.

    Returns:
        A MediaWiki-shaped JSON body.
    """
    if params.get("list") == "search":
        return {"query": {"search": [dict(row) for row in _WIKI_SEARCH_ROWS]}}
    if params.get("prop") == "sections" or params.get("action") == "parse":
        return {"parse": {"sections": [dict(s) for s in _WIKI_SECTIONS]}}
    if "links" in str(params.get("prop", "")):
        return {"query": {"pages": {"6789": {**dict(_WIKI_ARTICLE), "links": _WIKI_RELATED}}}}
    return {"query": {"pages": {"6789": dict(_WIKI_ARTICLE)}}}


def _wikipedia_client() -> WikipediaClient:
    """A REAL ``WikipediaClient`` with only its HTTP call replaced."""
    client = WikipediaClient(language="fr")
    client._make_request = AsyncMock(side_effect=_mediawiki_response)  # type: ignore[method-assign]
    return client


async def _run_wikipedia(tool: Any, **kwargs: Any) -> UnifiedToolOutput:
    """Drive a wikipedia tool's real coroutine against the client double."""
    with patch.object(wikipedia_tools, "_get_wikipedia_client", return_value=_wikipedia_client()):
        return await _drive(tool, **kwargs)


def _pending_reminder() -> Reminder:
    """A REAL ``Reminder`` row, exactly what ``ReminderService`` hands back.

    The production model rather than a stand-in: SQLAlchemy rejects an unknown
    column name, so a renamed field breaks this guard instead of letting it
    certify a shape the service no longer returns.

    Returns:
        One pending reminder, carrying the fields the tools read.
    """
    return Reminder(
        id=uuid.UUID("11111111-2222-3333-4444-555555555555"),
        user_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        content="Rappeler le dentiste",
        original_message="rappelle-moi d'appeler le dentiste demain à 9h",
        trigger_at=datetime(2026, 8, 3, 9, 0, tzinfo=UTC),
        created_at=datetime(2026, 8, 2, 8, 0, tzinfo=UTC),
    )


def _db_context_double() -> Any:
    """Stand in for ``get_db_context()``: an async context manager over a fake session.

    The session's own awaitables (``commit``/``rollback``/``flush``) must be
    async, otherwise the tool's ``await db.commit()`` fails inside its own
    try/except and the tool reports a *business* error instead of running.
    """
    session = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.flush = AsyncMock()

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def _tool_runtime() -> ToolRuntime:
    """A runtime carrying the ids every tool here reads.

    Not reminder-specific: routes and relation reads pull the same identity.
    Built through the shared helper so the typed context is real — since
    ADR-231 the identity comes from ``runtime.context``, not from the bag.
    """
    return make_tool_runtime(
        user_id=UUID("11111111-1111-1111-1111-111111111111"),
        thread_id="session-under-test",
        conversation_id="session-under-test",
        store=MagicMock(),
    )


async def _run_create_reminder() -> UnifiedToolOutput:
    """Drive ``create_reminder_tool`` with its service and session mocked away."""
    service = MagicMock()
    service.create_reminder = AsyncMock(return_value=_pending_reminder())

    with (
        patch(
            "src.infrastructure.database.session.get_db_context",
            return_value=_db_context_double(),
        ),
        patch("src.domains.reminders.service.ReminderService", return_value=service),
    ):
        return await _drive(
            reminder_tools.create_reminder_tool,
            content="Rappeler le dentiste",
            original_message="rappelle-moi d'appeler le dentiste demain à 9h",
            runtime=_tool_runtime(),
            trigger_datetime="2026-08-03T09:00:00+02:00",
        )


async def _run_list_reminders() -> UnifiedToolOutput:
    """Drive ``list_reminders_tool`` with its service and session mocked away.

    Both are imported INSIDE the tool body, so the patch targets the defining
    modules rather than ``reminder_tools``.
    """
    service = MagicMock()
    service.list_pending_for_user = AsyncMock(return_value=[_pending_reminder()])

    with (
        patch(
            "src.infrastructure.database.session.get_db_context",
            return_value=_db_context_double(),
        ),
        patch("src.domains.reminders.service.ReminderService", return_value=service),
    ):
        return await _drive(reminder_tools.list_reminders_tool, runtime=_tool_runtime())


#: The Routes API matrix response, in the shape ``compute_route_matrix`` returns
#: it: a FLAT element list carrying its own origin/destination indices, which
#: the tool folds into the nested `matrix[origin][destination]` grid.
_ROUTE_MATRIX_RESPONSE = {
    "elements": [
        {
            "originIndex": 0,
            "destinationIndex": 0,
            "duration": "3600s",
            "staticDuration": "3300s",
            "distanceMeters": 65000,
            "condition": "ROUTE_EXISTS",
        }
    ]
}


async def _run_route_matrix() -> UnifiedToolOutput:
    """Drive ``get_route_matrix_tool`` with the Routes client and cache mocked away.

    The cache double reports a miss so the tool takes its live branch — the one
    that actually builds the matrix a `$steps` reference reads.
    """
    cache = MagicMock()
    cache.get_matrix = AsyncMock(return_value=(None, False, None, None))
    cache.set_matrix = AsyncMock()

    with (
        # The tool refuses to call out when no API key is configured; the test
        # environment has none, so the key is what unlocks the live branch.
        patch.object(routes_tools.settings, "google_api_key", "test-key"),
        # Without this the helper opens a REAL database session and the test
        # spends ~21s failing to reach Postgres before carrying on. A unit test
        # must not touch a database — the preferences are input, not subject.
        patch.object(
            routes_tools,
            "get_user_preferences",
            AsyncMock(return_value=("Europe/Paris", "fr", "fr-FR")),
        ),
        # Patch the INSTANCE methods, not the class: `parse_duration`,
        # `meters_to_km` and `format_duration` are static helpers the tool calls
        # on the class itself, and replacing the class would hand the matrix
        # MagicMocks instead of the real conversions this test is here to check.
        patch.object(
            routes_tools.GoogleRoutesClient,
            "compute_route_matrix",
            AsyncMock(return_value=dict(_ROUTE_MATRIX_RESPONSE)),
        ),
        patch.object(routes_tools.GoogleRoutesClient, "close", AsyncMock()),
        patch.object(routes_tools, "get_redis_cache", AsyncMock(return_value=MagicMock())),
        patch.object(routes_tools, "RoutesCache", return_value=cache),
    ):
        return await _drive(
            routes_tools.get_route_matrix_tool,
            origins=["Paris"],
            destinations=["Lyon"],
            runtime=_tool_runtime(),
        )


#: A computed route, in the shape ``compute_route`` returns it: the Routes API
#: wraps candidates in a `routes` list, and the tool reads the first one.
_ROUTE_RESPONSE = {
    "routes": [
        {
            "duration": "3600s",
            "staticDuration": "3300s",
            "distanceMeters": 65000,
            # A real encoded polyline: a bogus one only makes the tool log a
            # decode warning, which would be noise in every run of this suite.
            "polyline": {"encodedPolyline": "_p~iF~ps|U_ulLnnqC_mqNvxq`@"},
            "legs": [],
        }
    ]
}


async def _run_route() -> UnifiedToolOutput:
    """Drive ``get_route_tool``; origin/destination resolution is stubbed out.

    Both resolvers reach geocoding and the user's saved home address — network
    and database, neither of which belongs in a unit test.
    """
    cache = MagicMock()
    cache.get_route = AsyncMock(return_value=(None, False, None, None))
    cache.set_route = AsyncMock()

    with (
        patch.object(routes_tools.settings, "google_api_key", "test-key"),
        patch.object(
            routes_tools,
            "get_user_preferences",
            AsyncMock(return_value=("Europe/Paris", "fr", "fr-FR")),
        ),
        patch.object(routes_tools, "_resolve_origin", AsyncMock(return_value=("Paris", None))),
        patch.object(routes_tools, "_resolve_destination", AsyncMock(return_value="Lyon")),
        patch.object(
            routes_tools.GoogleRoutesClient,
            "compute_route",
            AsyncMock(return_value=dict(_ROUTE_RESPONSE)),
        ),
        patch.object(routes_tools.GoogleRoutesClient, "close", AsyncMock()),
        patch.object(routes_tools, "get_redis_cache", AsyncMock(return_value=MagicMock())),
        patch.object(routes_tools, "RoutesCache", return_value=cache),
    ):
        return await _drive(
            routes_tools.get_route_tool,
            destination="Lyon",
            origin="Paris",
            runtime=_tool_runtime(),
        )


def _relation_detail() -> RelationDetail:
    """A REAL ``RelationDetail`` carrying one row in each block the tools page.

    The production schema, not a stand-in: Pydantic validates every field here,
    so a renamed or dropped attribute breaks this guard instead of letting it
    certify a contract the aggregate no longer produces. That is exactly the
    failure mode a hand-rolled double cannot catch.

    Returns:
        One relationship detail with a call, an open loop and a peer message.
    """
    return RelationDetail(
        display_name="Alice Vernier",
        identity_confidence=IdentityConfidence.EXACT,
        open_loops=[
            RelationOpenLoop(
                id="loop-1",
                subject="renvoyer le devis",
                direction="user_owes",
                due_hint=None,
                days_open=3,
            )
        ],
        open_loops_total=1,
        recent_calls=[
            RelationCall(
                id="call-1",
                objective="prendre des nouvelles",
                outcome="answered",
                summary="échange court",
                created_at=datetime(2026, 8, 1, 18, 30, tzinfo=UTC),
            )
        ],
        recent_calls_total=1,
        memories=[],
        memories_total=0,
        peer_messages=[
            RelationPeerMessage(
                id="msg-1",
                direction="received",
                content="on se rappelle demain",
                occurred_at=datetime(2026, 8, 1, 19, 0, tzinfo=UTC),
            )
        ],
        peer_messages_total=1,
        is_peer=True,
        source="Alice Vernier",
        target="Alice Vernier",
    )


async def _run_relation_read(tool: Any) -> UnifiedToolOutput:
    """Drive a relation read tool with ``RelationsService`` mocked away."""
    service = MagicMock()
    service.build_detail = AsyncMock(return_value=_relation_detail())

    with patch.object(relation_read_tools, "RelationsService", return_value=service):
        return await _drive(tool, person_name="Alice Vernier", runtime=_tool_runtime())


#: tool_name -> how to produce its real output with the provider mocked away.
_PROVIDER_BUILDERS: dict[str, Any] = {
    # `get_calls_tool` (telephony) and `get_peer_messages_tool` (peer) share this
    # builder but are NOT listed: their families are flag-gated and the test
    # environment loads a catalogue without them, so the manifest lookup would
    # raise rather than assert. They are covered wherever those flags are on.
    "get_open_loops_tool": lambda: _run_relation_read(relation_read_tools.get_open_loops_tool),
    "get_route_tool": _run_route,
    "get_route_matrix_tool": _run_route_matrix,
    "create_reminder_tool": _run_create_reminder,
    "list_reminders_tool": _run_list_reminders,
    "search_wikipedia_tool": lambda: _run_wikipedia(
        wikipedia_tools.search_wikipedia_tool, query="Lyon", language="fr", max_results=2
    ),
    "get_wikipedia_summary_tool": lambda: _run_wikipedia(
        wikipedia_tools.get_wikipedia_summary_tool, title="Lyon", language="fr"
    ),
    "get_wikipedia_article_tool": lambda: _run_wikipedia(
        wikipedia_tools.get_wikipedia_article_tool, title="Lyon", language="fr"
    ),
    "get_wikipedia_related_tool": lambda: _run_wikipedia(
        wikipedia_tools.get_wikipedia_related_tool, title="Lyon", language="fr", max_results=2
    ),
}

PROVIDER_TOOLS = tuple(_PROVIDER_BUILDERS)


@pytest.mark.parametrize("tool_name", PROVIDER_TOOLS)
class TestProviderToolsKeepTheirPublishedContract:
    """A path published for these tools must resolve against a real run."""

    async def test_every_reference_example_resolves(
        self, tool_name: str, manifests: dict[str, ToolManifest]
    ) -> None:
        output = await _PROVIDER_BUILDERS[tool_name]()
        assert output.success, f"{tool_name} failed on a nominal provider payload: {output}"

        completed = {"step_1": completed_step(output)}
        broken = unresolved_reference_examples(manifests[tool_name], completed)

        assert not broken, (
            f"{tool_name} publishes {len(broken)} reference_example(s) its output does not "
            f"produce: {broken}. The planner reads these paths as a contract and nothing "
            f"verifies them at runtime. Available top-level keys: {sorted(completed['step_1'])}."
        )

    async def test_every_declared_top_level_output_resolves(
        self, tool_name: str, manifests: dict[str, ToolManifest]
    ) -> None:
        output = await _PROVIDER_BUILDERS[tool_name]()
        completed = {"step_1": completed_step(output)}
        broken = unresolved_top_level_outputs(manifests[tool_name], completed)

        assert not broken, (
            f"{tool_name} declares {len(broken)} top-level output path(s) its execution never "
            f"produces: {broken}. Available top-level keys: {sorted(completed['step_1'])}."
        )

    async def test_every_resolvable_output_has_its_declared_type(
        self, tool_name: str, manifests: dict[str, ToolManifest]
    ) -> None:
        output = await _PROVIDER_BUILDERS[tool_name]()
        completed = {"step_1": completed_step(output)}
        mismatches = type_mismatches(manifests[tool_name], completed)

        assert not mismatches, (
            f"{tool_name} declares output types its execution contradicts: {mismatches}. "
            f"The planner chains values on the strength of these types."
        )
