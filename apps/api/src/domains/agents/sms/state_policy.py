"""Ephemeral model projection of source copies; never mutate the stored checkpoint."""

from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import replace
from uuid import UUID

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from pydantic import ValidationError

from src.domains.agents.analysis.query_intelligence import QueryIntelligence
from src.domains.agents.context.runtime_context import runtime_user_id_str
from src.domains.agents.data_registry.models import RegistryItem, RegistryItemType
from src.domains.agents.models import MessagesState
from src.domains.agents.sms.live_authority import (
    SmsLiveAuthority as SmsLiveAuthority,
)
from src.domains.agents.sms.live_authority import (
    load_sms_authority,
)
from src.domains.agents.sms.projection import SmsToolItem
from src.domains.agents.sms.proof import SmsSnapshotProof
from src.domains.agents.sms.schemas import SMS_TOOL_MODELS

_STALE = {
    "success": False,
    "error_code": "STALE_STATE",
    "message": "SMS source copy is no longer authorized or current. Read the source again if permitted.",
}


def _carries_sms(message: ToolMessage) -> bool:
    return message.name in SMS_TOOL_MODELS or "sms_snapshot" in message.response_metadata


def _mapping(value: object) -> dict[str, object]:
    return (
        {key: item for key, item in value.items() if isinstance(key, str)}
        if isinstance(value, Mapping)
        else {}
    )


def _item(value: object) -> SmsToolItem | None:
    data = _mapping(value)
    data.pop("index", None)
    try:
        return SmsToolItem.model_validate(data)
    except ValidationError:
        return None


def _allowed(value: object, authority: SmsLiveAuthority | None) -> bool:
    item = _item(value)
    return bool(
        item
        and authority
        and item.owner_id == authority.owner
        and item.revision == authority.revision
        and item.id in authority.ids
    )


def _registry(value: object, authority: SmsLiveAuthority | None) -> RegistryItem | None:
    try:
        item = value if isinstance(value, RegistryItem) else RegistryItem.model_validate(value)
    except ValidationError:
        return None
    return (
        item if item.type is not RegistryItemType.SMS or _allowed(item.payload, authority) else None
    )


def _registry_map(value: object, authority: SmsLiveAuthority | None) -> dict[str, RegistryItem]:
    result = {}
    for key, item in _mapping(value).items():
        selected = _registry(item, authority)
        if selected is not None:
            result[key] = selected
    return result


def _proof_allowed(value: object, authority: SmsLiveAuthority | None) -> bool:
    if not isinstance(value, str) or authority is None:
        return False
    try:
        proof = SmsSnapshotProof.model_validate_json(value)
    except ValidationError:
        return False
    return (
        proof.owner == authority.owner
        and proof.revision == authority.revision
        and set(proof.ids) <= authority.ids
    )


def _sms_domain(value: object) -> bool:
    return isinstance(value, str) and value in {"sms", "sms_messages"}


def _selection_allowed(items: object, authority: SmsLiveAuthority | None) -> bool:
    return (
        authority is not None
        and isinstance(items, list)
        and all(_allowed(item, authority) for item in items)
    )


def _payload_marker(data: Mapping[str, object]) -> bool:
    return "owner_id" in data and "body_offset" in data


def _mapping_tree(data: dict[str, object], authority: SmsLiveAuthority | None) -> object:
    if data.get("type") == "SMS":
        item = _registry(data, authority)
        return item.model_dump(mode="json") if item else None
    if "sms_messages" in data and not _selection_allowed(data["sms_messages"], authority):
        return dict(_STALE)
    if (
        "items" in data
        and _sms_domain(data.get("source_domain"))
        and not _selection_allowed(data["items"], authority)
    ):
        return None
    if _payload_marker(data) and not _allowed(data, authority):
        return None
    return {key: _tree(item, authority) for key, item in data.items()}


def _tree(value: object, authority: SmsLiveAuthority | None) -> object:
    if isinstance(value, RegistryItem):
        return _registry(value, authority)
    if isinstance(value, list):
        return [_tree(item, authority) for item in value]
    return _mapping_tree(_mapping(value), authority) if isinstance(value, Mapping) else value


def _messages(
    source: Sequence[BaseMessage], authority: SmsLiveAuthority | None
) -> tuple[list[BaseMessage], bool]:
    messages = list(source)
    last_human = max(
        (index for index, message in enumerate(messages) if isinstance(message, HumanMessage)),
        default=-1,
    )
    stale_current = False
    for index, message in enumerate(messages):
        if isinstance(message, ToolMessage) and _carries_sms(message):
            if not _proof_allowed(message.response_metadata.get("sms_snapshot"), authority):
                messages[index] = message.model_copy(
                    update={
                        "content": _STALE["message"],
                        "status": "error",
                        "response_metadata": {"error_code": "STALE_STATE"},
                    }
                )
                stale_current = stale_current or index > last_human
    return messages, stale_current


def _mute_current_ai(messages: list[BaseMessage]) -> list[BaseMessage]:
    last_human = max(
        (index for index, message in enumerate(messages) if isinstance(message, HumanMessage)),
        default=-1,
    )
    return [
        (
            message.model_copy(update={"content": ""})
            if isinstance(message, AIMessage) and index > last_human
            else message
        )
        for index, message in enumerate(messages)
    ]


def _registry_stale(value: object, authority: SmsLiveAuthority | None) -> bool:
    for item in _mapping(value).values():
        kind = item.type if isinstance(item, RegistryItem) else _mapping(item).get("type")
        if kind == "SMS" and _registry(item, authority) is None:
            return True
    return False


def _query_projection(state: MessagesState, authority: SmsLiveAuthority | None) -> object:
    qi = state.get("query_intelligence")
    if isinstance(qi, QueryIntelligence):
        context = qi.resolved_context
        if (
            context
            and _sms_domain(context.source_domain)
            and not _selection_allowed(context.items, authority)
        ):
            return replace(
                qi,
                resolved_context=None,
                resolved_references=(),
                english_enriched_query=None,
                source_domain=None,
            )
        return qi
    if not isinstance(qi, Mapping):
        return qi
    data = _mapping(qi)
    if _sms_domain(data.get("source_domain")):
        context_data = _mapping(data.get("resolved_context") or state.get("resolved_context"))
        if not _selection_allowed(context_data.get("items"), authority):
            data.update(
                resolved_context=None,
                resolved_references=[],
                english_enriched_query=None,
                source_domain=None,
            )
    return _tree(data, authority)


def _filter_references(
    clean: MessagesState, state: MessagesState, authority: SmsLiveAuthority | None
) -> None:
    if "resolved_context" in state:
        value = _tree(state["resolved_context"], authority)
        clean["resolved_context"] = _mapping(value) if value is not None else None
    if "query_intelligence" in state:
        clean["query_intelligence"] = _query_projection(state, authority)


def _agent_projection(
    values: Mapping[str, object], authority: SmsLiveAuthority | None, stale: bool
) -> dict[str, object]:
    result = {}
    for key, value in values.items():
        if stale and _collect(value, set()):
            continue
        if key.endswith(":sms_agent") and (authority is None or stale):
            continue
        if key.endswith(":react_agent") and stale:
            continue
        result[key] = _tree(value, authority)
    return result


def filter_sms_state(state: MessagesState, authority: SmsLiveAuthority | None) -> MessagesState:
    clean = state.copy()
    messages, stale = _messages(state.get("messages", []), authority)
    stale = stale or _registry_stale(state.get("current_turn_registry"), authority)
    clean["messages"] = _mute_current_ai(messages) if stale else messages
    if "registry" in state:
        clean["registry"] = _registry_map(state["registry"], authority)
    if state.get("current_turn_registry") is not None:
        clean["current_turn_registry"] = _registry_map(state["current_turn_registry"], authority)
    if "agent_results" in state:
        clean["agent_results"] = _agent_projection(state["agent_results"], authority, stale)
    if "tool_results" in state:
        clean["tool_results"] = [
            _mapping(_tree(value, authority)) for value in state["tool_results"]
        ]
    _filter_references(clean, state, authority)
    react_result = state.get("react_agent_result")
    if stale and react_result:
        clean["react_agent_result"] = {**react_result, "final_message": ""}
    return clean


def _collect_mapping(data: dict[str, object], ids: set[UUID]) -> bool:
    present = (
        data.get("type") == "SMS"
        or "sms_messages" in data
        or _sms_domain(data.get("source_domain"))
    )
    if _payload_marker(data):
        item = _item(data)
        if item:
            ids.add(item.id)
        present = True
    children = [
        _collect(item, ids)
        for item in data.values()
        if isinstance(item, Mapping | list | RegistryItem)
    ]
    return any([present, *children])


def _collect(value: object, ids: set[UUID]) -> bool:
    if isinstance(value, RegistryItem):
        return _collect(value.payload, ids) if value.type is RegistryItemType.SMS else False
    if isinstance(value, list):
        # Every id must be collected, even after the first match.
        present = False
        for item in value:
            found = _collect(item, ids)
            present = present or found
        return present
    return _collect_mapping(_mapping(value), ids) if isinstance(value, Mapping) else False


async def guard_sms_state(state: MessagesState) -> MessagesState:
    ids: set[UUID] = set()
    present = any(
        [
            _collect(state.get("registry"), ids),
            _collect(state.get("current_turn_registry"), ids),
            _collect(state.get("agent_results"), ids),
            _collect(state.get("tool_results"), ids),
            _collect(state.get("resolved_context"), ids),
        ]
    )
    qi = state.get("query_intelligence")
    if isinstance(qi, QueryIntelligence) and qi.resolved_context:
        present = _collect(qi.resolved_context.items, ids) or present
    elif isinstance(qi, dict):
        present = _collect(qi, ids) or present
    present = _message_ids(state.get("messages", []), ids) or present
    if not present:
        return state
    owner = runtime_user_id_str(None)
    authority = await load_sms_authority(UUID(owner), ids) if owner else None
    return filter_sms_state(state, authority)


def _message_ids(messages: Sequence[BaseMessage], ids: set[UUID]) -> bool:
    present = False
    for message in messages:
        if isinstance(message, ToolMessage) and _carries_sms(message):
            present = True
            proof = message.response_metadata.get("sms_snapshot")
            # Invalid proofs still mark the message as SMS and are filtered;
            # they contribute no trusted source identifiers.
            with suppress(ValidationError):
                selected = (
                    SmsSnapshotProof.model_validate_json(proof) if isinstance(proof, str) else None
                )
                if selected:
                    ids.update(selected.ids)
    return present


async def guard_sms_messages(messages: Sequence[BaseMessage]) -> list[BaseMessage]:
    """The same live authority and filtering for a domain agent's smaller state."""
    ids: set[UUID] = set()
    if not _message_ids(messages, ids):
        return list(messages)
    owner = runtime_user_id_str(None)
    authority = await load_sms_authority(UUID(owner), ids) if owner else None
    clean, stale = _messages(messages, authority)
    return _mute_current_ai(clean) if stale else clean
