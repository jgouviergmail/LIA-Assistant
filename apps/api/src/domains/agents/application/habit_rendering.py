"""Full public source facts appear as escaped data on both sides of approval."""

import json
from collections.abc import Callable

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.habit_forget_schemas import HabitForgetPatch
from src.domains.agents.application.habit_recompute_schemas import HabitRecomputePatch
from src.domains.agents.drafts.card_spec import Note, PreviewLine, Row


def habit_preview(
    draft: ApplicationActionDraftContent,
    labels: dict[str, str],
    format_dt: Callable[[str | None], str],
) -> list[PreviewLine]:
    note = (
        "application_habit_status_note"
        if draft.operation_id == "habits.status"
        else "application_habit_delete_note"
    )
    return [
        Note(text=labels[note]),
        Row(
            label=labels["application_field_habit"],
            value=json.dumps(
                {
                    labels["application_before"]: draft.before["habit"],
                    labels["application_after"]: draft.after["habit"],
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


def habit_forgetting_preview(
    draft: ApplicationActionDraftContent,
    labels: dict[str, str],
    format_dt: Callable[[str | None], str],
) -> list[PreviewLine]:
    scope = HabitForgetPatch.model_validate(draft.intent).habit_data
    return [
        Note(text=labels["application_habit_forget_note"]),
        Row(label=labels["application_habit_count"], value=str(scope.habits)),
        Row(label=labels["application_habit_profile_count"], value=str(scope.profiles)),
        Row(label=labels["application_habit_activity_count"], value=str(scope.activity_days)),
        Row(
            label=labels["application_expiry"],
            value=format_dt(draft.expires_at.isoformat()),
            key="date",
        ),
    ]


def habit_recompute_preview(
    draft: ApplicationActionDraftContent,
    labels: dict[str, str],
    format_dt: Callable[[str | None], str],
) -> list[PreviewLine]:
    scope = HabitRecomputePatch.model_validate(draft.intent).habit_recompute
    return [
        Note(text=labels["application_habit_recompute_note"]),
        Row(
            label=labels["application_field_timezone"],
            value=scope.timezone,
        ),
        Row(
            label=labels["application_expiry"],
            value=format_dt(draft.expires_at.isoformat()),
            key="date",
        ),
    ]
