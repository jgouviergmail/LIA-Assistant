"""What LIA reads of a file (ADR-372, lot 6).

A file is read by what it is: its text goes to the assists' slot, an image or a scan is read by
sight on the vision slot, and that slot is what the run is billed under. The bytes come through the
Tools' doors, inside the run's reading; a refusal is said in the page's words; what a model read
past its bound is stated, never guessed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import pytest

from src.core.exceptions import BaseAPIException
from src.domains.agents.emails import attachment_content
from src.domains.agents.emails.attachment_content import (
    AttachmentReading,
    ReadingOutcome,
    Route,
)
from src.domains.connectors.clients.email_attachments import EmailAttachmentContent
from src.domains.tool_assists import files
from src.domains.tool_assists.door import AssistRun
from src.domains.tool_assists.files import summarize_attachment, summarize_file
from src.domains.tool_assists.llm import assist_line
from src.domains.tool_assists.text import WrittenText
from src.domains.workbench.schemas.files import DownloadQuery
from src.domains.workbench.schemas.mail import AttachmentRequest

pytestmark = pytest.mark.unit

PERSON = uuid4()
VISION = attachment_content.LLM_TYPE
PDF = "application/pdf"


@dataclass
class _Download:
    data: bytes
    filename: str
    mime_type: str


def _run() -> AssistRun:
    return AssistRun(PERSON, "fr", {}, slot="tool_assist", sections=("files",))


def _code(refused: pytest.ExceptionInfo[BaseAPIException]) -> str:
    detail = refused.value.detail
    assert isinstance(detail, dict)
    return str(detail["code"])


def _reading(
    route: Route, outcome: ReadingOutcome, text: str = "", read: int = 0, total: int = 0
) -> AttachmentReading:
    return AttachmentReading(route, outcome, text, PDF, pages_read=read, pages_total=total)


@pytest.fixture
def downloads(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """What was asked of the Tools' doors."""
    seen: list[Any] = []

    async def download_file(user_id: UUID, query: DownloadQuery) -> _Download:
        seen.append(query)
        return _Download(b"bytes", "Plan.pdf", PDF)

    async def download_attachment(
        user_id: UUID, request: AttachmentRequest
    ) -> EmailAttachmentContent:
        seen.append(request)
        return EmailAttachmentContent("Plan.pdf", PDF, b"bytes")

    monkeypatch.setattr(files, "download_file", download_file)
    monkeypatch.setattr(files, "download_attachment", download_attachment)
    return seen


@pytest.fixture
def reader(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """The reading the next file gets, and how it was asked."""
    state: dict[str, Any] = {"reading": _reading(Route.TEXT, "ok", "The words")}

    async def read(content: EmailAttachmentContent, **asked: Any) -> AttachmentReading:
        state["content"] = content
        state["asked"] = asked
        reading: AttachmentReading = state["reading"]
        return reading

    monkeypatch.setattr(files, "read_attachment", read)
    return state


@pytest.fixture
def slot(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """What reached the assists' slot, answered with one short summary."""
    prompts: list[str] = []

    async def ask(run: AssistRun, prompt: str, schema: type[WrittenText]) -> WrittenText:
        prompts.append(prompt)
        return schema(text="A short summary")

    monkeypatch.setattr(files, "ask_slot", ask)
    return prompts


async def test_a_text_is_read_by_the_assists_slot_inside_the_run_s_reading(
    downloads: list[Any], reader: dict[str, Any], slot: list[str]
) -> None:
    run = _run()

    read = await summarize_file(run, "f1")

    assert read.text == "A short summary"
    assert read.cut is False
    assert run.opened is True
    assert run.slot == "tool_assist"
    assert downloads == [DownloadQuery(id="f1")]
    assert "The words" in slot[0]
    assert reader["asked"]["config"] is run.config
    assert reader["asked"]["language"] == "fr"
    assert reader["asked"]["user_id"] == str(PERSON)


async def test_a_file_s_words_reach_the_model_as_a_third_party_s(
    downloads: list[Any], reader: dict[str, Any], slot: list[str]
) -> None:
    await summarize_file(_run(), "f1")

    assert "<external_content" in slot[0]


async def test_an_image_or_a_scan_is_said_by_the_vision_slot_and_billed_there(
    downloads: list[Any], reader: dict[str, Any], slot: list[str]
) -> None:
    reader["reading"] = _reading(Route.VISION, "ok", "A scanned invoice", read=2, total=2)
    run = _run()

    read = await summarize_file(run, "f1")

    assert read.text == "A scanned invoice"
    assert read.cut is False
    assert run.slot == VISION
    assert slot == []


async def test_pages_left_unseen_are_said(
    downloads: list[Any], reader: dict[str, Any], slot: list[str]
) -> None:
    reader["reading"] = _reading(Route.VISION, "ok", "Page 1: …", read=4, total=9)

    read = await summarize_file(_run(), "f1")

    assert read.cut is True


async def test_a_long_text_is_cut_at_its_bound_and_the_cut_reaches_model_and_person(
    downloads: list[Any],
    reader: dict[str, Any],
    slot: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(files.settings, "tool_assist_document_max_chars", 10)
    reader["reading"] = _reading(Route.TEXT, "ok", "x" * 9 + "§" * 50)

    read = await summarize_file(_run(), "f1")

    assert read.cut is True
    assert "§§" not in slot[0]
    assert assist_line("document_cut") in slot[0]


async def test_a_whole_text_carries_no_cut_note(
    downloads: list[Any], reader: dict[str, Any], slot: list[str]
) -> None:
    await summarize_file(_run(), "f1")

    assert assist_line("document_cut") not in slot[0]


async def test_an_attachment_comes_through_the_mail_door(
    downloads: list[Any], reader: dict[str, Any], slot: list[str]
) -> None:
    request = AttachmentRequest(message_id="m1", attachment_id="a1", filename="Plan.pdf")
    run = _run()

    read = await summarize_attachment(run, request)

    assert read.text == "A short summary"
    assert downloads == [request]
    assert run.opened is True


@pytest.mark.parametrize(
    ("outcome", "code"),
    [
        ("unsupported", "assist_unreadable"),
        ("empty", "assist_empty"),
        ("skipped_quota", "assist_quota"),
        ("failed", "assist_failed"),
        ("truncated", "assist_failed"),
    ],
)
async def test_what_could_not_be_read_is_said_in_the_page_s_words(
    downloads: list[Any],
    reader: dict[str, Any],
    slot: list[str],
    outcome: ReadingOutcome,
    code: str,
) -> None:
    reader["reading"] = _reading(Route.VISION, outcome)

    with pytest.raises(BaseAPIException) as refused:
        await summarize_file(_run(), "f1")

    assert _code(refused) == code
    assert slot == []


async def test_a_vision_failure_stays_billed_on_its_slot(
    downloads: list[Any], reader: dict[str, Any], slot: list[str]
) -> None:
    reader["reading"] = _reading(Route.VISION, "failed")
    run = _run()

    with pytest.raises(BaseAPIException):
        await summarize_file(run, "f1")

    assert run.slot == VISION


async def test_an_empty_answer_is_no_summary(
    downloads: list[Any], reader: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def ask(run: AssistRun, prompt: str, schema: type[WrittenText]) -> WrittenText:
        return schema(text="   ")

    monkeypatch.setattr(files, "ask_slot", ask)

    with pytest.raises(BaseAPIException) as refused:
        await summarize_file(_run(), "f1")

    assert _code(refused) == "assist_failed"


async def test_a_download_that_fails_stays_filed_as_failed(
    monkeypatch: pytest.MonkeyPatch, reader: dict[str, Any]
) -> None:
    async def download_file(user_id: UUID, query: DownloadQuery) -> _Download:
        raise RuntimeError("provider down")

    monkeypatch.setattr(files, "download_file", download_file)
    run = _run()

    with pytest.raises(RuntimeError):
        await summarize_file(run, "f1")

    assert run.opened is True
    assert run.failed is True
