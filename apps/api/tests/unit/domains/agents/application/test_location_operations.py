"""A location proposal freezes provider resolution, never guessed model coordinates."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.users.models import User
from src.domains.users.schemas import HomeLocationData

pytestmark = pytest.mark.unit


async def test_address_resolution_is_frozen_before_approval_without_a_write(monkeypatch) -> None:
    from src.domains.agents.application.location_preparation import prepare_location_change
    from src.domains.agents.application.location_schemas import LocationChangeRequest

    user = User(id=uuid4(), is_active=True, deleted_at=None, home_location_encrypted=None)
    db = AsyncMock(spec=AsyncSession)
    db.scalar.side_effect = ["true", user, "true", user]
    resolver = AsyncMock(return_value=HomeLocationData(address="Paris", lat=48.85, lon=2.35))
    monkeypatch.setattr(
        "src.domains.agents.application.location_preparation.resolve_home_location", resolver
    )
    draft = await prepare_location_change(
        db, user.id, LocationChangeRequest(action="set", address="Paris")
    )
    assert draft.operation_id == "home_location.update"
    assert draft.before == {"home_location": None}
    assert draft.after["home_location"] == {
        "address": "Paris",
        "lat": 48.85,
        "lon": 2.35,
        "place_id": None,
    }
    assert draft.intent == draft.after
    assert user.home_location_encrypted is None
    resolver.assert_awaited_once()
    db.commit.assert_not_awaited()


async def test_provider_wait_cannot_change_the_pre_resolution_approval_snapshot(
    monkeypatch,
) -> None:
    from src.core.security.utils import encrypt_data
    from src.domains.agents.application.location_preparation import prepare_location_change
    from src.domains.agents.application.location_schemas import LocationChangeRequest

    user = User(id=uuid4(), is_active=True, deleted_at=None, home_location_encrypted=None)
    db = AsyncMock(spec=AsyncSession)
    db.scalar.side_effect = ["true", user, "true", user]

    async def resolve(*args, **kwargs):
        user.home_location_encrypted = encrypt_data(
            HomeLocationData(address="Concurrent", lat=4, lon=5).model_dump_json()
        )
        return HomeLocationData(address="Proposed", lat=6, lon=7)

    monkeypatch.setattr(
        "src.domains.agents.application.location_preparation.resolve_home_location", resolve
    )
    draft = await prepare_location_change(
        db, user.id, LocationChangeRequest(action="set", address="Proposed")
    )
    assert draft.before == {"home_location": None}


async def test_capability_disabled_during_resolution_refuses_a_new_proposal(monkeypatch) -> None:
    from src.core.exceptions import AuthorizationError
    from src.domains.agents.application.location_preparation import prepare_location_change
    from src.domains.agents.application.location_schemas import LocationChangeRequest

    user = User(id=uuid4(), is_active=True, deleted_at=None, home_location_encrypted=None)
    db = AsyncMock(spec=AsyncSession)
    db.scalar.side_effect = ["true", user, "false"]
    resolver = AsyncMock(return_value=HomeLocationData(address="Paris", lat=48, lon=2))
    monkeypatch.setattr(
        "src.domains.agents.application.location_preparation.resolve_home_location", resolver
    )
    with pytest.raises(AuthorizationError):
        await prepare_location_change(
            db, user.id, LocationChangeRequest(action="set", address="Paris")
        )
    resolver.assert_awaited_once()
    db.commit.assert_not_awaited()


@pytest.mark.parametrize(
    "values",
    [
        {"action": "set"},
        {"action": "set", "address": None},
        {"action": "clear", "address": "Paris"},
    ],
)
def test_published_location_schema_refuses_the_same_ambiguous_shapes(values) -> None:
    from jsonschema import Draft202012Validator

    from src.domains.agents.application.location_schemas import LocationChangeRequest

    assert not Draft202012Validator(LocationChangeRequest.model_json_schema()).is_valid(values)


@pytest.mark.parametrize(
    "values",
    [
        {"action": "set"},
        {"action": "set", "address": " "},
        {"action": "clear", "address": "Paris"},
        {"action": "set", "address": "Paris", "lat": 2, "lon": 3},
    ],
)
def test_location_input_refuses_missing_address_ambiguous_clear_and_invented_coordinates(
    values,
) -> None:
    from src.domains.agents.application.location_schemas import LocationChangeRequest

    with pytest.raises(ValidationError):
        LocationChangeRequest.model_validate(values)


async def test_clear_preview_names_the_remembered_position_cascade(monkeypatch) -> None:
    from src.domains.agents.application.location_preparation import prepare_location_change
    from src.domains.agents.application.location_schemas import LocationChangeRequest

    user = User(
        id=uuid4(),
        is_active=True,
        deleted_at=None,
        home_location_encrypted=None,
        last_known_location_encrypted=None,
        last_known_location_updated_at=None,
    )
    db = AsyncMock(spec=AsyncSession)
    db.scalar.side_effect = ["true", user]
    resolver = AsyncMock()
    monkeypatch.setattr(
        "src.domains.agents.application.location_preparation.resolve_home_location", resolver
    )
    draft = await prepare_location_change(db, user.id, LocationChangeRequest(action="clear"))
    assert draft.before == draft.after == {"home_location": None, "last_known_location": None}
    resolver.assert_not_awaited()
    db.commit.assert_not_awaited()


def test_frozen_clear_cannot_omit_its_cascade_or_inject_a_position() -> None:
    from src.domains.agents.application.location_schemas import HomeLocationPatch

    for values in (
        {"home_location": None},
        {"home_location": None, "last_known_location": {"lat": 4}},
    ):
        with pytest.raises(ValidationError):
            HomeLocationPatch.model_validate(values)


def test_location_preview_displays_complete_before_and_after_with_clear_consequence() -> None:
    from src.core.i18n_drafts import get_draft_preview_labels
    from src.domains.agents.application.draft_rendering import render_application_preview
    from src.domains.agents.application.location_schemas import HomeLocationPatch
    from src.domains.agents.application.preparation import _preference_content

    draft = _preference_content(
        uuid4(),
        HomeLocationPatch(home_location=None, last_known_location=None),
        {"home_location": {"address": "Old", "lat": 4, "lon": 5}, "last_known_location": None},
    )
    lines = render_application_preview(
        draft.model_dump(mode="json"), get_draft_preview_labels("fr"), lambda value: value or ""
    )
    assert any("Old" in getattr(line, "value", "") for line in lines)
    assert any("position" in getattr(line, "text", "") for line in lines)
