"""All changes are visible as data, with no truncated approval arguments."""

import json
from collections.abc import Callable

from pydantic import ValidationError

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.export_download_schemas import ExportDownloadPatch
from src.domains.agents.application.habit_action_schemas import canonical_habit
from src.domains.agents.application.habit_forgetting import canonical_habit_forgetting
from src.domains.agents.application.habit_recompute import canonical_habit_recompute
from src.domains.agents.application.habit_rendering import (
    habit_forgetting_preview,
    habit_preview,
    habit_recompute_preview,
)
from src.domains.agents.application.health_removal import canonical_health_removal
from src.domains.agents.application.health_removal_rendering import health_removal_preview
from src.domains.agents.application.health_token_creation import canonical_health_token_creation
from src.domains.agents.application.health_token_rendering import (
    health_token_creation_preview,
    health_token_preview,
)
from src.domains.agents.application.health_token_revocation import canonical_health_token_revocation
from src.domains.agents.application.interest_reactivation_schemas import (
    canonical_interest_reactivation,
)
from src.domains.agents.application.interest_rendering import (
    interest_bulk_removal_preview,
    interest_creation_preview,
    interest_feedback_preview,
    interest_reactivation_preview,
    interest_removal_preview,
    interest_update_preview,
)
from src.domains.agents.application.journal_consolidation_rendering import (
    journal_consolidation_preview,
)
from src.domains.agents.application.journal_consolidation_schemas import (
    canonical_journal_consolidation,
)
from src.domains.agents.application.journal_creation_rendering import journal_creation_preview
from src.domains.agents.application.journal_feedback_rendering import journal_feedback_preview
from src.domains.agents.application.journal_feedback_schemas import canonical_journal_feedback
from src.domains.agents.application.journal_removal import canonical_journal_removal
from src.domains.agents.application.journal_removal_rendering import journal_removal_preview
from src.domains.agents.application.journal_update import canonical_journal_update
from src.domains.agents.application.journal_update_rendering import journal_update_preview
from src.domains.agents.application.management_export_rendering import management_export_preview
from src.domains.agents.application.management_rendering import (
    MANAGEMENT_CANONICAL,
    MANAGEMENT_PREVIEW_NOTES,
)
from src.domains.agents.application.memory_rendering import (
    _memory_bulk_removal_preview,
    _memory_creation_preview,
    _memory_pin_preview,
    _memory_removal_preview,
    _memory_update_preview,
)
from src.domains.agents.application.open_loop_action_schemas import canonical_open_loop
from src.domains.agents.application.open_loop_rendering import open_loop_preview
from src.domains.agents.application.operation_spec import OperationKind
from src.domains.agents.application.phone_number_schemas import PhoneNumberCommandValues
from src.domains.agents.application.psyche_reset import canonical_psyche_reset
from src.domains.agents.application.psyche_reset_rendering import render_psyche_reset
from src.domains.agents.application.psyche_summary import canonical_psyche_summary
from src.domains.agents.application.psyche_summary_rendering import psyche_summary_preview
from src.domains.agents.application.registry import APPLICATION_OPERATIONS
from src.domains.agents.application.reminder_rendering import (
    _reminder_creation_preview,
    _reminder_update_preview,
)
from src.domains.agents.application.routine_create_schemas import RoutineCreatePatch
from src.domains.agents.application.routine_run_schemas import RoutineRunPatch
from src.domains.agents.application.routine_schemas import RoutineStatePatch
from src.domains.agents.application.routine_update_schemas import RoutineUpdatePatch
from src.domains.agents.application.session_bulk_operations import OtherSessionsRevokePatch
from src.domains.agents.application.session_revocation_schemas import DeviceSessionRevokePatch
from src.domains.agents.drafts.card_spec import Note, PreviewLine, Row
from src.domains.connectors.models import ConnectorType, get_connector_display_name

_UNLINK_FIELDS = {
    "interests.delete_all": "interests_to_delete",
    "interests.delete": "interest_to_delete",
    "memories.delete_all": "memories_to_delete",
    "memories.delete": "memory_to_delete",
    "reminder.delete": "reminder_to_delete",
    "routine.delete": "routine_to_delete",
    "device_sessions.revoke_others": "other_sessions_to_revoke",
    "device_session.revoke": "session_to_revoke",
    "channel_binding.unlink": "channel_binding",
    "connector_connection.unlink": "connector_to_disconnect",
    "notification_device.remove": "notification_device_to_remove",
}
_REMOVAL_NOTES = {
    "journal_settings.update": "application_journal_settings_note",
    "psyche_settings.update": "application_psyche_settings_note",
    **MANAGEMENT_PREVIEW_NOTES,
    "habit_settings.update": "application_habit_settings_note",
    "reminder.delete": "application_reminder_removal_note",
    "routine.delete": "application_routine_removal_note",
    "phone_number.update": "application_phone_number",
    "phone_preferences.update": "application_phone_preferences",
    "live_connector_preferences.update": "application_live_connector",
    "channel_binding.unlink": "application_channel_unlink",
    "connector_connection.unlink": "application_connector_unlink",
    "notification_device.remove": "application_notification_device_remove",
}
_EDITABLE_NESTED_FIELDS = {
    "interests.update": ("interest_configuration", "configuration"),
    "memories.update": ("memory_configuration", "configuration"),
    "memories.pin": ("memory_pin", "pinned"),
    "routine_state.update": ("routine_state", "enabled"),
    "phone_number.update": ("phone_number", "number"),
    "phone_preferences.update": ("phone_preferences", "values"),
    "live_connector_preferences.update": ("live_connector_settings", "settings"),
    "live_preferences.update": ("live_reflexes", "values"),
    "shared_mcp_preferences.update": ("shared_mcp_server", "enabled_for_user"),
}
_STRUCTURED_OPERATIONS = frozenset(
    {
        *MANAGEMENT_CANONICAL,
        "relation_settings.update",
        "journal_portrait.feedback",
        "journals.consolidate",
        "journal_entries.update",
        "journal_entries.create",
        "journal_entries.delete",
        "psyche.reset",
        "health_token.revoke",
        "health_token.create",
        "health_samples.delete",
        "psyche.summary",
        "habits.recompute",
        "habits.forget",
        "habits.status",
        "habits.delete",
        "open_loops.update",
        "open_loops.close",
        "interests.export",
        "memories.export",
        "journals.export",
        "interests.reactivate",
        "interests.feedback",
        "interests.create",
        "interests.delete_all",
        "interests.delete",
        "interests.update",
        "memories.create",
        "memories.update",
        "memories.delete",
        "memories.delete_all",
        "memories.pin",
        "account_export.download",
        "routine.delete",
        "routine.create",
        "reminder.create",
        "reminder.delete",
        "reminder.update",
        "routine.update",
        "routine.execute",
        "routine_state.update",
        "channel_binding.update",
        "channel_binding.unlink",
        "connector_connection.unlink",
        "notification_device.remove",
        "connector_preferences.update",
        "shared_mcp_preferences.update",
        "layout_preferences.update",
        "home_location.update",
        "heartbeat_preferences.update",
        "live_preferences.update",
        "live_connector_preferences.update",
        "phone_preferences.update",
        "phone_number.update",
        "device_session.revoke",
        "device_sessions.revoke_others",
    }
)


def _preview_draft(content: dict[str, object]) -> ApplicationActionDraftContent:
    draft = ApplicationActionDraftContent.model_validate(content)
    spec = APPLICATION_OPERATIONS.get(draft.operation_id)
    if spec.kind not in {OperationKind.ACTION, OperationKind.SECURE_HANDOFF, OperationKind.DEVICE}:
        raise ValueError("Operation cannot produce an action preview")
    spec.input_model.model_validate(draft.intent)
    if not _canonical_after(draft) or draft.before.keys() != draft.after.keys():
        raise ValueError("Inconsistent preview")
    if draft.operation_id not in _STRUCTURED_OPERATIONS and any(
        isinstance(value, dict | list) for value in draft.before.values()
    ):
        raise ValueError("Unexpected structured preview")
    return draft


def render_application_preview(
    content: dict[str, object], labels: dict[str, str], format_dt: Callable[[str | None], str]
) -> list[PreviewLine]:
    try:
        draft = _preview_draft(content)
    except ValidationError, ValueError, KeyError:
        return [Note(text=labels["application_unavailable"])]
    specialized = {
        "journal_portrait.feedback": journal_feedback_preview,
        "journals.consolidate": journal_consolidation_preview,
        "journal_entries.update": journal_update_preview,
        "journal_entries.create": journal_creation_preview,
        "journal_entries.delete": journal_removal_preview,
        "psyche.reset": render_psyche_reset,
        "health_token.revoke": health_token_preview,
        "health_token.create": health_token_creation_preview,
        "health_samples.delete": health_removal_preview,
        "psyche.summary": psyche_summary_preview,
        "habits.recompute": habit_recompute_preview,
        "habits.forget": habit_forgetting_preview,
        "habits.status": habit_preview,
        "habits.delete": habit_preview,
        "open_loops.update": open_loop_preview,
        "open_loops.close": open_loop_preview,
        "interests.export": management_export_preview,
        "memories.export": management_export_preview,
        "journals.export": management_export_preview,
        "interests.reactivate": interest_reactivation_preview,
        "interests.feedback": interest_feedback_preview,
        "interests.create": interest_creation_preview,
        "interests.delete_all": interest_bulk_removal_preview,
        "interests.delete": interest_removal_preview,
        "interests.update": interest_update_preview,
        "memories.update": _memory_update_preview,
        "memories.delete": _memory_removal_preview,
        "memories.delete_all": _memory_bulk_removal_preview,
        "memories.create": _memory_creation_preview,
        "memories.pin": _memory_pin_preview,
        "account_export.download": _export_download_preview,
        "reminder.update": _reminder_update_preview,
        "reminder.create": _reminder_creation_preview,
        "device_sessions.revoke_others": _other_sessions_preview,
        "routine_state.update": _routine_state_preview,
        "routine.create": _routine_creation_preview,
        "routine.update": _routine_update_preview,
        "routine.execute": _routine_run_preview,
    }.get(draft.operation_id)
    if specialized is not None:
        return specialized(draft, labels, format_dt)
    if draft.operation_id == "account_export.request":
        if draft.before != {"account_export": False}:
            return [Note(text=labels["application_unavailable"])]
        return [
            Note(text=labels["application_export_note"]),
            Row(
                label=labels["application_expiry"],
                value=format_dt(draft.expires_at.isoformat()),
                key="date",
            ),
        ]
    if draft.operation_id == "device_session.revoke":
        return _session_revocation_preview(draft, labels, format_dt)
    lines: list[PreviewLine] = []
    if (
        draft.operation_id == "interest_settings.update"
        and {"interests_notify_start_hour", "interests_notify_end_hour"} & draft.intent.keys()
    ):
        lines.append(
            Row(
                label=labels["application_field_timezone"], value=draft.user_timezone, key="details"
            )
        )
    if note := _REMOVAL_NOTES.get(draft.operation_id):
        lines.append(Note(text=labels[note]))
    if draft.operation_id == "live_preferences.update":
        lines.append(Note(text=labels["application_live_preferences"]))
    if draft.after.get("use_last_known_location") is False or (
        "home_location" in draft.after and draft.after["home_location"] is None
    ):
        lines.append(Note(text=labels["application_location_clear"]))
    for name, value in draft.after.items():
        before = _display_value(draft, draft.before.get(name), labels, before=True)
        after = _display_value(draft, value, labels)
        lines.append(
            Row(
                label=labels[f"application_field_{name}"],
                value=f"{labels['application_before']}: {before} → {labels['application_after']}: {after}",
                key="details",
            )
        )
    lines.append(
        Row(
            label=labels["application_expiry"],
            value=format_dt(draft.expires_at.isoformat()),
            key="date",
        )
    )
    return lines


def _export_download_preview(
    draft: ApplicationActionDraftContent,
    labels: dict[str, str],
    format_dt: Callable[[str | None], str],
) -> list[PreviewLine]:
    archive = ExportDownloadPatch.model_validate(draft.intent).archive_to_download
    if draft.before != {"archive_to_download": None} or draft.expires_at > archive.expires_at:
        return [Note(text=labels["application_unavailable"])]
    return [
        Note(text=labels["application_export_download_note"]),
        Row(
            label=labels["application_export_download_title"],
            value=json.dumps(
                archive.model_dump(mode="json", exclude={"archive_digest"}), ensure_ascii=False
            ),
            key="details",
        ),
        Row(
            label=labels["application_expiry"],
            value=format_dt(draft.expires_at.isoformat()),
            key="date",
        ),
    ]


def _other_sessions_preview(
    draft: ApplicationActionDraftContent,
    labels: dict[str, str],
    format_dt: Callable[[str | None], str],
) -> list[PreviewLine]:
    selected = OtherSessionsRevokePatch.model_validate(draft.intent).other_sessions_to_revoke
    return [
        Note(text=labels["application_other_sessions_note"]),
        Row(
            label=labels["application_other_sessions_count"],
            value=str(len(selected.sessions)),
            key="details",
        ),
        Row(
            label=labels["application_current_session_kept"],
            value=selected.current_display_id,
            key="details",
        ),
        Row(
            label=labels["application_expiry"],
            value=format_dt(draft.expires_at.isoformat()),
            key="date",
        ),
    ]


def _routine_creation_preview(
    draft: ApplicationActionDraftContent,
    labels: dict[str, str],
    format_dt: Callable[[str | None], str],
) -> list[PreviewLine]:
    created = RoutineCreatePatch.model_validate(draft.intent).routine_to_create
    if draft.before != {"routine_to_create": None} or created.id != draft.command_id:
        return [Note(text=labels["application_unavailable"])]
    return [
        Note(text=labels["application_routine_creation_note"]),
        Row(
            label=labels["application_routine_creation_title"],
            value=json.dumps(
                {
                    "timezone": created.user_timezone,
                    **created.configuration.model_dump(mode="json"),
                },
                ensure_ascii=False,
            ),
            key="details",
        ),
        Row(
            label=labels["application_expiry"],
            value=format_dt(draft.expires_at.isoformat()),
            key="date",
        ),
    ]


def _routine_run_preview(
    draft: ApplicationActionDraftContent,
    labels: dict[str, str],
    format_dt: Callable[[str | None], str],
) -> list[PreviewLine]:
    selected = RoutineRunPatch.model_validate(draft.intent).routine_to_run
    if draft.before != {"routine_to_run": None}:
        return [Note(text=labels["application_unavailable"])]
    return [
        Note(text=labels["application_routine_run_note"]),
        Row(
            label=labels["application_routine_title"],
            value=f"{selected.expected.title} · {selected.expected.id}",
            key="details",
        ),
        Row(
            label=labels["application_routine_creation_title"],
            value=json.dumps(
                {
                    "timezone": selected.user_timezone,
                    **selected.configuration.model_dump(mode="json"),
                },
                ensure_ascii=False,
            ),
            key="details",
        ),
        Row(
            label=labels["application_expiry"],
            value=format_dt(draft.expires_at.isoformat()),
            key="date",
        ),
    ]


def _routine_update_preview(
    draft: ApplicationActionDraftContent,
    labels: dict[str, str],
    format_dt: Callable[[str | None], str],
) -> list[PreviewLine]:
    previous = RoutineUpdatePatch.model_validate(draft.before).routine_configuration
    selected = RoutineUpdatePatch.model_validate(draft.intent).routine_configuration
    if (
        previous.expected != selected.expected
        or previous.changes != selected.changes
        or previous.user_timezone != selected.user_timezone
        or previous.enabled != previous.expected.enabled
    ):
        return [Note(text=labels["application_unavailable"])]
    return [
        Note(text=labels["application_routine_update_note"]),
        Row(
            label=labels["application_routine_title"],
            value=f"{selected.expected.title} · {selected.expected.id}",
            key="details",
        ),
        Row(
            label=labels["application_routine_creation_title"],
            value=json.dumps(
                {
                    "timezone": selected.user_timezone,
                    labels["application_before"]: {
                        "enabled": previous.enabled,
                        **previous.configuration.model_dump(mode="json"),
                    },
                    labels["application_after"]: {
                        "enabled": selected.enabled,
                        **selected.configuration.model_dump(mode="json"),
                    },
                },
                ensure_ascii=False,
            ),
            key="details",
        ),
        Row(
            label=labels["application_expiry"],
            value=format_dt(draft.expires_at.isoformat()),
            key="date",
        ),
    ]


def _routine_state_preview(
    draft: ApplicationActionDraftContent,
    labels: dict[str, str],
    format_dt: Callable[[str | None], str],
) -> list[PreviewLine]:
    previous = RoutineStatePatch.model_validate(draft.before).routine_state
    selected = RoutineStatePatch.model_validate(draft.intent).routine_state
    if previous.enabled != previous.expected.enabled:
        return [Note(text=labels["application_unavailable"])]
    before = labels[
        "application_routine_enabled" if previous.enabled else "application_routine_disabled"
    ]
    after = labels[
        "application_routine_enabled" if selected.enabled else "application_routine_disabled"
    ]
    return [
        Note(text=labels["application_routine_note"]),
        Row(
            label=labels["application_routine_title"],
            value=f"{selected.expected.title} · {selected.expected.id}",
            key="details",
        ),
        Row(
            label=labels["application_routine_title"],
            value=f"{labels['application_before']}: {before} → {labels['application_after']}: {after}",
            key="details",
        ),
        Row(
            label=labels["application_expiry"],
            value=format_dt(draft.expires_at.isoformat()),
            key="date",
        ),
    ]


def _session_revocation_preview(
    draft: ApplicationActionDraftContent,
    labels: dict[str, str],
    format_dt: Callable[[str | None], str],
) -> list[PreviewLine]:
    selected = DeviceSessionRevokePatch.model_validate(draft.intent).session_to_revoke
    device = " · ".join(
        value for value in (selected.device_name, selected.ua_family, selected.os_family) if value
    )
    before = f"{device} · {selected.id} · {format_dt(selected.created_at.isoformat())}"
    return [
        Note(text=labels["application_session_revoke"]),
        Row(
            label=labels["application_field_session_to_revoke"],
            value=f"{labels['application_before']}: {before} → {labels['application_after']}: {labels['application_session_closed']}",
            key="details",
        ),
        Row(
            label=labels["application_expiry"],
            value=format_dt(draft.expires_at.isoformat()),
            key="date",
        ),
    ]


def _display_live_connector(
    value: dict[str, object], _before: bool, _labels: dict[str, str]
) -> str:
    expected = value.get("expected")
    return json.dumps(
        {
            "provider": expected.get("provider") if isinstance(expected, dict) else None,
            "settings": value.get("settings"),
        },
        ensure_ascii=False,
    )


def _display_phone_number(value: dict[str, object], before: bool, labels: dict[str, str]) -> str:
    command = PhoneNumberCommandValues.model_validate(value)
    values = command.expected.values if before else command.public_values()
    number = values.phone_number or labels[f"application_number_{values.number_status}"]
    verification = labels[
        "application_number_verified" if values.verified else "application_number_unverified"
    ]
    return f"{number} ({verification})"


_NESTED_DISPLAYS: dict[str, Callable[[dict[str, object], bool, dict[str, str]], str]] = {
    "phone_number.update": _display_phone_number,
    "phone_preferences.update": lambda value, before, labels: json.dumps(
        value.get("values"), ensure_ascii=False
    ),
    "live_connector_preferences.update": _display_live_connector,
    "live_preferences.update": lambda value, before, labels: json.dumps(
        value.get("values"), ensure_ascii=False
    ),
}
_PRIVATE_DISPLAY_FIELDS = {
    "reminder.delete": frozenset({"configuration_digest", "card_selection"}),
    "routine.delete": frozenset({"configuration_digest"}),
    "notification_device.remove": frozenset({"token_digest", "updated_at"}),
    "shared_mcp_preferences.update": frozenset({"catalogue_digest"}),
}


def _display_value(
    draft: ApplicationActionDraftContent,
    value: object,
    labels: dict[str, str],
    *,
    before: bool = False,
) -> str:
    if not isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    if display := _NESTED_DISPLAYS.get(draft.operation_id):
        return display(value, before, labels)
    private = _PRIVATE_DISPLAY_FIELDS.get(draft.operation_id, frozenset())
    value = {key: item for key, item in value.items() if key not in private}
    if draft.operation_id == "connector_connection.unlink":
        value = {
            "service": get_connector_display_name(ConnectorType(value.get("connector_type"))),
            "id": value.get("id"),
            "account": value.get("account_email"),
        }
    return json.dumps(value, ensure_ascii=False)


_CANONICAL_OPERATIONS = {
    **MANAGEMENT_CANONICAL,
    "journal_portrait.feedback": canonical_journal_feedback,
    "journals.consolidate": canonical_journal_consolidation,
    "journal_entries.update": canonical_journal_update,
    "journal_entries.delete": canonical_journal_removal,
    "psyche.reset": canonical_psyche_reset,
    "health_token.revoke": canonical_health_token_revocation,
    "health_token.create": canonical_health_token_creation,
    "health_samples.delete": canonical_health_removal,
    "psyche.summary": canonical_psyche_summary,
    "habits.recompute": canonical_habit_recompute,
    "habits.forget": canonical_habit_forgetting,
    "habits.status": canonical_habit,
    "habits.delete": canonical_habit,
    "open_loops.update": canonical_open_loop,
    "open_loops.close": canonical_open_loop,
    "interests.reactivate": canonical_interest_reactivation,
}


def _canonical_after(draft: ApplicationActionDraftContent) -> bool:
    if validator := _CANONICAL_OPERATIONS.get(draft.operation_id):
        return validator(draft)
    if draft.operation_id == "phone_number.update":
        previous_number = PhoneNumberCommandValues.model_validate(draft.before.get("phone_number"))
        if previous_number.number != previous_number.expected.values.phone_number:
            return False
    if not _unchanged_snapshot(draft):
        return False
    if draft.operation_id in _UNLINK_FIELDS:
        return draft.intent == draft.before and draft.after == {
            _UNLINK_FIELDS[draft.operation_id]: None
        }
    return draft.after == draft.intent


def _unchanged_snapshot(draft: ApplicationActionDraftContent) -> bool:
    contract = _EDITABLE_NESTED_FIELDS.get(draft.operation_id)
    if contract is None:
        return True
    field, editable = contract
    before = draft.before.get(field)
    after = draft.after.get(field)
    if not isinstance(before, dict) or not isinstance(after, dict):
        return False
    return {key: value for key, value in before.items() if key != editable} == {
        key: value for key, value in after.items() if key != editable
    }


def summarize_application_action(
    content: dict[str, object], format_dt: Callable[[str | None], str]
) -> tuple[str, dict[str, str]]:
    return "application_action", {}
