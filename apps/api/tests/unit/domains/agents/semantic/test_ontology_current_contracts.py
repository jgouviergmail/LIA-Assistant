"""Pin the ontology's current data contracts, without synthetic type coercion."""

import pytest

from src.domains.agents.semantic.core_types import load_core_types
from src.domains.agents.semantic.type_registry import TypeRegistry

pytestmark = pytest.mark.unit


@pytest.fixture
def ontology() -> TypeRegistry:
    registry = TypeRegistry()
    load_core_types(registry)
    return registry


def test_complete_ontology_is_consistent_and_idempotent(ontology: TypeRegistry) -> None:
    before = ontology.get_stats()
    load_core_types(ontology)
    assert ontology.get_stats() == before
    assert ontology.validate_hierarchy() == []
    assert ontology.get_stats()["hierarchy_nodes"] == len(ontology)


@pytest.mark.parametrize(
    ("entity", "ranges"),
    [
        ("Contact", {"contact_id", "email_address", "organization_name", "birthday"}),
        ("Place", {"place_id", "physical_address", "coordinate", "website_url"}),
        ("CalendarEvent", {"event_id", "calendar_id", "datetime", "conference_link"}),
        ("EmailMessage", {"message_id", "email_address", "email_label_id", "attachment_info"}),
    ],
)
def test_evidence_entities_declare_current_payload_values(
    ontology: TypeRegistry, entity: str, ranges: set[str]
) -> None:
    definition = ontology.get(entity)
    assert definition is not None
    assert ranges <= set(definition.properties.values())


def test_dates_and_units_do_not_claim_incompatible_parent_types(ontology: TypeRegistry) -> None:
    birthday = ontology.get("birthday")
    assert birthday is not None and birthday.parent == "Date"
    for value_type in ("Date", "unix_timestamp", "duration_minutes"):
        definition = ontology.get(value_type)
        assert definition is not None and definition.parent == "Intangible"


def test_provider_handles_are_distinct_from_names_and_other_resources(
    ontology: TypeRegistry,
) -> None:
    for type_name in ("email_label_id", "email_attachment_id", "ticket_id"):
        definition = ontology.get(type_name)
        assert definition is not None and definition.parent == "Identifier"
    assert ontology.get("email_label").parent == "Text"
    assert ontology.get("file_name").parent == "Text"
    assert ontology.get("email_address").parent == "ContactPoint"
    assert ontology.get("contact_id").parent == "Identifier"


@pytest.mark.parametrize(
    "type_name",
    [
        "memory_category",
        "health_metric_kind",
        "journal_entry_kind",
        "identity_confidence",
        "effect_status",
    ],
)
def test_current_closed_vocabularies_have_distinct_semantic_types(
    ontology: TypeRegistry, type_name: str
) -> None:
    definition = ontology.get(type_name)
    assert definition is not None and definition.parent == "Enumeration"
    assert definition.source_domains
    assert not definition.related_types


def test_localized_price_label_is_not_a_numeric_value_or_filter_code(
    ontology: TypeRegistry,
) -> None:
    definition = ontology.get("price_level")
    assert definition is not None and definition.parent == "Text"
    assert definition.category.value == "content"


def test_coordinate_components_do_not_claim_to_be_whole_pairs(ontology: TypeRegistry) -> None:
    for type_name in ("latitude", "longitude"):
        definition = ontology.get(type_name)
        assert definition is not None and definition.parent == "QuantitativeValue"
        assert definition.category.value == "location"
    for type_name in ("GeoCoordinates", "coordinate"):
        definition = ontology.get(type_name)
        assert definition is not None
        assert definition.properties == {"latitude": "latitude", "longitude": "longitude"}
