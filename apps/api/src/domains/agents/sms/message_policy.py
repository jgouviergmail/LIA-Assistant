"""Recover server-produced SMS proofs from LangChain's persisted tool text."""

import json
from collections.abc import Mapping, Sequence

from langchain_core.messages import AnyMessage, ToolMessage
from pydantic import ValidationError

from src.domains.agents.sms.projection import SmsToolItem
from src.domains.agents.sms.proof import SmsSnapshotProof
from src.domains.agents.sms.schemas import SMS_TOOL_MODELS

_CONTEXT_TOOLS = frozenset(
    {"get_context_list", "get_context_state", "resolve_reference", "get_person_overview_tool"}
)
_MAX_CHARS = 262144


def _items(value: object) -> tuple[bool, list[SmsToolItem]]:
    pending = [value]
    found = False
    items = []
    visited = 0
    while pending:
        visited += 1
        if visited > 2000:
            return True, []
        node = pending.pop()
        if isinstance(node, list):
            pending.extend(node)
        elif isinstance(node, Mapping):
            found = found or "sms_messages" in node or node.get("domain") == "sms_messages"
            if "owner_id" in node and "body_offset" in node:
                found = True
                try:
                    items.append(
                        SmsToolItem.model_validate({k: v for k, v in node.items() if k != "index"})
                    )
                except ValidationError:
                    return True, []
            else:
                pending.extend(node.values())
    return found, items


def _proof(text: str) -> tuple[bool, str | None]:
    if len(text) > _MAX_CHARS:
        return _has_sms_marker(text), None
    start, end = text.find("{"), text.rfind("}")
    if start < 0:
        return False, None
    try:
        value: object = json.loads(text[start : end + 1])
    except ValueError, RecursionError:
        return False, None
    if isinstance(value, Mapping) and isinstance(value.get("sms_snapshot"), str):
        try:
            return (
                True,
                SmsSnapshotProof.model_validate_json(value["sms_snapshot"]).model_dump_json(),
            )
        except ValidationError:
            return True, None
    found, items = _items(value)
    owners = {item.owner_id for item in items}
    revisions = {item.revision for item in items}
    if not found or len(owners) != 1 or len(revisions) != 1 or len(items) > 50:
        return found, None
    return (
        True,
        SmsSnapshotProof(
            owner=next(iter(owners)),
            revision=next(iter(revisions)),
            ids=[item.id for item in items],
        ).model_dump_json(),
    )


def source_message(message: ToolMessage) -> ToolMessage:
    if "sms_snapshot" in message.response_metadata:
        return message
    if message.name not in SMS_TOOL_MODELS and message.name not in _CONTEXT_TOOLS:
        return message
    found, proof = _proof(str(message.text))
    if not found:
        return message
    return message.model_copy(
        update={
            "response_metadata": {**message.response_metadata, "sms_snapshot": proof or "invalid"}
        }
    )


def normalize_sms_messages(messages: Sequence[AnyMessage]) -> list[AnyMessage]:
    return [
        source_message(message) if isinstance(message, ToolMessage) else message
        for message in messages
    ]


def is_sms_source_message(message: ToolMessage) -> bool:
    return (
        message.name in SMS_TOOL_MODELS
        or "sms_snapshot" in source_message(message).response_metadata
    )


def _has_sms_marker(text: str) -> bool:
    return any(marker in text for marker in ('"sms_snapshot"', '"sms_messages"', '"body_offset"'))
