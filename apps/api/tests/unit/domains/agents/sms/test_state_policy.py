"""Source copies from a checkpoint never bypass live consent or erasure."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from src.domains.agents.nodes.react_result_reading import tool_message_metadata
from src.domains.agents.sms.projection import project_page
from src.domains.agents.sms.state_policy import SmsLiveAuthority, filter_sms_state
from src.domains.agents.tools.sms_tools import sms_output
from src.domains.sms.read_schemas import SmsPage, SmsView


@pytest.mark.parametrize("allowed", [True, False])
def test_checkpoint_registry_results_and_messages_share_one_live_authority(allowed):
    owner = uuid4()
    identity = uuid4()
    view = SmsView(
        id=identity,
        sender="Alice",
        display_name="Alice",
        body="private SMS body",
        received_at=datetime.now(UTC),
        date_kind="received",
        origin="iphone",
    )
    page = project_page(
        SmsPage(items=[view], total=1, as_of=datetime.now(UTC), revision=3), owner=owner
    )
    output = sms_output(page, "get_sms_tool")
    metadata = tool_message_metadata(output)
    assert "sms_snapshot" in metadata
    state = {
        "messages": [
            HumanMessage(content="Bonjour"),
            ToolMessage(
                content="private SMS body",
                tool_call_id="call",
                name="get_sms_tool",
                response_metadata=metadata,
            ),
        ],
        "registry": output.registry_updates,
        "current_turn_registry": output.registry_updates,
        "agent_results": {"1:sms_agent": {"data": output.model_dump(mode="json")}},
        "tool_results": [{"tool_name": "get_sms_tool", "result": output.model_dump(mode="json")}],
        "resolved_context": {
            "source_domain": "sms_messages",
            "items": [page.sms_messages[0].model_dump(mode="json")],
        },
    }
    serializer = JsonPlusSerializer()
    restored = serializer.loads_typed(serializer.dumps_typed(state))
    authority = (
        SmsLiveAuthority(owner=owner, revision=3, ids=frozenset({identity})) if allowed else None
    )
    clean = filter_sms_state(restored, authority)
    assert clean["messages"][0].content == "Bonjour"
    serialized = str(clean)
    assert ("private SMS body" in serialized) is allowed
    assert len(clean["registry"]) == (1 if allowed else 0)
    assert "private SMS body" in str(
        restored
    ), "The stored checkpoint must not be mutated by a prompt projection"


def test_named_sms_tool_result_without_proof_is_never_trusted():
    clean = filter_sms_state(
        {
            "messages": [
                ToolMessage(content="private stale SMS", tool_call_id="x", name="search_sms_tool")
            ]
        },
        None,
    )
    assert "private stale SMS" not in str(clean)


def test_empty_result_still_has_live_owner_and_revision_proof():
    owner = uuid4()
    page = project_page(
        SmsPage(items=[], total=0, as_of=datetime.now(UTC), revision=3), owner=owner
    )
    output = sms_output(page, "search_sms_tool")
    assert tool_message_metadata(output).get("sms_snapshot")


def test_withdrawal_removes_even_empty_page_metadata():
    state = {
        "messages": [],
        "agent_results": {},
        "tool_results": [
            {
                "tool_name": "search_sms_tool",
                "result": {"sms_messages": [], "total": 42, "next_cursor": "private_cursor"},
            }
        ],
    }
    assert "private_cursor" not in str(filter_sms_state(state, None))


@pytest.mark.asyncio
async def test_malformed_sms_registry_cannot_bypass_the_provider_guard(monkeypatch):
    from src.domains.agents.sms import state_policy

    owner = uuid4()

    async def authority(*args):
        return SmsLiveAuthority(owner=owner, revision=0, ids=frozenset())

    monkeypatch.setattr(state_policy, "runtime_user_id_str", lambda default: str(owner))
    monkeypatch.setattr(state_policy, "load_sms_authority", authority)
    state = {
        "messages": [],
        "registry": {
            "sms_bad": {"type": "SMS", "payload": {"body": "untrusted malformed private SMS"}}
        },
    }
    assert "untrusted malformed private SMS" not in str(await state_policy.guard_sms_state(state))


@pytest.mark.parametrize("allowed", [True, False])
def test_serialized_query_intelligence_preserves_only_current_ordinal_evidence(allowed):
    from src.domains.agents.analysis.query_intelligence import QueryIntelligence, UserGoal
    from src.domains.agents.services.reference_resolver import ResolvedContext

    owner = uuid4()
    identity = uuid4()
    view = SmsView(
        id=identity,
        sender="Alice",
        display_name="Alice",
        body="Exact ordinal SMS",
        received_at=datetime.now(UTC),
        date_kind="received",
        origin="iphone",
    )
    page = project_page(
        SmsPage(items=[view], total=1, as_of=datetime.now(UTC), revision=3), owner=owner
    )
    context = ResolvedContext(
        items=[page.sms_messages[0].model_dump(mode="json")],
        confidence=1,
        method="explicit",
        source_turn_id=1,
        source_domain="sms_messages",
    )
    qi = QueryIntelligence(
        original_query="Le deuxième",
        english_query="The second",
        immediate_intent="read",
        immediate_confidence=1,
        user_goal=UserGoal.UNDERSTAND,
        goal_reasoning="Read selected source",
        resolved_context=context,
        source_domain="sms_messages",
    )
    state = {
        "messages": [],
        "query_intelligence": qi.to_serializable_dict(),
        "resolved_context": context.to_dict(),
    }
    authority = (
        SmsLiveAuthority(owner=owner, revision=3, ids=frozenset({identity})) if allowed else None
    )
    clean = filter_sms_state(state, authority)
    assert clean["query_intelligence"]["english_query"] == "The second"
    assert ("Exact ordinal SMS" in str(clean)) is allowed
