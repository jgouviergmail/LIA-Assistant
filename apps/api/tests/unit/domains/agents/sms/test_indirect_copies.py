"""360-degree source copies obey the same withdrawal contract as SMS tools."""

from uuid import uuid4

from langchain_core.messages import HumanMessage, ToolMessage

from src.domains.agents.sms.proof import SmsSnapshotProof
from src.domains.agents.sms.state_policy import filter_sms_state


def test_person_overview_sms_proof_is_removed_before_another_provider_call():
    owner, identity = uuid4(), uuid4()
    proof = SmsSnapshotProof(owner=owner, revision=1, ids=[identity]).model_dump_json()
    state = {
        "messages": [
            HumanMessage(content="360"),
            ToolMessage(
                content="private SMS inside 360",
                name="get_person_overview_tool",
                tool_call_id="360",
                response_metadata={"sms_snapshot": proof},
            ),
        ]
    }
    clean = filter_sms_state(state, None)
    assert "private SMS" not in clean["messages"][1].content
    assert clean["messages"][1].status == "error"


def test_sms_in_person_result_never_enters_automatic_memory_extraction():
    from src.domains.agents.services.memory_extraction_context import format_messages_for_extraction

    message = ToolMessage(
        content="private indirect SMS",
        tool_call_id="360",
        name="get_person_overview_tool",
        response_metadata={"sms_snapshot": "proof"},
    )
    assert "private indirect SMS" not in format_messages_for_extraction([message])


def test_oversized_context_copy_cannot_hide_its_sms_proof():
    from src.domains.agents.sms.message_policy import source_message

    message = ToolMessage(
        content='{"sms_messages":[] , "padding":"' + "x" * 262144 + '"}',
        name="get_context_list",
        tool_call_id="large",
    )
    assert source_message(message).response_metadata.get("sms_snapshot") == "invalid"
