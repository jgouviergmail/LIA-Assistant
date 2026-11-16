"""Untrusted restoration names are refused before account or filesystem access."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.core.exceptions import ValidationError
from src.domains.skills.models import SkillProvenance
from src.domains.skills.restore import restore_previous
from tests.helpers.account_file_writes import account_writer_sql_stub as account_writer_sql_stub

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "name",
    [
        "../notes",
        "../../another-owner/.lia-previous/notes",
        "nested/notes",
        "/outside/notes",
        "..\\notes",
        "C:\\outside\\notes",
        "notes:stream",
        ".",
        "..",
    ],
)
async def test_restore_rejects_path_names_before_account_or_disk_access(
    name: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    account_writer_sql_stub: None,
) -> None:
    """Even an owned row cannot make a malformed name a filesystem authority."""
    monkeypatch.setattr("src.domains.skills.restore.settings.skills_users_path", str(tmp_path))
    db = MagicMock(bind=None)
    db.scalar = AsyncMock(return_value=SkillProvenance.AUTHORED.value)

    with pytest.raises(ValidationError):
        await restore_previous(db, uuid4(), name)

    db.scalar.assert_not_awaited()
    assert list(tmp_path.iterdir()) == []
