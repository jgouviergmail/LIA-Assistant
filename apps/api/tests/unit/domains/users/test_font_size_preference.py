"""The ``users.font_size`` display preference, from the write path to the column.

The text size scales the whole interface: the frontend sets the root font size
of the document, and every ``rem`` of the UI follows. The bounds are therefore
not a matter of taste but of layout — below the minimum the smallest captions
fall under readability, above the maximum the densest bars overflow. The server
half enforces them strictly on write (a value the UI cannot draw is refused,
never clamped in silence), forgivingly on read (a NULL reads as the default),
and in the table itself, so no path around the schema can store one.

The bounds are a cross-layer contract: the settings slider offers exactly the
range this module accepts. They are read from the web constants below rather
than restated, so a change on one side only fails here — the same shape as
``test_theme_preference_contract.py``.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import CheckConstraint, SmallInteger

from src.core.constants import (
    USER_FONT_SIZE_DEFAULT_PX,
    USER_FONT_SIZE_MAX_PX,
    USER_FONT_SIZE_MIN_PX,
)
from src.domains.shared.schemas import UserBase
from src.domains.users.models import User
from src.domains.users.schemas import UserUpdate

pytestmark = pytest.mark.unit

WEB_FONT_CONSTANTS = Path(__file__).resolve().parents[5] / "web" / "src" / "constants" / "fonts.ts"

ALLOWED = range(USER_FONT_SIZE_MIN_PX, USER_FONT_SIZE_MAX_PX + 1)


def test_bounds_frame_the_default() -> None:
    """The default is a legal value strictly inside the range."""
    assert USER_FONT_SIZE_MIN_PX < USER_FONT_SIZE_DEFAULT_PX < USER_FONT_SIZE_MAX_PX


@pytest.mark.parametrize("size", ALLOWED)
def test_update_accepts_every_offered_size(size: int) -> None:
    """Every step the slider offers survives the write path."""
    assert UserUpdate(font_size=size).font_size == size


@pytest.mark.parametrize(
    "size",
    [USER_FONT_SIZE_MIN_PX - 1, USER_FONT_SIZE_MAX_PX + 1, 0, -16, 1000],
)
def test_update_refuses_a_size_out_of_bounds(size: int) -> None:
    """Outside the range the interface degrades: refused, never clamped."""
    with pytest.raises(ValidationError):
        UserUpdate(font_size=size)


@pytest.mark.parametrize("value", ["16", 16.0, 16.5, True])
def test_update_refuses_what_is_not_an_integer(value: Any) -> None:
    """Strict on write: a string, a float or a boolean is a client defect.

    Pydantic's lax mode would read ``"16"`` and ``True`` as integers, so a
    malformed client would store a size it never meant.
    """
    with pytest.raises(ValidationError):
        UserUpdate(font_size=value)


@pytest.mark.parametrize("field", ["theme", "color_theme", "font_family", "font_size"])
def test_update_refuses_an_explicit_null_display_preference(field: str) -> None:
    """The four display columns are NOT NULL: an explicit null is a 422.

    ``exclude_unset`` keeps a key the client SENT as null, so without this the
    value reached the flush and answered a 500 (review 2026-09-29).
    """
    with pytest.raises(ValidationError):
        UserUpdate.model_validate({field: None})


def test_update_without_font_size_leaves_it_unset() -> None:
    """A PATCH that does not name the field must not write it."""
    update = UserUpdate(full_name="Someone")
    assert "font_size" not in update.model_dump(exclude_unset=True)


def test_profile_reads_a_missing_size_as_the_default() -> None:
    """Forgiving on read: a NULL from an old row reads as the default."""
    now = datetime.now(UTC)
    profile = UserBase.model_validate(
        {
            "id": uuid.uuid4(),
            "email": "reader@example.com",
            "is_active": True,
            "is_verified": True,
            "is_superuser": False,
            "created_at": now,
            "updated_at": now,
            "font_size": None,
        }
    )
    assert profile.font_size == USER_FONT_SIZE_DEFAULT_PX


def test_column_is_a_non_null_small_integer_with_the_default() -> None:
    """The column stores the default for every existing and new account."""
    column = User.__table__.columns["font_size"]
    assert isinstance(column.type, SmallInteger)
    assert column.nullable is False
    assert column.server_default is not None
    assert str(column.server_default.arg) == str(USER_FONT_SIZE_DEFAULT_PX)


def test_table_refuses_a_size_out_of_bounds() -> None:
    """The bound holds below the schema too (a script, a seed, a migration)."""
    checks = [
        str(c.sqltext)
        for c in User.__table__.columns["font_size"].constraints
        if isinstance(c, CheckConstraint)
    ]
    assert checks == [f"font_size BETWEEN {USER_FONT_SIZE_MIN_PX} AND {USER_FONT_SIZE_MAX_PX}"]


@pytest.mark.parametrize(
    ("web_name", "server_value"),
    [
        ("FONT_SIZE_MIN_PX", USER_FONT_SIZE_MIN_PX),
        ("FONT_SIZE_MAX_PX", USER_FONT_SIZE_MAX_PX),
        ("DEFAULT_FONT_SIZE_PX", USER_FONT_SIZE_DEFAULT_PX),
    ],
)
def test_web_offers_exactly_the_range_the_server_accepts(web_name: str, server_value: int) -> None:
    """A bound moved on one side only is a slider step answered by a 422."""
    source = WEB_FONT_CONSTANTS.read_text(encoding="utf-8")
    match = re.search(rf"export const {web_name}\b[^=]*=\s*(\d+)\s*;", source)
    assert match is not None, f"{web_name} not found in {WEB_FONT_CONSTANTS}"
    assert int(match.group(1)) == server_value
