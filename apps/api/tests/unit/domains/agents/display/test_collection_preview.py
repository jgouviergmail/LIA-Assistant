"""A preview belongs to its response lifetime and never delays that response."""

import asyncio
import importlib
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.data_registry.models import RegistryItem, RegistryItemMeta, RegistryItemType
from src.domains.agents.display.jev_qualification import QualifiedCollection

pytestmark = pytest.mark.unit


def registry() -> dict[str, RegistryItem]:
    return {
        "email_1": RegistryItem(
            id="email_1",
            type=RegistryItemType.EMAIL,
            payload={"subject": "A contract"},
            meta=RegistryItemMeta(source="test", domain="email"),
        )
    }


async def test_result_is_emitted_before_response_completion_with_trusted_owner() -> None:
    module = importlib.import_module("src.domains.agents.display.collection_preview")
    owner = uuid4()
    events = []
    result = QualifiedCollection(
        kind=RegistryItemType.EMAIL, items=[], candidate_count=1, evaluated_count=1, omitted_count=0
    )
    state = {
        "query_intelligence": {
            "english_query": "Contracts",
            "immediate_intent": "search",
            "is_mutation_intent": False,
        }
    }
    with (
        patch.object(
            module,
            "runtime_context_if_running",
            return_value=LiaRuntimeContext(
                user_id=owner,
                thread_id="t",
                conversation_id="t",
                browser_context={"viewport": "desktop"},
            ),
        ),
        patch.object(module, "get_stream_writer", return_value=events.append),
        patch.object(module, "qualify_collection", AsyncMock(return_value=result)) as native,
    ):
        preview = module.CollectionPreview()
        preview.start(
            state, {key: value.model_dump(mode="json") for key, value in registry().items()}, "run"
        )
        await asyncio.sleep(0.01)
        assert events[0]["type"] == "result_preview"
        assert events[0]["metadata"]["collection"] == result.model_dump(mode="json")
        assert native.call_args.kwargs["user_id"] == owner
        assert native.call_args.kwargs["query"] == "Contracts"
        await preview.close()


async def test_closing_response_cancels_and_joins_unfinished_preview() -> None:
    module = importlib.import_module("src.domains.agents.display.collection_preview")
    entered, stopped = asyncio.Event(), asyncio.Event()

    async def blocked(**kwargs):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    with (
        patch.object(
            module,
            "runtime_context_if_running",
            return_value=LiaRuntimeContext(
                user_id=uuid4(),
                thread_id="t",
                conversation_id="t",
                browser_context={"viewport": "desktop"},
            ),
        ),
        patch.object(module, "get_stream_writer", return_value=lambda _: None),
        patch.object(module, "qualify_collection", side_effect=blocked),
    ):
        preview = module.CollectionPreview()
        preview.start(
            {"query_intelligence": {"english_query": "Contracts", "immediate_intent": "search"}},
            registry(),
            "run",
        )
        await asyncio.wait_for(entered.wait(), 0.5)
        await asyncio.wait_for(preview.close(), 0.5)
        assert stopped.is_set()


@pytest.mark.parametrize(
    "qi",
    [
        {},
        {"english_query": "Send a contract", "immediate_intent": "send"},
        {
            "english_query": "Find and delete",
            "immediate_intent": "search",
            "is_mutation_intent": True,
        },
    ],
)
async def test_unqualified_intent_makes_no_call(qi) -> None:
    module = importlib.import_module("src.domains.agents.display.collection_preview")
    with (
        patch.object(
            module,
            "runtime_context_if_running",
            return_value=LiaRuntimeContext(
                user_id=uuid4(),
                thread_id="t",
                conversation_id="t",
                browser_context={"viewport": "desktop"},
            ),
        ),
        patch.object(module, "get_stream_writer", return_value=lambda _: None),
        patch.object(module, "qualify_collection", AsyncMock()) as native,
    ):
        preview = module.CollectionPreview()
        preview.start({"query_intelligence": qi}, registry(), "run")
        await preview.close()
    native.assert_not_called()


async def test_a_channel_without_a_browser_does_not_spend_on_an_invisible_preview() -> None:
    module = importlib.import_module("src.domains.agents.display.collection_preview")
    with (
        patch.object(
            module,
            "runtime_context_if_running",
            return_value=LiaRuntimeContext(user_id=uuid4(), thread_id="t", conversation_id="t"),
        ),
        patch.object(module, "get_stream_writer", return_value=lambda _: None),
        patch.object(module, "qualify_collection", AsyncMock()) as native,
    ):
        preview = module.CollectionPreview()
        preview.start(
            {"query_intelligence": {"english_query": "Mail", "immediate_intent": "search"}},
            registry(),
            "run",
        )
        await asyncio.sleep(0.01)
        await preview.close()
    native.assert_not_awaited()


async def test_no_stream_writer_preserves_the_ordinary_response() -> None:
    module = importlib.import_module("src.domains.agents.display.collection_preview")
    with (
        patch.object(
            module,
            "runtime_context_if_running",
            return_value=LiaRuntimeContext(
                user_id=uuid4(), thread_id="t", conversation_id="t", browser_context={}
            ),
        ),
        patch.object(
            module, "get_stream_writer", side_effect=RuntimeError("not in streaming graph")
        ),
    ):
        preview = module.CollectionPreview()
        preview.start(
            {"query_intelligence": {"english_query": "Mail", "immediate_intent": "search"}},
            registry(),
            "run",
        )
        await preview.close()
