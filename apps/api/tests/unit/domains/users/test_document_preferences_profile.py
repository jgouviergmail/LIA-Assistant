"""The document preferences are written strictly and published as the choice a generation reads.

The account stores both choices through the generic profile update
(``PATCH /users/{user_id}``) — no new route. Writes are strict: the published
values, anything else refused, and the database driver receives an exact
``str``. Reads are forgiving: the profile publishes the choice a generation
would read, so an account that never chose shows the owner's defaults rather
than an empty choice, and a value nobody can interpret reads as the default.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from src.core.document_preferences import (
    DOCUMENT_ANIMATIONS_DEFAULT,
    DOCUMENT_ILLUSTRATIONS_DEFAULT,
    DocumentAnimations,
    DocumentIllustrations,
)
from src.domains.users.schemas import UserProfile, UserUpdate
from src.domains.users.service import UserService
from tests.unit.domains.users.test_user_profile_completeness import _orm_user

pytestmark = pytest.mark.unit

_FIELDS = {
    "document_illustrations": DocumentIllustrations,
    "document_animations": DocumentAnimations,
}


class TestTheWrite:
    @pytest.mark.parametrize(
        ("field", "value"),
        [(field, choice.value) for field, vocabulary in _FIELDS.items() for choice in vocabulary],
    )
    def test_a_choice_reaches_the_update_as_an_exact_string(self, field: str, value: str) -> None:
        dumped = UserUpdate.model_validate({field: value}).model_dump(exclude_unset=True)

        assert dumped == {field: value}
        assert type(dumped[field]) is str

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("document_illustrations", "sometimes"),
            ("document_illustrations", "AUTO"),
            ("document_illustrations", "presented"),
            ("document_illustrations", ""),
            ("document_animations", "on_request"),
            ("document_animations", "read"),
            ("document_animations", ""),
        ],
    )
    def test_anything_else_is_refused(self, field: str, value: str) -> None:
        with pytest.raises(ValidationError):
            UserUpdate.model_validate({field: value})

    def test_an_update_that_does_not_name_them_leaves_them_alone(self) -> None:
        dumped = UserUpdate(full_name="x").model_dump(exclude_unset=True)

        assert not set(_FIELDS) & set(dumped)

    async def test_the_service_stores_the_choice(self) -> None:
        service = UserService(MagicMock(commit=AsyncMock()))
        row = _orm_user(document_illustrations=None)
        stored = _orm_user(document_illustrations="on_request")

        with (
            patch.object(service.repository, "get_by_id", AsyncMock(return_value=row)),
            patch.object(service.repository, "update", AsyncMock(return_value=stored)) as update,
        ):
            profile = await service.update_user(
                uuid.uuid4(), UserUpdate(document_illustrations=DocumentIllustrations.ON_REQUEST)
            )

        update.assert_awaited_once_with(row, {"document_illustrations": "on_request"})
        assert profile.document_illustrations is DocumentIllustrations.ON_REQUEST


class TestThePublishedValue:
    def test_an_account_that_never_chose_shows_the_owners_defaults(self) -> None:
        profile = UserProfile.model_validate(
            _orm_user(document_illustrations=None, document_animations=None)
        )

        assert profile.document_illustrations is DOCUMENT_ILLUSTRATIONS_DEFAULT
        assert profile.document_animations is DOCUMENT_ANIMATIONS_DEFAULT

    @pytest.mark.parametrize("chosen", list(DocumentIllustrations))
    def test_the_illustration_choice_is_shown(self, chosen: DocumentIllustrations) -> None:
        profile = UserProfile.model_validate(_orm_user(document_illustrations=chosen.value))

        assert profile.document_illustrations is chosen

    @pytest.mark.parametrize("chosen", list(DocumentAnimations))
    def test_the_animation_choice_is_shown(self, chosen: DocumentAnimations) -> None:
        profile = UserProfile.model_validate(_orm_user(document_animations=chosen.value))

        assert profile.document_animations is chosen

    def test_a_value_nobody_wrote_reads_as_the_default(self) -> None:
        profile = UserProfile.model_validate(
            _orm_user(document_illustrations="sometimes", document_animations="weekly")
        )

        assert profile.document_illustrations is DOCUMENT_ILLUSTRATIONS_DEFAULT
        assert profile.document_animations is DOCUMENT_ANIMATIONS_DEFAULT

    def test_the_json_carries_plain_strings(self) -> None:
        profile = UserProfile.model_validate(
            _orm_user(document_illustrations="never", document_animations="always")
        )

        dumped = profile.model_dump(mode="json")
        assert dumped["document_illustrations"] == "never"
        assert dumped["document_animations"] == "always"
