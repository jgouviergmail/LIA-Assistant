"""Runtime semantic parameter guard (C3a) — unit tests.

The guard blocks tool calls that pass a person name resolved for the current
turn on a parameter whose manifest declares an address/email semantic type,
BEFORE the paid API call. Fail-open everywhere else.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.core.field_names import FIELD_RESOLVED_PERSON_NAMES
from src.domains.agents.analysis.resolved_references import (
    ReferenceSource,
    ReferenceValueKind,
    ResolvedReferenceEntry,
)
from src.domains.agents.registry.agent_registry import ToolManifestNotFound
from src.domains.agents.registry.catalogue import (
    CostProfile,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)
from src.domains.agents.semantic.param_guard import (
    SemanticParamViolation,
    check_semantic_params,
    collect_resolved_person_names,
    config_with_person_names,
    person_names_from_config,
    request_from_config,
    strip_placeholder_arguments,
    turn_person_names,
    turn_request,
)

PERSON = "Marc Lemoine"
NAMES = frozenset({"marc lemoine"})


def _state(*entries: ResolvedReferenceEntry) -> dict[str, object]:
    return {"query_intelligence": {"resolved_references": [e.to_dict() for e in entries]}}


NAME = ResolvedReferenceEntry(
    "mon frère", PERSON, ReferenceValueKind.PERSON_NAME, ReferenceSource.MEMORY
)
CITY = ResolvedReferenceEntry(
    "montbéliard", "Montbéliard", ReferenceValueKind.OTHER, ReferenceSource.ANALYZER
)
DATES = ResolvedReferenceEntry(
    "les 5 prochains jours",
    "2026-10-11 to 2026-10-15",
    ReferenceValueKind.DATETIME,
    ReferenceSource.ANALYZER,
)
ADDRESS = ResolvedReferenceEntry(
    "chez mon frère",
    "12 rue des Lilas, Lyon",
    ReferenceValueKind.POSTAL_ADDRESS,
    ReferenceSource.MEMORY,
)


def _manifest(
    params: list[tuple[str, str | None]],
    required: frozenset[str] = frozenset(),
) -> ToolManifest:
    """Build a fake tool manifest with (name, semantic_type) parameters."""
    return ToolManifest(
        name="get_route_tool",
        agent="route_agent",
        description="Read-only guard fixture",
        parameters=[
            ParameterSchema(
                name=name,
                type="string",
                description="Typed value",
                semantic_type=semantic_type,
                required=name in required,
            )
            for name, semantic_type in params
        ],
        outputs=[],
        cost=CostProfile(),
        permissions=PermissionProfile(),
        mutation_policy="read",
    )


def _registry_with(manifest: ToolManifest) -> MagicMock:
    registry = MagicMock()
    registry.get_tool_manifest = MagicMock(return_value=manifest)
    return registry


# =============================================================================
# collect_resolved_person_names
# =============================================================================


class TestCollectResolvedPersonNames:
    def test_normalizes_case_and_whitespace(self):
        entry = ResolvedReferenceEntry(
            "mon frère", "  Marc   LEMOINE ", ReferenceValueKind.PERSON_NAME, ReferenceSource.MEMORY
        )
        assert collect_resolved_person_names((entry,)) == {"marc lemoine"}

    def test_empty_inputs(self):
        assert collect_resolved_person_names(()) == frozenset()

    def test_only_declared_person_names_count(self):
        assert collect_resolved_person_names((NAME, CITY, DATES, ADDRESS)) == NAMES


class TestTurnPersonNames:
    def test_only_person_names_are_collected(self) -> None:
        assert turn_person_names(_state(NAME, CITY, DATES, ADDRESS)) == NAMES

    def test_a_later_turn_never_guards_on_the_previous_turns_values(self) -> None:
        stale = {
            "query_intelligence": {"resolved_references": None},
            "resolved_references": {"montbéliard": "Montbéliard"},
        }
        assert turn_person_names(stale) == frozenset()

    def test_a_legacy_checkpoint_is_never_guarded(self) -> None:
        legacy = {"query_intelligence": {"resolved_references": {"mon frère": PERSON}}}
        assert turn_person_names(legacy) == frozenset()


class TestIncident20261011:
    """The places search on the city the person asked about is not blocked."""

    def test_city_reference_does_not_block_places(self) -> None:
        with patch(
            "src.domains.agents.semantic.param_guard.available_manifest",
            return_value=_manifest([("location", "physical_address")]),
        ):
            assert (
                check_semantic_params(
                    "get_places_tool",
                    {"location": "Montbéliard"},
                    turn_person_names(_state(CITY, DATES)),
                )
                is None
            )

    def test_memory_address_does_not_block_its_route(self) -> None:
        with patch(
            "src.domains.agents.semantic.param_guard.available_manifest",
            return_value=_manifest([("destination", "physical_address")]),
        ):
            assert (
                check_semantic_params(
                    "get_route_tool",
                    {"destination": "12 rue des Lilas, Lyon"},
                    turn_person_names(_state(ADDRESS)),
                )
                is None
            )

    def test_a_person_name_is_still_blocked(self) -> None:
        with patch(
            "src.domains.agents.semantic.param_guard.available_manifest",
            return_value=_manifest([("destination", "physical_address")]),
        ):
            assert (
                check_semantic_params(
                    "get_route_tool", {"destination": PERSON}, turn_person_names(_state(NAME))
                )
                is not None
            )

    def test_homonym_place_is_not_blocked(self) -> None:
        sister = ResolvedReferenceEntry(
            "ma sœur", "Florence", ReferenceValueKind.PERSON_NAME, ReferenceSource.MEMORY
        )
        there = ResolvedReferenceEntry(
            "là-bas", "Florence", ReferenceValueKind.PLACE, ReferenceSource.ANALYZER
        )
        with patch(
            "src.domains.agents.semantic.param_guard.available_manifest",
            return_value=_manifest([("location", "locality")]),
        ):
            assert (
                check_semantic_params(
                    "get_weather_forecast_tool",
                    {"location": "Florence"},
                    turn_person_names(_state(sister, there)),
                )
                is None
            )


# =============================================================================
# check_semantic_params
# =============================================================================


class TestCheckSemanticParams:
    def test_blocks_person_name_on_physical_address_param(self):
        manifest = _manifest([("destination", "physical_address"), ("origin", None)])
        with patch(
            "src.domains.agents.registry.get_global_registry",
            return_value=_registry_with(manifest),
        ):
            violation = check_semantic_params("get_route_tool", {"destination": PERSON}, NAMES)

        assert isinstance(violation, SemanticParamViolation)
        assert violation.param_name == "destination"
        assert violation.semantic_type == "physical_address"
        # The recoverable message guides the LLM towards contacts.
        assert "contacts" in violation.llm_message()

    def test_match_is_case_and_whitespace_insensitive(self):
        manifest = _manifest([("to", "email_address")])
        with patch(
            "src.domains.agents.registry.get_global_registry",
            return_value=_registry_with(manifest),
        ):
            violation = check_semantic_params("send_email_tool", {"to": "  marc   lemoine "}, NAMES)
        assert violation is not None
        assert violation.semantic_type == "email_address"

    def test_blocks_person_name_inside_list_param(self):
        manifest = _manifest([("waypoints", "physical_address")])
        with patch(
            "src.domains.agents.registry.get_global_registry",
            return_value=_registry_with(manifest),
        ):
            violation = check_semantic_params(
                "get_route_tool", {"waypoints": ["10 rue de la Paix", PERSON]}, NAMES
            )
        assert violation is not None
        assert violation.value == PERSON

    def test_non_guarded_semantic_type_passes(self):
        # person_name params legitimately receive person names (create_contact).
        manifest = _manifest([("name", "person_name")])
        with patch(
            "src.domains.agents.registry.get_global_registry",
            return_value=_registry_with(manifest),
        ):
            assert check_semantic_params("create_contact_tool", {"name": PERSON}, NAMES) is None

    def test_real_address_value_passes(self):
        manifest = _manifest([("destination", "physical_address")])
        with patch(
            "src.domains.agents.registry.get_global_registry",
            return_value=_registry_with(manifest),
        ):
            assert (
                check_semantic_params(
                    "get_route_tool", {"destination": "10 rue de la Paix, Paris"}, NAMES
                )
                is None
            )

    def test_no_names_short_circuits_without_registry(self):
        # Must not even try to resolve the manifest.
        assert check_semantic_params("get_route_tool", {"destination": PERSON}, frozenset()) is None

    def test_missing_manifest_fails_open(self):
        registry = MagicMock()
        registry.get_tool_manifest = MagicMock(side_effect=ToolManifestNotFound("nope"))
        with patch(
            "src.domains.agents.registry.get_global_registry",
            return_value=registry,
        ):
            assert check_semantic_params("unknown_tool", {"destination": PERSON}, NAMES) is None

    def test_registry_error_fails_open(self):
        with patch(
            "src.domains.agents.registry.get_global_registry",
            side_effect=RuntimeError("registry down"),
        ):
            assert check_semantic_params("get_route_tool", {"destination": PERSON}, NAMES) is None


# =============================================================================
# Config plumbing (state → configurable → executor)
# =============================================================================


class TestConfigPlumbing:
    def test_round_trip_through_configurable(self):
        config = {"configurable": {"langgraph_user_id": "u1"}}
        state = _state(NAME, CITY)

        enriched = config_with_person_names(config, state)

        assert enriched["configurable"]["langgraph_user_id"] == "u1"
        assert enriched["configurable"][FIELD_RESOLVED_PERSON_NAMES] == ["marc lemoine"]
        assert person_names_from_config(enriched) == NAMES

    def test_returns_same_config_when_nothing_to_guard(self):
        config = {"configurable": {}}
        assert config_with_person_names(config, {}) is config
        assert config_with_person_names(config, _state(CITY, DATES)) is config
        assert person_names_from_config(config) == frozenset()

    def test_original_config_not_mutated(self):
        config = {"configurable": {"k": "v"}}
        state = _state(
            ResolvedReferenceEntry(
                "ma femme", "Corinne", ReferenceValueKind.PERSON_NAME, ReferenceSource.MEMORY
            )
        )
        config_with_person_names(config, state)
        assert FIELD_RESOLVED_PERSON_NAMES not in config["configurable"]

    def test_the_turn_request_travels_for_the_value_kind_judgment(self):
        state = {"query_intelligence": {"original_query": "Restaurants à Montbéliard"}}
        enriched = config_with_person_names({"configurable": {}}, state)
        assert request_from_config(enriched) == "Restaurants à Montbéliard"
        assert FIELD_RESOLVED_PERSON_NAMES not in enriched["configurable"]

    @pytest.mark.parametrize("query", [None, "", "   ", 42])
    def test_a_turn_without_words_carries_no_request(self, query: object):
        state = {"query_intelligence": {"original_query": query}}
        assert turn_request(state) is None
        assert request_from_config(config_with_person_names({"configurable": {}}, state)) is None


class TestViolationMessage:
    def test_a_resolved_name_keeps_its_contacts_hint(self):
        message = SemanticParamViolation("t", "p", "email_address", "Ana").llm_message()
        assert "person's name" in message and "contacts" in message
        assert "expects an email address" in message

    @pytest.mark.parametrize(
        ("kind", "words"),
        [("phone_number", "a phone number"), ("datetime", "a date or a time"), ("x", "another")],
    )
    def test_a_judged_kind_is_named(self, kind: str, words: str):
        message = SemanticParamViolation("t", "p", "locality", "v", kind).llm_message()
        assert words in message and "person's name" not in message


# =============================================================================
# strip_placeholder_arguments
# =============================================================================


class TestStripPlaceholderArguments:
    """A JSON-emitting planner writes "null" when it means "not provided".

    Prod 2026-07-23: `location="null"` reached get_weather_forecast_tool, sailed
    past its `if not location` guard, was geocoded as a city name and produced
    the forecast for Cappaghnanool, IE. Dropping the argument restores the
    intended fallback (auto-geolocation).
    """

    LOC = [("location", "physical_address"), ("date", "event_start_datetime")]

    def _run(self, args: dict, manifest: ToolManifest | None = None) -> dict:
        manifest = manifest or _manifest(self.LOC)
        with patch(
            "src.domains.agents.registry.get_global_registry",
            return_value=_registry_with(manifest),
        ):
            return strip_placeholder_arguments("get_weather_forecast_tool", args)

    def test_drops_the_placeholder_and_keeps_the_rest(self):
        cleaned = self._run({"location": "null", "date": "2026-07-25"})
        assert "location" not in cleaned
        assert cleaned["date"] == "2026-07-25"

    @pytest.mark.parametrize("value", ["null", "None", " NULL ", "undefined", "n/a", "nil"])
    def test_covers_the_usual_stand_ins(self, value: str):
        assert "location" not in self._run({"location": value})

    @pytest.mark.parametrize("value", ["Nullarbor", "Nonancourt", "None-sur-Mer", "Nanterre"])
    def test_real_place_names_survive(self, value: str):
        """Exact match only — a substring must never trigger."""
        assert self._run({"location": value})["location"] == value

    def test_required_parameter_is_kept_so_the_bug_fails_loudly(self):
        """A required slot holding "null" is a planning bug, not an omission."""
        manifest = _manifest(self.LOC, required=frozenset({"location"}))
        assert self._run({"location": "null"}, manifest)["location"] == "null"

    def test_untyped_parameter_is_kept(self):
        """Free text (a search query) must never be second-guessed."""
        manifest = _manifest([("query", None)])
        assert self._run({"query": "none"}, manifest)["query"] == "none"

    def test_non_string_values_are_untouched(self):
        manifest = _manifest([("location", "physical_address")])
        assert self._run({"location": 0}, manifest)["location"] == 0

    def test_unknown_tool_fails_open(self):
        registry = MagicMock()
        registry.get_tool_manifest = MagicMock(side_effect=ToolManifestNotFound("nope"))
        with patch("src.domains.agents.registry.get_global_registry", return_value=registry):
            args = {"location": "null"}
            assert strip_placeholder_arguments("some_future_tool", args) == args

    def test_registry_error_fails_open(self):
        with patch(
            "src.domains.agents.registry.get_global_registry",
            side_effect=RuntimeError("registry down"),
        ):
            args = {"location": "null"}
            assert strip_placeholder_arguments("get_weather_forecast_tool", args) == args

    def test_caller_dict_is_not_mutated(self):
        args = {"location": "null"}
        cleaned = self._run(args)
        assert args == {"location": "null"}
        assert cleaned is not args

    def test_empty_args(self):
        assert strip_placeholder_arguments("get_weather_forecast_tool", {}) == {}
