"""A published reference path must be one the tool actually produces.

Sibling of ``test_catalogue_registry_parity`` — same doctrine, one level
deeper. That test keeps the promise "the advertised tool exists"; this one
keeps "the advertised PATH resolves".

The defect it closes, measured in production 2026-08-01: the planner read
``contacts[0].name`` from ``get_contacts_tool``'s ``reference_examples``,
generated exactly that reference, and the run died on::

    Failed to resolve $steps.step_1.contacts[0].name:
    path 'contacts[0].name' not found in step result. Error: 'name'

Worse than a silent miss: the runtime validator built for exactly this case
never rejected anything — both of its arms were inert from the first commit, so
the broken reference sailed through (ADR-194 removed it). The manifest is
therefore the only authority in play — and an authority that lies has to be
caught here, before merge, because nothing catches it at runtime.

The oracle is the real pipeline, not a hand-written fixture: the tool's own
mixin builds the output, and the derivation below mirrors
``parallel_executor._execute_tool_step`` (registry payloads grouped by
``meta.domain``, then the tool's ``structured_data`` merged without overwrite),
which is what ``completed_steps`` holds when a ``$steps`` reference resolves.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.domains.agents.orchestration.condition_evaluator import ReferenceResolver
from src.domains.agents.registry.catalogue import ToolManifest
from src.domains.agents.tools.mixins import ToolOutputMixin
from src.domains.agents.tools.output import UnifiedToolOutput
from tests.unit.domains.agents.registry.reference_harness import (
    completed_step,
    root_key,
    type_mismatches,
    unresolved_reference_examples,
    unresolved_top_level_outputs,
)

pytestmark = pytest.mark.unit


class _Builder(ToolOutputMixin):
    """Minimal host for the mixin builders (they only need ``operation``)."""

    operation = "search"


# --------------------------------------------------------------------------
# Provider payloads, in the shape the tools hand to their builder: RAW records
# straight from the provider. `google_contacts_tools` passes `result["person"]`
# / `connections` verbatim, `emails_tools` the Gmail message, etc. Using a
# pre-normalized dict here would test the fixture instead of the product.
# --------------------------------------------------------------------------
_PERSON = {
    "resourceName": "people/c6737050419687533025",
    "names": [{"displayName": "Alice Vernier", "givenName": "Alice"}],
    "emailAddresses": [{"value": "alice@example.com", "type": "home"}],
    "phoneNumbers": [{"value": "+33612345678", "type": "mobile"}],
    "addresses": [{"formattedValue": "1 rue de la Paix\n75002 Paris", "type": "home"}],
    "organizations": [{"name": "ACME"}],
    "birthdays": [{"date": {"year": 1985, "month": 4, "day": 12}}],
    "biographies": [{"value": "note"}],
}
_MESSAGE = {
    "id": "18f0a1b2c3d4e5f6",
    "threadId": "18f0a1b2c3d4e5f0",
    "snippet": "Bonjour, on se voit jeudi ?",
    "internalDate": "1753900000000",
    "payload": {
        "headers": [
            {"name": "Subject", "value": "Point de jeudi"},
            {"name": "From", "value": "Alice <alice@example.com>"},
        ]
    },
    "body": "Bonjour, on se voit jeudi ?",
}
_EVENT = {
    "id": "evt_123",
    "summary": "Point hebdo",
    "location": "Paris",
    "description": "ordre du jour",
    "calendar_id": "primary",
    "start": {"dateTime": "2026-08-06T10:00:00+02:00"},
    "end": {"dateTime": "2026-08-06T11:00:00+02:00"},
}
_TASK = {"id": "task_1", "title": "Rappeler Alice", "notes": "avant jeudi", "status": "needsAction"}
_FILE = {"id": "file_1", "name": "compte-rendu.pdf", "mimeType": "application/pdf", "content": "x"}
_PLACE = {
    "id": "place_1",
    "place_id": "place_1",
    "name": "Café de la Paix",
    "phone": "+33142000000",
    "opening_hours": ["lundi 08:00-19:00"],
}


# --------------------------------------------------------------------------
# Tools that format their own output instead of delegating to a mixin builder.
# The payload below is what the tool hands `format_registry_response` in
# production — the client's parsed response — so the derivation stays real.
# --------------------------------------------------------------------------
_PARIS = {"name": "Paris", "country": "FR", "lat": 48.85, "lon": 2.35}
_CURRENT_WEATHER = {
    "temperature": 21.5,
    "feels_like": 21.0,
    "description": "ciel dégagé",
    "humidity": 55,
    "pressure": 1015,
    "wind": {"speed": 3.2, "deg": 180},
    "clouds": 5,
    "icon": "01d",
    "main": "Clear",
}
_DAILY_FORECAST = {
    "date": "2026-08-03",
    "datetime": "2026-08-03T12:00:00Z",
    "temperature": 20.0,
    "temp_min": 14.0,
    "temp_max": 25.0,
    "description": "ensoleillé",
    "humidity": 50,
    "wind_speed": 3.0,
    "icon": "01d",
}
_HOURLY_FORECAST = {
    "datetime": "2026-08-02T15:00:00Z",
    "datetime_text": "15:00",
    "temp": 22.0,
    "description": "clair",
    "humidity": 48,
    "wind_speed": 2.5,
    "icon": "01d",
    "pop": 0.1,
}


_LABELS_RESULT = {
    "success": True,
    "labels": [{"id": "Label_1", "name": "Perso", "type": "user", "messagesTotal": 3}],
    "total_user_labels": 1,
    "total_system_labels": 0,
}
_CALENDARS_RESULT = {
    "success": True,
    "calendars": [
        {
            "id": "primary",
            "summary": "Agenda",
            "primary": True,
            "accessRole": "owner",
            "timeZone": "Europe/Paris",
        }
    ],
}


_BRAVE_DATA = {
    "query": "meilleur restaurant Lyon",
    "endpoint": "web",
    "requested_count": 5,
    "results": [
        {
            "title": "Guide Lyon",
            "url": "https://example.org/lyon",
            "description": "Sélection de tables",
            "age": "1 day ago",
        }
    ],
}
_PERPLEXITY_DATA = {
    "query": "quelle est la capitale du Portugal",
    "answer": "Lisbonne.",
    "citations": [{"url": "https://example.org/pt", "title": "Portugal"}],
    "related_questions": ["Quelle est la population de Lisbonne ?"],
    "model": "sonar",
}
_HUE_LIGHTS_DATA = {
    "lights": [
        {
            "id": "light-1",
            "name": "Salon",
            "on": {"on": True},
            "dimming": {"brightness": 80},
            "room": "Salon",
        }
    ]
}
_HUE_ROOMS_DATA = {
    "rooms": [
        {
            "id": "room-1",
            "name": "Salon",
            "lights": ["light-1"],
            "any_on": True,
            "children_count": 1,
        }
    ]
}
#: Hue scenes arrive with the provider's nested shape (`metadata.name`,
#: `group.rid`), not a flattened one — the tool is what flattens them.
_HUE_SCENES_DATA = {
    "scenes": [{"id": "scene-1", "metadata": {"name": "Détente"}, "group": {"rid": "room-1"}}]
}
_HUE_CONTROL_DATA = {"name": "Salon", "on": True, "brightness": 80, "color": None}
_LABEL_CREATED_RESULT = {"success": True, "label": {"id": "Label_1", "name": "Perso"}}
_LABEL_RENAMED_RESULT = {
    "success": True,
    "old_name": "Perso",
    "new_name": "Personnel",
    "label": {"id": "Label_1", "name": "Personnel"},
}
_LABELS_APPLIED_RESULT = {"success": True, "message_count": 2, "labels_applied": ["Perso"]}
_LABELS_REMOVED_RESULT = {"success": True, "message_count": 2, "labels_removed": ["Perso"]}
_TASK_LISTS_RESULT = {"success": True, "task_lists": [{"id": "tasklist-1", "title": "Perso"}]}
_LOCATION_DATA = {
    "locations": [
        {
            "formatted_address": "1 rue de la Paix, 75002 Paris",
            "locality": "Paris",
            "country": "France",
            "postal_code": "75002",
            "lat": 48.8698,
            "lng": 2.3312,
        }
    ]
}


def _formatter_builders() -> dict[str, Any]:
    """Tools that own their formatting; drive their real entry point.

    ``format_registry_response`` is what the tool calls in production once the
    provider client has answered, so feeding it the client's parsed result
    keeps the derivation real without touching the network.
    """
    from src.domains.agents.tools.brave_tools import BraveSearchToolImpl
    from src.domains.agents.tools.calendar_tools import ListCalendarsTool
    from src.domains.agents.tools.hue_tools import (
        ActivateHueSceneTool,
        ControlHueLightTool,
        ControlHueRoomTool,
        ListHueLightsTool,
        ListHueRoomsTool,
        ListHueScenesTool,
    )
    from src.domains.agents.tools.labels_tools import (
        ApplyLabelsTool,
        CreateLabelTool,
        ListLabelsTool,
        RemoveLabelsTool,
        UpdateLabelTool,
    )
    from src.domains.agents.tools.perplexity_tools import PerplexityAskTool, PerplexitySearchTool
    from src.domains.agents.tools.places_tools import GetCurrentLocationTool
    from src.domains.agents.tools.tasks_tools import ListTaskListsTool
    from src.domains.agents.tools.weather_tools import (
        GetCurrentWeatherTool,
        GetHourlyForecastTool,
        GetWeatherForecastTool,
    )

    def _fmt(cls: Any, tool_name: str, operation: str, data: dict[str, Any]) -> UnifiedToolOutput:
        tool = cls(tool_name=tool_name, operation=operation)
        return tool.format_registry_response({"success": True, "data": data})

    return {
        "brave_search_tool": lambda: _fmt(
            BraveSearchToolImpl, "brave_search_tool", "search", dict(_BRAVE_DATA)
        ),
        "brave_news_tool": lambda: _fmt(
            BraveSearchToolImpl, "brave_news_tool", "news", {**_BRAVE_DATA, "endpoint": "news"}
        ),
        "perplexity_search_tool": lambda: _fmt(
            PerplexitySearchTool, "perplexity_search_tool", "search", dict(_PERPLEXITY_DATA)
        ),
        "perplexity_ask_tool": lambda: _fmt(
            PerplexityAskTool, "perplexity_ask_tool", "ask", dict(_PERPLEXITY_DATA)
        ),
        "list_hue_lights_tool": lambda: _fmt(
            ListHueLightsTool, "list_hue_lights_tool", "list", dict(_HUE_LIGHTS_DATA)
        ),
        "list_hue_rooms_tool": lambda: _fmt(
            ListHueRoomsTool, "list_hue_rooms_tool", "list", dict(_HUE_ROOMS_DATA)
        ),
        "list_hue_scenes_tool": lambda: _fmt(
            ListHueScenesTool, "list_hue_scenes_tool", "list", dict(_HUE_SCENES_DATA)
        ),
        "control_hue_light_tool": lambda: _fmt(
            ControlHueLightTool, "control_hue_light_tool", "control", dict(_HUE_CONTROL_DATA)
        ),
        "control_hue_room_tool": lambda: _fmt(
            ControlHueRoomTool, "control_hue_room_tool", "control", dict(_HUE_CONTROL_DATA)
        ),
        "activate_hue_scene_tool": lambda: _fmt(
            ActivateHueSceneTool, "activate_hue_scene_tool", "activate", dict(_HUE_CONTROL_DATA)
        ),
        "get_current_location_tool": lambda: GetCurrentLocationTool().format_registry_response(
            {"success": True, "data": dict(_LOCATION_DATA)}
        ),
        # Label/task mutations that act directly (no HITL draft in between), so
        # what they return IS what a `$steps` reference reads.
        "create_label_tool": lambda: CreateLabelTool().format_registry_response(
            dict(_LABEL_CREATED_RESULT)
        ),
        "update_label_tool": lambda: UpdateLabelTool().format_registry_response(
            dict(_LABEL_RENAMED_RESULT)
        ),
        "apply_labels_tool": lambda: ApplyLabelsTool().format_registry_response(
            dict(_LABELS_APPLIED_RESULT)
        ),
        "remove_labels_tool": lambda: RemoveLabelsTool().format_registry_response(
            dict(_LABELS_REMOVED_RESULT)
        ),
        "list_task_lists_tool": lambda: ListTaskListsTool().format_registry_response(
            dict(_TASK_LISTS_RESULT)
        ),
        "list_labels_tool": lambda: ListLabelsTool().format_registry_response(dict(_LABELS_RESULT)),
        "list_calendars_tool": lambda: ListCalendarsTool().format_registry_response(
            dict(_CALENDARS_RESULT)
        ),
        "get_current_weather_tool": lambda: _fmt(
            GetCurrentWeatherTool,
            "get_current_weather_tool",
            "current",
            {"location": dict(_PARIS), "weather": dict(_CURRENT_WEATHER)},
        ),
        "get_weather_forecast_tool": lambda: _fmt(
            GetWeatherForecastTool,
            "get_weather_forecast_tool",
            "forecast",
            {"location": dict(_PARIS), "daily": [dict(_DAILY_FORECAST), dict(_DAILY_FORECAST)]},
        ),
        "get_hourly_forecast_tool": lambda: _fmt(
            GetHourlyForecastTool,
            "get_hourly_forecast_tool",
            "hourly",
            {"location": dict(_PARIS), "hourly": [dict(_HOURLY_FORECAST), dict(_HOURLY_FORECAST)]},
        ),
    }


def _build(tool_name: str) -> UnifiedToolOutput:
    """Build the tool's real output from a raw provider payload."""
    builder = _Builder()
    builders = {
        "get_contacts_tool": lambda: builder.build_contacts_output(contacts=[dict(_PERSON)]),
        "get_emails_tool": lambda: builder.build_emails_output(emails=[dict(_MESSAGE)]),
        "get_events_tool": lambda: builder.build_events_output(events=[dict(_EVENT)]),
        "get_tasks_tool": lambda: builder.build_tasks_output(tasks=[dict(_TASK)]),
        "get_files_tool": lambda: builder.build_files_output(files=[dict(_FILE)]),
        "get_places_tool": lambda: builder.build_places_output(places=[dict(_PLACE)]),
        **_formatter_builders(),
    }
    return builders[tool_name]()


#: The read tools whose output shape this test can build without a provider.
#: Two families, both on the production path: those whose output comes from a
#: shared `ToolOutputMixin` builder, and those that format it themselves through
#: `format_registry_response` (fed here with the client's parsed result).
COVERED_TOOLS = (
    "get_contacts_tool",
    "get_emails_tool",
    "get_events_tool",
    "get_tasks_tool",
    "get_files_tool",
    "get_places_tool",
    "get_current_weather_tool",
    "get_weather_forecast_tool",
    "get_hourly_forecast_tool",
    "list_labels_tool",
    "list_calendars_tool",
    "brave_search_tool",
    "brave_news_tool",
    "perplexity_search_tool",
    "perplexity_ask_tool",
    "list_hue_lights_tool",
    "list_hue_rooms_tool",
    "list_hue_scenes_tool",
    "control_hue_light_tool",
    "control_hue_room_tool",
    "activate_hue_scene_tool",
    "get_current_location_tool",
    "create_label_tool",
    "update_label_tool",
    "apply_labels_tool",
    "remove_labels_tool",
    "list_task_lists_tool",
)

#: The subset of :data:`COVERED_TOOLS` whose result is a countable collection.
#: Weather reads return one observation, not a list of hits — they expose no
#: `count`, and demanding one would test a contract they never made.
COUNTABLE_TOOLS = (
    "get_contacts_tool",
    "get_emails_tool",
    "get_events_tool",
    "get_tasks_tool",
    "get_files_tool",
    "get_places_tool",
)


#: Strong coverage is a ratchet, like every other quality floor in this repo.
#: Without it, the cheapest way to silence a failing manifest is to delete its
#: name from COVERED_TOOLS — the tool then falls back to the WEAK check with no
#: alarm, and the catalogue starts lying again exactly where it was fixed.
_STRONG_COVERAGE_FLOOR = 27


def test_strong_coverage_never_shrinks() -> None:
    """Removing a tool from the strong check must be a deliberate, visible act."""
    assert len(COVERED_TOOLS) >= _STRONG_COVERAGE_FLOOR, (
        f"{_STRONG_COVERAGE_FLOOR - len(COVERED_TOOLS)} tool(s) left the strong "
        f"reference check. Add a builder rather than dropping the tool; if a tool "
        f"genuinely disappeared from the catalogue, lower the floor in the same "
        f"commit and say why."
    )
    assert len(set(COVERED_TOOLS)) == len(COVERED_TOOLS), "duplicate entry inflates the count"


@pytest.mark.parametrize("tool_name", COVERED_TOOLS)
class TestReferenceExamplesResolve:
    def test_every_reference_example_resolves(
        self, tool_name: str, manifests: dict[str, ToolManifest]
    ) -> None:
        """Each published path must resolve against the tool's real output."""
        completed = {"step_1": completed_step(_build(tool_name))}
        broken = unresolved_reference_examples(manifests[tool_name], completed)

        assert not broken, (
            f"{tool_name} publishes {len(broken)} reference_example(s) its output does not "
            f"produce: {broken}. The planner reads these paths as a contract and "
            f"nothing verifies them at runtime — a wrong one fails at execution, "
            f"after the plan is committed. Available top-level keys: "
            f"{sorted(completed['step_1'])}. Fix the manifest, or make the tool produce "
            f"the path (see the `subject`/`from` promotions in ToolOutputMixin)."
        )

    def test_every_declared_top_level_output_resolves(
        self, tool_name: str, manifests: dict[str, ToolManifest]
    ) -> None:
        """Top-level `outputs` entries are STRUCTURAL and must always resolve.

        Scoped to paths without ``[]`` on purpose. A per-item field
        (``places[].rating``, ``events[].attendees``) is absent whenever the
        provider held no value for THAT record — its absence proves nothing
        about the manifest, and asserting on it would only test the fixture.
        A top-level scalar (``total``, ``count``) does not depend on the data:
        either the execution exposes it for every call, or it never does.
        """
        completed = {"step_1": completed_step(_build(tool_name))}
        broken = unresolved_top_level_outputs(manifests[tool_name], completed)

        assert not broken, (
            f"{tool_name} declares {len(broken)} top-level output path(s) its execution "
            f"never produces: {broken}. Available top-level keys: "
            f"{sorted(completed['step_1'])}."
        )


@pytest.mark.parametrize("tool_name", COVERED_TOOLS)
class TestDeclaredTypesMatchProducedTypes:
    """A published TYPE is a contract too, not only a published path.

    A path can resolve and still lie: `places[].opening_hours` was declared
    `object` while the Places API hands back `weekdayDescriptions`, a list of
    per-day strings. The planner reads the type to decide what it may chain a
    value into — announcing a record where a list lives sends it to fail at
    execution, exactly like a wrong path does, but one step later.
    """

    def test_every_resolvable_output_has_its_declared_type(
        self, tool_name: str, manifests: dict[str, ToolManifest]
    ) -> None:
        completed = {"step_1": completed_step(_build(tool_name))}
        mismatches = type_mismatches(manifests[tool_name], completed)

        assert not mismatches, (
            f"{tool_name} declares output types its execution contradicts: {mismatches}. "
            f"The planner chains values on the strength of these types."
        )


class TestEmptyResultStillCountable:
    """A zero-result read must still expose its count.

    `contacts[0]` cannot resolve on an empty search — but `count` must, so a
    plan can branch on "nothing found" without the reference blowing up.
    """

    @pytest.mark.parametrize("tool_name", COUNTABLE_TOOLS)
    def test_count_resolves_on_empty_result(self, tool_name: str) -> None:
        builder = _Builder()
        empty = {
            "get_contacts_tool": lambda: builder.build_contacts_output(contacts=[]),
            "get_emails_tool": lambda: builder.build_emails_output(emails=[]),
            "get_events_tool": lambda: builder.build_events_output(events=[]),
            "get_tasks_tool": lambda: builder.build_tasks_output(tasks=[]),
            "get_files_tool": lambda: builder.build_files_output(files=[]),
            "get_places_tool": lambda: builder.build_places_output(places=[]),
        }[tool_name]()
        completed = {"step_1": completed_step(empty)}

        assert ReferenceResolver().resolve("$steps.step_1.count", completed, None) == 0


class TestEveryManifestIsInternallyConsistent:
    """The WHOLE catalogue, not the tools whose output can be built here.

    The tests above run the real pipeline, so they need a builder — which is why
    they cover the 27 manifests listed in `COVERED_TOOLS`. The remaining 32 that
    publish `reference_examples` are verified by this weaker check only.

    Still uncovered by the strong check, and why (see
    docs/plans/2026-08-02-dette-post-adr194.md for the full accounting):

    * 15 HITL-draft mutations (`send_email_tool`, `create_event_tool`, …). Their
      step output is a DRAFT, not the action's result — `parallel_executor`
      stores the draft in `completed_steps` and the real execution happens later
      in `response_node`. Whether their manifests should describe the draft or
      the effect is a product call, not a mechanical fix;
    * 17 tools with no `format_registry_response` seam (routes, reminders,
      wikipedia, web_search, telephony, peer, sub-agents). Covering them means a
      mocked client or extracting that seam — a refactor, not a test.

    Naming the gap is the point: silence would read as coverage.

    What CAN be checked without any provider is internal consistency: a
    published example must address something the manifest itself declares in
    `outputs`. It is weaker than resolving against a real payload, and it caught
    six real defects the day it was written — three Hue list tools publishing
    bare `name` / `is_on` / `brightness` / `children`, where the execution puts
    those fields INSIDE `hues[]` / `rooms[]` / `scenes[]` (and calls the last
    one `children_count`). A planner following them would have generated
    `$steps.step_1.name` and died exactly like the contacts case did.
    """

    def test_no_manifest_publishes_a_path_it_does_not_declare(
        self, manifests: dict[str, ToolManifest]
    ) -> None:
        offenders: list[str] = []
        for manifest in manifests.values():
            declared = {root_key(output.path) for output in manifest.outputs or []}
            # No declared outputs at all = nothing to contradict. Those tools
            # are covered by the resolution tests above or by nothing yet, which
            # is a different (documented) gap.
            if not declared or not manifest.reference_examples:
                continue
            for example in manifest.reference_examples:
                if root_key(example) not in declared:
                    offenders.append(f"{manifest.name}: {example!r} (declares {sorted(declared)})")

        assert not offenders, (
            "reference_examples addressing a key the manifest never declares — "
            "the planner is told to read a path that does not exist:\n  "
            + "\n  ".join(sorted(offenders))
        )
