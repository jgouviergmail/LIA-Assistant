"""``get_email_attachment_tool`` — the assistant reads what was attached.

``get_emails`` lists the attachments of a message and stops there; this tool
downloads ONE of them through the account's own mail client (Gmail, Graph or
IMAP, one shape) and serves its reading: the extracted text, paginated like a
body, or the vision slot's reading of an image or a scan. What the tests pin:

- a handle or a name selects the part; an ambiguous name lists the
  candidates rather than guessing; a missing one is NOT_FOUND;
- a file past the published size bound is refused with the bound stated;
- the text is served in PARTS under the e-mail body budget, and it is wrapped
  as external content — an attachment is what a stranger sent;
- the outcome of the reading travels to the caller (``skipped_quota`` and
  ``truncated`` are refusals told by name, never invented text);
- the tool is registered, its manifest is a read one, and the e-mail agent
  lists it.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, patch
from uuid import uuid4

import pytest

from src.domains.agents.emails import attachment_content as ac
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.email_attachment_tools import (
    GetEmailAttachmentTool,
    get_email_attachment_tool,
)
from src.domains.connectors.clients.email_attachments import (
    EmailAttachmentAmbiguousError,
    EmailAttachmentContent,
    EmailAttachmentNotFoundError,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def tool() -> GetEmailAttachmentTool:
    return GetEmailAttachmentTool()


def _client(content: EmailAttachmentContent | Exception) -> AsyncMock:
    client = AsyncMock()
    if isinstance(content, Exception):
        client.download_attachment = AsyncMock(side_effect=content)
    else:
        client.download_attachment = AsyncMock(return_value=content)
    return client


def _reading(
    text: str, outcome: str = "ok", route: ac.Route = ac.Route.TEXT
) -> ac.AttachmentReading:
    return ac.AttachmentReading(route, outcome, text, "application/pdf", 0)  # type: ignore[arg-type]


def _settings(**over: object) -> SimpleNamespace:
    base = {
        "email_attachment_max_mb": 20,
        "email_attachment_vision_max_pages": 4,
        "email_attachment_image_max_edge": 1568,
        "emails_body_part_tokens": 1500,
        "default_language": "en",
    }
    base.update(over)
    return SimpleNamespace(**base)


class TestReading:
    async def test_serves_the_text_in_parts_wrapped_as_external(
        self, tool: GetEmailAttachmentTool
    ) -> None:
        body = "\n\n".join(" ".join(f"w{p}n{i}" for i in range(120)) for p in range(6))
        client = _client(EmailAttachmentContent("report.pdf", "application/pdf", b"%PDF"))
        with (
            patch.object(tool, "_read", AsyncMock(return_value=_reading(body))),
            patch(
                "src.domains.agents.tools.email_attachment_tools.settings",
                _settings(emails_body_part_tokens=300),
            ),
        ):
            result = await tool.execute_api_call(
                client, uuid4(), message_id="m1", attachment_id="a1", question=None, part=1
            )
        output = tool.format_registry_response(result)
        assert output.success is True
        data = output.structured_data
        assert data["filename"] == "report.pdf"
        assert data["route"] == "text"
        assert data["outcome"] == "ok"
        assert data["parts"] > 1 and data["part"] == 1
        assert "<external_content" in data["text"]
        assert "pass part=2" in data["text"]
        client.download_attachment.assert_awaited_once_with(
            "m1", attachment_id="a1", filename=None, max_bytes=ANY
        )

    async def test_a_question_reaches_the_reading(self, tool: GetEmailAttachmentTool) -> None:
        client = _client(EmailAttachmentContent("scan.pdf", "application/pdf", b"%PDF"))
        read = AsyncMock(return_value=_reading("A receipt.", route=ac.Route.VISION))
        with (
            patch.object(tool, "_read", read),
            patch("src.domains.agents.tools.email_attachment_tools.settings", _settings()),
        ):
            result = await tool.execute_api_call(
                client, uuid4(), message_id="m1", filename="scan.pdf", question="amount?", part=1
            )
        assert read.await_args.kwargs["question"] == "amount?"
        assert tool.format_registry_response(result).structured_data["route"] == "vision"

    @pytest.mark.parametrize(
        ("outcome", "code"),
        [
            ("skipped_quota", ToolErrorCode.RATE_LIMIT_EXCEEDED),
            ("truncated", ToolErrorCode.INVALID_RESPONSE_FORMAT),
            ("unsupported", ToolErrorCode.INVALID_PARAM_VALUE),
            ("empty", ToolErrorCode.EMPTY_RESULT),
            ("failed", ToolErrorCode.EXTERNAL_API_ERROR),
        ],
    )
    async def test_a_refused_reading_is_told_by_name(
        self, tool: GetEmailAttachmentTool, outcome: str, code: ToolErrorCode
    ) -> None:
        client = _client(EmailAttachmentContent("x.bin", "application/octet-stream", b"\x00" * 40))
        with (
            patch.object(tool, "_read", AsyncMock(return_value=_reading("", outcome))),
            patch("src.domains.agents.tools.email_attachment_tools.settings", _settings()),
        ):
            result = await tool.execute_api_call(client, uuid4(), message_id="m1", filename="x.bin")
        output = tool.format_registry_response(result)
        assert output.success is False
        assert output.error_code == code.value
        assert outcome in output.summary_for_llm


class TestRefusals:
    async def test_needs_a_handle_or_a_name(self, tool: GetEmailAttachmentTool) -> None:
        result = await tool.execute_api_call(_client(Exception("never")), uuid4(), message_id="m1")
        output = tool.format_registry_response(result)
        assert output.error_code == ToolErrorCode.MISSING_REQUIRED_PARAM.value

    async def test_a_missing_part_is_not_found(self, tool: GetEmailAttachmentTool) -> None:
        client = _client(EmailAttachmentNotFoundError("no attachment called 'x'"))
        result = await tool.execute_api_call(client, uuid4(), message_id="m1", filename="x")
        assert tool.format_registry_response(result).error_code == ToolErrorCode.NOT_FOUND.value

    async def test_an_ambiguous_name_lists_the_candidates(
        self, tool: GetEmailAttachmentTool
    ) -> None:
        candidates = [
            {"attachmentId": "a1", "filename": "photo.jpg", "mimeType": "image/jpeg", "size": 20},
            {"attachmentId": "a2", "filename": "photo.jpg", "mimeType": "image/jpeg", "size": 30},
        ]
        client = _client(EmailAttachmentAmbiguousError("photo.jpg", candidates))
        result = await tool.execute_api_call(client, uuid4(), message_id="m1", filename="photo.jpg")
        output = tool.format_registry_response(result)
        assert output.error_code == ToolErrorCode.DISAMBIGUATION_REQUIRED.value
        assert "a1" in output.summary_for_llm and "a2" in output.summary_for_llm

    async def test_a_file_past_the_bound_is_refused_with_the_bound(
        self, tool: GetEmailAttachmentTool
    ) -> None:
        client = _client(
            EmailAttachmentContent("big.pdf", "application/pdf", b"x" * (2 * 1024 * 1024))
        )
        with patch(
            "src.domains.agents.tools.email_attachment_tools.settings",
            _settings(email_attachment_max_mb=1),
        ):
            result = await tool.execute_api_call(
                client, uuid4(), message_id="m1", filename="big.pdf"
            )
        output = tool.format_registry_response(result)
        assert output.error_code == ToolErrorCode.CONSTRAINT_VIOLATION.value
        assert "1 MB" in output.summary_for_llm


class TestRegistration:
    def test_the_tool_is_a_read_tool_of_the_email_agent(self) -> None:
        from src.domains.agents.emails.attachment_manifest import (
            get_email_attachment_catalogue_manifest as manifest,
        )
        from src.domains.agents.registry.agent_manifest_definitions import EMAIL_AGENT_MANIFEST

        assert get_email_attachment_tool.name == "get_email_attachment_tool"
        assert manifest.name == "get_email_attachment_tool"
        assert manifest.mutation_policy == "read"
        assert "get_email_attachment_tool" in EMAIL_AGENT_MANIFEST.tools
        names = {p.name: p for p in manifest.parameters}
        assert names["message_id"].required is True
        assert names["attachment_id"].required is False and names["filename"].required is False
        part = names["part"]
        assert any(c.kind == "minimum" and c.value == 1 for c in part.constraints)

    def test_the_tool_module_is_imported_by_the_registry(self) -> None:
        import inspect

        from src.domains.agents.tools.tool_registry import _import_tool_modules

        assert "email_attachment_tools" in inspect.getsource(_import_tool_modules)


class TestTheBoundIsPassedToTheClient:
    async def test_the_client_is_told_the_bound_and_its_refusal_is_named(
        self, tool: GetEmailAttachmentTool
    ) -> None:
        from src.domains.connectors.clients.email_attachments import EmailAttachmentTooLargeError

        client = _client(EmailAttachmentTooLargeError(size=3 * 1024 * 1024, max_bytes=1024 * 1024))
        with patch(
            "src.domains.agents.tools.email_attachment_tools.settings",
            _settings(email_attachment_max_mb=1),
        ):
            result = await tool.execute_api_call(
                client, uuid4(), message_id="m1", filename="big.pdf"
            )
        client.download_attachment.assert_awaited_once_with(
            "m1", attachment_id=None, filename="big.pdf", max_bytes=1024 * 1024
        )
        output = tool.format_registry_response(result)
        assert output.error_code == ToolErrorCode.CONSTRAINT_VIOLATION.value
        assert "1 MB" in output.summary_for_llm
