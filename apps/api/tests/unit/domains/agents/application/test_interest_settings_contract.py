"""Native settings inherit every source field while refusing coercion and identity injection."""

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.interest_settings_schemas import (
    InterestSettingField,
    InterestSettingsPatch,
)
from src.domains.agents.tools.application_interest_tools import update_lia_interest_settings_tool
from src.domains.interests.schemas import InterestSettingsResponse, InterestSettingsUpdate

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "invalid",
    [
        {},
        {"actor_id": "foreign"},
        {"interests_enabled": "false"},
        {"interests_enabled": 0},
        {"interests_enabled": None},
        {"interests_notify_start_hour": -1},
        {"interests_notify_end_hour": 24},
        {"interests_notify_min_per_day": 0},
        {"interests_notify_max_per_day": 11},
        {"interests_notify_min_per_day": "2"},
        {"interests_notify_start_hour": False},
    ],
)
def test_native_settings_refuse_ambiguous_or_coerced_changes(invalid: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        InterestSettingsPatch.model_validate(invalid)


def test_source_settings_additions_cannot_silently_miss_the_native_protocol() -> None:
    source = set(InterestSettingsUpdate.model_fields)
    assert (
        source
        == set(InterestSettingsResponse.model_fields)
        == set(InterestSettingsPatch.model_fields)
        == {field.value for field in InterestSettingField}
    )
    schema = InterestSettingsPatch.model_json_schema()
    assert set(schema["properties"]) == source and schema["minProperties"] == 1
    assert (
        "runtime"
        not in update_lia_interest_settings_tool.tool_call_schema.model_json_schema()["properties"]
    )
    for value in schema["properties"].values():
        assert "anyOf" not in value and "default" not in value


@pytest.mark.parametrize("language", ["en", "fr", "de", "es", "it", "zh-CN"])
def test_confirmation_labels_cover_every_source_setting(language: str) -> None:
    labels = get_draft_preview_labels(language)
    for field in InterestSettingsUpdate.model_fields:
        assert labels[f"application_field_{field}"]
