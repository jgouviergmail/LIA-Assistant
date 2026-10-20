"""Every domain-agent provider call revalidates persisted SMS evidence."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.graphs.sms_agent_builder import build_sms_agent
from src.domains.agents.sms.live_authority import SmsLiveAuthority
from src.domains.agents.sms.projection import project_page
from src.domains.agents.tools.sms_tools import sms_output
from src.domains.sms.read_schemas import SmsPage, SmsView
from tests.unit.domains.agents.graphs.test_base_agent_builder_invocation import (
    _captured_prompts,
    _CapturingChatModel,
)


@pytest.mark.parametrize("allowed", [True, False])
async def test_real_compiled_domain_call_rechecks_sms_consent_before_model(allowed):
    owner, identity = uuid4(), uuid4()
    body = "PRIVATE_SMS_FOR_CURRENT_DOMAIN_CALL"
    page = project_page(
        SmsPage(
            items=[
                SmsView(
                    id=identity,
                    sender="Alice",
                    display_name="Alice",
                    body=body,
                    received_at=datetime.now(UTC),
                    date_kind="received",
                    origin="iphone",
                )
            ],
            total=1,
            revision=7,
            as_of=datetime.now(UTC),
        ),
        owner=owner,
    )
    output = sms_output(page, "list_sms_tool")
    messages = [
        HumanMessage(content="Read the SMS"),
        AIMessage(
            content="",
            tool_calls=[{"id": "sms-call", "name": "list_sms_tool", "args": {"request": {}}}],
        ),
        ToolMessage(content=str(output), name="list_sms_tool", tool_call_id="sms-call"),
    ]
    live = SmsLiveAuthority(owner=owner, revision=7, ids=frozenset({identity})) if allowed else None
    check = AsyncMock(return_value=live)
    _captured_prompts.clear()
    with (
        patch(
            "src.domains.agents.graphs.base_agent_builder.get_llm",
            return_value=_CapturingChatModel(),
        ),
        patch("src.domains.agents.sms.state_policy.load_sms_authority", check),
    ):
        agent = build_sms_agent()
        context = LiaRuntimeContext(
            user_id=owner, thread_id=str(uuid4()), conversation_id=str(uuid4())
        )
        await agent.ainvoke(
            {"messages": messages},
            context=context,
            config={"configurable": {"thread_id": context.thread_id}},
        )
    seen = " ".join(str(item.content) for item in _captured_prompts[-1])
    assert (body in seen) == allowed
    _captured_prompts.clear()


async def test_summarizer_never_creates_persistent_copies_of_sms():
    from src.domains.agents.sms.model_middleware import SmsSafeSummarization

    _captured_prompts.clear()
    middleware = SmsSafeSummarization(
        model=_CapturingChatModel(), trigger=("tokens", 1), keep=("messages", 1)
    )
    message = ToolMessage(content="PRIVATE_SMS_IN_SUMMARY", name="list_sms_tool", tool_call_id="s")
    await middleware._acreate_summary([HumanMessage(content="public context"), message])
    assert "PRIVATE_SMS_IN_SUMMARY" not in " ".join(
        str(item.content) for item in _captured_prompts[-1]
    )
    _captured_prompts.clear()


def test_360_sms_wrapper_preserves_other_bounded_relation_evidence():
    from src.domains.agents.sms.model_output import SmsModelToolOutput

    page = project_page(
        SmsPage(items=[], total=0, revision=7, as_of=datetime.now(UTC)), owner=uuid4()
    )
    output = SmsModelToolOutput.data_success(
        message="360 overview",
        structured_data={
            "sms_archive": page.model_dump(mode="json"),
            "emails": [{"subject": "OTHER_RELATION_EVIDENCE"}],
        },
    )
    assert "OTHER_RELATION_EVIDENCE" in str(output)
