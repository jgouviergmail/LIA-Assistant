"""A display zone by name, with the doctrine's safe fallback (lot 17)."""

from __future__ import annotations

from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.core.time_utils import resolve_user_timezone, resolve_zone

pytestmark = pytest.mark.unit


def test_a_valid_name_is_its_zone() -> None:
    assert resolve_zone("Asia/Tokyo") == ZoneInfo("Asia/Tokyo")


@pytest.mark.parametrize("name", [None, "", "Not/AZone", "../etc/passwd"])
def test_anything_else_falls_back_to_the_declared_display_zone(name: str | None) -> None:
    assert resolve_zone(name) == ZoneInfo(DEFAULT_USER_DISPLAY_TIMEZONE)


def test_a_person_resolves_through_the_same_door() -> None:
    assert resolve_user_timezone(SimpleNamespace(timezone="Asia/Tokyo")) == ZoneInfo("Asia/Tokyo")
    assert resolve_user_timezone(object()) == ZoneInfo(DEFAULT_USER_DISPLAY_TIMEZONE)
