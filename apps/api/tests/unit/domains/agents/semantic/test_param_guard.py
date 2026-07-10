"""Runtime semantic parameter guard (C3a) — unit tests.

The guard blocks tool calls that pass a person name resolved for the current
turn on a parameter whose manifest declares an address/email semantic type,
BEFORE the paid API call. Fail-open everywhere else.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.core.field_names import FIELD_RESOLVED_PERSON_NAMES
from src.domains.agents.registry.agent_registry import ToolManifestNotFound
from src.domains.agents.semantic.param_guard import (
    SemanticParamViolation,
    check_semantic_params,
    collect_resolved_person_names,
    config_with_person_names,
    person_names_from_config,
)

PERSON = "Alexandre Gouvier"
NAMES = frozenset({"alexandre gouvier"})


def _manifest(params: list[tuple[str, str | None]]) -> SimpleNamespace:
    """Build a fake tool manifest with (name, semantic_type) parameters."""
    return SimpleNamespace(
        parameters=[
            SimpleNamespace(name=name, semantic_type=semantic_type)
            for name, semantic_type in params
        ]
    )


def _registry_with(manifest: SimpleNamespace) -> MagicMock:
    registry = MagicMock()
    registry.get_tool_manifest = MagicMock(return_value=manifest)
    return registry


# =============================================================================
# collect_resolved_person_names
# =============================================================================


class TestCollectResolvedPersonNames:
    def test_normalizes_case_and_whitespace(self):
        names = collect_resolved_person_names({"mon frère": "  Alexandre   GOUVIER "})
        assert names == {"alexandre gouvier"}

    def test_empty_inputs(self):
        assert collect_resolved_person_names(None) == frozenset()
        assert collect_resolved_person_names({}) == frozenset()

    def test_ignores_non_string_and_blank_values(self):
        names = collect_resolved_person_names({"a": 42, "b": "", "c": "  ", "d": "Jean"})
        assert names == {"jean"}


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
            violation = check_semantic_params(
                "send_email_tool", {"to": "  alexandre   gouvier "}, NAMES
            )
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
        state = {"resolved_references": {"mon frère": PERSON}}

        enriched = config_with_person_names(config, state)

        assert enriched["configurable"]["langgraph_user_id"] == "u1"
        assert enriched["configurable"][FIELD_RESOLVED_PERSON_NAMES] == ["alexandre gouvier"]
        assert person_names_from_config(enriched) == NAMES

    def test_returns_same_config_when_nothing_to_guard(self):
        config = {"configurable": {}}
        assert config_with_person_names(config, {}) is config
        assert person_names_from_config(config) == frozenset()

    def test_original_config_not_mutated(self):
        config = {"configurable": {"k": "v"}}
        state = {"resolved_references": {"ma femme": "Corinne"}}
        config_with_person_names(config, state)
        assert FIELD_RESOLVED_PERSON_NAMES not in config["configurable"]
