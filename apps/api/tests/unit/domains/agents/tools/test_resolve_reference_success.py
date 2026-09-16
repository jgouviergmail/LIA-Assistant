"""``resolve_reference`` on its SUCCESS path.

It returned ``UnifiedToolOutput.action_success(data=…)`` — a keyword the
constructor never had — so every successful resolution raised ``TypeError``
("Erreur interne : TypeError" to the model) from v1.0.0 to 2026-09-15. The
registry smoke test invokes every tool with minimal arguments and therefore
only ever reached the 'no context' branch, which is why nothing caught it
(ADR-286).
"""

from __future__ import annotations

import pytest
from langgraph.store.memory import InMemoryStore

from src.domains.agents.context.manager import ToolContextManager
from src.domains.agents.context.registry import ContextTypeDefinition, ContextTypeRegistry
from src.domains.agents.tools.context_tools import resolve_reference
from src.domains.agents.tools.output import UnifiedToolOutput
from tests.helpers.runtime_context import make_tool_runtime

pytestmark = [pytest.mark.unit]

DOMAIN = "emails_resolve_success_test"
THREAD = "thread-resolve-success"


@pytest.fixture(autouse=True)
def _domain() -> None:
    if DOMAIN not in ContextTypeRegistry._registry:
        ContextTypeRegistry.register(
            ContextTypeDefinition(
                domain=DOMAIN,
                agent_name="email_agent",
                context_type=DOMAIN,
                primary_id_field="message_id",
                display_name_field="subject",
                reference_fields=["subject"],
            )
        )


async def _seeded_runtime(store: InMemoryStore):  # type: ignore[no-untyped-def]
    runtime = make_tool_runtime(store=store, thread_id=THREAD)
    await ToolContextManager().save_list(
        user_id=str(runtime.context.user_id),
        session_id=THREAD,
        domain=DOMAIN,
        items=[
            {"message_id": "m1", "subject": "Premier"},
            {"message_id": "m2", "subject": "Second"},
        ],
        metadata={"turn_id": 1, "total_count": 2, "timestamp": "2026-09-15T12:00:00Z"},
        store=store,
    )
    return runtime


async def _resolve(reference: str, runtime: object) -> UnifiedToolOutput:
    """Call the tool the way the ReAct node does: through its coroutine."""
    assert resolve_reference.coroutine is not None
    result = await resolve_reference.coroutine(reference=reference, runtime=runtime, domain=DOMAIN)
    assert isinstance(result, UnifiedToolOutput)
    return result


async def test_an_ordinal_resolves_to_the_item() -> None:
    runtime = await _seeded_runtime(InMemoryStore())

    result = await _resolve("2", runtime)

    assert isinstance(result, UnifiedToolOutput)
    assert result.success is True, result.message
    assert result.structured_data is not None
    assert result.structured_data["item"]["message_id"] == "m2"
    assert result.structured_data["match_type"] == "index"


async def test_a_name_resolves_by_fuzzy_match() -> None:
    runtime = await _seeded_runtime(InMemoryStore())

    result = await _resolve("Premier", runtime)

    assert result.success is True, result.message
    assert result.structured_data is not None
    assert result.structured_data["item"]["message_id"] == "m1"
