"""Renamed UI choices must update the packaged native-tool vocabulary in CI."""

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def test_packaged_setting_choices_equal_current_schemas_and_six_ui_locales():
    root = Path(__file__).resolve().parents[7]
    spec = importlib.util.spec_from_file_location(
        "setting_choice_generator", root / "scripts/application_setting_choices.py"
    )
    assert spec is not None and spec.loader is not None
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    assert generator.TARGET.read_text(encoding="utf-8") == generator.render()


def test_new_personalization_fields_require_confirmation_review():
    from src.domains.agents.application.confirmation_policy import (
        CONFIRMATION_FREE_FIELDS,
    )
    from src.domains.agents.application.preference_fields import PreferenceField

    assert CONFIRMATION_FREE_FIELDS["preferences.update"] == {
        field.value for field in PreferenceField if field.writable
    }


def test_every_static_native_setting_enum_has_an_authoritative_ui_vocabulary():
    from src.domains.agents.application.schemas import PreferencePatch
    from src.domains.agents.application.setting_choices import setting_choices
    from src.domains.auth.preference_commands import AssistantPreferencePatch

    def has_enum(node, definitions):
        if "enum" in node:
            return True
        if "$ref" in node:
            return has_enum(definitions[node["$ref"].split("/")[-1]], definitions)
        return any(has_enum(item, definitions) for item in node.get("anyOf", []))

    for model in (PreferencePatch, AssistantPreferencePatch):
        schema = model.model_json_schema()
        for field, prop in schema["properties"].items():
            if has_enum(prop, schema.get("$defs", {})):
                assert field in setting_choices(), f"Missing UI vocabulary for {field}"


@pytest.mark.parametrize("family", ["habit", "psyche", "journal", "interest", "heartbeat"])
def test_reversible_writer_publishes_committed_result_in_its_manifest(family):
    from importlib import import_module

    module = import_module(f"src.domains.agents.application.{family}_catalogue")
    name = (
        "HEARTBEAT_UPDATE_MANIFEST"
        if family == "heartbeat"
        else f"{family.upper()}_SETTINGS_MANIFEST"
    )
    manifest = getattr(module, name)
    assert "application_result" in {output.path for output in manifest.outputs}
