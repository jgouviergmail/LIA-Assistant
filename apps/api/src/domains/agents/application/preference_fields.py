"""Reviewed field-to-surface ownership for the shared UserUpdate schema.

Adding a field to UserUpdate enriches the inherited tool schema automatically,
but must also declare its UI/sensitivity owner here before the boot guard passes.
An API field must never silently become a credential-bearing tool parameter.
"""

from collections.abc import Set
from enum import Enum
from types import MappingProxyType


class PreferenceField(str, Enum):
    """One declaration publishes the field vocabulary and its reviewed owner."""

    section: str
    writable: bool

    def __new__(cls, value: str, section: str, writable: bool = True) -> PreferenceField:
        member = str.__new__(cls, value)
        member._value_ = value
        member.section = section
        member.writable = writable
        return member

    FULL_NAME = "full_name", "profile", False
    PICTURE_URL = "picture_url", "profile", False
    TIMEZONE = "timezone", "timezone"
    LANGUAGE = "language", "language"
    PERSONALITY_ID = "personality_id", "personality"
    THEME = "theme", "theme"
    THEME_LIGHT_START_MINUTE = "theme_light_start_minute", "theme"
    THEME_DARK_START_MINUTE = "theme_dark_start_minute", "theme"
    COLOR_THEME = "color_theme", "theme"
    ICON_STYLE = "icon_style", "theme"
    FONT_FAMILY = "font_family", "font"
    FONT_SIZE = "font_size", "font-size"
    IMAGE_ENABLED = "image_generation_enabled", "image-generation"
    IMAGE_QUALITY = "image_generation_default_quality", "image-generation"
    IMAGE_SIZE = "image_generation_default_size", "image-generation"
    IMAGE_FORMAT = "image_generation_output_format", "image-generation"
    IMAGE_ENHANCEMENT = "image_generation_prompt_enhancement", "image-generation"
    DOCUMENT_ILLUSTRATIONS = "document_illustrations", "documents"
    DOCUMENT_ANIMATIONS = "document_animations", "documents"
    EXCHANGE_RHYTHM = "exchange_rhythm", "usage-preferences"
    # Tighten-only: the chat may switch it on, never off (spec 2026-10-30 D7).
    MCP_CONFIRMATION = "mcp_hitl_required", "mcp-servers"


PREFERENCE_FIELDS = MappingProxyType({field.value: field.section for field in PreferenceField})
PREFERENCE_READ_ONLY_FIELDS = frozenset(
    field.value for field in PreferenceField if not field.writable
)
#: The one value the chat may write for a field that only tightens, and why — the schema
#: publishes it and the preparation and the write refuse any other (spec 2026-10-30 D7).
PREFERENCE_TIGHTEN_ONLY: MappingProxyType[str, tuple[bool, str]] = MappingProxyType(
    {
        PreferenceField.MCP_CONFIRMATION.value: (
            True,
            "Only true: LIA asks before every call of the person's MCP tools that have no "
            "choice of their own. From the chat LIA can only make itself ask more; to ask "
            "less, the person changes it in Settings > MCP Servers.",
        )
    }
)


def assert_preference_field_coverage(fields: Set[str]) -> None:
    declared = set(PREFERENCE_FIELDS)
    if fields != declared:
        raise AssertionError(
            f"Unreviewed preference fields: {sorted(fields - declared)}; "
            f"stale field declarations: {sorted(declared - fields)}"
        )
