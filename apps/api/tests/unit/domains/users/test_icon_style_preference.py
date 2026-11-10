"""The account icon preference has one closed vocabulary and survives profile reads."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import CheckConstraint

from src.core.constants import USER_ICON_STYLE_DEFAULT, USER_ICON_STYLES
from src.domains.shared.schemas import UserBase
from src.domains.users.models import User
from src.domains.users.schemas import UserUpdate

pytestmark = pytest.mark.unit

_WEB_STYLE = Path(__file__).resolve().parents[5] / "web" / "src" / "lib" / "icon-style.ts"


@pytest.mark.parametrize("style", USER_ICON_STYLES)
def test_every_style_survives_the_write_payload(style: str) -> None:
    """The generic profile update receives the exact account preference."""
    update = UserUpdate.model_validate({"icon_style": style})
    assert update.model_dump(exclude_unset=True) == {"icon_style": style}


@pytest.mark.parametrize("value", [None, "iconpark", "Fluent Color", "", 1, True])
def test_invalid_or_null_styles_are_refused(value: object) -> None:
    """Malformed clients fail validation before any NOT NULL or CHECK violation."""
    with pytest.raises(ValidationError):
        UserUpdate.model_validate({"icon_style": value})


def test_an_unrelated_update_does_not_reset_the_icon_preference() -> None:
    """Omitting the field means preserving the account's current choice."""
    assert "icon_style" not in UserUpdate(full_name="Example").model_dump(exclude_unset=True)


@pytest.mark.parametrize("style", [*USER_ICON_STYLES, None])
def test_profile_serializes_the_choice_or_default(style: str | None) -> None:
    """Both auth and user profile DTOs inherit this shared field."""
    now = datetime.now(UTC)
    profile = UserBase.model_validate(
        {
            "id": uuid4(),
            "email": "icons@example.com",
            "is_active": True,
            "is_verified": True,
            "is_superuser": False,
            "created_at": now,
            "updated_at": now,
            "icon_style": style,
        }
    )
    assert profile.model_dump(mode="json")["icon_style"] == (style or USER_ICON_STYLE_DEFAULT)


def test_column_enforces_default_and_vocabulary_below_the_api() -> None:
    """Direct inserts use the same default and cannot store an unknown family."""
    column = User.__table__.columns["icon_style"]
    assert column.nullable is False
    assert column.default is not None
    assert column.default.arg == USER_ICON_STYLE_DEFAULT
    assert column.server_default is not None
    assert str(column.server_default.arg) == USER_ICON_STYLE_DEFAULT
    checks = [str(c.sqltext) for c in column.constraints if isinstance(c, CheckConstraint)]
    assert checks == ["icon_style IN (" + ", ".join(repr(s) for s in USER_ICON_STYLES) + ")"]


def test_frontend_offers_the_same_styles_and_rollout_default() -> None:
    """An option only one side accepts would look saved until the next reload."""
    source = _WEB_STYLE.read_text(encoding="utf-8")
    choices = re.search(r"export const ICON_STYLES\s*=\s*\[([^\]]+)\]", source)
    assert choices is not None
    assert tuple(re.findall(r"['\"]([\w-]+)['\"]", choices.group(1))) == USER_ICON_STYLES
    default = re.search(r"export const DEFAULT_ICON_STYLE\b[^=]*=\s*['\"]([^'\"]+)['\"]", source)
    assert default is not None
    assert default.group(1) == USER_ICON_STYLE_DEFAULT
