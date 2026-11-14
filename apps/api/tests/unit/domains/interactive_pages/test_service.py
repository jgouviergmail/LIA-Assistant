"""One page, written, checked and kept (ADR-370).

Boundaries are faked where the service meets them: the structured door, the
attachments repository, the session. What is asserted is what leaves: the file,
the card, the refusals. A failure leaves no card behind, and a mode that needs no
writer calls none.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.core.config import settings as app_settings
from src.core.constants import DYNAMIC_CONTEXT_MARKER, INTERACTIVE_PAGE_BYTES_PER_OUTPUT_TOKEN
from src.core.map_tile_providers import MAP_TILE_PROVIDERS
from src.domains.attachments.models import AttachmentOrigin
from src.domains.document_generation import document_store
from src.domains.document_generation import service as document_service
from src.domains.interactive_pages import service as svc
from src.domains.interactive_pages.document import PageRefusal, page_frame
from src.domains.interactive_pages.schemas import PageContent, PageMode, PageSource
from src.infrastructure.llm.structured_output import StructuredOutputTruncatedError
from tests.helpers.attachment_publication import CapturingAttachmentRepository as _FakeRepo
from tests.helpers.attachment_publication import publication_session as _fake_db_context
from tests.helpers.run_authority import unit_run_authority

pytestmark = pytest.mark.unit

_OWNER = uuid.UUID("00000000-0000-0000-0000-000000000001")
_CONVERSATION = "00000000-0000-0000-0000-00000000c001"
_RUNTIME = "00000000-0000-0000-0000-00000000c002"
PAGE = '<!doctype html><html lang="fr"><head><title>Morpion</title></head><body><p>🎃</p></body></html>'


@pytest.fixture(autouse=True)
def storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setattr(app_settings, "attachments_storage_path", str(tmp_path))
    _FakeRepo.snapshot = {}
    document_store.get_and_clear_pending_documents(_RUNTIME)
    with (
        unit_run_authority(_OWNER, uuid.UUID(_CONVERSATION), uuid.UUID(_RUNTIME)),
        patch("src.domains.attachments.file_publication.AttachmentFileRepository", _FakeRepo),
        patch.object(document_service, "get_db_context", _fake_db_context),
    ):
        yield tmp_path
    document_store.get_and_clear_pending_documents(_RUNTIME)


def _request(mode: PageMode, **overrides: Any) -> svc.PageRequest:
    values: dict[str, Any] = {
        "mode": mode,
        "user_id": _OWNER,
        "conversation_id": _CONVERSATION,
        "delivery_runtime_id": _RUNTIME,
        "instructions": "un morpion d'Halloween",
        "source_data": "",
        "base": None,
        "requested_filename": "",
        "language": "fr",
        "config": None,
    }
    return svc.PageRequest(**{**values, **overrides})


def _written(html: str = PAGE, stem: str = "morpion-halloween") -> PageContent:
    return PageContent(filename_stem=stem, title="Morpion d'Halloween", html=html)


async def test_a_new_page_is_written_stored_and_carded(storage: Path) -> None:
    writer = AsyncMock(return_value=_written())
    with patch.object(svc, "_call_page_llm", writer):
        page = await svc.produce_page(_request(PageMode.CREATE))

    writer.assert_awaited_once()
    assert page.title == "Morpion d'Halloween"
    assert page.source == PAGE
    assert page.stored is not None
    assert page.stored.filename == "morpion-halloween.html"

    row = _FakeRepo.snapshot
    assert row["mime_type"] == "text/html"
    assert row["origin"] == AttachmentOrigin.GENERATED_DOCUMENT.value
    assert row["title"] == "morpion-halloween.html"
    assert row["expires_at"] > datetime.now(UTC)

    data = (storage / row["file_path"]).read_bytes()
    assert data.startswith(b'<!DOCTYPE html><meta charset="utf-8">')
    assert data.endswith(PAGE.encode())
    assert row["file_size"] == len(data)

    assert row["conversation_id"] == uuid.UUID(_CONVERSATION)
    assert document_store.peek_pending_documents(_CONVERSATION) == []
    (card,) = document_store.peek_pending_documents(_RUNTIME)
    assert card.doc_type == "html"
    assert card.filename == "morpion-halloween.html"


async def test_a_requested_filename_wins_and_is_sanitized() -> None:
    with patch.object(svc, "_call_page_llm", AsyncMock(return_value=_written())):
        page = await svc.produce_page(_request(PageMode.CREATE, requested_filename="../mon/jeu"))
    assert page.stored is not None
    assert page.stored.filename == ".._mon_jeu.html".lstrip(".")


async def test_a_page_with_no_usable_name_still_gets_a_filename() -> None:
    with patch.object(svc, "_call_page_llm", AsyncMock(return_value=_written(stem="///"))):
        page = await svc.produce_page(_request(PageMode.CREATE))
    assert page.stored is not None
    assert page.stored.filename == "_.html"


async def test_a_revision_hands_the_current_page_to_the_writer() -> None:
    writer = AsyncMock(return_value=_written())
    base = PageSource(html="<p>avant</p>", title="Avant")
    with patch.object(svc, "_call_page_llm", writer):
        await svc.produce_page(_request(PageMode.REVISE, base=base, instructions="fond violet"))
    assert writer.await_args is not None
    assert writer.await_args.args[0].base == base


@pytest.mark.parametrize("mode", [PageMode.SHOW, PageMode.CODE])
async def test_showing_what_exists_calls_no_writer(mode: PageMode) -> None:
    writer = AsyncMock()
    base = PageSource(html=PAGE, title="Morpion")
    with patch.object(svc, "_call_page_llm", writer):
        page = await svc.produce_page(_request(mode, base=base, instructions=""))
    writer.assert_not_awaited()
    assert page.source == PAGE
    assert page.title == "Morpion"


@pytest.mark.parametrize("mode", [PageMode.REVISE, PageMode.SHOW, PageMode.CODE])
async def test_a_mode_with_nothing_to_work_from_says_so_and_pays_no_writer(mode: PageMode) -> None:
    writer = AsyncMock()
    with (
        patch.object(svc, "_call_page_llm", writer),
        pytest.raises(svc.PageSourceNotFoundError),
    ):
        await svc.produce_page(_request(mode, base=None))
    writer.assert_not_awaited()


async def test_show_files_the_page_and_code_files_nothing() -> None:
    base = PageSource(html=PAGE, title="Morpion")
    shown = await svc.produce_page(_request(PageMode.SHOW, base=base))
    assert shown.stored is not None
    assert shown.stored.filename == "Morpion.html"
    _FakeRepo.snapshot = {}
    document_store.get_and_clear_pending_documents(_CONVERSATION)

    code = await svc.produce_page(_request(PageMode.CODE, base=base))
    assert code.stored is None
    assert _FakeRepo.snapshot == {}
    assert document_store.peek_pending_documents(_CONVERSATION) == []


async def test_a_page_cut_at_the_budget_is_refused_and_names_it() -> None:
    cut = AsyncMock(
        side_effect=StructuredOutputTruncatedError(
            "cut", provider="anthropic", schema_name="PageContent"
        )
    )
    with (
        patch.object(svc, "_call_page_llm", cut),
        pytest.raises(svc.PageOutputTruncatedError) as err,
    ):
        await svc.produce_page(_request(PageMode.CREATE))
    assert err.value.budget_tokens > 0
    assert _FakeRepo.snapshot == {}
    assert document_store.peek_pending_documents(_CONVERSATION) == []


@pytest.mark.parametrize(
    ("html", "refusal"),
    [
        ("<body><script>var a=1;", PageRefusal.UNCLOSED_SCRIPT),
        (
            '<body><script src="https://cdn.example/x.js"></script></body>',
            PageRefusal.EXTERNAL_SCRIPT,
        ),
        ("rien", PageRefusal.EMPTY),
        (
            '<body><iframe src="https://maps.example/maps?q=x&output=embed"></iframe></body>',
            PageRefusal.EMBEDDED_DOCUMENT,
        ),
    ],
)
async def test_a_page_that_cannot_work_is_refused_before_any_file(
    html: str, refusal: PageRefusal
) -> None:
    with (
        patch.object(svc, "_call_page_llm", AsyncMock(return_value=_written(html))),
        pytest.raises(svc.PageRefusedError) as err,
    ):
        await svc.produce_page(_request(PageMode.CREATE))
    assert err.value.refusal is refusal
    assert _FakeRepo.snapshot == {}
    assert document_store.peek_pending_documents(_CONVERSATION) == []


async def test_a_page_over_its_budget_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_settings, "interactive_page_max_bytes", 1024)
    html = f"<p>{'x' * 2000}</p>"
    with (
        patch.object(svc, "_call_page_llm", AsyncMock(return_value=_written(html))),
        pytest.raises(svc.PageRefusedError) as err,
    ):
        await svc.produce_page(_request(PageMode.CREATE))
    assert err.value.refusal is PageRefusal.TOO_LARGE


async def test_what_jsonb_refuses_never_reaches_the_message() -> None:
    with patch.object(svc, "_call_page_llm", AsyncMock(return_value=_written("<p>a\x00b</p>"))):
        page = await svc.produce_page(_request(PageMode.CREATE))
    assert page.source == "<p>ab</p>"


async def test_a_page_with_no_title_is_still_named() -> None:
    base = PageSource(html=PAGE, title="")
    page = await svc.produce_page(_request(PageMode.SHOW, base=base))
    assert page.stored is not None
    assert page.stored.filename == "page.html"


async def test_a_cut_source_is_stated(monkeypatch: pytest.MonkeyPatch) -> None:
    """A cut is said: the writer read less than the caller handed over."""
    monkeypatch.setattr(app_settings, "document_generation_max_source_chars", 1000)
    with patch.object(svc, "_call_page_llm", AsyncMock(return_value=_written())):
        cut = await svc.produce_page(_request(PageMode.CREATE, source_data="x" * 1001))
        whole = await svc.produce_page(_request(PageMode.CREATE, source_data="x" * 1000))
    assert cut.truncated_source is True
    assert whole.truncated_source is False


async def test_showing_a_long_page_cuts_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_settings, "document_generation_max_source_chars", 1000)
    base = PageSource(html=f"<p>{'x' * 5000}</p>", title="Long")
    page = await svc.produce_page(_request(PageMode.SHOW, base=base, source_data=base.html))
    assert page.source == base.html
    assert page.truncated_source is False


async def test_a_storage_failure_queues_no_card() -> None:
    failing = Mock(side_effect=OSError("disk full"))
    with (
        patch.object(svc, "_call_page_llm", AsyncMock(return_value=_written())),
        patch("src.domains.attachments.generated_publication._write_bytes", failing),
        pytest.raises(OSError),
    ):
        await svc.produce_page(_request(PageMode.CREATE))
    failing.assert_called_once()
    assert document_store.peek_pending_documents(_RUNTIME) == []


class TestWriterCall:
    async def test_the_door_receives_the_owner_the_slot_and_the_node(self) -> None:
        door = AsyncMock(return_value=_written())
        request = _request(PageMode.CREATE)
        with (
            patch.object(svc, "get_structured_output_with_retry", door),
            patch.object(svc, "get_llm", return_value=object()) as get_llm,
        ):
            await svc._call_page_llm(request)
        get_llm.assert_called_once_with("interactive_page")
        kwargs = door.await_args.kwargs if door.await_args else {}
        assert kwargs["user_id"] == request.user_id
        assert kwargs["schema"] is PageContent
        assert kwargs["node_name"] == "interactive_page"

    def test_a_page_reads_its_own_slot_never_a_document_s(self) -> None:
        """Tuning one must not move the other: that is why the slot exists."""
        rows = {
            "interactive_page": {"max_tokens": 1000},
            "document_generation": {"max_tokens": 9000},
        }
        with patch(
            "src.domains.llm_config.cache.LLMConfigOverrideCache.get_override",
            side_effect=rows.get,
        ):
            assert svc._slot_budget_bytes() == int(1000 * INTERACTIVE_PAGE_BYTES_PER_OUTPUT_TOKEN)

    async def test_the_static_part_is_the_system_message(self) -> None:
        door = AsyncMock(return_value=_written())
        with (
            patch.object(svc, "get_structured_output_with_retry", door),
            patch.object(svc, "get_llm", return_value=object()),
        ):
            await svc._call_page_llm(_request(PageMode.CREATE, instructions="UNIQUE_REQUEST"))
        system, human = door.await_args.kwargs["messages"] if door.await_args else ([], [])
        assert "UNIQUE_REQUEST" not in system.content
        assert "UNIQUE_REQUEST" in human.content


class TestPromptValues:
    def _rendered(self, request: svc.PageRequest) -> str:
        return svc.load_page_prompt().format(**svc.prompt_values(request))

    def test_every_placeholder_is_produced_and_the_marker_is_there(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(app_settings, "interactive_page_map_providers", [])
        rendered = self._rendered(_request(PageMode.CREATE))
        assert DYNAMIC_CONTEXT_MARKER in rendered
        static = rendered.split(DYNAMIC_CONTEXT_MARKER)[0]
        # The three tile tokens are told to the writer as they are written in a pattern.
        assert set(re.findall(r"\{[^}]*\}", static)) <= {"{z}", "{x}", "{y}"}

    def test_the_writer_reads_the_sources_the_policy_allows(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """What the frame's policy ENFORCES, the prompt PUBLISHES, from one setting."""
        first, second = list(MAP_TILE_PROVIDERS)[:2]
        monkeypatch.setattr(app_settings, "interactive_page_map_providers", [first, second])
        sources = str(svc.prompt_values(_request(PageMode.CREATE))["map_tile_sources"])
        lines = sources.splitlines()
        assert len(lines) == 2
        for line, key in zip(lines, (first, second), strict=True):
            provider = MAP_TILE_PROVIDERS[key]
            assert provider.label in line
            assert provider.url_template in line
            assert provider.credit in line
            assert str(provider.max_zoom) in line
        prefix = page_frame("").document
        for key in (first, second):
            assert MAP_TILE_PROVIDERS[key].origin in prefix

    def test_a_deployment_that_allows_no_source_says_so_to_the_writer(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A writer told nothing would write tiles nobody loads."""
        monkeypatch.setattr(app_settings, "interactive_page_map_providers", [])
        sources = str(svc.prompt_values(_request(PageMode.CREATE))["map_tile_sources"])
        assert "http" not in sources
        assert "none" in sources

    def test_the_map_rules_sit_in_the_static_part(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Invariant for a deployment: they belong before the marker, beside the frame's rules."""
        (first,) = list(MAP_TILE_PROVIDERS)[:1]
        monkeypatch.setattr(app_settings, "interactive_page_map_providers", [first])
        static = self._rendered(_request(PageMode.CREATE)).split(DYNAMIC_CONTEXT_MARKER)[0]
        assert MAP_TILE_PROVIDERS[first].url_template in static
        assert "iframe" in static

    def test_writes_in_the_language_of_the_person(self) -> None:
        assert "French" in self._rendered(_request(PageMode.CREATE, language="fr"))

    def test_a_revision_shows_the_current_page_and_a_new_page_shows_none(self) -> None:
        base = PageSource(html="<p>CURRENT_PAGE_BODY</p>", title="")
        assert "CURRENT_PAGE_BODY" in self._rendered(_request(PageMode.REVISE, base=base))
        assert svc.prompt_values(_request(PageMode.CREATE))["current_page"] == ""

    def test_braces_of_a_page_survive_the_rendering(self) -> None:
        base = PageSource(html="<style>a{color:red}</style>", title="")
        assert "a{color:red}" in self._rendered(_request(PageMode.REVISE, base=base))

    def test_the_source_data_is_bounded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(app_settings, "document_generation_max_source_chars", 1000)
        values = svc.prompt_values(_request(PageMode.CREATE, source_data="x" * 5000))
        assert len(str(values["source_data"])) == 1000

    def test_the_published_ceiling_is_the_setting_when_the_slot_allows_more(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(app_settings, "interactive_page_max_bytes", 100 * 1024)
        with patch.object(svc, "_slot_budget_bytes", return_value=10**9):
            assert svc.prompt_values(_request(PageMode.CREATE))["max_page_kb"] == 100

    def test_the_published_ceiling_follows_a_small_slot(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(app_settings, "interactive_page_max_bytes", 100 * 1024)
        with patch.object(svc, "_slot_budget_bytes", return_value=20 * 1024):
            assert svc.prompt_values(_request(PageMode.CREATE))["max_page_kb"] == 20
