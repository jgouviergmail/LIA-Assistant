"""Continue a native application page after the last item actually shown to the model."""

import json
import re
from uuid import UUID

from pydantic import JsonValue, TypeAdapter

from src.core.constants import SESSION_DISPLAY_ID_LENGTH

_DATA: TypeAdapter[dict[str, JsonValue]] = TypeAdapter(dict[str, JsonValue])
_CURSORS = {
    "notifications": ("application_interest_history_cursor", "id"),
    "interests": ("application_interest_cursor", "id"),
    "memories": ("application_memory_cursor", "id"),
    "reminders": ("application_reminder_cursor", "id"),
    "scheduled_actions": ("application_routine_cursor", "id"),
    "actions": ("application_routine_cursor", "id"),
    "calls": ("application_phone_call_cursor", "id"),
    "sessions": ("application_session_cursor", "id"),
    "passkeys": ("application_passkey_cursor", "id"),
    "connectors": ("application_connector_cursor", "id"),
    "servers": ("application_shared_mcp_cursor", "server_key"),
    "devices": ("application_notification_cursor", "id"),
}


def visible_connector_cursor(
    text: str, metadata: object, *, key: str | None, truncated: bool
) -> str:
    if not truncated or not isinstance(metadata, dict):
        return text
    if key == "choices" and metadata.get("application_live_options_cursor") is True:
        return _visible_live_options_cursor(text)
    return _visible_resource_cursor(text, metadata, key)


def _visible_resource_cursor(text: str, metadata: dict[str, object], key: str | None) -> str:
    contract = _CURSORS.get(key or "")
    if contract is None or metadata.get(contract[0]) is not True:
        return text
    identity_field = contract[1]
    data = _DATA.validate_json(text)
    items = data.get(key or "")
    if not isinstance(items, list) or not items or not isinstance(items[-1], dict):
        raise ValueError("Invalid connector cursor projection")
    identity = items[-1].get(identity_field)
    if not isinstance(identity, str):
        raise ValueError("Invalid connector cursor identity")
    if key == "sessions":
        if re.fullmatch(rf"[0-9a-f]{{{SESSION_DISPLAY_ID_LENGTH}}}", identity) is None:
            raise ValueError("Invalid session cursor identity")
    elif identity_field == "id":
        UUID(identity)
    elif not identity or len(identity) > 256:
        raise ValueError("Invalid shared server cursor identity")
    data["next_cursor"] = identity
    _update_page_counts(data, len(items))
    return json.dumps(data, ensure_ascii=False)


def _update_page_counts(data: dict[str, JsonValue], returned_count: int) -> None:
    if "returned_count" in data:
        data["returned_count"] = returned_count
    if "truncated" in data:
        data["truncated"] = True


def _visible_live_options_cursor(text: str) -> str:
    data = _DATA.validate_json(text)
    items = data.get("choices")
    digest = data.get("catalogue_digest")
    offset = data.get("page_offset")
    if (
        not isinstance(items, list)
        or not items
        or not isinstance(digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        or type(offset) is not int
        or offset < 0
    ):
        raise ValueError("Invalid Live choice cursor projection")
    data["next_cursor"] = f"{digest}:{offset + len(items)}"
    return json.dumps(data, ensure_ascii=False)
