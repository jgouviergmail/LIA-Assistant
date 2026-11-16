"""The routine cards: a creation, a launch, an update and a switch, shown as data.

Extracted from ``draft_rendering`` unchanged (2026-11-16), beside the other families'
renderers (``habit_rendering``, ``reminder_rendering``): a card shows every field the
person approves, never a truncated argument, and a card whose before/after disagree
with its intent says it is unavailable instead of showing another state.
"""

import json
from collections.abc import Callable

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.routine_card_rows import preapproval_rows
from src.domains.agents.application.routine_create_schemas import RoutineCreatePatch
from src.domains.agents.application.routine_run_schemas import RoutineRunPatch
from src.domains.agents.application.routine_schemas import RoutineStatePatch
from src.domains.agents.application.routine_update_schemas import RoutineUpdatePatch
from src.domains.agents.drafts.card_spec import Note, PreviewLine, Row
from src.domains.scheduled_actions.models import TriggerKind


def routine_creation_preview(
    draft: ApplicationActionDraftContent,
    labels: dict[str, str],
    format_dt: Callable[[str | None], str],
) -> list[PreviewLine]:
    created = RoutineCreatePatch.model_validate(draft.intent).routine_to_create
    if draft.before != {"routine_to_create": None} or created.id != draft.command_id:
        return [Note(text=labels["application_unavailable"])]
    # ADR-386: the secret of a routine started by calls never reaches the chat.
    on_calls = created.configuration.trigger_kind is TriggerKind.WEBHOOK
    return [
        Note(text=labels["application_routine_creation_note"]),
        *([Note(text=labels["application_routine_webhook_note"])] if on_calls else []),
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


def routine_run_preview(
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
        *preapproval_rows(selected.mcp_preapproval, labels),
        Row(
            label=labels["application_expiry"],
            value=format_dt(draft.expires_at.isoformat()),
            key="date",
        ),
    ]


def routine_update_preview(
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
        *preapproval_rows(selected.mcp_preapproval, labels),
        Row(
            label=labels["application_expiry"],
            value=format_dt(draft.expires_at.isoformat()),
            key="date",
        ),
    ]


def routine_state_preview(
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
        *preapproval_rows(selected.mcp_preapproval, labels),
        Row(
            label=labels["application_expiry"],
            value=format_dt(draft.expires_at.isoformat()),
            key="date",
        ),
    ]
