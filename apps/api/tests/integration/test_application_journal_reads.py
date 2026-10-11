"""Journal management reads preserve complete UI counters without embeddings, injection or consolidation."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceNotFoundError
from src.domains.agents.application.journal_queries import read_journals
from src.domains.agents.application.journal_read_schemas import JournalRead
from src.domains.journals.models import JournalEntry
from src.domains.journals.service import JournalService
from src.domains.system_settings.models import SystemSetting, SystemSettingKey
from src.domains.users.models import User

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario", ["complete", "empty", "personal_off", "foreign_cursor", "native_off", "source_off"]
)
async def test_journal_reader_preserves_owned_complete_scope_and_source_sizes(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, scenario: str
) -> None:
    monkeypatch.setattr(settings, "journals_enabled", True)
    test_user.journals_enabled = scenario != "personal_off"
    other = User(
        id=uuid4(),
        email=f"journal-reader-{uuid4()}@example.test",
        full_name="Other",
        is_active=True,
    )
    async_session.add(other)
    await async_session.flush()
    count = 0 if scenario == "empty" else 53
    when = datetime.now(UTC)
    rows = [
        JournalEntry(
            user_id=test_user.id,
            theme="self_reflection",
            title=f"Owned {index}",
            content="Owned text",
            char_count=10,
            created_at=when,
            status="archived" if index % 2 else "active",
        )
        for index in range(count)
    ]
    foreign = JournalEntry(
        user_id=other.id,
        theme="self_reflection",
        title="FOREIGN SECRET",
        content="Foreign text",
        char_count=12,
    )
    async_session.add_all([*rows, foreign])
    await async_session.commit()
    if scenario == "native_off":
        monkeypatch.setattr(settings, "application_tools_enabled", False)
    elif scenario == "source_off":
        monkeypatch.setattr(settings, "journals_enabled", False)
    request = JournalRead(limit=5, after_id=foreign.id if scenario == "foreign_cursor" else None)
    if scenario in {"native_off", "source_off", "foreign_cursor"}:
        with pytest.raises(
            ResourceNotFoundError if scenario == "foreign_cursor" else AuthorizationError
        ):
            await read_journals(async_session, test_user.id, request)
        return
    seen = []
    while True:
        result = await read_journals(async_session, test_user.id, request)
        assert result.total == count and len(result.entries) <= 5
        assert result.settings.journals_enabled is (scenario != "personal_off")
        assert {theme.code for theme in result.themes.themes} == {
            "self_reflection",
            "user_observations",
            "ideas_analyses",
            "learnings",
        }
        assert result.total_chars == ((count + 1) // 2) * 10
        assert "FOREIGN SECRET" not in result.model_dump_json()
        assert "embedding" not in result.model_dump_json()
        seen.extend(item.id for item in result.entries)
        if result.next_cursor is None:
            break
        request = JournalRead(limit=5, after_id=result.next_cursor)
    assert len(seen) == len(set(seen)) == count
    for row in rows:
        await async_session.refresh(row)
        assert row.injection_count == 0 and row.revision == 1


async def test_journal_filters_bind_cursor_and_keep_active_global_counters(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "journals_enabled", True)
    rows = [
        JournalEntry(
            user_id=test_user.id,
            theme=theme,
            status=status,
            title=theme,
            content="value",
            char_count=5,
        )
        for theme, status in [
            ("learnings", "active"),
            ("learnings", "active"),
            ("learnings", "archived"),
            ("self_reflection", "active"),
        ]
    ]
    async_session.add_all(rows)
    await async_session.commit()
    result = await read_journals(
        async_session, test_user.id, JournalRead(theme="learnings", status="active", limit=1)
    )
    assert result.total == 2 and result.total_chars == 15 and result.truncated
    assert all(entry.theme.value == "learnings" for entry in result.entries)
    continuation = await read_journals(
        async_session,
        test_user.id,
        JournalRead(theme="learnings", status="active", limit=1, after_id=result.next_cursor),
    )
    assert continuation.total == 2 and not continuation.truncated
    assert continuation.entries[0].id != result.entries[0].id
    with pytest.raises(ResourceNotFoundError):
        await read_journals(
            async_session,
            test_user.id,
            JournalRead(theme="learnings", status="active", after_id=rows[2].id),
        )


@pytest.mark.parametrize("capability", ["native", "journals"])
async def test_journal_read_rechecks_operator_revocation_after_observation(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    capability: str,
) -> None:
    monkeypatch.setattr(settings, "journals_enabled", True)
    owner_id = test_user.id
    original = JournalService.get_theme_counts

    async def revoked(service: JournalService, user_id: object) -> dict[str, int]:
        observed = await original(service, owner_id)
        key = (
            SystemSettingKey.CAPABILITY_APPLICATION_TOOLS_ENABLED
            if capability == "native"
            else SystemSettingKey.CAPABILITY_JOURNALS_ENABLED
        )
        async_session.add(SystemSetting(key=key, value="false"))
        await async_session.flush()
        return observed

    monkeypatch.setattr(JournalService, "get_theme_counts", revoked)
    with pytest.raises(AuthorizationError):
        await read_journals(async_session, owner_id, JournalRead())
