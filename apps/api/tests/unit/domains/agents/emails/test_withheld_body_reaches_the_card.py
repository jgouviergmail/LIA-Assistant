"""A body the level withholds from the model still reaches the card (ADR-287 amendment).

Measured 2026-09-29: a listing asked at ``detail=metadata`` — what the planner,
the agent prompt and the manifest all prescribe for « my last emails » — drew
cards whose « see more » held the recipients alone and no attachment chip,
because the model and the card read the same payload. The level now decides
what the MODEL reads, never what the card draws: the withheld body travels in
``RegistryItemMeta.display``, which no model projection reads, and the card
renderers merge it back.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.core.field_names import FIELD_BODY, FIELD_DISPLAY_ONLY
from src.domains.agents.emails.detail_levels import EmailDetail, apply_detail_level
from src.domains.agents.nodes.response_node import generate_html_for_registry
from src.domains.agents.orchestration.correlation_detector import detect_correlations
from src.domains.agents.tools.emails_tools import GetEmailsTool
from src.domains.agents.tools.react_tool_wrapper import extract_data_for_llm

pytestmark = [pytest.mark.unit]

BODY = "Hello Bob,\n\nHere is the WITHHELD_BODY_MARKER quote you asked for.\n\nAlice"
# A real message is longer than the preview every normaliser cuts from its body
# (the snippet the model is served at ``metadata``): the marker lies past it.
OPENING = "Hello Bob, thank you for your call this morning about the renovation. " * 4
LONG_BODY = f"{OPENING}\n\nHere is the WITHHELD_BODY_MARKER quote you asked for.\n\nAlice"


def _message() -> dict[str, Any]:
    return {
        "id": "m1",
        "threadId": "t1",
        "labelIds": ["INBOX"],
        "subject": "Quote",
        "from": "Alice <alice@example.com>",
        "to": "bob@example.com",
        "snippet": "Here is the quote",
        "internalDate": "1790000000000",
        FIELD_BODY: BODY,
        "attachments": [{"filename": "quote.pdf", "mimeType": "application/pdf"}],
        "_provider": "google",
    }


def _output(detail: EmailDetail, **extra: Any) -> Any:
    emails = [{**_message(), **extra}]
    apply_detail_level(emails, detail=detail, part=1, part_tokens=2_000)
    return GetEmailsTool().build_emails_output(emails, query="in:inbox", detail=detail.value)


@pytest.fixture
def metadata_output() -> Any:
    return _output(EmailDetail.METADATA)


class TestTheModelNeverReadsIt:
    def test_no_payload_carries_the_body(self, metadata_output: Any) -> None:
        (item,) = metadata_output.registry_updates.values()
        (listed,) = metadata_output.structured_data["emails"]
        for payload in (item.payload, listed):
            assert FIELD_BODY not in payload
            assert FIELD_DISPLAY_ONLY not in payload

    def test_the_react_projection_does_not_carry_it(self, metadata_output: Any) -> None:
        assert "WITHHELD_BODY_MARKER" not in extract_data_for_llm(metadata_output)

    def test_the_registry_fallback_projection_does_not_carry_it(self, metadata_output: Any) -> None:
        """A tool with no structured data is projected from its registry payloads."""
        metadata_output.structured_data = {}
        assert "WITHHELD_BODY_MARKER" not in extract_data_for_llm(metadata_output)


class TestTheCardDrawsIt:
    def test_the_card_shows_the_body_and_the_attachment(self, metadata_output: Any) -> None:
        html = generate_html_for_registry(metadata_output.registry_updates, user_language="en")
        assert "WITHHELD_BODY_MARKER" in html
        assert "quote.pdf" in html

    def test_it_survives_the_checkpoint(self, metadata_output: Any) -> None:
        """State holds registry items as objects (ReAct) or JSON dicts
        (parallel_executor), serialized by the checkpointer's own serde."""
        from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

        from src.domains.conversations.checkpointer import _CHECKPOINT_ALLOWED_MODULES

        serde = JsonPlusSerializer(allowed_msgpack_modules=_CHECKPOINT_ALLOWED_MODULES)
        as_dicts = {
            k: v.model_dump(mode="json") for k, v in metadata_output.registry_updates.items()
        }
        for registry in (metadata_output.registry_updates, as_dicts):
            restored = serde.loads_typed(serde.dumps_typed(registry))
            html = generate_html_for_registry(restored, user_language="en")
            assert "WITHHELD_BODY_MARKER" in html

    def test_a_correlated_card_shows_it_too(self, metadata_output: Any) -> None:
        item_id, item = next(iter(metadata_output.registry_updates.items()))
        parent = item.model_copy(deep=True)
        child = item.model_copy(deep=True)
        child.meta.correlated_to = "parent"
        clusters, uncorrelated = detect_correlations({"parent": parent, item_id: child})
        (cluster,) = clusters
        assert cluster.parent_item[FIELD_BODY] == BODY
        assert cluster.child_items[0][1][FIELD_BODY] == BODY
        assert not uncorrelated

    def test_a_digested_summary_keeps_it_for_the_card(self) -> None:
        output = _output(EmailDetail.SUMMARY, gist="Alice sends the quote.", digest_status="cached")
        (item,) = output.registry_updates.values()
        assert FIELD_BODY not in item.payload
        html = generate_html_for_registry(output.registry_updates, user_language="en")
        assert "Alice sends the quote." in html
        assert "WITHHELD_BODY_MARKER" in html

    def test_a_served_body_is_not_kept_twice(self) -> None:
        output = _output(EmailDetail.FULL)
        (item,) = output.registry_updates.values()
        assert "WITHHELD_BODY_MARKER" in item.payload[FIELD_BODY]
        assert item.meta.display == {}


class TestEveryConstructionHoldsTheInvariant:
    """Whoever builds a registry item, its payload never carries display-only
    fields — a tool formatter or a rehydrated reference may bypass
    ``create_registry_item``."""

    def test_a_direct_construction_moves_them_to_meta(self) -> None:
        from src.domains.agents.data_registry.models import (
            RegistryItem,
            RegistryItemMeta,
            RegistryItemType,
        )

        item = RegistryItem(
            id="email_x",
            type=RegistryItemType.EMAIL,
            payload={"id": "m1", FIELD_DISPLAY_ONLY: {FIELD_BODY: BODY}},
            meta=RegistryItemMeta(source="gmail", display={"other": "kept"}),
        )

        assert FIELD_DISPLAY_ONLY not in item.payload
        assert item.meta.display == {"other": "kept", FIELD_BODY: BODY}


class TestAReferenceToAListedMessage:
    """« Open the second one » after a ``metadata`` listing (ADR-287 amendment)."""

    @staticmethod
    def _resolved(metadata_output: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        from src.domains.agents.services.context_resolution_service import (
            ContextResolutionService,
        )

        registry = dict(metadata_output.registry_updates)
        state: Any = {"registry": registry}
        agent_results = {"1:plan_executor": {"registry_updates": registry}}
        items = ContextResolutionService()._extract_items_from_registry(
            state, "run", last_action_turn=1, agent_results=agent_results
        )
        return registry, {"items": items, "source_turn_id": 1, "source_domain": "emails"}

    def test_the_card_of_the_resolved_message_shows_the_body(self, metadata_output: Any) -> None:
        from src.domains.agents.utils.registry_filtering import filter_registry_by_current_turn

        registry, resolved = self._resolved(metadata_output)
        turn_registry = filter_registry_by_current_turn({}, 2, registry, resolved, "REFERENCE")

        assert turn_registry, "the reference is matched back to the registry item"
        html = generate_html_for_registry(turn_registry, user_language="en")
        assert "WITHHELD_BODY_MARKER" in html

    def test_the_model_reads_the_reference_without_the_body(self, metadata_output: Any) -> None:
        from src.domains.agents.formatters.resolved_context import (
            format_resolved_context_for_prompt,
        )

        _, resolved = self._resolved(metadata_output)
        assert "WITHHELD_BODY_MARKER" not in format_resolved_context_for_prompt(resolved)

    def test_the_resolved_items_fallback_card_shows_the_body(self, metadata_output: Any) -> None:
        """Drawn from the resolved items when the registry no longer matches them."""
        from src.domains.agents.formatters.resolved_context import (
            generate_html_for_resolved_context,
        )

        _, resolved = self._resolved(metadata_output)
        html = generate_html_for_resolved_context(resolved, user_language="en")
        assert "WITHHELD_BODY_MARKER" in html

    def test_the_rehydrated_candidates_keep_it_for_the_card_only(
        self, metadata_output: Any
    ) -> None:
        from src.domains.agents.nodes.response_node import _registry_from_resolved_context

        _, resolved = self._resolved(metadata_output)
        candidates = _registry_from_resolved_context(resolved)

        assert candidates
        for candidate in candidates.values():
            assert FIELD_BODY not in candidate["payload"]
            assert FIELD_DISPLAY_ONLY not in candidate["payload"]
        assert "WITHHELD_BODY_MARKER" in generate_html_for_registry(candidates, user_language="en")


def _gmail_whole_hit() -> dict[str, Any]:
    """A Gmail ``format=full`` hit, normalised by the client itself."""
    import base64

    from src.core.constants import GMAIL_FORMAT_FULL
    from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient

    message: dict[str, Any] = {
        "id": "g1",
        "threadId": "g1",
        "labelIds": ["INBOX"],
        "snippet": "Here is the quote",
        "internalDate": "1790000000000",
        "payload": {
            "mimeType": "multipart/mixed",
            "headers": [
                {"name": "From", "value": "Alice <alice@example.com>"},
                {"name": "Subject", "value": "Quote"},
            ],
            "parts": [
                {
                    "mimeType": "text/plain",
                    "filename": "",
                    "body": {"data": base64.urlsafe_b64encode(LONG_BODY.encode()).decode()},
                },
                {
                    "mimeType": "application/pdf",
                    "filename": "quote.pdf",
                    "body": {"attachmentId": "a1", "size": 12},
                },
            ],
        },
    }
    GoogleGmailClient._normalize_message_fields(message, GMAIL_FORMAT_FULL)
    return message


def _graph_message(*, listing: bool) -> dict[str, Any]:
    """A Graph message: the listing selects a preview, a read is whole."""
    from src.domains.connectors.clients.normalizers.microsoft_email_normalizer import (
        normalize_graph_message,
    )

    raw: dict[str, Any] = {
        "id": "o1",
        "conversationId": "c1",
        "subject": "Quote",
        "from": {"emailAddress": {"name": "Alice", "address": "alice@example.com"}},
        "toRecipients": [{"emailAddress": {"address": "bob@example.com"}}],
        "receivedDateTime": "2026-09-28T10:00:00Z",
        "isRead": False,
        "hasAttachments": True,
        "bodyPreview": "Here is the quote",
    }
    if not listing:
        raw["body"] = {"contentType": "text", "content": LONG_BODY}
        raw["attachments"] = [
            {"id": "a1", "name": "quote.pdf", "contentType": "application/pdf", "size": 12}
        ]
    return normalize_graph_message(raw)


def _imap_whole_hit() -> dict[str, Any]:
    from datetime import datetime
    from types import SimpleNamespace

    from src.domains.connectors.clients.normalizers.email_normalizer import (
        normalize_imap_message,
    )

    attachment = SimpleNamespace(filename="quote.pdf", content_type="application/pdf", payload=b"x")
    message = SimpleNamespace(
        uid="7",
        subject="Quote",
        from_="alice@example.com",
        to=("bob@example.com",),
        cc=(),
        date=datetime(2026, 9, 28, 10, 0, 0),
        date_str="Mon, 28 Sep 2026 10:00:00 +0000",
        text=LONG_BODY,
        html="",
        attachments=[attachment],
        flags=(),
    )
    return normalize_imap_message(message, "INBOX")


class TestEveryProviderListingDrawsAWholeCard:
    """The three real normalisers, from a ``metadata`` search to the card and to
    what the model reads — the IMAP and Graph paths included."""

    @staticmethod
    def _client(provider: str) -> Any:
        from unittest.mock import AsyncMock

        from src.domains.connectors.clients.apple_email_client import AppleEmailClient
        from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
        from src.domains.connectors.clients.microsoft_outlook_client import (
            MicrosoftOutlookClient,
        )

        client = AsyncMock()
        client.list_labels = AsyncMock(return_value={})
        if provider == "google":
            client.SEARCH_HITS_ARE_WHOLE = GoogleGmailClient.SEARCH_HITS_ARE_WHOLE
            hits = [_gmail_whole_hit()]
        elif provider == "apple":
            client.SEARCH_HITS_ARE_WHOLE = AppleEmailClient.SEARCH_HITS_ARE_WHOLE
            hits = [_imap_whole_hit()]
        else:
            client.SEARCH_HITS_ARE_WHOLE = MicrosoftOutlookClient.SEARCH_HITS_ARE_WHOLE
            hits = [_graph_message(listing=True)]
            client.get_message = AsyncMock(return_value=_graph_message(listing=False))
        client.search_emails = AsyncMock(return_value={"messages": hits})
        return client

    @pytest.mark.parametrize("provider", ["google", "apple", "microsoft"])
    async def test_the_card_is_whole_and_the_model_reads_no_body(self, provider: str) -> None:
        from uuid import uuid4

        tool = GetEmailsTool()
        result = await tool.execute_api_call(
            self._client(provider), uuid4(), query="in:inbox", detail="metadata"
        )
        output = tool.format_registry_response(result)

        html = generate_html_for_registry(output.registry_updates, user_language="en")
        seen_by_model = extract_data_for_llm(output)
        assert "WITHHELD_BODY_MARKER" in html
        assert "quote.pdf" in html
        assert "WITHHELD_BODY_MARKER" not in seen_by_model
        assert "quote.pdf" in seen_by_model, "the manifest publishes attachments at metadata"
