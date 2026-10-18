"""A managed skill's refusal sends the model to where the person manages it (ADR-327).

Both managed provenances were told « It is updated from Settings > Features >
Extensions & Data > Skills ». A plugin's skill is not: it is updated and removed
with its plugin, in the Plugins section, and the Skills section refuses to remove
it — the model relayed a path that leads nowhere for that provenance.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.skills.models import SkillProvenance
from src.domains.skills.tools import _resolve_edit_target

pytestmark = pytest.mark.unit

_USER = UUID("00000000-0000-4000-8000-0000000000b1")
_SKILLS_SECTION = "Settings > Features > Extensions & Data > Skills"
_PLUGINS_SECTION = "Settings > Features > Extensions & Data > Plugins"


@asynccontextmanager
async def _session() -> AsyncIterator[MagicMock]:
    yield MagicMock()


async def _refusal_for(provenance: SkillProvenance) -> UnifiedToolOutput:
    """The refusal of an edit to the person's own, active skill of ``provenance``."""
    preferences = MagicMock()
    preferences.get_active_skills_for_user = AsyncMock(return_value={"ma-skill"})
    with (
        patch(
            "src.domains.skills.cache.SkillsCache.get_by_name_for_user",
            return_value={"name": "ma-skill", "scope": "user", "owner_id": str(_USER)},
        ),
        patch("src.infrastructure.database.session.get_db_context", _session),
        patch(
            "src.domains.skills.preference_service.SkillPreferenceService",
            return_value=preferences,
        ),
        patch(
            "src.domains.skills.repository.SkillRepository.get_owned",
            AsyncMock(return_value=SimpleNamespace(provenance=provenance)),
        ),
    ):
        existing, refusal = await _resolve_edit_target("ma-skill", str(_USER))
    assert existing is None
    assert refusal is not None
    assert refusal.error_code == "SKILL_MANAGED"
    return refusal


class TestTheRefusalNamesWhereTheSkillIsManaged:
    async def test_a_plugin_skill_is_sent_to_the_plugins_section(self) -> None:
        refusal = await _refusal_for(SkillProvenance.PLUGIN)

        assert _PLUGINS_SECTION in refusal.message
        assert "with its plugin" in refusal.message
        assert _SKILLS_SECTION not in refusal.message

    async def test_a_library_skill_is_sent_to_the_skills_section(self) -> None:
        refusal = await _refusal_for(SkillProvenance.LIBRARY)

        assert _SKILLS_SECTION in refusal.message
        assert _PLUGINS_SECTION not in refusal.message
