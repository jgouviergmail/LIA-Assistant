"""The exchange rhythm is written strictly and published as the rhythm a turn runs with (ADR-311).

The account stores the person's choice through the generic profile update
(``PATCH /users/{user_id}``, the same door as the theme and the font) — no new
route. Writes are strict: two values, anything else refused, and the database
driver receives an exact ``str``. Reads are forgiving: the profile, which
``/auth/me`` returns and which the chat turn reads, publishes the EFFECTIVE
rhythm, so an account that never chose shows the instance default it runs with
rather than an empty choice.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from src.core.config import settings
from src.core.exchange_rhythm import ExchangeRhythm, effective_exchange_rhythm
from src.domains.users.schemas import UserProfile, UserUpdate
from src.domains.users.service import UserService
from tests.unit.domains.users.test_user_profile_completeness import _orm_user

pytestmark = pytest.mark.unit


class TestTheWrite:
    @pytest.mark.parametrize("value", ["frequent", "occasional"])
    def test_a_rhythm_reaches_the_update_as_an_exact_string(self, value: str) -> None:
        dumped = UserUpdate(exchange_rhythm=value).model_dump(exclude_unset=True)

        assert dumped == {"exchange_rhythm": value}
        assert type(dumped["exchange_rhythm"]) is str

    @pytest.mark.parametrize("value", ["weekly", "FREQUENT", ""])
    def test_anything_else_is_refused(self, value: str) -> None:
        with pytest.raises(ValidationError):
            UserUpdate(exchange_rhythm=value)

    def test_an_update_that_does_not_name_it_leaves_it_alone(self) -> None:
        assert "exchange_rhythm" not in UserUpdate(full_name="x").model_dump(exclude_unset=True)

    async def test_the_service_stores_the_choice(self) -> None:
        service = UserService(MagicMock(commit=AsyncMock()))
        row = _orm_user(exchange_rhythm=None)
        service.repository.get_by_id = AsyncMock(return_value=row)
        service.repository.update = AsyncMock(return_value=_orm_user(exchange_rhythm="frequent"))

        profile = await service.update_user(uuid.uuid4(), UserUpdate(exchange_rhythm="frequent"))

        service.repository.update.assert_awaited_once_with(row, {"exchange_rhythm": "frequent"})
        assert profile.exchange_rhythm is ExchangeRhythm.FREQUENT


class TestThePublishedValue:
    @pytest.mark.parametrize("instance_default", [True, False])
    def test_an_account_that_never_chose_shows_the_instance_default(
        self, monkeypatch: pytest.MonkeyPatch, instance_default: bool
    ) -> None:
        monkeypatch.setattr(settings, "react_cross_turn_cache_enabled", instance_default)

        profile = UserProfile.model_validate(_orm_user(exchange_rhythm=None))

        assert profile.exchange_rhythm is effective_exchange_rhythm(None)

    @pytest.mark.parametrize("chosen", list(ExchangeRhythm))
    def test_the_person_s_choice_is_shown(self, chosen: ExchangeRhythm) -> None:
        profile = UserProfile.model_validate(_orm_user(exchange_rhythm=chosen.value))

        assert profile.exchange_rhythm is chosen

    def test_a_value_nobody_wrote_reads_as_the_default(self) -> None:
        profile = UserProfile.model_validate(_orm_user(exchange_rhythm="weekly"))

        assert profile.exchange_rhythm is effective_exchange_rhythm(None)

    def test_the_json_carries_a_plain_string(self) -> None:
        profile = UserProfile.model_validate(_orm_user(exchange_rhythm="occasional"))

        assert profile.model_dump(mode="json")["exchange_rhythm"] == "occasional"
