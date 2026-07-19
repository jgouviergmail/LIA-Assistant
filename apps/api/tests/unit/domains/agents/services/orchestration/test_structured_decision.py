"""Unit tests: ``build_structured_decision`` (Lot 1 T1.2/T1.3 — option B).

One-click HITL approvals send a structured ``hitl_decision`` instead of
natural language. This builder maps it DETERMINISTICALLY to the exact resume
payload each interrupt kind expects — no LLM classifier call — and fails
CLOSED: any stale/mismatched/unsupported input raises
``HitlDecisionStaleError`` (the caller emits a typed error chunk; the message
is never processed as a new turn).

V1 scope: actions ``confirm``/``cancel`` only. Structured edit
(``updated_content``) is P1-V2 and must stay rejected until the draft node
path is verified for it.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.field_names import (
    FIELD_ACTION_REQUESTS,
    FIELD_DRAFT_ID,
    FIELD_INTERRUPT_DATA,
    FIELD_TYPE,
)
from src.domains.agents.services.orchestration.approval_decision import (
    HitlDecisionStaleError,
    build_structured_decision,
)

MESSAGE_ID = "hitl_conv_abc123"


def _pending(
    interrupt_type: str | None, *, draft_id: str | None = None, message_id: str | None = MESSAGE_ID
) -> dict | None:
    if interrupt_type is None:
        return None
    action: dict = {FIELD_TYPE: interrupt_type}
    if draft_id is not None:
        action[FIELD_DRAFT_ID] = draft_id
    data: dict = {FIELD_INTERRUPT_DATA: {FIELD_ACTION_REQUESTS: [action]}}
    if message_id is not None:
        data[FIELD_INTERRUPT_DATA]["message_id"] = message_id
    return data


async def _build(decision: dict, pending: dict | None) -> dict:
    store = MagicMock()
    store.get_interrupt = AsyncMock(return_value=pending)
    with (
        patch(
            "src.infrastructure.cache.redis.get_redis_cache",
            new=AsyncMock(return_value=MagicMock()),
        ),
        patch("src.domains.agents.utils.HITLStore", return_value=store),
    ):
        return await build_structured_decision(
            hitl_decision=decision, conversation_id=uuid4(), run_id="test"
        )


class TestMappingMatrix:
    async def test_tool_confirmation_confirm(self):
        result = await _build(
            {"message_id": MESSAGE_ID, "action": "confirm"}, _pending("tool_confirmation")
        )
        assert result == {"action": "confirm"}

    async def test_tool_confirmation_cancel(self):
        result = await _build(
            {"message_id": MESSAGE_ID, "action": "cancel"}, _pending("tool_confirmation")
        )
        assert result == {"action": "cancel"}

    async def test_draft_confirm_carries_draft_id(self):
        result = await _build(
            {"message_id": MESSAGE_ID, "action": "confirm"},
            _pending("draft_critique", draft_id="d1"),
        )
        assert result == {"action": "confirm", "draft_id": "d1"}

    async def test_draft_cancel_carries_draft_id_and_reason(self):
        result = await _build(
            {"message_id": MESSAGE_ID, "action": "cancel"},
            _pending("draft_critique", draft_id="d1"),
        )
        assert result["action"] == "cancel"
        assert result["draft_id"] == "d1"
        assert result["reason"]

    async def test_destructive_confirm_maps_to_plan_approve(self):
        result = await _build(
            {"message_id": MESSAGE_ID, "action": "confirm"}, _pending("destructive_confirm")
        )
        assert result == {"decision": "APPROVE"}

    async def test_destructive_cancel_maps_to_plan_reject(self):
        result = await _build(
            {"message_id": MESSAGE_ID, "action": "cancel"}, _pending("destructive_confirm")
        )
        assert result["decision"] == "REJECT"
        assert result["rejection_reason"]

    async def test_for_each_confirm_maps_to_plan_approve(self):
        result = await _build(
            {"message_id": MESSAGE_ID, "action": "confirm"}, _pending("for_each_confirmation")
        )
        assert result == {"decision": "APPROVE"}

    async def test_wire_action_aliases_are_canonicalized(self):
        # destructive_confirm emits action id "confirm_delete"; the legacy
        # for_each STANDARD set defines "confirm_all" — the frontend passes
        # wire ids through verbatim, the server canonicalizes.
        destructive = await _build(
            {"message_id": MESSAGE_ID, "action": "confirm_delete"},
            _pending("destructive_confirm"),
        )
        assert destructive == {"decision": "APPROVE"}

        for_each = await _build(
            {"message_id": MESSAGE_ID, "action": "confirm_all"},
            _pending("for_each_confirmation"),
        )
        assert for_each == {"decision": "APPROVE"}

    async def test_clarification_cancel_maps_to_abort(self):
        result = await _build(
            {"message_id": MESSAGE_ID, "action": "cancel"}, _pending("clarification")
        )
        assert result == {"clarification": "", "cancelled": True}


class TestFailClosed:
    async def test_no_pending_raises_stale(self):
        with pytest.raises(HitlDecisionStaleError):
            await _build({"message_id": MESSAGE_ID, "action": "confirm"}, None)

    async def test_message_id_mismatch_raises_stale(self):
        with pytest.raises(HitlDecisionStaleError):
            await _build(
                {"message_id": "hitl_other", "action": "confirm"},
                _pending("tool_confirmation", message_id=MESSAGE_ID),
            )

    async def test_legacy_pending_without_message_id_is_tolerated(self):
        result = await _build(
            {"message_id": MESSAGE_ID, "action": "confirm"},
            _pending("tool_confirmation", message_id=None),
        )
        assert result == {"action": "confirm"}

    async def test_unsupported_action_raises_stale(self):
        with pytest.raises(HitlDecisionStaleError):
            await _build(
                {"message_id": MESSAGE_ID, "action": "limit"},
                _pending("for_each_confirmation"),
            )

    async def test_clarification_confirm_is_rejected(self):
        with pytest.raises(HitlDecisionStaleError):
            await _build({"message_id": MESSAGE_ID, "action": "confirm"}, _pending("clarification"))


class TestStructuredEdit:
    """P1-V2: structured edit routes the LIVE draft path (modification
    instructions -> draft_modifier LLM loop). ``updated_content`` (per-field
    edit without LLM) remains dead code on the whole chain and stays
    rejected."""

    async def test_draft_edit_with_instructions_maps_to_live_edit_payload(self):
        result = await _build(
            {
                "message_id": MESSAGE_ID,
                "action": "edit",
                "modification_instructions": "Change le sujet en 'Bonjour'",
            },
            _pending("draft_critique", draft_id="d1"),
        )
        assert result == {
            "action": "edit",
            "draft_id": "d1",
            "modification_instructions": "Change le sujet en 'Bonjour'",
        }

    async def test_draft_edit_without_instructions_is_rejected(self):
        with pytest.raises(HitlDecisionStaleError):
            await _build(
                {"message_id": MESSAGE_ID, "action": "edit"},
                _pending("draft_critique", draft_id="d1"),
            )

    async def test_draft_edit_with_blank_instructions_is_rejected(self):
        with pytest.raises(HitlDecisionStaleError):
            await _build(
                {"message_id": MESSAGE_ID, "action": "edit", "modification_instructions": "   "},
                _pending("draft_critique", draft_id="d1"),
            )

    async def test_edit_on_tool_confirmation_is_rejected(self):
        with pytest.raises(HitlDecisionStaleError):
            await _build(
                {"message_id": MESSAGE_ID, "action": "edit", "modification_instructions": "x"},
                _pending("tool_confirmation"),
            )

    async def test_edit_on_destructive_confirm_is_rejected(self):
        with pytest.raises(HitlDecisionStaleError):
            await _build(
                {"message_id": MESSAGE_ID, "action": "edit", "modification_instructions": "x"},
                _pending("destructive_confirm"),
            )

    async def test_edit_with_updated_content_only_stays_rejected(self):
        """Per-field edit has no live execution path — fail-closed."""
        with pytest.raises(HitlDecisionStaleError):
            await _build(
                {"message_id": MESSAGE_ID, "action": "edit", "updated_content": {"to": "x"}},
                _pending("draft_critique", draft_id="d1"),
            )


async def _parse_nl(message: str, pending: dict | None) -> dict:
    """Run the conversational parser on the fast-path words (no classifier)."""
    from src.domains.agents.services.orchestration.approval_decision import (
        parse_approval_decision,
    )

    store = MagicMock()
    store.get_interrupt = AsyncMock(return_value=pending)
    with (
        patch(
            "src.infrastructure.cache.redis.get_redis_cache",
            new=AsyncMock(return_value=MagicMock()),
        ),
        patch("src.domains.agents.utils.HITLStore", return_value=store),
    ):
        return await parse_approval_decision(
            user_message=message, conversation_id=uuid4(), run_id="test"
        )


class TestParityWithConversationalPath:
    """T1.5: a button and its natural-language equivalent produce the same
    resume payload — the graph cannot tell them apart (single downstream
    contract, no behavioral fork)."""

    async def test_tool_confirmation_confirm_parity(self):
        nl = await _parse_nl("oui", _pending("tool_confirmation"))
        button = await _build(
            {"message_id": MESSAGE_ID, "action": "confirm"}, _pending("tool_confirmation")
        )
        assert nl == button

    async def test_tool_confirmation_cancel_parity(self):
        nl = await _parse_nl("non", _pending("tool_confirmation"))
        button = await _build(
            {"message_id": MESSAGE_ID, "action": "cancel"}, _pending("tool_confirmation")
        )
        assert nl == button

    async def test_draft_confirm_parity(self):
        nl = await _parse_nl("oui", _pending("draft_critique", draft_id="d1"))
        button = await _build(
            {"message_id": MESSAGE_ID, "action": "confirm"},
            _pending("draft_critique", draft_id="d1"),
        )
        assert nl == button

    async def test_draft_cancel_parity_modulo_reason(self):
        # The button adds an informational "reason"; action + draft_id are
        # identical — the draft node reads only those for the cancel path.
        nl = await _parse_nl("annule", _pending("draft_critique", draft_id="d1"))
        button = await _build(
            {"message_id": MESSAGE_ID, "action": "cancel"},
            _pending("draft_critique", draft_id="d1"),
        )
        assert nl["action"] == button["action"] == "cancel"
        assert nl["draft_id"] == button["draft_id"] == "d1"

    async def test_destructive_confirm_parity(self):
        nl = await _parse_nl("oui", _pending("destructive_confirm"))
        button = await _build(
            {"message_id": MESSAGE_ID, "action": "confirm"}, _pending("destructive_confirm")
        )
        assert nl == button


class TestChannelsCompatibility:
    """Channels (Telegram/WhatsApp) build ChatRequest without the new field —
    the schema default must keep their payloads valid and NL-routed."""

    def test_chat_request_defaults_hitl_decision_to_none(self):
        import uuid as uuid_mod

        from src.domains.agents.api.schemas import ChatRequest

        req = ChatRequest(message="oui", user_id=uuid_mod.uuid4(), session_id="session_x")
        assert req.hitl_decision is None
