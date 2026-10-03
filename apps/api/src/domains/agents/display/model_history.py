"""Preserve authorized answer facts without persisting card HTML as model context."""

import json
from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from langchain_core.messages import AIMessage

from src.core.field_names import FIELD_DISPLAY_ONLY
from src.domains.agents.data_registry.models import INTERACTIVE_WIDGET_TYPES, RegistryItem
from src.domains.agents.data_registry.trust import is_external
from src.domains.agents.display.llm_serializer import SKIP_FIELDS
from src.domains.agents.utils.content_wrapper import wrap_external_content
from src.domains.agents.utils.message_filters import _neutralize_assistant_formatting
from src.infrastructure.llm.message_view import MODEL_VIEW_KEY, MODEL_VIEW_VERSION


def _json_default(value: object) -> object:
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, UUID | Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    raise TypeError("Non-serializable registry value")


def _record(item: object) -> tuple[str, dict[str, object]] | None:
    if isinstance(item, RegistryItem):
        return item.type.value, item.payload
    if not isinstance(item, dict):
        return None
    kind = item.get("type")
    payload = item.get("payload")
    if not isinstance(payload, dict):
        return None
    return str(kind.value if isinstance(kind, Enum) else kind), payload


def _fact(item_id: str, kind: str, payload: Mapping[str, object]) -> str:
    # Reuse the existing technical-field declaration, preserving complete
    # authorized content. Display fields and meta are deliberately never read.
    data = {
        key: value
        for key, value in payload.items()
        if isinstance(key, str) and key != FIELD_DISPLAY_ONLY and key.lower() not in SKIP_FIELDS
    }
    record = {"registry_id": item_id, "type": kind, "data": data}
    try:
        text = json.dumps(record, ensure_ascii=False, default=_json_default)
    except TypeError, ValueError, RecursionError:
        text = json.dumps({"registry_id": item_id, "type": kind, "data_unavailable": True})
    return wrap_external_content(text, item_id, "registry_snapshot") if is_external(kind) else text


def with_model_view(
    message: AIMessage,
    prose: str,
    registry: Mapping[str, object] | None,
    *,
    enabled: bool = True,
) -> AIMessage:
    """Attach a serializable semantic snapshot of the selected current-turn data.

    No fetch, model call, field truncation or display-only restoration occurs.
    Widgets retain their existing history policy. Empty selection remains empty.
    """
    if not enabled:
        return message
    parts = [_neutralize_assistant_formatting(prose)]
    widget_types = {kind.value for kind in INTERACTIVE_WIDGET_TYPES}
    for item_id, item in (registry or {}).items():
        record = _record(item)
        if record is None:
            continue
        kind, payload = record
        if kind not in widget_types:
            parts.append(_fact(item_id, kind, payload))
    content = "\n\n".join(part for part in parts if part)
    return message.model_copy(
        update={
            "additional_kwargs": {
                **message.additional_kwargs,
                MODEL_VIEW_KEY: {"version": MODEL_VIEW_VERSION, "content": content},
            }
        }
    )
