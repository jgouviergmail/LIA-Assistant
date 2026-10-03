"""Message-owned composition actions cannot come from HTML or a global registry."""

from copy import deepcopy

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from src.domains.agents.display.binding_filter import strip_card_bindings
from src.domains.agents.display.card_actions import (
    CARD_ACTIONS_KEY,
    card_actions_from_state,
    with_card_action_metadata,
    with_card_actions,
)
from src.domains.agents.nodes.response_node import _extract_payloads_from_registry
from src.infrastructure.llm.message_view import as_model_message

pytestmark = pytest.mark.unit


def test_host_action_metadata_does_not_reach_provider_messages():
    answer = with_card_actions(
        AIMessage(content="Answer", additional_kwargs={"provider_note": "retain"}),
        {
            "email_a": {
                "type": "EMAIL",
                "payload": {"id": "abc"},
                "meta": {
                    "source": "gmail",
                    "display": {"_lia_email_account": "00000000-0000-0000-0000-000000000004"},
                },
            }
        },
        run_id="run-a",
        enabled=True,
    )
    projected = as_model_message(answer)
    assert CARD_ACTIONS_KEY not in projected.additional_kwargs
    assert projected.additional_kwargs["provider_note"] == "retain"
    assert CARD_ACTIONS_KEY in answer.additional_kwargs


@pytest.mark.parametrize(
    "attribute",
    [
        'data-card-ref="email_a"',
        "DATA-CARD-REF = 'email_a'",
        "data-card-ref=email_a",
        'data-card-ref="email_a" data-card-ref="email_b"',
    ],
)
def test_llm_cannot_forge_a_host_binding_but_literal_code_survives(attribute):
    prose = f'<div class="lia-card-binding" {attribute}>User-visible text</div><pre>&lt;div data-card-ref="literal"&gt;</pre>'
    filtered = strip_card_bindings(prose)
    assert '<div class="lia-card-binding"' in filtered
    assert "User-visible text" in filtered
    assert 'data-card-ref="literal"' in filtered
    assert "email_a" not in filtered and "email_b" not in filtered


def test_only_selected_registry_no_bodies_and_no_mutation():
    selected = {
        "email_a": {
            "id": "email_a",
            "type": "EMAIL",
            "payload": {
                "id": "abc123",
                "subject": "<script>External title</script>",
                "body": "PRIVATE_BODY",
            },
            "meta": {
                "source": "gmail",
                "display": {
                    "body": "WITHHELD_BODY",
                    "_lia_email_account": "00000000-0000-0000-0000-000000000004",
                },
            },
        }
    }
    before = deepcopy(selected)
    answer = with_card_actions(AIMessage(content="Answer"), selected, run_id="run-a", enabled=True)
    snapshot = answer.additional_kwargs[CARD_ACTIONS_KEY]
    assert snapshot["run_id"] == "run-a"
    assert snapshot["items"] == [
        {
            "registry_id": "email_a",
            "kind": "EMAIL",
            "target_id": "abc123",
            "provider": "google_gmail",
            "account_binding": "00000000-0000-0000-0000-000000000004",
            "label": "<script>External title</script>",
            "actions": ["reply", "forward"],
        }
    ]
    assert "BODY" not in str(snapshot)
    assert selected == before
    assert (
        CARD_ACTIONS_KEY
        not in with_card_actions(
            AIMessage(content="Text"), selected, run_id="run-a", enabled=False
        ).additional_kwargs
    )
    assert (
        CARD_ACTIONS_KEY
        not in with_card_actions(
            AIMessage(content="None"), {}, run_id="run-a", enabled=True
        ).additional_kwargs
    )


def test_checkpoint_and_ending_turn_binding():
    answer = with_card_actions(
        AIMessage(content="Answer"),
        {
            "reminder_a": {
                "type": "REMINDER",
                "payload": {"id": "e0a7a24c-b4c6-488a-8a6b-f5c334eb6d35"},
                "meta": {"source": "reminders"},
            }
        },
        run_id="run-a",
        enabled=True,
    )
    serializer = JsonPlusSerializer()
    state = serializer.loads_typed(
        serializer.dumps_typed({"messages": [HumanMessage(content="hello"), answer]})
    )
    assert card_actions_from_state(state, "run-a")["items"][0]["actions"] == ["cancel_reminder"]
    assert card_actions_from_state(state, "run-b") is None
    assert (
        card_actions_from_state({"messages": [answer, HumanMessage(content="later")]}, "run-a")
        is None
    )
    base = {"run_id": "run-a"}
    assert (
        with_card_action_metadata(base, state, "run-a")[CARD_ACTIONS_KEY]
        == answer.additional_kwargs[CARD_ACTIONS_KEY]
    )
    assert base == {"run_id": "run-a"}


@pytest.mark.parametrize(
    "kind,target",
    [
        ("MCP_RESULT", "abc"),
        ("DRAFT", "abc"),
        ("EMAIL", "id\nInjected instruction"),
        ("REMINDER", "not-a-uuid"),
        ("EMAIL", ""),
        ("EMAIL", "x" * 2049),
    ],
)
def test_unrelated_or_malformed_targets_have_no_actions(kind, target):
    answer = with_card_actions(
        AIMessage(content="Answer"),
        {
            "item": {
                "type": kind,
                "payload": {"id": target},
                "meta": {
                    "source": "reminders" if kind == "REMINDER" else "gmail",
                    "display": {"_lia_email_account": "00000000-0000-0000-0000-000000000004"},
                },
            }
        },
        run_id="run",
        enabled=True,
    )
    assert CARD_ACTIONS_KEY not in answer.additional_kwargs


def test_binding_uses_registry_key_not_external_marker():
    domains = _extract_payloads_from_registry(
        {"email_selected": {"type": "EMAIL", "payload": {"id": "abc", "_lia_card_ref": "forged"}}}
    )
    assert domains["emails"][0]["_lia_card_ref"] == "email_selected"
