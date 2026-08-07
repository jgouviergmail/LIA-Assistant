"""Every field ``UserProfile`` declares must come from the database.

``UserService._build_user_profile`` is the single chokepoint through which the
user DTO is produced — seven call sites depend on it, from the chat stream to
the schedulers. It used to name its fields one by one, and the list had fallen
behind the schema: 21 arguments for 34 declared fields. The thirteen that were
never passed silently took their Pydantic default, so the DTO reported a
preference the user had never expressed.

Measured on the public demonstrator, 2026-08-07:

============================================  =====================
source                                        ``debug_panel_enabled``
============================================  =====================
PostgreSQL (``SELECT``)                       ``true``
``UserService.get_user_by_id()``              ``False``
============================================  =====================

The consequence was a debug panel that displayed and never filled: the stream
computes ``user_access AND user.debug_panel_enabled``, so ``True AND False``
disabled the emission on every turn, and the failure was mute — the fallback
branch logs at DEBUG. It survived because administrators take the other branch
(``is_superuser`` *was* passed) and read a system setting instead; the
non-admin path was exercised by nobody until an instance where everyone is one.

This is the class CLAUDE.md names: adding a field on one side of a
serialisation pair only. The column existed, the schema declared it, the
hand-written constructor forgot it, and Pydantic filled the hole in silence.

So the oracle here is behavioural, not structural: give the ORM a value that
differs from the DTO's default for EVERY declared field, then require the built
profile to carry it. A field the builder ignores comes back as its default and
fails. The value table is required to be exhaustive, so a field added tomorrow
cannot be quietly left out of the check either.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.domains.shared.schemas import (
    VALID_COLOR_THEMES,
    VALID_FONT_FAMILIES,
    VALID_THEMES,
)
from src.domains.users.models import User
from src.domains.users.schemas import UserProfile
from src.domains.users.service import UserService

pytestmark = pytest.mark.unit

#: ``home_address`` is the one field with no column behind it: it is decrypted
#: from ``home_location_encrypted``. It gets its own test below.
DERIVED_FIELDS = frozenset({"home_address"})

#: A legal value that differs from the field's default, for every declared
#: field. "Differs from the default" is what gives the test its power — a value
#: equal to the default cannot distinguish a carried field from a dropped one.
DISTINCTIVE_VALUES: dict[str, Any] = {
    "id": uuid.UUID("11111111-2222-3333-4444-555555555555"),
    "email": "visiteur@client.fr",
    "full_name": "Visiteur du demonstrateur",
    "timezone": "America/New_York",
    "language": "de",
    "personality_id": uuid.UUID("66666666-7777-8888-9999-aaaaaaaaaaaa"),
    "is_active": False,
    "is_verified": True,
    "is_superuser": True,
    "oauth_provider": "google",
    "picture_url": "https://example.com/avatar.png",
    "memory_enabled": False,
    "execution_mode": "react",
    "voice_enabled": True,
    "voice_mode_enabled": True,
    "voice_stt_mode": "remote",
    "tokens_display_enabled": True,
    "debug_panel_enabled": True,
    "response_display_mode": "text",
    "onboarding_completed": True,
    "login_notifications_enabled": False,
    "onboarding_checklist": {"connect_calendar": True},
    "theme": "dark",
    "color_theme": "ocean",
    "font_family": "",  # replaced below: the allowed set is the authority
    "image_generation_enabled": True,
    # Legal members of their allowed sets, not merely "not the default". The
    # strict validators for these three live in ``ImageGenerationValidatorMixin``,
    # which ``UserProfile`` does not inherit today — so an out-of-set value
    # would pass here and turn this suite red for an unrelated reason the day
    # somebody wires that mixin in, which would be an improvement, not a break.
    "image_generation_default_quality": "high",
    "image_generation_default_size": "1536x1024",
    "image_generation_output_format": "webp",
    "weather_use_last_known_location": True,
    "health_metrics_agents_enabled": True,
    "created_at": datetime(2020, 1, 2, 3, 4, 5, tzinfo=UTC),
    "updated_at": datetime(2021, 6, 7, 8, 9, 10, tzinfo=UTC),
}

# Read the allowed sets rather than hardcoding a member: a test that pins a
# literal breaks the day the list is reordered, for no reason of its own.
DISTINCTIVE_VALUES["font_family"] = next(f for f in VALID_FONT_FAMILIES if f != "system")
assert DISTINCTIVE_VALUES["theme"] in VALID_THEMES
assert DISTINCTIVE_VALUES["color_theme"] in VALID_COLOR_THEMES


def _service() -> UserService:
    """The builder reads only its ``user`` argument; the session is inert here."""
    return UserService(MagicMock())


def _orm_user(**overrides: Any) -> User:
    """An ORM instance carrying a distinctive value for every declared field."""
    user = User()
    for name, value in {**DISTINCTIVE_VALUES, **overrides}.items():
        setattr(user, name, value)
    user.home_location_encrypted = None
    return user


class TestTheValueTableCoversTheWholeSchema:
    """A check that skips a field is a check that cannot see it disappear."""

    def test_every_declared_field_has_a_distinctive_value(self) -> None:
        declared = set(UserProfile.model_fields) - DERIVED_FIELDS

        missing = sorted(declared - set(DISTINCTIVE_VALUES))

        assert not missing, (
            f"UserProfile declares {missing} but the table has no value for "
            "them, so this suite would not notice the builder dropping them. "
            "Add a legal value that differs from the field's default."
        )

    def test_no_value_differs_from_its_field_default_by_accident(self) -> None:
        """Each value must actually differ from the default, or it proves nothing."""
        same_as_default = [
            name
            for name, value in DISTINCTIVE_VALUES.items()
            if name in UserProfile.model_fields
            and UserProfile.model_fields[name].default is not None
            and UserProfile.model_fields[name].default == value
        ]

        assert not same_as_default, (
            f"{same_as_default} equal their schema default, so a builder that "
            "ignored them would still pass"
        )


class TestEveryDeclaredFieldComesFromTheDatabase:
    def test_the_profile_carries_what_the_row_holds(self) -> None:
        profile = _service()._build_user_profile(_orm_user())

        dropped = {
            name: (getattr(profile, name), DISTINCTIVE_VALUES[name])
            for name in set(UserProfile.model_fields) - DERIVED_FIELDS
            if getattr(profile, name) != DISTINCTIVE_VALUES[name]
        }

        assert not dropped, (
            "these fields did not survive the build (got, expected): "
            f"{dropped} — a field absent from the builder takes its Pydantic "
            "default, which reports a preference the user never expressed"
        )

    def test_the_field_that_broke_the_debug_panel(self) -> None:
        """Named on its own: it is the one that cost a production investigation."""
        profile = _service()._build_user_profile(_orm_user(debug_panel_enabled=True))

        assert profile.debug_panel_enabled is True

    def test_a_disabled_preference_is_reported_as_disabled(self) -> None:
        """The default happened to be False, so only the True case exposed it."""
        profile = _service()._build_user_profile(_orm_user(debug_panel_enabled=False))

        assert profile.debug_panel_enabled is False


class TestTheEnrichedProfileCarriesThemToo:
    """The admin listing had drifted exactly the same way, ten lines below.

    ``_build_user_profile_with_stats`` re-named the twenty base fields it took
    from the profile it had just built, so it dropped the same thirteen a
    second time — and an administrator reading the user list saw defaults
    instead of what each account had chosen. Fixing one builder and leaving
    its sibling would have left the class alive in the same file.
    """

    def test_the_statistics_view_keeps_every_preference(self) -> None:
        enriched = _service()._build_user_profile_with_stats(_orm_user(), None)

        dropped = {
            name: (getattr(enriched, name), DISTINCTIVE_VALUES[name])
            for name in set(UserProfile.model_fields) - DERIVED_FIELDS
            if getattr(enriched, name) != DISTINCTIVE_VALUES[name]
        }

        assert not dropped, (
            f"the enriched profile lost {dropped} — the base fields must be "
            "spread from the profile, never re-listed by hand"
        )

    def test_it_still_reports_its_own_statistics(self) -> None:
        """Spreading the base must not swallow what this view exists for."""
        enriched = _service()._build_user_profile_with_stats(
            _orm_user(), None, memories_count=7, is_usage_blocked=True
        )

        assert enriched.memories_count == 7
        assert enriched.is_usage_blocked is True


class TestTheDerivedHomeAddressStillWorks:
    """The one field with no column behind it must not be lost in the fix."""

    def test_it_is_decrypted_from_the_encrypted_column(self) -> None:
        user = _orm_user()
        user.home_location_encrypted = b"opaque"

        with patch(
            "src.core.security.utils.decrypt_data",
            return_value='{"address": "12 rue des Lilas, Lognes", "lat": 48.83, "lon": 2.63}',
        ):
            profile = _service()._build_user_profile(user)

        assert profile.home_address == "12 rue des Lilas, Lognes"

    def test_an_undecryptable_value_leaves_it_empty_rather_than_failing(self) -> None:
        """Losing an address must never cost the user their whole profile."""
        user = _orm_user()
        user.home_location_encrypted = b"corrupted"

        with patch("src.core.security.utils.decrypt_data", side_effect=ValueError("bad key")):
            profile = _service()._build_user_profile(user)

        assert profile.home_address is None
        assert profile.email == DISTINCTIVE_VALUES["email"]

    def test_no_encrypted_location_means_no_address(self) -> None:
        profile = _service()._build_user_profile(_orm_user())

        assert profile.home_address is None
