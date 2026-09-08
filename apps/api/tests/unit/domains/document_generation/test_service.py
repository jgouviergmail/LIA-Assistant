"""DocumentGenerationService: LLM -> render -> attachment -> pending store (ADR-226)."""

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.document_generation.schemas import (
    DocumentType,
    TableSheet,
    TabularContent,
)

_ATTACHMENT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture
def tabular_result() -> TabularContent:
    return TabularContent(
        filename_stem="modeles-llm",
        title="Modèles LLM",
        sheets=[TableSheet(name="M", headers=["modèle"], rows=[["Fable 5"]])],
    )


class _FakeAttachment:
    """Row double carrying only what the service reads back."""

    def __init__(self, expires_at: datetime) -> None:
        self.id = _ATTACHMENT_ID
        self.expires_at = expires_at


class _FakeRepo:
    """Captures the create() payload; boundary shape preserved."""

    created: dict = {}

    def __init__(self, db: object) -> None:
        self._db = db

    async def create(self, payload: dict) -> _FakeAttachment:
        type(self).created = dict(payload)
        return _FakeAttachment(expires_at=payload["expires_at"])


class _FakeDb:
    async def commit(self) -> None:
        return None


@asynccontextmanager
async def _fake_db_context():
    yield _FakeDb()


@pytest.mark.unit
async def test_generate_csv_end_to_end(tmp_path, monkeypatch, tabular_result) -> None:
    from src.core.config import settings as app_settings

    monkeypatch.setattr(app_settings, "attachments_storage_path", str(tmp_path))

    from src.domains.document_generation import service as svc

    _FakeRepo.created = {}
    with (
        patch.object(svc, "AttachmentRepository", _FakeRepo),
        patch.object(svc, "get_db_context", _fake_db_context),
        patch.object(svc, "_call_document_llm", AsyncMock(return_value=tabular_result)),
    ):
        user_id = uuid.uuid4()
        result = await svc.generate_document_for_user(
            user_id=user_id,
            conversation_id="conv-svc-1",
            doc_type=DocumentType.CSV,
            instructions="liste des modèles",
            source_data="",
            requested_filename="",
            language="fr",
            timezone="Europe/Paris",
            config=None,
        )

    assert result.filename == "modeles-llm.csv"
    assert result.doc_type == "csv"
    assert result.url == f"/api/v1/attachments/{_ATTACHMENT_ID}"
    assert result.truncated_source is False

    created = _FakeRepo.created
    assert created["mime_type"] == "text/csv"
    assert created["content_type"] == "document"
    assert created["status"] == "ready"
    assert created["original_filename"] == "modeles-llm.csv"
    assert created["user_id"] == user_id
    # TTL comes from settings, timezone-aware.
    assert created["expires_at"].tzinfo is not None
    assert created["expires_at"] > datetime.now(UTC)

    # Bytes actually landed on disk under the user's segment.
    stored = tmp_path / created["file_path"]
    assert stored.is_file()
    assert stored.stat().st_size == result.size_bytes == created["file_size"]
    assert created["file_path"].startswith(str(user_id))

    # The card is queued for delivery.
    from src.domains.document_generation.document_store import (
        get_and_clear_pending_documents,
    )

    pending = get_and_clear_pending_documents("conv-svc-1")
    assert len(pending) == 1
    assert pending[0].doc_type == "csv"
    assert pending[0].filename == "modeles-llm.csv"
    assert pending[0].expires_at == result.expires_at_iso


@pytest.mark.unit
async def test_requested_filename_wins_and_is_sanitized(
    tmp_path, monkeypatch, tabular_result
) -> None:
    from src.core.config import settings as app_settings

    monkeypatch.setattr(app_settings, "attachments_storage_path", str(tmp_path))

    from src.domains.document_generation import service as svc

    with (
        patch.object(svc, "AttachmentRepository", _FakeRepo),
        patch.object(svc, "get_db_context", _fake_db_context),
        patch.object(svc, "_call_document_llm", AsyncMock(return_value=tabular_result)),
    ):
        result = await svc.generate_document_for_user(
            user_id=uuid.uuid4(),
            conversation_id="conv-svc-2",
            doc_type=DocumentType.CSV,
            instructions="x",
            source_data="",
            requested_filename="../mes modèles?",
            language="fr",
            timezone="Europe/Paris",
            config=None,
        )

    assert "/" not in result.filename
    assert "?" not in result.filename
    assert result.filename.endswith(".csv")
    assert "mes modèles" in result.filename.replace("_", " ") or "mes" in result.filename

    from src.domains.document_generation.document_store import (
        get_and_clear_pending_documents,
    )

    get_and_clear_pending_documents("conv-svc-2")


@pytest.mark.unit
async def test_source_data_truncation_flagged(tmp_path, monkeypatch, tabular_result) -> None:
    from src.core.config import settings as app_settings

    monkeypatch.setattr(app_settings, "attachments_storage_path", str(tmp_path))
    # Threshold read from settings — computed relative, never hardcoded.
    cap = app_settings.document_generation_max_source_chars

    from src.domains.document_generation import service as svc

    captured: dict = {}

    async def _fake_llm(**kwargs):
        captured.update(kwargs)
        return tabular_result

    with (
        patch.object(svc, "AttachmentRepository", _FakeRepo),
        patch.object(svc, "get_db_context", _fake_db_context),
        patch.object(svc, "_call_document_llm", AsyncMock(side_effect=_fake_llm)),
    ):
        result = await svc.generate_document_for_user(
            user_id=uuid.uuid4(),
            conversation_id="conv-svc-3",
            doc_type=DocumentType.CSV,
            instructions="x",
            source_data="y" * (cap + 100),
            requested_filename="",
            language="fr",
            timezone="Europe/Paris",
            config=None,
        )

    assert result.truncated_source is True
    assert len(captured["source_data"]) == cap

    from src.domains.document_generation.document_store import (
        get_and_clear_pending_documents,
    )

    get_and_clear_pending_documents("conv-svc-3")


@pytest.mark.unit
async def test_renderer_failure_propagates_no_pending_card(
    tmp_path, monkeypatch, tabular_result
) -> None:
    """A failure after the paid LLM call must surface — and queue NO card."""
    from src.core.config import settings as app_settings

    monkeypatch.setattr(app_settings, "attachments_storage_path", str(tmp_path))

    from src.domains.document_generation import service as svc

    with (
        patch.object(svc, "AttachmentRepository", _FakeRepo),
        patch.object(svc, "get_db_context", _fake_db_context),
        patch.object(svc, "_call_document_llm", AsyncMock(return_value=tabular_result)),
        patch.object(svc, "render_document", side_effect=RuntimeError("render boom")),
        pytest.raises(RuntimeError, match="render boom"),
    ):
        await svc.generate_document_for_user(
            user_id=uuid.uuid4(),
            conversation_id="conv-svc-4",
            doc_type=DocumentType.CSV,
            instructions="x",
            source_data="",
            requested_filename="",
            language="fr",
            timezone="Europe/Paris",
            config=None,
        )

    from src.domains.document_generation.document_store import (
        peek_pending_documents,
    )

    assert peek_pending_documents("conv-svc-4") == []


@pytest.mark.unit
async def test_the_structured_door_receives_the_owner() -> None:
    """ADR-272/ADR-275: the caller knows the account, so the door is told.

    ``resolve_owner`` reads ``config.metadata.user_id``, which LangGraph never
    sets (only ``thread_id`` is merged), so a door left to infer the owner asks
    the instance ceiling alone.
    """
    from src.domains.document_generation import service as svc

    door = AsyncMock(
        return_value=TabularContent(
            filename_stem="x",
            title="T",
            sheets=[TableSheet(name="S", headers=["a"], rows=[])],
        )
    )
    user_id = uuid.uuid4()
    with (
        patch.object(svc, "get_structured_output_with_retry", door),
        patch.object(svc, "get_llm", lambda _type: object()),
        patch.object(svc, "get_llm_config_for_agent", lambda *_: MagicMock(provider="openai")),
        patch.object(
            svc, "load_document_prompt", lambda *_: "{language}|{instructions}|{source_data}"
        ),
    ):
        await svc._call_document_llm(
            doc_type=DocumentType.CSV,
            instructions="i",
            source_data="",
            language="fr",
            config=None,
            user_id=user_id,
        )
    assert door.await_args is not None
    assert door.await_args.kwargs["user_id"] == user_id


@pytest.mark.unit
async def test_a_truncated_document_is_an_explicit_failure_naming_the_budget(
    tmp_path, monkeypatch
) -> None:
    """Nothing is rendered, nothing is stored, no card is queued (ADR-275)."""
    from src.core.config import settings as app_settings
    from src.domains.document_generation import service as svc
    from src.infrastructure.llm.structured_output import StructuredOutputTruncatedError

    monkeypatch.setattr(app_settings, "attachments_storage_path", str(tmp_path))
    cut = StructuredOutputTruncatedError("cut", provider="openai", schema_name="SectionedContent")
    with (
        patch.object(svc, "_call_document_llm", AsyncMock(side_effect=cut)),
        patch.object(svc, "get_llm_config_for_agent", lambda *_: MagicMock(max_tokens=16000)),
    ):
        with pytest.raises(svc.DocumentOutputTruncatedError) as excinfo:
            await svc.generate_document_for_user(
                user_id=uuid.uuid4(),
                conversation_id="conv-trunc",
                doc_type=DocumentType.DOCX,
                instructions="x",
                source_data="",
                requested_filename="",
                language="fr",
                timezone="Europe/Paris",
                config=None,
            )

    assert excinfo.value.budget_tokens == 16000
    assert "16000" in str(excinfo.value)
    assert not list(tmp_path.iterdir())

    from src.domains.document_generation.document_store import (
        get_and_clear_pending_documents,
    )

    assert get_and_clear_pending_documents("conv-trunc") == []


@pytest.mark.unit
async def test_the_renderer_receives_the_readers_own_context(
    tmp_path, monkeypatch, tabular_result
) -> None:
    """The date on a title block is read in the READER's day (ADR-274)."""
    from src.core.config import settings as app_settings
    from src.domains.document_generation import service as svc

    monkeypatch.setattr(app_settings, "attachments_storage_path", str(tmp_path))
    seen: dict = {}

    def _fake_render(doc_type, content, context):
        seen["context"] = context
        return b"x"

    with (
        patch.object(svc, "AttachmentRepository", _FakeRepo),
        patch.object(svc, "get_db_context", _fake_db_context),
        patch.object(svc, "_call_document_llm", AsyncMock(return_value=tabular_result)),
        patch.object(svc, "render_document", _fake_render),
    ):
        await svc.generate_document_for_user(
            user_id=uuid.uuid4(),
            conversation_id="conv-ctx",
            doc_type=DocumentType.CSV,
            instructions="i",
            source_data="",
            requested_filename="",
            language="zh",
            timezone="Asia/Tokyo",
            config=None,
        )

    context = seen["context"]
    assert context.language == "zh-CN"  # backend canon
    assert context.timezone == "Asia/Tokyo"
    assert context.structure == "auto"
    assert context.generated_at is not None and context.generated_at.tzinfo is not None

    from src.domains.document_generation.document_store import (
        get_and_clear_pending_documents,
    )

    get_and_clear_pending_documents("conv-ctx")
