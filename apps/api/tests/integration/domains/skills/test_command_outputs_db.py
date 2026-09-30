"""A skill command's files, filed on PostgreSQL (ADR-327 lot 2).

The unit tests record what the delivery ASKS for; only a real database says
what it gets: the ``attachments`` row the gallery lists (its origin, its type,
its lifetime), the NULL conversation of a run that has none — the column is a
real foreign key — and the file on disk under the path the row names.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.attachments.models import Attachment, AttachmentOrigin
from src.domains.skills import command_outputs
from src.domains.skills.command_bundle import OutputFile
from tests.fixtures.factories import UserFactory

pytestmark = pytest.mark.integration

_PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 8


@pytest.fixture()
def one_session(async_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> AsyncSession:
    """The delivery's short session is the test's (rolled back at the end)."""

    @asynccontextmanager
    async def context() -> AsyncIterator[AsyncSession]:
        yield async_session

    monkeypatch.setattr(command_outputs, "get_db_context", context)
    return async_session


@pytest.mark.asyncio
async def test_the_files_are_the_persons_generated_files(
    one_session: AsyncSession, tmp_path: Path
) -> None:
    from src.core.config import settings

    user = UserFactory.create()
    one_session.add(user)
    await one_session.flush()
    with (
        patch.object(settings, "attachments_storage_path", str(tmp_path)),
        patch.object(command_outputs, "store_pending_document"),
        patch.object(command_outputs, "store_pending_image"),
    ):
        delivery = await command_outputs.deliver_outputs(
            [OutputFile("chart.png", _PNG), OutputFile("notes.md", b"# notes")],
            user_id=user.id,
            # A scheduled run has no conversation: the row must still land.
            conversation_id="unknown",
        )

    assert [item.name for item in delivery.delivered] == ["chart.png", "notes.md.txt"]
    rows = (
        (await one_session.execute(select(Attachment).where(Attachment.user_id == user.id)))
        .scalars()
        .all()
    )
    by_name = {row.original_filename: row for row in rows}
    assert by_name["chart.png"].origin == AttachmentOrigin.GENERATED_IMAGE.value
    assert by_name["notes.md.txt"].origin == AttachmentOrigin.GENERATED_DOCUMENT.value
    assert by_name["notes.md.txt"].mime_type == "text/plain"
    for row in rows:
        assert row.conversation_id is None
        assert row.expires_at is not None
        assert (tmp_path / row.file_path).is_file()
        assert row.file_path.startswith(f"{user.id}/")
        uuid.UUID(Path(row.file_path).stem)
