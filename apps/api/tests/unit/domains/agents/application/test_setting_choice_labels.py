"""Displayed options and accepted names must share the UI's actual vocabulary."""

import pytest

from src.domains.agents.application.schemas import PreferencePatch

pytestmark = pytest.mark.unit


def test_canonical_transport_value_stays_valid_when_a_visible_label_collides(
    monkeypatch,
):
    from src.domains.agents.application import setting_choices as vocabulary

    monkeypatch.setattr(
        vocabulary,
        "setting_choices",
        lambda: {"color_theme": {"en": {"default": "Blue", "forest": "default"}}},
    )
    assert vocabulary.normalize_setting_value("color_theme", "default") == "default"
    assert vocabulary.normalize_setting_value("color_theme", "Blue") == "default"


@pytest.mark.parametrize("label", ["Sage", "Sauge", "  SAUGE  ", "forest"])
def test_displayed_theme_names_resolve_to_the_same_persisted_value(label: str):
    assert PreferencePatch(color_theme=label).color_theme == "forest"


def test_unknown_theme_is_refused_without_inventing_a_mapping():
    with pytest.raises(ValueError):
        PreferencePatch(color_theme="oceanic moon")


def test_assistant_choices_share_labels_without_changing_the_http_contract():
    from src.domains.agents.application.assistant_schemas import (
        AssistantPreferenceChange,
    )
    from src.domains.agents.application.setting_choices import setting_choices
    from src.domains.auth.preference_commands import AssistantPreferencePatch

    assert (
        AssistantPreferenceChange.model_json_schema()
        == AssistantPreferencePatch.model_json_schema()
    )
    for field in ("execution_mode", "voice_stt_mode", "response_display_mode"):
        for labels in setting_choices()[field].values():
            for value, label in labels.items():
                assert (
                    getattr(AssistantPreferenceChange.model_validate({field: label}), field)
                    == value
                )


def test_french_choice_projection_preserves_ids_and_uses_the_interface_labels():
    from src.domains.agents.application.setting_choices import describe_setting_values

    projection = describe_setting_values({"color_theme": "forest", "theme": "system"}, "fr")
    assert projection["color_theme"]["label"] == "Sauge"
    assert projection["color_theme"]["options"] == [
        {"value": "default", "label": "Bleu Professionnel"},
        {"value": "ocean", "label": "Turquoise"},
        {"value": "forest", "label": "Sauge"},
        {"value": "sunset", "label": "Rose"},
        {"value": "slate", "label": "Lavande"},
    ]
    assert projection["theme"]["label"] == "Système"


def test_generic_settings_read_keeps_original_values_and_localizes_boolean_state():
    from src.domains.agents.application.setting_choices import with_read_setting_labels
    from src.domains.agents.tools.output import UnifiedToolOutput
    from tests.helpers.runtime_context import installed_runtime_context

    source = UnifiedToolOutput.data_success(
        message="Observed",
        structured_data={"settings": {"habits_enabled": False, "count": 1}},
    )
    with installed_runtime_context(language="fr"):
        enriched = with_read_setting_labels(source)
    assert enriched.structured_data["settings"] == source.structured_data["settings"]
    assert enriched.structured_data["setting_choices"]["habits_enabled"]["label"] == "Non"
    assert "count" not in enriched.structured_data["setting_choices"]
    assert "setting_choices" not in source.structured_data


def test_display_enrichment_does_not_break_non_json_legacy_settings():
    from src.domains.agents.application.setting_choices import with_read_setting_labels
    from src.domains.agents.tools.output import UnifiedToolOutput

    source = UnifiedToolOutput.data_success(
        message="Legacy", structured_data={"settings": {"legacy": object()}}
    )
    assert with_read_setting_labels(source) is source


def test_a_same_named_field_from_another_domain_cannot_borrow_account_options():
    from src.domains.agents.application.setting_choices import with_read_setting_labels
    from src.domains.agents.tools.output import UnifiedToolOutput

    source = UnifiedToolOutput.data_success(
        message="Meeting preferences",
        structured_data={"settings": {"language": "auto", "count": 1}},
    )
    enriched = with_read_setting_labels(source, tool_name="get_lia_meeting_preferences_tool")
    assert "setting_choices" not in enriched.structured_data


def test_registered_account_read_keeps_its_own_authoritative_static_choices():
    from src.domains.agents.application.setting_choices import with_read_setting_labels
    from src.domains.agents.tools.output import UnifiedToolOutput
    from tests.helpers.runtime_context import installed_runtime_context

    source = UnifiedToolOutput.data_success(
        message="Account preferences",
        structured_data={"preferences": {"values": {"color_theme": "forest"}}},
    )
    with installed_runtime_context(language="fr"):
        enriched = with_read_setting_labels(source, tool_name="get_lia_preferences_tool")
    assert enriched.structured_data["setting_choices"]["color_theme"]["label"] == "Sauge"


@pytest.mark.parametrize(("declared", "expected"), [(None, "Nein"), ("fr", "Non")])
def test_unbound_read_uses_the_declared_or_instance_language(monkeypatch, declared, expected):
    from src.core.config import settings
    from src.core.i18n import language_scope
    from src.domains.agents.application.setting_choices import with_read_setting_labels
    from src.domains.agents.tools.output import UnifiedToolOutput

    monkeypatch.setattr(settings, "default_language", "de")
    source = UnifiedToolOutput.data_success(
        message="Settings", structured_data={"settings": {"habits_enabled": False}}
    )
    with language_scope(declared):
        result = with_read_setting_labels(source)
    assert result.structured_data["setting_choices"]["habits_enabled"]["label"] == expected


def test_chinese_variants_use_the_actual_chinese_ui_labels():
    from src.domains.agents.application.setting_choices import (
        describe_setting_values,
        setting_choices,
    )

    expected = setting_choices()["color_theme"]["zh-CN"]["forest"]
    result = describe_setting_values({"color_theme": "forest"}, "ZH_tw")
    assert result["color_theme"]["label"] == expected
