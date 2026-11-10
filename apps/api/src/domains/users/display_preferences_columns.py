"""How the person wants the interface drawn — the columns of ``users`` they live in.

A declarative mixin like ``TurnPreferencesColumns``: the display mode, the colour
theme, the icon style, the font family and the text size. Preferences follow the
account across devices. The profile service validates merged schedule boundaries;
the browser resolves the account's civil-time schedule into light or absolute black.
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from src.core.constants import (
    USER_FONT_SIZE_DEFAULT_PX,
    USER_FONT_SIZE_MAX_PX,
    USER_FONT_SIZE_MIN_PX,
    USER_ICON_STYLE_DEFAULT,
    USER_ICON_STYLES,
    USER_THEME_DARK_START_MINUTE,
    USER_THEME_LIGHT_START_MINUTE,
    USER_THEME_MINUTE_MAX,
)


class DisplayPreferencesColumns:
    """Mapped columns of the display preferences (a declarative mixin)."""

    theme: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="system",
        server_default="system",
        comment="Display preference: light, dark, system, oled or auto (account civil-time schedule).",
    )
    theme_light_start_minute: Mapped[int] = mapped_column(
        SmallInteger,
        CheckConstraint(
            f"theme_light_start_minute BETWEEN 0 AND {USER_THEME_MINUTE_MAX}",
            name="ck_users_theme_light_minute",
        ),
        CheckConstraint(
            "theme_light_start_minute <> theme_dark_start_minute",
            name="ck_users_theme_distinct_boundaries",
        ),
        nullable=False,
        default=USER_THEME_LIGHT_START_MINUTE,
        server_default=str(USER_THEME_LIGHT_START_MINUTE),
    )
    theme_dark_start_minute: Mapped[int] = mapped_column(
        SmallInteger,
        CheckConstraint(
            f"theme_dark_start_minute BETWEEN 0 AND {USER_THEME_MINUTE_MAX}",
            name="ck_users_theme_dark_minute",
        ),
        nullable=False,
        default=USER_THEME_DARK_START_MINUTE,
        server_default=str(USER_THEME_DARK_START_MINUTE),
    )
    color_theme: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="default",
        server_default="default",
        comment="User color theme preference: 'default', 'ocean', 'forest', 'sunset', 'slate'.",
    )
    icon_style: Mapped[str] = mapped_column(
        String(20),
        CheckConstraint(
            "icon_style IN (" + ", ".join(repr(value) for value in USER_ICON_STYLES) + ")",
            name="ck_users_icon_style",
        ),
        nullable=False,
        default=USER_ICON_STYLE_DEFAULT,
        server_default=USER_ICON_STYLE_DEFAULT,
        comment="Interface icon style: lucide, fluent, flex.",
    )
    font_family: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="system",
        server_default="system",
        comment="User font family preference: system, noto-sans, plus-jakarta-sans, ibm-plex-sans, geist, source-sans-pro, merriweather, libre-baskerville, fira-code.",
    )
    # The table holds the bound too: a script or a seed never reaches UserUpdate.
    font_size: Mapped[int] = mapped_column(
        SmallInteger,
        CheckConstraint(
            f"font_size BETWEEN {USER_FONT_SIZE_MIN_PX} AND {USER_FONT_SIZE_MAX_PX}",
            name="ck_users_font_size_range",
        ),
        nullable=False,
        default=USER_FONT_SIZE_DEFAULT_PX,
        server_default=str(USER_FONT_SIZE_DEFAULT_PX),
        comment=(
            "Interface text size in CSS px at the browser's default root size "
            f"({USER_FONT_SIZE_MIN_PX}-{USER_FONT_SIZE_MAX_PX})."
        ),
    )
