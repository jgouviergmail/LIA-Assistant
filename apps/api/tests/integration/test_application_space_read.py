"""Knowledge-space tools expose source UI metadata without foreign or storage data."""

from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import event, update
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceNotFoundError
from src.domains.agents.application import discovery
from src.domains.agents.application.space_read import read_space_ui
from src.domains.agents.application.space_read_schemas import SpaceUIQuery
from src.domains.agents.application.space_read_spec import SPACE_UI_READ_MANIFEST
from src.domains.agents.tools import application_space_tools
from src.domains.agents.tools.react_tool_wrapper import mark_untrusted_data
from src.domains.rag_spaces import ui_queries
from src.domains.rag_spaces.models import RAGDocument, RAGDriveSource, RAGMailSource, RAGSpace
from src.domains.rag_spaces.service import RAGSpaceService
from src.domains.users.models import User
from tests.helpers.runtime_context import make_tool_runtime

pytestmark = pytest.mark.integration


async def seed_space(db: AsyncSession, user: User) -> RAGSpace:
    space = RAGSpace(user_id=user.id, name="Literal <script>space</script>", is_active=False)
    db.add(space)
    await db.flush()
    db.add_all(
        [
            RAGDocument(
                space_id=space.id,
                user_id=user.id,
                filename=f"private-storage-{index}.pdf",
                original_filename=f"Visible document {index}.pdf",
                file_size=10 + index,
                content_type="application/pdf",
                status="ready" if index < 2 else "error",
                embedding_tokens=20 + index,
                embedding_cost_eur=0.01,
            )
            for index in range(3)
        ]
        + [
            RAGDriveSource(
                space_id=space.id,
                user_id=user.id,
                folder_id="actual-drive-id",
                folder_name="Folder",
            ),
            RAGMailSource(
                space_id=space.id, user_id=user.id, label_id="Label_1", label_name="Literal label"
            ),
        ]
    )
    await db.commit()
    return space


@pytest.mark.parametrize(
    "section", ["spaces", "space", "documents", "drive_sources", "mail_sources"]
)
async def test_owned_space_sections_preserve_source_dtos_and_exact_counts(
    async_session: AsyncSession, test_user: User, monkeypatch, section: str
):
    monkeypatch.setattr(settings, "rag_spaces_enabled", True)
    space = await seed_space(async_session, test_user)
    identity, actor_id = space.id, test_user.id
    query = SpaceUIQuery(
        section=section,
        space_id=None if section == "spaces" else identity,
        limit=25 if section == "space" else 1,
    )
    result = await read_space_ui(async_session, actor_id, query)
    source = await RAGSpaceService(async_session).get_space_detail(identity, actor_id)
    if section == "spaces":
        assert result.total == 1 and result.spaces[0].name == space.name
        assert result.spaces[0].document_count == 3 and result.spaces[0].total_size == 33
        assert result.spaces[0].ready_document_count == 2 and not result.spaces[0].is_active
    elif section == "space":
        assert result.space.id == identity and result.space.document_count == 3
    else:
        rows = getattr(result, section)
        assert len(rows) == 1 and result.total == len(source[section])
        source_row = next(row for row in source[section] if row["id"] == rows[0].id)
        assert rows[0].model_dump() == type(rows[0]).model_validate(source_row).model_dump()
        assert result.next_offset == (1 if section == "documents" else None)
    assert "private-storage" not in result.model_dump_json()
    if section == "documents":
        page = await read_space_ui(async_session, actor_id, query.model_copy(update={"offset": 2}))
        assert len(page.documents) == 1 and page.total == 3 and page.next_offset is None


@pytest.mark.parametrize("target", ["foreign", "system", "stale_owner"])
async def test_space_identity_is_scoped_freshly_to_current_account(
    async_session: AsyncSession, test_user: User, monkeypatch, target: str
):
    monkeypatch.setattr(settings, "rag_spaces_enabled", True)
    space = await seed_space(async_session, test_user)
    identity, actor_id = space.id, test_user.id
    if target == "foreign":
        other = User(id=uuid4(), email=f"space-owner-{uuid4()}@example.test", is_active=True)
        async_session.add(other)
        await async_session.flush()
        space.user_id = other.id
    elif target == "system":
        space.is_system = True
    else:
        await async_session.execute(
            update(RAGSpace)
            .where(RAGSpace.id == identity)
            .values(user_id=None)
            .execution_options(synchronize_session=False)
        )
    await async_session.flush()
    with pytest.raises(ResourceNotFoundError):
        await read_space_ui(
            async_session, actor_id, SpaceUIQuery(section="documents", space_id=identity)
        )
    result = await read_space_ui(async_session, actor_id, SpaceUIQuery())
    assert result.total == 0 and not result.spaces


@pytest.mark.parametrize("flag", ["application_tools_enabled", "rag_spaces_enabled"])
async def test_space_read_respects_disabled_capabilities(
    async_session, test_user, monkeypatch, flag
):
    monkeypatch.setattr(settings, flag, False)
    with pytest.raises(AuthorizationError):
        await read_space_ui(async_session, test_user.id, SpaceUIQuery())


@pytest.mark.parametrize("revocation", ["owner", "account", "capability"])
async def test_space_read_rechecks_authority_after_fetch(
    async_session, test_user, monkeypatch, revocation
):
    monkeypatch.setattr(settings, "rag_spaces_enabled", True)
    space = await seed_space(async_session, test_user)
    identity, actor_id = space.id, test_user.id
    source = ui_queries.documents_page

    async def fetched(db, selected, **paging):
        result = await source(db, selected, **paging)
        if revocation == "capability":
            monkeypatch.setattr(settings, "rag_spaces_enabled", False)
        else:
            statement = (
                update(RAGSpace).where(RAGSpace.id == identity).values(user_id=None)
                if revocation == "owner"
                else update(User).where(User.id == actor_id).values(is_active=False)
            )
            await db.execute(statement.execution_options(synchronize_session=False))
        return result

    monkeypatch.setattr(ui_queries, "documents_page", fetched)
    with pytest.raises(ResourceNotFoundError if revocation == "owner" else AuthorizationError):
        await read_space_ui(
            async_session, actor_id, SpaceUIQuery(section="documents", space_id=identity)
        )


async def test_space_page_totals_use_constant_source_queries(
    async_session: AsyncSession, test_user: User
):
    await seed_space(async_session, test_user)
    async_session.add_all(
        [RAGSpace(user_id=test_user.id, name=f"Empty {index}") for index in range(12)]
    )
    await async_session.commit()
    binding = async_session.bind
    assert isinstance(binding, (AsyncEngine, AsyncConnection))
    engine = binding.sync_engine if isinstance(binding, AsyncEngine) else binding.engine.sync_engine
    statements: list[str] = []

    def counted(
        conn: Connection,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", counted)
    try:
        spaces, total = await ui_queries.spaces_page(async_session, test_user.id, limit=5, offset=0)
    finally:
        event.remove(engine, "before_cursor_execute", counted)
    assert total == 13 and len(spaces) == 5 and len(statements) == 2
    empty, total = await ui_queries.spaces_page(async_session, test_user.id, limit=5, offset=99)
    assert total == 13 and empty == []


async def test_space_page_bound_refuses_whole_metadata_without_cutting(
    async_session, test_user, monkeypatch
):
    monkeypatch.setattr(settings, "rag_spaces_enabled", True)
    space = await seed_space(async_session, test_user)
    from src.domains.agents.application import space_read

    monkeypatch.setattr(space_read, "SPACE_READ_MAX_BYTES", 100)
    with pytest.raises(ValueError, match="too large"):
        await read_space_ui(
            async_session, test_user.id, SpaceUIQuery(section="documents", space_id=space.id)
        )


@pytest.mark.parametrize(
    "section,source_model",
    [
        ("documents", RAGDocument),
        ("drive_sources", RAGDriveSource),
        ("mail_sources", RAGMailSource),
    ],
)
async def test_raw_support_diagnostics_never_enter_model_context(
    async_session, test_user, monkeypatch, section, source_model
):
    monkeypatch.setattr(settings, "rag_spaces_enabled", True)
    space = await seed_space(async_session, test_user)
    identity, actor_id = space.id, test_user.id
    await async_session.execute(
        update(source_model)
        .where(source_model.space_id == identity)
        .values(
            error_message="Provider diagnostic Authorization: Bearer controlled-secret /private/storage/name"
        )
    )
    await async_session.commit()
    result = await read_space_ui(
        async_session, actor_id, SpaceUIQuery(section=section, space_id=identity)
    )
    assert "controlled-secret" not in result.model_dump_json()
    assert "/private/storage" not in result.model_dump_json()
    assert result.technical_diagnostics_withheld
    assert all(row.error_message is None for row in getattr(result, section))
    original = await RAGSpaceService(async_session).get_space_detail(identity, actor_id)
    assert "controlled-secret" in original[section][0]["error_message"]


@pytest.mark.parametrize(
    "state", ["enabled", "application_tools_enabled", "rag_spaces_enabled", "inactive"]
)
async def test_real_space_tool_and_discovery_follow_the_same_current_authority(
    async_session, test_user, monkeypatch, state
):
    monkeypatch.setattr(settings, "rag_spaces_enabled", True)
    await seed_space(async_session, test_user)
    actor_id = test_user.id
    if state == "inactive":
        await async_session.execute(update(User).where(User.id == actor_id).values(is_active=False))
    elif state != "enabled":
        monkeypatch.setattr(settings, state, False)

    @asynccontextmanager
    async def session():
        yield async_session

    monkeypatch.setattr(application_space_tools, "get_db_context", session)
    monkeypatch.setattr(discovery, "get_db_context", session)
    offered = await discovery.filter_application_manifests([SPACE_UI_READ_MANIFEST], actor_id)
    result = await application_space_tools.get_lia_knowledge_spaces_tool.coroutine(
        runtime=make_tool_runtime(user_id=actor_id, store=InMemoryStore())
    )
    assert bool(offered) == result.success == (state == "enabled")
    if state == "enabled":
        assert result.structured_data["total"] == 1
        wrapped = mark_untrusted_data(result, result.model_dump_json())
        assert wrapped.startswith("<external_content ") and wrapped.endswith("</external_content>")
    else:
        assert not result.structured_data and not result.registry_updates
