"""Portability covers the whole source corpus and stored portrait beyond display limits."""

import csv
import io
import json
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.journals.models import JournalEntry
from src.domains.journals.router import export_entries
from src.domains.users.models import User

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("format", ["json", "csv"])
async def test_journal_export_is_complete_owned_and_formula_safe(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, format: str
) -> None:
    monkeypatch.setattr(settings, "journals_enabled", True)
    test_user.journals_enabled = False
    test_user.journal_portrait_full = "Stored historical portrait"
    test_user.journal_portrait_sources = {"legacy": "Unversioned historical provenance"}
    other = User(id=uuid4(), email=f"journal-export-{uuid4()}@example.test", is_active=True)
    async_session.add(other)
    await async_session.flush()
    rows = [
        JournalEntry(
            user_id=test_user.id,
            theme="learnings",
            title="=1+1",
            content=f"Owned {index}",
            char_count=10,
            status="active" if index % 2 else "archived",
        )
        for index in range(10003)
    ]
    async_session.add_all(
        [
            *rows,
            JournalEntry(
                user_id=other.id,
                theme="learnings",
                title="FOREIGN SECRET",
                content="Foreign",
                char_count=7,
            ),
        ]
    )
    await async_session.commit()
    response = await export_entries(export_format=format, user=test_user, db=async_session)
    try:
        payload = b"".join([chunk async for chunk in response.body_iterator])
    finally:
        await response._reader.close()
    assert b"FOREIGN SECRET" not in payload and b"embedding" not in payload
    if format == "json":
        decoded = json.loads(payload)
        assert len(decoded["entries"]) == 10003
        assert decoded["portrait"]["full"] == "Stored historical portrait"
        assert decoded["portrait"]["sources"] == {"legacy": "Unversioned historical provenance"}
    else:
        exported = list(csv.DictReader(io.StringIO(payload.decode("utf-8-sig"))))
        assert len(exported) == 10003
        assert all(row["title"] == "'=1+1" for row in exported)
