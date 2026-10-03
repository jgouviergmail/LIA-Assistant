"""Exercise missing card families through the actual response registry boundary."""

import pytest

from src.domains.agents.data_registry.models import RegistryItem, RegistryItemMeta, RegistryItemType
from src.domains.agents.nodes.response_node import generate_html_for_registry

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("language", ["en", "fr", "de", "es", "it", "zh-CN"])
@pytest.mark.parametrize(
    ("kind", "payload", "needles"),
    [
        (
            RegistryItemType.HUE_LIGHT,
            {"name": "Desk lamp", "is_on": True, "brightness": 0, "room": "opaque-room-id"},
            ["Desk lamp", "0%"],
        ),
        (
            RegistryItemType.TICKET,
            {
                "title": "A real ticket",
                "status": "waiting",
                "priority": "urgent",
                "assignee_kind": "human",
                "start_at": "2026-10-03T08:00:00Z",
                "due_at": "2026-10-05T18:00:00Z",
            },
            ["A real ticket", "2026"],
        ),
    ],
    ids=["hue", "ticket"],
)
def test_registry_facts_reach_cards(language, kind, payload, needles):
    item = RegistryItem(
        id="reference",
        type=kind,
        payload=payload,
        meta=RegistryItemMeta(source="fixture"),
    )
    markup = generate_html_for_registry({item.id: item}, user_language=language)
    assert 'data-card-version="2"' in markup
    for value in needles:
        assert value in markup
    assert "opaque-room-id" not in markup
    assert "<script>" not in markup
    assert "data-action=" not in markup


def test_new_cards_preserve_mixed_domain_answer():
    registry = {
        "light": {"type": "HUE_LIGHT", "payload": {"name": "LIGHT", "is_on": False}},
        "task": {"type": "TASK", "payload": {"title": "TASK"}},
        "ticket": {"type": "TICKET", "payload": {"title": "TICKET"}},
        "document": {
            "type": "NOTE",
            "payload": {
                "title": "DOCUMENT",
                "content": "EXCERPT",
                "evidence_scope": "document_excerpt",
            },
        },
    }
    markup = generate_html_for_registry(registry)
    for text in ("LIGHT", "TASK", "TICKET"):
        assert text in markup
    assert "EXCERPT" not in markup


def test_note_with_no_declared_excerpt_is_not_a_document():
    markup = generate_html_for_registry(
        {
            "note": {
                "type": "NOTE",
                "payload": {"title": "TECHNICAL_NOTE", "content": "PRIVATE_CONTEXT"},
            }
        }
    )
    assert "PRIVATE_CONTEXT" not in markup


@pytest.mark.parametrize("brightness", [False, float("nan"), -1, 101, {"secret": "raw"}])
def test_invalid_brightness_draws_no_false_measurement(brightness):
    markup = generate_html_for_registry(
        {"hue": {"type": "HUE_LIGHT", "payload": {"name": "LAMP", "brightness": brightness}}}
    )
    assert "LAMP" in markup
    assert "%" not in markup
    assert "secret" not in markup


def test_every_registry_type_has_an_explicit_presentation_decision():
    from src.domains.agents.data_registry.models import INTERACTIVE_WIDGET_TYPES
    from src.domains.agents.display.component_registry import PRESENTATIONS, build_components
    from src.domains.agents.tools.output import REGISTRY_TYPE_TO_KEY
    from src.domains.agents.utils.type_domain_mapping import get_result_key_from_type

    assert set(PRESENTATIONS) == set(RegistryItemType)
    assert {kind for kind, spec in PRESENTATIONS.items() if spec.mode == "widget"} == set(
        INTERACTIVE_WIDGET_TYPES
    )
    components, keys = build_components()
    for kind, spec in PRESENTATIONS.items():
        canonical = REGISTRY_TYPE_TO_KEY[kind]
        if spec.mode == "card":
            assert spec.component is not None
        if spec.mode in ("inline", "inactive"):
            assert spec.component is None
        if spec.component is not None:
            assert get_result_key_from_type(kind.value) == canonical
            assert isinstance(components[canonical], spec.component)
            assert canonical in keys[canonical]
            for alias in spec.aliases:
                assert components[alias] is components[canonical]
        else:
            assert spec.reason
            assert canonical not in components


@pytest.mark.parametrize("kind", [RegistryItemType.WEB_PAGE, RegistryItemType.BROWSER_PAGE])
def test_model_evidence_is_not_dumped_into_a_duplicate_card(kind):
    item = {
        "type": kind,
        "payload": {
            "title": "Source",
            "content_summary": "RAW_ACCESSIBILITY_TREE",
            "content": "RAW_PAGE",
        },
    }
    markup = generate_html_for_registry({"source": item})
    assert "RAW_ACCESSIBILITY_TREE" not in markup
    assert "RAW_PAGE" not in markup


@pytest.mark.parametrize("state", [True, False, None])
def test_hue_formatter_preserves_known_and_unknown_state(state):
    from src.domains.agents.tools.hue_tools import ListHueLightsTool

    tool = ListHueLightsTool(tool_name="list_hue_lights", operation="list_lights")
    light = {"id": "light-id", "metadata": {"name": "Desk"}}
    if state is not None:
        light["on"] = {"on": state}
    output = tool.format_registry_response({"success": True, "data": {"lights": [light]}})
    assert output.registry_updates["light-id"].payload["is_on"] is state


@pytest.mark.parametrize("language", ["en", "fr", "de", "es", "it", "zh-CN"])
def test_all_workboard_columns_have_localized_labels(language):
    from src.domains.agents.display.ticket_labels import _LABELS, ticket_status_label
    from src.domains.workboard.constants import TicketStatus

    assert set(_LABELS) == set(TicketStatus)
    for status in TicketStatus:
        assert ticket_status_label(status, language).strip()
