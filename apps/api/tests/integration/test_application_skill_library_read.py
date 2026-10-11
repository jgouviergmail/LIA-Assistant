"""Library reads retain original account ports, rate keys and post-network authority."""

from unittest.mock import AsyncMock

import pytest

from src.core.config import settings
from src.core.exceptions import BaseAPIException
from src.domains.agents.application.skill_library_read import read_skill_library
from src.domains.agents.application.skill_library_read_schemas import SkillLibraryReadInput
from src.domains.skill_library.schemas import LibrarySearchItem, LibrarySearchResponse

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("scenario", ["valid", "revoked", "library_off", "rate_limited"])
async def test_library_lookup_reuses_original_service_and_refuses_late_revocation(
    async_session, test_user, monkeypatch, scenario
):
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "skills_enabled", True)
    monkeypatch.setattr(settings, "skill_library_enabled", True)
    owner = test_user.id
    item = LibrarySearchItem(
        registry_id="third-party",
        name="Untrusted display text",
        source="acme/skills",
        skill_id="card",
        installs=3,
        repository="acme/skills",
        supported=True,
        installed=False,
    )
    answer = LibrarySearchResponse(portal="skills_sh", items=[item] * 3)

    async def lookup(*args):
        if scenario == "revoked":
            test_user.is_active = False
            await async_session.commit()
        return answer

    search = AsyncMock(side_effect=lookup)
    limit = AsyncMock()
    if scenario == "library_off":
        monkeypatch.setattr(settings, "skill_library_enabled", False)
    elif scenario == "rate_limited":
        from src.core.exceptions import RateLimitError

        limit.side_effect = RateLimitError(limit=1, window_seconds=1, retry_after=1)
    monkeypatch.setattr("src.domains.agents.application.skill_library_read.service.search", search)
    monkeypatch.setattr(
        "src.domains.agents.application.skill_library_read.rate_limit_library", limit
    )
    query = SkillLibraryReadInput.model_validate(
        {"request": {"kind": "search", "q": "literal"}, "limit": 1}
    )
    if scenario == "valid":
        result = await read_skill_library(async_session, owner, query)
        assert (
            len(result.data.items) == 1
            and result.windows["items"].total == 3
            and result.windows["items"].next_offset == 1
        )
        search.assert_awaited_once_with(owner, "literal", None)
        limit.assert_awaited_once()
    else:
        with pytest.raises(BaseAPIException):
            await read_skill_library(async_session, owner, query)
        if scenario in {"library_off", "rate_limited"}:
            search.assert_not_awaited()
