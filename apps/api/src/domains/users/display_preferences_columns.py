"""How the person wants the interface drawn — the columns of ``users`` they live in.

A declarative mixin like ``TurnPreferencesColumns``: the display mode, the colour
theme, the font family and the text size. None of them is read by the backend;
they are persisted so a preference follows the account across devices, written
through the generic profile update and validated by ``UserUpdate``.
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from src.core.constants import (
    USER_FONT_SIZE_DEFAULT_PX,
    USER_FONT_SIZE_MAX_PX,
    USER_FONT_SIZE_MIN_PX,
)


class DisplayPreferencesColumns:
    """Mapped columns of the display preferences (a declarative mixin)."""

    theme: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="system",
        server_default="system",
        comment="User display mode preference: 'light', 'dark', or 'system' (follow OS).",
    )
    color_theme: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="default",
        server_default="default",
        comment="User color theme preference: 'default', 'ocean', 'forest', 'sunset', 'slate'.",
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
