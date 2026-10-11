"""Live choice reads are bounded and cannot become probes or credential validation."""

from importlib import import_module

import pytest
from pydantic import ValidationError

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "payload",
    [
        {"section": "voices"},
        {"section": "probe"},
        {"section": "models", "api_key": "secret"},
        {"section": "models", "limit": 0},
        {"section": "models", "limit": True},
        {"section": "models", "offset": -1},
        {"section": "models", "cursor": "a" * 64 + ":1", "offset": 2},
        {"section": "models", "cursor": "a" * 64 + ":0"},
    ],
)
def test_options_read_refuses_unbounded_secret_probe_and_unselected_voice_requests(
    payload: dict[str, object],
) -> None:
    schema = import_module("src.domains.agents.application.live_options_schemas")
    with pytest.raises(ValidationError):
        schema.LiveOptionsRead.model_validate(payload)


def test_model_schema_also_requires_a_provider_for_voices() -> None:
    from jsonschema import Draft202012Validator

    schema = import_module("src.domains.agents.application.live_options_schemas")
    validator = Draft202012Validator(schema.LiveOptionsRead.model_json_schema())
    assert not validator.is_valid({"section": "voices"})
    assert not validator.is_valid({"section": "voices", "provider": None})
    assert validator.is_valid({"section": "models"})
    assert validator.is_valid({"section": "voices", "provider": "gemini"})
    assert not validator.is_valid({"section": "models", "cursor": "a" * 64 + ":1", "offset": 2})
