"""Native action journal names the confirmed operation without copying its payload."""

import pytest

from src.core.config import settings
from src.core.i18n_effects import EFFECT_LABELS, render_effect_label
from src.domains.agents.application.operation_spec import OperationKind
from src.domains.agents.application.registry import APPLICATION_OPERATIONS
from src.domains.agents.effects.labels import build_effect_label

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("wrapped", [False, True])
def test_native_label_names_the_confirmation_and_excludes_private_context(wrapped):
    content = {
        "operation_id": "workboard_ticket.create",
        "title": "Create a workboard ticket",
        "intent": {"private_selection": "PRIVATE_CONTEXT", "request": {"title": "SECRET_BRIEF"}},
        "expected_digest": "PRIVATE_DIGEST",
    }
    label = build_effect_label(
        "draft:application_action", {"draft": {"content": content} if wrapped else content}
    )
    assert label == {
        "i18n_key": "effects.labels.draft.application_action_named",
        "values": {"target": "create ticket", "operation": content["operation_id"]},
    }
    for language in EFFECT_LABELS:
        assert "create ticket" in render_effect_label(label, language)
    assert "PRIVATE" not in str(label) and "SECRET" not in str(label)


@pytest.mark.parametrize(
    "content",
    [
        None,
        [],
        {},
        {"operation_id": "unknown", "title": "Forged"},
        {"operation_id": "workboard_ui.read", "title": "Read"},
        {"operation_id": "workboard_ticket.create", "title": {"secret": "hidden"}},
    ],
)
def test_legacy_or_invalid_content_keeps_the_generic_translated_label(content):
    label = build_effect_label("draft:application_action", {"draft": content})
    assert label == {"i18n_key": "effects.labels.draft.application_action", "values": {}}
    for language in EFFECT_LABELS:
        assert render_effect_label(label, language) == EFFECT_LABELS[language][label["i18n_key"]]


def test_native_label_applies_the_existing_runtime_bound(monkeypatch):
    monkeypatch.setattr(settings, "effect_label_value_max_chars", 8)
    label = build_effect_label(
        "draft:application_action",
        {"draft": {"operation_id": "workboard_ticket.create", "title": "word " * 100}},
    )
    assert len(label["values"]["target"]) <= 8
    assert label["values"]["target"].endswith("…")


def test_every_registered_mutation_automatically_has_a_named_label():
    actions = [spec for spec in APPLICATION_OPERATIONS.all() if spec.kind != OperationKind.READ]
    assert actions
    for spec in actions:
        label = build_effect_label(
            "draft:application_action",
            {"draft": {"operation_id": spec.operation_id, "title": "Public action"}},
        )
        assert label["values"]["operation"] == spec.operation_id
        assert all(label["i18n_key"] in table for table in EFFECT_LABELS.values())
