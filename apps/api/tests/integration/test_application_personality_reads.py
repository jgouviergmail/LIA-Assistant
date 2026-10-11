"""Public personality reads preserve the UI's localization and effective selection."""

from uuid import uuid4

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceNotFoundError
from src.domains.agents.application.personality_queries import read_personalities
from src.domains.agents.application.personality_schemas import PersonalityRead
from src.domains.personalities.models import Personality, PersonalityTranslation
from src.domains.personalities.service import PersonalityService
from src.domains.users.models import User

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario",
    [
        "catalogue",
        "inactive_selected",
        "missing_cursor",
        "native_off",
        "late_actor",
        "late_language",
    ],
)
async def test_personality_observation_matches_public_ui_without_private_configuration(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    test_user.language = "fr"
    await async_session.execute(update(Personality).values(is_default=False))
    rows = [
        Personality(
            id=uuid4(),
            code=f"reader-{uuid4()}",
            emoji="🙂",
            sort_order=index,
            is_default=index == 0,
            is_active=index < 7,
            prompt_instruction="ADMIN SECRET PROMPT",
            trait_openness=0.73,
            translations=[
                PersonalityTranslation(
                    language_code="fr", title=f"Titre {index}", description="Texte public"
                )
            ],
        )
        for index in range(8)
    ]
    async_session.add_all(rows)
    test_user.personality_id = rows[-1].id if scenario == "inactive_selected" else None
    await async_session.commit()
    source = PersonalityService(async_session)
    expected = await source.list_active("fr")
    effective = await source.get_user_personality(test_user.personality_id, "fr")
    if scenario == "native_off":
        monkeypatch.setattr(settings, "application_tools_enabled", False)
        with pytest.raises(AuthorizationError):
            await read_personalities(async_session, test_user.id, PersonalityRead())
        return
    if scenario == "missing_cursor":
        with pytest.raises(ResourceNotFoundError):
            await read_personalities(
                async_session, test_user.id, PersonalityRead(after_id=rows[-1].id)
            )
        return
    if scenario.startswith("late_"):
        original = PersonalityService.list_active

        async def change_owner(service: PersonalityService, user_language: str | None = None):
            result = await original(service, user_language)
            values = {"is_active": False} if scenario == "late_actor" else {"language": "de"}
            await async_session.execute(
                update(User).where(User.id == test_user.id).values(**values)
            )
            return result

        monkeypatch.setattr(PersonalityService, "list_active", change_owner)
        with pytest.raises(AuthorizationError if scenario == "late_actor" else ValueError):
            await read_personalities(async_session, test_user.id, PersonalityRead())
        return
    seen = []
    request = PersonalityRead(limit=2)
    while True:
        result = await read_personalities(async_session, test_user.id, request)
        assert result.total == expected.total and result.returned_count <= 2
        assert result.personality == effective
        assert result.personality_id == test_user.personality_id
        assert "ADMIN SECRET" not in result.model_dump_json()
        assert "trait_openness" not in result.model_dump_json()
        seen.extend(result.personalities)
        if result.next_cursor is None:
            assert not result.truncated
            break
        assert result.truncated
        request = PersonalityRead(limit=2, after_id=result.next_cursor)
    assert seen == expected.personalities
