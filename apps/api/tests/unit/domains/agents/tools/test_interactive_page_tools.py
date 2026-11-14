"""generate_interactive_page: guards, honest failures, what reaches the model (ADR-370).

Invocation mirrors ``test_document_generation_tools.py``: ``tool.coroutine(...)``,
module-level settings patch, in-memory tracker reset between tests.
"""

import uuid
from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from src.core.field_names import FIELD_REGISTRY_ID
from src.domains.agents.data_registry.models import RegistryItemType
from src.domains.agents.interactive_page.catalogue_manifests import (
    PAGE_SOURCE_DATA_DESCRIPTION,
    PAGE_TOOL_DESCRIPTION,
)
from src.domains.agents.tools import interactive_page_tools as mod
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.utils.rate_limiting import _rate_limit_tracker
from src.domains.document_generation.service import StoredDocument
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.interactive_pages.document import PageRefusal
from src.domains.interactive_pages.schemas import PageMode, PageSource
from src.domains.interactive_pages.service import (
    PageOutputTruncatedError,
    PageRefusedError,
    PageSourceNotFoundError,
    ProducedPage,
)
from tests.helpers.runtime_context import make_tool_runtime

pytestmark = pytest.mark.unit

SETTINGS_PATCH_PATH = "src.core.config.get_settings"
_USER_ID = "11111111-1111-1111-1111-111111111111"
_SOURCE = "<html><head><title>Morpion</title></head><body><p>UNIQUE_PAGE_BODY</p></body></html>"
_STORED = StoredDocument(
    attachment_id=str(uuid.uuid4()),
    url="/api/v1/attachments/x",
    filename="morpion.html",
    size_bytes=1200,
    expires_at_iso=None,
)


@pytest.fixture(autouse=True)
def isolated() -> Iterator[AsyncMock]:
    """A clean rate tracker, the capability on, no settings store read."""
    _rate_limit_tracker.clear()
    wrapper = MagicMock()
    wrapper.rate_limit_enabled = True
    with (
        patch.object(mod, "is_capability_enabled", AsyncMock(return_value=True)) as gate,
        patch(SETTINGS_PATCH_PATH, return_value=wrapper),
    ):
        yield gate
    _rate_limit_tracker.clear()


def _runtime(language: str = "fr") -> Any:
    return make_tool_runtime(
        user_id=UUID(_USER_ID),
        thread_id="sub-agent-thread",
        conversation_id="conversation-1",
        language=language,
    )


def _produced(stored: StoredDocument | None = _STORED, **overrides: Any) -> ProducedPage:
    return ProducedPage(title="Morpion", source=_SOURCE, stored=stored, **overrides)


async def _call(service: AsyncMock | None = None, **kwargs: Any) -> Any:
    produce = service or AsyncMock(return_value=_produced())
    with (
        patch.object(mod, "produce_page", produce),
        patch.object(mod, "resolve_page_base", AsyncMock(return_value=None)),
    ):
        arguments: dict[str, Any] = {"instructions": "un morpion", "runtime": _runtime()}
        return await mod.generate_interactive_page.coroutine(**{**arguments, **kwargs})


class TestGuards:
    async def test_refuses_a_call_with_no_identity(self) -> None:
        runtime = MagicMock()
        runtime.context = None
        out = await _call(runtime=runtime)
        assert out.success is False
        assert out.error_code == "AUTH_ERROR"

    async def test_refuses_when_the_operator_switched_it_off(self, isolated: AsyncMock) -> None:
        isolated.return_value = False
        service = AsyncMock()
        out = await _call(service=service)
        assert out.success is False
        assert out.error_code == ToolErrorCode.CONFIGURATION_ERROR.value
        isolated.assert_awaited_once_with(PlatformCapability.INTERACTIVE_PAGES)
        service.assert_not_awaited()

    async def test_refuses_an_unknown_mode_and_publishes_the_accepted_ones(self) -> None:
        service = AsyncMock()
        out = await _call(service=service, mode="draw")
        assert out.success is False
        assert out.error_code == ToolErrorCode.INVALID_INPUT.value
        for mode in PageMode:
            assert mode.value in out.message
        service.assert_not_awaited()

    def test_a_mode_is_repaired_when_only_its_spelling_differs(self) -> None:
        assert mod._parsed_mode(" Revise ") is PageMode.REVISE

    @pytest.mark.parametrize("mode", ["create", "revise"])
    async def test_a_writer_needs_instructions(self, mode: str) -> None:
        service = AsyncMock()
        out = await _call(service=service, mode=mode, instructions="   ")
        assert out.success is False
        assert out.error_code == ToolErrorCode.MISSING_REQUIRED_PARAM.value
        service.assert_not_awaited()

    @pytest.mark.parametrize("mode", ["show", "code"])
    async def test_showing_needs_none(self, mode: str) -> None:
        out = await _call(mode=mode, instructions="")
        assert out.success is True


class TestSuccess:
    async def test_the_page_travels_in_the_registry_under_its_policy(self) -> None:
        out = await _call()
        assert out.success is True
        ((registry_id, item),) = out.registry_updates.items()
        assert item.type is RegistryItemType.PAGE_APP
        payload = item.payload
        assert payload[FIELD_REGISTRY_ID] == registry_id
        assert payload["title"] == "Morpion"
        assert payload["initial_view"] == "page"
        assert payload["html_content"].startswith('<!DOCTYPE html><meta charset="utf-8">')
        assert payload["html_content"][payload["source_offset"] :] == _SOURCE

    async def test_the_model_never_reads_the_page(self) -> None:
        """Its code would be retyped into the answer, and paid for twice."""
        out = await _call()
        assert "UNIQUE_PAGE_BODY" not in out.message
        assert "UNIQUE_PAGE_BODY" not in str(out.structured_data)
        assert out.structured_data, "an empty block would fall back on the registry payload"

    async def test_the_message_forbids_repeating_the_code(self) -> None:
        out = await _call()
        assert "Do NOT repeat its code" in out.message
        assert "Code button" in out.message

    async def test_the_file_is_named_to_the_model(self) -> None:
        out = await _call()
        (entry,) = out.structured_data["page_apps"]
        assert entry["filename"] == "morpion.html"

    async def test_a_source_request_opens_on_the_code_and_files_nothing(self) -> None:
        out = await _call(
            service=AsyncMock(return_value=_produced(stored=None)), mode="code", instructions=""
        )
        (item,) = out.registry_updates.values()
        assert item.payload["initial_view"] == "code"
        (entry,) = out.structured_data["page_apps"]
        assert entry["filename"] is None
        assert "Do NOT retype it" in out.message

    async def test_a_cut_source_is_stated_to_the_model(self) -> None:
        out = await _call(service=AsyncMock(return_value=_produced(truncated_source=True)))
        assert "truncated" in out.message

    async def test_the_service_receives_the_conversation_and_the_language(self) -> None:
        service = AsyncMock(return_value=_produced())
        await _call(service=service, runtime=_runtime(language="de"), filename="jeu")
        request = service.await_args.args[0] if service.await_args else None
        assert request is not None
        assert request.conversation_id == "conversation-1"
        assert request.language == "de"
        assert request.user_id == UUID(_USER_ID)
        assert request.requested_filename == "jeu"
        assert request.mode is PageMode.CREATE

    async def test_the_base_reaches_the_service(self) -> None:
        service = AsyncMock(return_value=_produced())
        base = PageSource(html="<p>x</p>", title="X")
        resolver = AsyncMock(return_value=base)
        with (
            patch.object(mod, "produce_page", service),
            patch.object(mod, "resolve_page_base", resolver),
        ):
            await mod.generate_interactive_page.coroutine(
                instructions="fond violet", mode="revise", runtime=_runtime()
            )
        resolver.assert_awaited_once_with(PageMode.REVISE, "", "conversation-1")
        assert service.await_args is not None
        assert service.await_args.args[0].base == base


class TestHonestFailures:
    async def test_nothing_to_work_from(self) -> None:
        out = await _call(service=AsyncMock(side_effect=PageSourceNotFoundError), mode="show")
        assert out.success is False
        assert out.error_code == ToolErrorCode.NOT_FOUND.value

    async def test_a_cut_page_names_the_budget(self) -> None:
        out = await _call(service=AsyncMock(side_effect=PageOutputTruncatedError(16000)))
        assert out.success is False
        assert "16000" in out.message
        assert "No page was produced" in out.message

    @pytest.mark.parametrize("refusal", list(PageRefusal))
    async def test_every_refusal_is_said_in_its_own_words(self, refusal: PageRefusal) -> None:
        out = await _call(service=AsyncMock(side_effect=PageRefusedError(refusal)))
        assert out.success is False
        assert out.message == mod._REFUSAL_MESSAGES[refusal]

    async def test_a_failure_of_the_writer_stays_a_failure(self) -> None:
        out = await _call(service=AsyncMock(side_effect=RuntimeError("provider down")))
        assert "RuntimeError" not in out.message
        assert out.success is False
        assert "No page was produced" in out.message
        assert "provider down" not in out.message


def test_the_schema_the_loop_binds_says_what_the_manifest_says() -> None:
    assert mod.generate_interactive_page.description == PAGE_TOOL_DESCRIPTION


class TestWhatTheLoopIsTold:
    """A limit the frame enforces is published to whoever asks for the page (ADR-184)."""

    def test_the_tool_says_a_page_has_no_network(self) -> None:
        """Told nothing, the loop asked for an embedded map, and the page showed a hole."""
        assert "no network" in PAGE_TOOL_DESCRIPTION
        assert "iframe" in PAGE_TOOL_DESCRIPTION

    def test_the_tool_says_what_a_map_needs(self) -> None:
        """A page cannot look a place up: its coordinates travel with the request."""
        assert "latitude" in PAGE_TOOL_DESCRIPTION
        assert "latitude" in PAGE_SOURCE_DATA_DESCRIPTION

    def test_the_refusal_of_an_embedded_document_says_what_to_ask_instead(self) -> None:
        message = mod._REFUSAL_MESSAGES[PageRefusal.EMBEDDED_DOCUMENT]
        assert "No page was produced" in message
        assert "iframe" in message
