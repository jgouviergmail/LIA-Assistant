"""A draft its executor refused for a missing connector says WHY, never a code.

Four executors write through ONE provider — Gmail's vacation responder and
filters, Google Drive's sheets and docs. A missing connector came back as a
free string, ``connector_not_activated``, and the person read
« EXECUTION_FAILED »: ``incomplete_draft_result`` put a CODE in
``DraftExecutionResult.error``, whose contract is the MESSAGE the card shows
(the already-claimed path puts a translated sentence there).

The failures directive is not the channel on this path: a confirmed draft
takes the response node's fast path, no model writes the answer, and the
execution card IS the answer. So the card states the reason itself.

Under the RC2.1 mask a tool of an unconnected provider is not offered, so the
refusal is reached when the connector stops being active between the card and
the confirmation (an expired grant marks it ``ERROR``): rare, and then the one
thing the person needs to read.
"""

from __future__ import annotations

import html
from collections.abc import Awaitable, Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from src.core.field_names import FIELD_CONNECTOR_TYPE, FIELD_ERROR_CODE, FIELD_SUCCESS
from src.core.i18n_api_messages import APIMessages
from src.core.i18n_draft_refusals import get_draft_refusal_message
from src.core.i18n_drafts import get_draft_error_message
from src.core.i18n_types import Language
from src.domains.agents.drafts.card_html import CardSurface
from src.domains.agents.drafts.models import DraftType
from src.domains.agents.drafts.result_renderer import render_execution_result
from src.domains.agents.services import draft_executor
from src.domains.agents.services.draft_execution_result import DraftExecutionResult
from src.domains.agents.services.draft_result_adaptation import incomplete_draft_result
from src.domains.agents.tools.common import ToolErrorCode, connector_not_activated_refusal
from src.domains.agents.tools.gmail_settings_tools import (
    execute_email_filter_draft,
    execute_vacation_responder_draft,
)
from src.domains.agents.tools.workspace_docs_tools import (
    execute_document_append_draft,
    execute_spreadsheet_write_draft,
)
from src.domains.connectors.errors import ConnectorRevokedError
from src.domains.connectors.models import ConnectorType
from src.infrastructure.email.smtp_outcome import SMTPPartialAcceptanceError
from tests.helpers.runtime_context import installed_runtime_context

pytestmark = pytest.mark.unit

_CODE = ToolErrorCode.CONNECTOR_NOT_ACTIVATED.value
_LANGUAGES: tuple[Language, ...] = ("fr", "en", "es", "de", "it", "zh-CN")

Executor = Callable[[dict[str, Any], UUID, Any], Awaitable[dict[str, Any]]]

_EXECUTORS: list[tuple[Executor, dict[str, Any], ConnectorType]] = [
    (
        execute_vacation_responder_draft,
        {"enable": True, "subject": "Away", "body": "Back on Monday"},
        ConnectorType.GOOGLE_GMAIL,
    ),
    (
        execute_email_filter_draft,
        {"criteria": {"from": "news@example.com"}, "archive": True},
        ConnectorType.GOOGLE_GMAIL,
    ),
    (
        execute_spreadsheet_write_draft,
        {"file_id": "sheet-1", "sheet_name": "Expenses", "mode": "append", "values": [["x"]]},
        ConnectorType.GOOGLE_DRIVE,
    ),
    (
        execute_document_append_draft,
        {"file_id": "doc-1", "text": "A new note."},
        ConnectorType.GOOGLE_DRIVE,
    ),
]


def _deps_without_credentials() -> tuple[MagicMock, MagicMock]:
    """Dependencies whose connector service holds no active credentials."""
    service = MagicMock()
    service.get_connector_credentials = AsyncMock(return_value=None)
    deps = MagicMock()
    deps.get_connector_service = AsyncMock(return_value=service)
    return deps, service


class TestEveryExecutorStatesTheFacts:
    """The executor states a code and the connector; the words are the card's."""

    @pytest.mark.parametrize(
        ("executor", "content", "connector"),
        _EXECUTORS,
        ids=["vacation_responder", "email_filter", "spreadsheet_write", "document_append"],
    )
    async def test_a_missing_connector_is_a_typed_refusal_naming_it(
        self, executor: Executor, content: dict[str, Any], connector: ConnectorType
    ) -> None:
        deps, service = _deps_without_credentials()

        result = await executor(content, uuid4(), deps)

        assert result == {
            FIELD_SUCCESS: False,
            FIELD_ERROR_CODE: _CODE,
            FIELD_CONNECTOR_TYPE: connector.value,
        }
        assert service.get_connector_credentials.await_args.args[1] is connector


class TestTheCardSaysWhy:
    """What ``DraftExecutionResult.error`` carries: the card's sentence where it
    can say the reason, the owner's code where only that owner can."""

    @pytest.mark.parametrize("language", _LANGUAGES)
    def test_the_refusal_names_the_connector_in_the_person_s_language(
        self, language: Language
    ) -> None:
        refusal = connector_not_activated_refusal(ConnectorType.GOOGLE_DRIVE)

        result = incomplete_draft_result(
            "draft-1", DraftType.SPREADSHEET_WRITE.value, refusal, language, MagicMock()
        )

        assert result is not None and result.success is False
        assert result.error == APIMessages.connector_not_activated("Google Drive", language)
        assert _CODE not in result.error

    @pytest.mark.parametrize(
        "refusal",
        [{"success": False, "error": "STALE_STATE"}, {"success": False}],
        ids=["free_string", "nothing"],
    )
    def test_a_refusal_with_no_code_reads_the_generic_sentence(
        self, refusal: dict[str, Any]
    ) -> None:
        # « EXECUTION_FAILED » was a code the adapter invented for want of
        # one: the generic sentence says exactly that much, readably.
        result = incomplete_draft_result(
            "draft-1", DraftType.EMAIL_FILTER.value, refusal, "de", MagicMock()
        )

        assert result is not None
        assert result.error == get_draft_error_message("de")

    @pytest.mark.parametrize(
        "refusal",
        [
            {"success": False, "error_code": _CODE},
            {"success": False, "error_code": _CODE, "connector_type": "not_a_connector"},
            {"success": False, "error_code": _CODE, "connector_type": {"k": "v"}},
        ],
        ids=[
            "no_connector",
            "unknown_connector",
            "unhashable_connector",
        ],
    )
    def test_a_missing_connector_identity_keeps_the_code_in_diagnostics_only(
        self, refusal: dict[str, Any]
    ) -> None:
        # A malformed connector fact does not invent the connector's identity.
        result = incomplete_draft_result(
            "draft-1", DraftType.EMAIL_FILTER.value, refusal, "de", MagicMock()
        )

        assert result is not None
        assert result.error == get_draft_error_message("de")
        assert result.result_data["error_code"] == _CODE

    @pytest.mark.parametrize("language", _LANGUAGES)
    @pytest.mark.parametrize(
        "code",
        ["DRAFT_CHANGED", "DRAFT_GONE", "NO_RECIPIENT", "SCHEMA_CHANGED", "POST_COMMIT_FAILURE"],
    )
    def test_a_known_refusal_is_readable_on_both_card_surfaces(
        self, language: Language, code: str
    ) -> None:
        result = incomplete_draft_result(
            "draft-1",
            DraftType.MAILBOX_DRAFT_SEND.value,
            {"success": False, "error_code": code},
            language,
            MagicMock(),
        )
        assert result is not None and not result.success
        assert result.result_data["error_code"] == code
        for surface in CardSurface:
            card = render_execution_result(result.to_agent_result(), surface=surface)
            assert code not in card
            assert result.error and result.error in html.unescape(card)

    def test_an_uncertain_completion_preserves_the_fact_that_the_write_committed(self) -> None:
        result = incomplete_draft_result(
            "draft-1",
            DraftType.APPLICATION_ACTION.value,
            {"success": False, "error_code": "COMPLETION_UNKNOWN", "committed": True},
            "fr",
            MagicMock(),
        )
        assert result is not None and not result.success
        assert result.error and "enregistr" in result.error.lower()
        assert "avant de réessayer" in result.error

    def test_an_uncertain_completion_never_invents_a_successful_write(self) -> None:
        result = incomplete_draft_result(
            "draft-1",
            DraftType.APPLICATION_ACTION.value,
            {"success": False, "error_code": "COMPLETION_UNKNOWN", "committed": False},
            "fr",
            MagicMock(),
        )
        assert result is not None and not result.success
        assert result.error and "enregistr" not in result.error.lower()
        assert "avant de réessayer" in result.error

    def test_a_refusal_carrying_the_member_itself_still_names_it(self) -> None:
        # ``str()`` of a ``(str, Enum)`` member is « ConnectorType.X »: read
        # through it, the member would have named no connector at all.
        refusal = {**connector_not_activated_refusal(ConnectorType.GOOGLE_GMAIL)}
        refusal[FIELD_CONNECTOR_TYPE] = ConnectorType.GOOGLE_GMAIL

        result = incomplete_draft_result(
            "draft-1", DraftType.EMAIL_FILTER.value, refusal, "en", MagicMock()
        )

        assert result is not None
        assert result.error == APIMessages.connector_not_activated("Gmail", "en")

    async def test_the_confirmed_draft_reads_why_through_the_real_dispatcher(self) -> None:
        deps, _service = _deps_without_credentials()
        draft_type = DraftType.VACATION_RESPONDER.value
        with (
            installed_runtime_context(deps=deps),
            patch.dict(
                draft_executor.EXECUTOR_REGISTRY, {draft_type: execute_vacation_responder_draft}
            ),
            patch.object(draft_executor, "_sync_tcm_after_draft_execution", AsyncMock()),
        ):
            result = await draft_executor._execute_confirmed_draft(
                {
                    "draft_id": "draft-vacation",
                    "draft_type": draft_type,
                    "draft_content": {"enable": True, "subject": "Away", "body": "Back"},
                },
                {"configurable": {"thread_id": "test-conversation"}},
                "run-refusal",
                "fr",
            )

        assert result.success is False
        # The chat draws a lia-card, a ticket or a channel the Markdown: the
        # person reads the reason on either (ADR-289).
        for surface in CardSurface:
            card = render_execution_result(result.to_agent_result(), surface=surface)
            assert "Gmail" in card, surface
            assert _CODE not in card, surface
            assert "EXECUTION_FAILED" not in card, surface


class TestARaisedFailureReadsItsFactsNeverItsText:
    """An executor that RAISES reaches the card by the facts it carries.

    Its message may quote a provider, a URL or a mailbox (ADR-303): the card
    reads a typed fact when the exception carries one — a revoked connector,
    a partial SMTP acceptance — and the generic sentence otherwise.
    """

    async def _confirm(self, failure: BaseException) -> DraftExecutionResult:
        async def raising(content: dict[str, Any], user_id: UUID, deps: object) -> dict[str, Any]:
            raise failure

        with (
            installed_runtime_context(deps=object()),
            patch.dict(draft_executor.EXECUTOR_REGISTRY, {"raise_probe": raising}),
        ):
            return await draft_executor._execute_confirmed_draft(
                {"draft_id": "draft-raise", "draft_type": "raise_probe", "draft_content": {}},
                {"configurable": {"thread_id": "test-conversation"}},
                "run-raise",
                "fr",
            )

    async def test_a_connector_revoked_since_the_card_is_named(self) -> None:
        result = await self._confirm(ConnectorRevokedError(ConnectorType.GOOGLE_DRIVE, uuid4()))

        assert result.success is False
        assert result.error == APIMessages.connector_not_activated("Google Drive", "fr")
        assert result.result_data[FIELD_ERROR_CODE] == _CODE

    async def test_a_partial_send_keeps_its_facts(self) -> None:
        result = await self._confirm(SMTPPartialAcceptanceError(1, 2))

        assert result.error == get_draft_refusal_message("PARTIAL_SEND", "fr")
        assert result.result_data["accepted_recipients_count"] == 1
        assert result.result_data["refused_recipients_count"] == 2

    async def test_any_other_exception_reads_the_generic_sentence(self) -> None:
        result = await self._confirm(
            RuntimeError("https://provider.example/v1/mail?key=hidden refused the call")
        )

        assert result.error == get_draft_error_message("fr")
        assert result.result_data == {}
