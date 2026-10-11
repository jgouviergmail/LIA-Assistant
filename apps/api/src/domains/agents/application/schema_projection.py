"""Publish the same nullability and choice authority the application enforces."""

from pydantic.json_schema import JsonSchemaValue

from src.core.config import settings
from src.domains.agents.application.preference_fields import PREFERENCE_FIELDS
from src.domains.shared.schemas import VALID_COLOR_THEMES, VALID_FONT_FAMILIES, VALID_THEMES
from src.domains.users.models import User

NON_NULL_PREFERENCE_FIELDS = frozenset(
    name for name in PREFERENCE_FIELDS if not User.__table__.columns[name].nullable
)

_CHOICES = {
    "language": tuple(settings.supported_languages),
    "theme": VALID_THEMES,
    "color_theme": VALID_COLOR_THEMES,
    "font_family": VALID_FONT_FAMILIES,
}


def patch_property_schema(name: str, value: JsonSchemaValue) -> JsonSchemaValue:
    result = dict(value)
    if name in NON_NULL_PREFERENCE_FIELDS:
        alternatives = [item for item in result.pop("anyOf", []) if item.get("type") != "null"]
        if len(alternatives) == 1:
            result.update(alternatives[0])
        elif alternatives:
            result["anyOf"] = alternatives
        if result.get("default") is None:
            result.pop("default", None)
    if name in _CHOICES:
        result["enum"] = list(_CHOICES[name])
    return result
