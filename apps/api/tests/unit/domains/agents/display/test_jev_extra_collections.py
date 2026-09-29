"""New collection sources retain source ownership, provenance and all evidence."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.domains.agents.data_registry.models import RegistryItem, RegistryItemMeta, RegistryItemType
from src.domains.agents.display import jev_qualification as module
from src.infrastructure.llm.decision_types import DecisionAttempt
from tests.unit.domains.agents.display.test_jev_qualification import answer

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "kind,usage",
    [
        ("REMINDER", "filter_reminder"),
        ("TICKET", "filter_ticket"),
        ("MCP_RESULT", "filter_mcp"),
        ("NOTE", "filter_document"),
    ],
)
async def test_each_source_owns_switch_and_keeps_its_full_payload(kind, usage):
    payload = {"title": "Review", "completed": False, "description": "Full source " * 60}
    source = "test"
    if kind == "MCP_RESULT":
        payload["_mcp_structured"] = True
        source = "mcp_synthetic"
    if kind == "NOTE":
        source = "rag_user_excerpt"
        payload["evidence_scope"] = "document_excerpt"
    item = RegistryItem(
        id="source_1",
        type=RegistryItemType(kind),
        payload=payload,
        meta=RegistryItemMeta(source=source),
    )
    original = item.model_dump()
    with patch.object(
        module,
        "choose_many_with_jev",
        AsyncMock(return_value=DecisionAttempt(outcome="success", answers={"q0": answer("match")})),
    ) as native:
        result = await module.qualify_collection(
            user_id=uuid4(), run_id="r", query="Find reviews", items=[item]
        )
    assert result is not None and result.items[0].verdict == "match"
    assert native.call_args.kwargs["usage"] == usage
    assert "False" in native.call_args.kwargs["state"]["items"]["q0"]
    assert "Full source " * 60 in native.call_args.kwargs["state"]["items"]["q0"]
    assert item.model_dump() == original


@pytest.mark.parametrize(
    "kind,payload,source",
    [
        ("NOTE", {"content": "Unrelated note"}, "test"),
        ("MCP_RESULT", {"result": "Scalar response"}, "mcp_synthetic"),
        ("MCP_APP", {"_mcp_structured": True}, "mcp_synthetic"),
        ("MCP_RESULT", {"_mcp_structured": True, "title": "Spoof"}, "test"),
    ],
)
async def test_incompatible_sources_do_not_call_native(kind, payload, source):
    item = RegistryItem(
        id="x", type=RegistryItemType(kind), payload=payload, meta=RegistryItemMeta(source=source)
    )
    with patch.object(module, "choose_many_with_jev", AsyncMock()) as native:
        assert (
            await module.qualify_collection(
                user_id=uuid4(), run_id="r", query="Anything", items=[item]
            )
            is None
        )
    native.assert_not_awaited()


def test_document_projection_is_ephemeral_and_cannot_claim_a_whole_document():
    from src.domains.agents.display.document_preview import document_preview_registry
    from src.domains.rag_spaces.retrieval import RAGContext, RAGRetrievedChunk

    context = RAGContext(
        chunks=[
            RAGRetrievedChunk(
                content="Evidence " * 120,
                score=0.8,
                space_name="Private",
                original_filename="contract.pdf",
                chunk_index=2,
            )
        ]
    )
    registry = document_preview_registry(context)
    item = next(iter(registry.values()))
    assert item.payload["content"] == context.chunks[0].content
    assert item.payload["evidence_scope"] == "document_excerpt"
    assert item.meta.source == "rag_user_excerpt"
    assert item.payload["title"] == "contract.pdf"
    assert set(document_preview_registry(context)) == set(registry)
    assert document_preview_registry(RAGContext(chunks=context.chunks, context_type="system")) == {}


async def test_mcp_arbitrary_schema_keeps_metadata_and_raw_fields_as_evidence():
    item = RegistryItem(
        id="m",
        type=RegistryItemType.MCP_RESULT,
        payload={
            "_mcp_structured": True,
            "title": "Sample",
            "metadata": {"owner": "Lina"},
            "raw_material": "steel",
        },
        meta=RegistryItemMeta(source="mcp_sample"),
    )
    with patch.object(
        module, "choose_many_with_jev", AsyncMock(return_value=DecisionAttempt(outcome="timeout"))
    ) as native:
        await module.qualify_collection(
            user_id=uuid4(), run_id="r", query="Steel samples owned by Lina", items=[item]
        )
    evidence = native.call_args.kwargs["state"]["items"]["q0"]
    assert "Lina" in evidence and "steel" in evidence


async def test_document_preview_reuses_authorized_fetch_and_preserves_prompt_when_projection_fails():
    from contextlib import asynccontextmanager

    from src.domains.agents.display import document_preview
    from src.domains.agents.services.response_context import fetch_user_rag_context
    from src.domains.rag_spaces.retrieval import RAGContext, RAGRetrievedChunk
    from tests.helpers.runtime_context import installed_runtime_context

    owner = uuid4()
    context = RAGContext(
        chunks=[RAGRetrievedChunk("Complete chunk", 0.8, "Private", "contract.pdf", 0)]
    )

    @asynccontextmanager
    async def db_context():
        yield object()

    with (
        installed_runtime_context(user_id=owner, thread_id="t"),
        patch("src.core.config.settings.rag_spaces_enabled", True),
        patch("src.infrastructure.database.session.get_db_context", db_context),
        patch(
            "src.domains.rag_spaces.retrieval.retrieve_rag_context", AsyncMock(return_value=context)
        ) as retrieve,
    ):
        previews = {}
        text, _ = await fetch_user_rag_context(
            config={"configurable": {"thread_id": "t"}},
            last_user_message="Contracts",
            run_id="r",
            preview_items=previews,
        )
        assert text == context.to_prompt_context() and len(previews) == 1
        assert retrieve.await_count == 1 and retrieve.call_args.kwargs["user_id"] == owner
        with patch.object(document_preview, "_project", side_effect=ValueError("unavailable")):
            more = {}
            same, _ = await fetch_user_rag_context(
                config={}, last_user_message="Contracts", run_id="r", preview_items=more
            )
            assert same == text and more == {}


async def test_mixed_collection_publisher_keeps_domains_and_skips_incompatible_mcp():
    from src.domains.agents.display import collection_preview
    from src.domains.agents.display.collection_preview import _publish

    sources = {}
    for kind in [RegistryItemType.REMINDER, RegistryItemType.TICKET, RegistryItemType.MCP_RESULT]:
        sources[kind.value] = RegistryItem(
            id=kind.value, type=kind, payload={"title": "A"}, meta=RegistryItemMeta(source="test")
        )
    with patch.object(
        collection_preview, "qualify_collection", AsyncMock(return_value=None)
    ) as native:
        await _publish(lambda _: None, uuid4(), "r", "Items", sources)
    assert {call.kwargs["items"][0].type for call in native.call_args_list} == {
        RegistryItemType.REMINDER,
        RegistryItemType.TICKET,
    }
