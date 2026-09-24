"""The context store keeps a list as it was shown, up to the connectors' ceiling.

A list saved for reference resolution (« the 4th », « that one ») is capped by the
connectors' per-request ceiling — the largest page a list tool can return — so a
native list is never cut. A longer list keeps its FIRST items under the numbers
they were shown with: the former 70 %-recent / 30 %-confidence cut kept events
1-3 and 9-15 of a 15-event agenda and renumbered them 1..10, so « the 4th » resolved
to the 9th event (measured 2026-09-23).
"""

from collections.abc import Iterator
from typing import Any
from unittest.mock import patch

import pytest
from langgraph.store.memory import InMemoryStore

from src.core.config import settings
from src.domains.agents.context import (
    ContextTypeDefinition,
    ContextTypeRegistry,
    ToolContextManager,
)

pytestmark = pytest.mark.unit

_DOMAIN = "events_cap_test"


@pytest.fixture(autouse=True)
def _register_domain() -> Iterator[None]:
    if _DOMAIN not in ContextTypeRegistry._registry:
        ContextTypeRegistry.register(
            ContextTypeDefinition(
                domain=_DOMAIN,
                agent_name="event_agent",
                context_type=_DOMAIN,
                primary_id_field="id",
                display_name_field="summary",
                reference_fields=["summary"],
            )
        )
    yield


def _events(count: int) -> list[dict[str, Any]]:
    return [
        {"id": f"evt_{position}", "summary": f"Event {position}"}
        for position in range(1, count + 1)
    ]


async def _save_and_read(items: list[dict[str, Any]]) -> Any:
    store = InMemoryStore()
    manager = ToolContextManager()
    await manager.save_list(
        user_id="u1",
        session_id="s1",
        domain=_DOMAIN,
        items=items,
        metadata={"turn_id": 0, "timestamp": "2026-09-23T10:00:00Z"},
        store=store,
    )
    return await manager.get_list(user_id="u1", session_id="s1", domain=_DOMAIN, store=store)


class TestTheCeiling:
    async def test_a_full_page_of_the_largest_list_tool_is_kept_whole(self) -> None:
        page = _events(settings.api_max_items_per_request)

        saved = await _save_and_read(page)

        assert [item["id"] for item in saved.items] == [event["id"] for event in page]

    async def test_it_follows_the_connectors_per_request_ceiling(self) -> None:
        with patch.object(settings, "api_max_items_per_request", 3):
            saved = await _save_and_read(_events(5))

        assert len(saved.items) == 3


class TestALongerList:
    async def test_keeps_its_first_items_under_the_numbers_they_were_shown_with(self) -> None:
        with patch.object(settings, "api_max_items_per_request", 10):
            saved = await _save_and_read(_events(15))

        assert [(item["index"], item["id"]) for item in saved.items] == [
            (position, f"evt_{position}") for position in range(1, 11)
        ]

    async def test_states_the_exact_total_of_the_original_list(self) -> None:
        with patch.object(settings, "api_max_items_per_request", 10):
            saved = await _save_and_read(_events(15))

        assert saved.metadata.total_count == 15


class TestOneAuthority:
    def test_the_store_has_no_ceiling_of_its_own(self) -> None:
        assert not hasattr(settings, "tool_context_max_items")
