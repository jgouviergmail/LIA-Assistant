"""Read only owned capability identities and freeze the exact portable package."""

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import BaseAPIException
from src.domains.peers.capability_contracts import CapabilityKind
from src.domains.peers.capability_sources import load_capability_source
from src.domains.skills.models import Skill
from tests.fixtures.factories import UserFactory

pytestmark = pytest.mark.integration


async def test_source_uses_exact_owner_and_independent_bytes(
    async_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = UserFactory.create()
    async_session.add(user)
    await async_session.flush()
    row = Skill(
        name="peer-example",
        description="A useful skill",
        owner_id=user.id,
        is_system=False,
        provenance="authored",
    )
    async_session.add(row)
    await async_session.flush()
    monkeypatch.setattr(settings, "skills_users_path", str(tmp_path))
    root = tmp_path / str(user.id) / row.name
    root.mkdir(parents=True)
    (root / "SKILL.md").write_text(
        "---\nname: peer-example\ndescription: A useful skill\n---\nApproved instructions",
        encoding="utf-8",
    )
    with pytest.raises(BaseAPIException):
        await load_capability_source(async_session, uuid4(), CapabilityKind.SKILL, row.id)
    source = await load_capability_source(async_session, user.id, CapabilityKind.SKILL, row.id)
    snapshot = await source.snapshot()
    (root / "SKILL.md").write_text("changed after preview", encoding="utf-8")
    assert b"Approved instructions" in snapshot.files[0].content
    assert b"changed after preview" not in snapshot.model_dump_json().encode()
