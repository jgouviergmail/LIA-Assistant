"""A skill records the CHANNEL that brought it, and a managed one keeps its owner (ADR-327).

``url``, ``plugin`` and ``library`` are third-party. A plugin's or a library's
skill is MANAGED: only its own channel replaces it — an upload, a URL import or
a chat edit never captures it, and it never captures a skill the person made.
A chat edit keeps the provenance of what it edits: rewriting a third-party
skill in conversation must not launder it into the person's own.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.exceptions import BaseAPIException
from src.domains.skills.import_service import SkillImportService
from src.domains.skills.models import (
    MANAGED_PROVENANCES,
    THIRD_PARTY_PROVENANCES,
    SkillProvenance,
)
from src.domains.skills.preference_service import SkillPreferenceService

pytestmark = pytest.mark.unit

_OWNER = uuid4()


def _pref(existing: object) -> SkillPreferenceService:
    pref = SkillPreferenceService.__new__(SkillPreferenceService)
    pref.db = MagicMock()
    pref.db.flush = AsyncMock()
    pref.skill_repo = MagicMock()
    pref.skill_repo.get_system = AsyncMock(return_value=None)
    pref.skill_repo.get_owned = AsyncMock(return_value=existing)
    pref.state_repo = MagicMock()
    pref.state_repo.create_states_for_all_users = AsyncMock(return_value=0)
    return pref


def _row(provenance: SkillProvenance, plugin_id: object = None) -> MagicMock:
    return MagicMock(is_system=False, owner_id=_OWNER, plugin_id=plugin_id, provenance=provenance)


class TestTheVocabulary:
    def test_third_party_is_what_lia_fetched_from_someone_else(self) -> None:
        assert THIRD_PARTY_PROVENANCES == {
            SkillProvenance.URL,
            SkillProvenance.PLUGIN,
            SkillProvenance.LIBRARY,
        }

    def test_managed_is_what_a_channel_keeps_updating(self) -> None:
        assert MANAGED_PROVENANCES == {SkillProvenance.PLUGIN, SkillProvenance.LIBRARY}


class TestANewRowRecordsItsChannel:
    @pytest.mark.asyncio
    async def test_a_system_import_is_system_whatever_is_passed(self) -> None:
        skill = await _pref(None).create_skill_for_import(
            name="brief", description="d", is_system=True, provenance=SkillProvenance.URL
        )
        assert skill.provenance == SkillProvenance.SYSTEM

    @pytest.mark.asyncio
    async def test_a_user_import_records_the_channel(self) -> None:
        skill = await _pref(None).create_skill_for_import(
            name="pdf",
            description="d",
            is_system=False,
            owner_id=_OWNER,
            provenance=SkillProvenance.LIBRARY,
        )
        assert skill.provenance == SkillProvenance.LIBRARY

    @pytest.mark.asyncio
    async def test_a_chat_creation_is_authored(self) -> None:
        skill = await _pref(None).create_skill_for_import(
            name="mine", description="d", is_system=False, owner_id=_OWNER
        )
        assert skill.provenance == SkillProvenance.AUTHORED


class TestAReimportRespectsTheOwnerChannel:
    @pytest.mark.asyncio
    async def test_a_chat_edit_keeps_a_third_party_provenance(self) -> None:
        row = _row(SkillProvenance.URL)
        await _pref(row).create_skill_for_import(
            name="pdf", description="d", is_system=False, owner_id=_OWNER, provenance=None
        )
        assert row.provenance == SkillProvenance.URL

    @pytest.mark.asyncio
    async def test_an_upload_over_a_url_skill_is_the_person_s_own_file(self) -> None:
        row = _row(SkillProvenance.URL)
        await _pref(row).create_skill_for_import(
            name="pdf",
            description="d",
            is_system=False,
            owner_id=_OWNER,
            provenance=SkillProvenance.AUTHORED,
        )
        assert row.provenance == SkillProvenance.AUTHORED

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("existing", "incoming"),
        [
            (SkillProvenance.LIBRARY, SkillProvenance.AUTHORED),
            (SkillProvenance.LIBRARY, None),
            (SkillProvenance.LIBRARY, SkillProvenance.URL),
            (SkillProvenance.AUTHORED, SkillProvenance.LIBRARY),
            (SkillProvenance.URL, SkillProvenance.LIBRARY),
        ],
    )
    async def test_a_managed_skill_is_replaced_by_its_own_channel_only(
        self, existing: SkillProvenance, incoming: SkillProvenance | None
    ) -> None:
        with pytest.raises(ValueError):
            await _pref(_row(existing)).create_skill_for_import(
                name="pdf", description="d", is_system=False, owner_id=_OWNER, provenance=incoming
            )

    @pytest.mark.asyncio
    async def test_a_library_update_is_an_upsert(self) -> None:
        row = _row(SkillProvenance.LIBRARY)
        skill = await _pref(row).create_skill_for_import(
            name="pdf",
            description="new",
            is_system=False,
            owner_id=_OWNER,
            provenance=SkillProvenance.LIBRARY,
        )
        assert skill is row
        assert row.description == "new"


def _svc(own: object) -> SkillImportService:
    svc = SkillImportService(db=MagicMock())
    svc.skill_repo = MagicMock()
    svc.skill_repo.get_system = AsyncMock(return_value=None)
    svc.skill_repo.get_owned = AsyncMock(return_value=own)
    return svc


def _no_system_cache() -> MagicMock:
    cache = MagicMock()
    cache.get_system_by_name.return_value = None
    return cache


class TestTheImportRefusesBeforeWriting:
    @pytest.mark.asyncio
    async def test_an_upload_never_captures_a_library_skill(self) -> None:
        with patch("src.domains.skills.cache.SkillsCache", _no_system_cache()):
            with pytest.raises(BaseAPIException) as exc:
                await _svc(_row(SkillProvenance.LIBRARY))._check_user_conflict(
                    "pdf", _OWNER, provenance=SkillProvenance.AUTHORED
                )
        assert exc.value.status_code == 409

    @pytest.mark.asyncio
    async def test_a_library_install_never_captures_the_person_s_skill(self) -> None:
        with patch("src.domains.skills.cache.SkillsCache", _no_system_cache()):
            with pytest.raises(BaseAPIException):
                await _svc(_row(SkillProvenance.AUTHORED))._check_user_conflict(
                    "pdf", _OWNER, provenance=SkillProvenance.LIBRARY
                )

    @pytest.mark.asyncio
    async def test_a_chat_edit_of_an_authored_skill_passes(self) -> None:
        with patch("src.domains.skills.cache.SkillsCache", _no_system_cache()):
            await _svc(_row(SkillProvenance.AUTHORED))._check_user_conflict(
                "pdf", _OWNER, provenance=None
            )
