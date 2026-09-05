"""Turning one effect into something a person can read (ADR-263).

Built at CLAIM time, because that is the only moment the arguments exist: the
ledger deliberately keeps a digest rather than the call, so a label produced
later could only ever say "a tool ran".

Stored as ``{i18n_key, values}``, never as a sentence — the reader's language
is theirs at the moment they read, not ours at the moment we wrote. The same
keys are resolved by the frontend for the live card and by
``core.i18n_effects`` for the export.

Natives declare a builder; a third-party MCP tool cannot (its server names and
shapes its own tools), so its label is DERIVED from the registered name. That
is the same split as the mutation policy, for the same reason — and the
completeness assert covers exactly the declaring half.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from src.core.constants import MCP_TOOL_NAME_PREFIX

#: A builder reads the call arguments and returns the values its wording needs.
LabelValuesBuilder = Callable[[dict[str, Any]], dict[str, Any]]

#: One value is one line of a card: long enough to identify, short enough to read.
MAX_VALUE_CHARS = 120

#: Prefix under which a draft executor is recorded (``draft:email``).
DRAFT_TOOL_PREFIX = "draft:"

#: Wording used when a row carries no readable label of its own.
GENERIC_LABEL_KEY = "effects.labels.generic"


def _text(value: Any, fallback: str = "?") -> str:
    """One readable, bounded value out of whatever the model sent."""
    if value is None or value == "":
        return fallback
    if isinstance(value, list | tuple):
        value = ", ".join(str(item) for item in value[:3]) or fallback
    text = " ".join(str(value).split())
    return text[:MAX_VALUE_CHARS] if len(text) > MAX_VALUE_CHARS else text


def _first(arguments: dict[str, Any], *names: str, fallback: str = "?") -> str:
    """The first named argument that carries something."""
    for name in names:
        if arguments.get(name):
            return _text(arguments[name], fallback)
    return fallback


def _target(*names: str) -> LabelValuesBuilder:
    """Builder for the common ``{target}`` wording."""
    return lambda arguments: {"target": _first(arguments, *names)}


def _recipient(*names: str) -> LabelValuesBuilder:
    """Builder for the common ``{recipient}`` wording."""
    return lambda arguments: {"recipient": _first(arguments, *names)}


def _count(*names: str) -> LabelValuesBuilder:
    """Builder for a wording counting items."""

    def build(arguments: dict[str, Any]) -> dict[str, Any]:
        for name in names:
            value = arguments.get(name)
            if isinstance(value, list | tuple | set):
                return {"count": len(value)}
            if value:
                return {"count": 1}
        return {"count": 0}

    return build


def _draft(*names: str, key: str = "target") -> LabelValuesBuilder:
    """Builder reading inside a draft's content rather than the arguments.

    A draft executor is called with ``{"draft": {...}}``, so its values live one
    level down.
    """

    def build(arguments: dict[str, Any]) -> dict[str, Any]:
        content = arguments.get("draft")
        content = content if isinstance(content, dict) else {}
        inner = content.get("content")
        if isinstance(inner, dict):
            content = {**content, **inner}
        return {key: _first(content, *names)}

    return build


def _nothing(_arguments: dict[str, Any]) -> dict[str, Any]:
    """Builder for a wording that names nothing (the sandbox)."""
    return {}


#: Every capability that CLAIMS an effect declares how it reads. Keys are the
#: registered tool name, or ``draft:<type>`` for a confirmed draft's executor.
#: Completeness is asserted at boot — an omission is refused, never inferred.
EFFECT_LABEL_BUILDERS: dict[str, LabelValuesBuilder] = {
    # --- acting tools -------------------------------------------------------
    "control_hue_light_tool": _target("light_name", "name", "room", "target"),
    "control_hue_room_tool": _target("room_name", "room", "name", "target"),
    "activate_hue_scene_tool": _target("scene_name", "scene", "name"),
    "apply_labels_tool": _count("label_ids", "labels", "message_ids"),
    "remove_labels_tool": _count("label_ids", "labels", "message_ids"),
    "complete_task_tool": _target("title", "task_title", "task_id"),
    "toggle_scheduled_action_tool": _target("name", "action_name", "action_id"),
    "browser_task_tool": _target("task", "instruction", "url"),
    "activate_skill_tool": _target("skill_name", "name", "skill_id"),
    "import_user_skill": _target("skill_name", "name", "source"),
    "set_current_item": _target("reference", "item_id", "domain"),
    "generate_image": _target("prompt", "description"),
    "edit_image": _target("prompt", "instruction", "image_id"),
    "generate_document": _target("title", "filename", "subject"),
    "run_python_tool": _nothing,
    "run_skill_script": _target("skill_name", "script", "name"),
    # --- confirmed drafts ---------------------------------------------------
    "draft:email": _draft("to", "recipient", key="recipient"),
    "draft:email_reply": _draft("to", "recipient", key="recipient"),
    "draft:email_forward": _draft("to", "recipient", key="recipient"),
    "draft:email_delete": _draft("subject", "message_id"),
    "draft:email_filter": _nothing,
    "draft:vacation_responder": _nothing,
    "draft:event": _draft("summary", "title"),
    "draft:event_update": _draft("summary", "title", "event_id"),
    "draft:event_delete": _draft("summary", "title", "event_id"),
    "draft:contact": _draft("name", "display_name"),
    "draft:contact_update": _draft("name", "display_name", "contact_id"),
    "draft:contact_delete": _draft("name", "display_name", "contact_id"),
    "draft:task": _draft("title", "name"),
    "draft:task_update": _draft("title", "name", "task_id"),
    "draft:task_delete": _draft("title", "name", "task_id"),
    "draft:reminder_delete": _draft("content", "title", "reminder_id"),
    "draft:scheduled_action": _draft("name", "title", "instruction"),
    "draft:file_delete": _draft("name", "filename", "file_id"),
    "draft:label_delete": _draft("name", "label_name", "label_id"),
    "draft:document_append": _draft("title", "document_id"),
    "draft:spreadsheet_write": _draft("title", "spreadsheet_id"),
    "draft:peer_message": _draft("recipient_name", "to", "peer_id", key="recipient"),
    "draft:phone_call": _draft("callee_name", "phone", "to", key="recipient"),
    "draft:devops_task": _draft("server", "target", "command"),
}


def build_effect_label(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """The stored label of one effect.

    Never raises and never returns ``None``: a register that drops a line
    because a wording was missing would be less trustworthy than one that says
    "an action ran".

    Args:
        tool_name: Registered tool name, or ``draft:<type>`` for an executor.
        arguments: The call arguments, by name.

    Returns:
        ``{"i18n_key": ..., "values": {...}}``, ready to be encrypted.
    """
    builder = EFFECT_LABEL_BUILDERS.get(tool_name)
    if builder is not None:
        key = (
            f"effects.labels.draft.{tool_name[len(DRAFT_TOOL_PREFIX):]}"
            if tool_name.startswith(DRAFT_TOOL_PREFIX)
            else f"effects.labels.{tool_name}"
        )
        try:
            return {"i18n_key": key, "values": builder(arguments)}
        except Exception:  # noqa: BLE001 - a wording must never break an effect
            return {"i18n_key": key, "values": {}}

    if tool_name.startswith(f"{MCP_TOOL_NAME_PREFIX}_"):
        from src.domains.agents.effects.confirmation import _readable_tool_name

        return {
            "i18n_key": "effects.labels.mcp",
            "values": {"tool": _readable_tool_name(tool_name)},
        }

    from src.domains.agents.effects.confirmation import _readable_tool_name

    return {
        "i18n_key": "effects.labels.generic",
        "values": {"tool": _readable_tool_name(tool_name)},
    }


def readable_label(row: Any) -> tuple[str, dict[str, Any]]:
    """What one ledger row says it did, as a key and its values (ADR-263).

    The single reader shared by every consumer — the card under a bubble, the
    debug panel, the endpoint and the export — so none of them can describe the
    same row differently. A row whose label is absent or unreadable (written by
    an older version, or a rotated key) still yields a line: the generic
    wording, filled with the tool that acted.

    Args:
        row: An ``AgentEffect`` row.

    Returns:
        ``(i18n key, values)``.
    """
    from src.domains.agents.effects.repository import EffectLedgerRepository

    label = EffectLedgerRepository.decrypted_label(row) or {}
    values = label.get("values")
    return (
        str(label.get("i18n_key") or GENERIC_LABEL_KEY),
        values if isinstance(values, dict) else {"tool": row.tool_name},
    )


def assert_effect_label_completeness() -> None:
    """Assert every capability that can claim an effect has a label (ADR-085).

    Covers the DECLARING half only: a third-party MCP tool derives its label
    from its registered name, exactly as it derives its mutation policy.

    Raises:
        AssertionError: Listing every capability with no label builder.
    """
    from src.domains.agents.registry import get_global_registry
    from src.domains.agents.registry.catalogue import ACTING_POLICIES, MCP_TOOL_NAME_PREFIX
    from src.domains.agents.services.draft_executor_types import (
        EXECUTOR_REGISTRY,
        EXECUTORS_GATED_BY_THEIR_TOOL,
    )

    missing: list[str] = []

    registry = get_global_registry()
    for manifest in registry.list_tool_manifests():
        name = str(getattr(manifest, "name", ""))
        if name.startswith(f"{MCP_TOOL_NAME_PREFIX}_"):
            continue
        policy = getattr(manifest, "mutation_policy", None)
        # ``draft`` tools do not claim: their executor does, and it is checked
        # below under its own name.
        if policy in ACTING_POLICIES - {"draft"} and name not in EFFECT_LABEL_BUILDERS:
            missing.append(name)

    for draft_type in EXECUTOR_REGISTRY:
        if draft_type in EXECUTORS_GATED_BY_THEIR_TOOL:
            continue
        if f"{DRAFT_TOOL_PREFIX}{draft_type}" not in EFFECT_LABEL_BUILDERS:
            missing.append(f"{DRAFT_TOOL_PREFIX}{draft_type}")

    if missing:
        raise AssertionError(
            f"{len(missing)} capability(ies) can claim an effect with no label "
            f"builder: {sorted(missing)}. Add one to EFFECT_LABEL_BUILDERS and its "
            "wording to core/i18n_effects.py, in all six languages."
        )
