"""Interest confirmation draws all source settings and never turns saved text into instructions."""

import json
from collections.abc import Callable

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.interest_bulk_schemas import InterestBulkDeletePatch
from src.domains.agents.application.interest_create_schemas import InterestCreatePatch
from src.domains.agents.application.interest_feedback_schemas import InterestFeedbackPatch
from src.domains.agents.application.interest_reactivation_schemas import InterestReactivationPatch
from src.domains.agents.application.interest_removal_schemas import InterestDeletePatch
from src.domains.agents.application.interest_update_schemas import InterestUpdatePatch
from src.domains.agents.drafts.card_spec import Note, PreviewLine, Row


def interest_reactivation_preview(
    draft: ApplicationActionDraftContent,
    labels: dict[str, str],
    format_dt: Callable[[str | None], str],
) -> list[PreviewLine]:
    dormant = InterestReactivationPatch.model_validate(draft.intent).interest_to_reactivate
    return [
        Note(text=labels["application_interest_reactivation_note"]),
        Row(
            label=labels["application_field_interest_to_reactivate"],
            value=json.dumps(
                {
                    labels["application_before"]: dormant.expected.model_dump(mode="json"),
                    labels["application_after"]: {
                        **dormant.expected.configuration.model_dump(mode="json"),
                        "subject": dormant.expected.subject,
                        **dormant.result.model_dump(mode="json"),
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


def interest_feedback_preview(
    draft: ApplicationActionDraftContent,
    labels: dict[str, str],
    format_dt: Callable[[str | None], str],
) -> list[PreviewLine]:
    before = InterestFeedbackPatch.model_validate(draft.before).interest_feedback
    after = InterestFeedbackPatch.model_validate(draft.intent).interest_feedback
    if draft.intent != draft.after:
        return [Note(text=labels["application_unavailable"])]
    return [
        Note(text=labels["application_interest_feedback_note"]),
        Row(
            label=labels["application_field_interest_feedback"],
            value=json.dumps(
                {
                    "id": str(before.expected.id),
                    "feedback": after.feedback,
                    "card_scope": before.card_scope,
                    "notification": (
                        before.notification.model_dump(mode="json", exclude={"source_digest"})
                        if before.notification
                        else None
                    ),
                    labels["application_before"]: {
                        **before.configuration.model_dump(mode="json"),
                        "status": before.expected.status.value,
                        "subject": before.expected.subject,
                    },
                    labels["application_after"]: {
                        **after.configuration.model_dump(mode="json"),
                        "status": after.expected.status.value,
                        "subject": after.expected.subject,
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


def interest_bulk_removal_preview(
    draft: ApplicationActionDraftContent,
    labels: dict[str, str],
    format_dt: Callable[[str | None], str],
) -> list[PreviewLine]:
    removed = InterestBulkDeletePatch.model_validate(draft.intent).interests_to_delete
    if draft.intent != draft.before or draft.after != {"interests_to_delete": None}:
        return [Note(text=labels["application_unavailable"])]
    return [
        Note(text=labels["application_interest_bulk_note"]),
        Row(
            label=labels["application_field_interests_to_delete"],
            value=json.dumps(
                removed.model_dump(mode="json", exclude={"selection_digest"}), ensure_ascii=False
            ),
            key="details",
        ),
        Row(
            label=labels["application_expiry"],
            value=format_dt(draft.expires_at.isoformat()),
            key="date",
        ),
    ]


def interest_removal_preview(
    draft: ApplicationActionDraftContent,
    labels: dict[str, str],
    format_dt: Callable[[str | None], str],
) -> list[PreviewLine]:
    removed = InterestDeletePatch.model_validate(draft.intent).interest_to_delete
    if draft.intent != draft.before or draft.after != {"interest_to_delete": None}:
        return [Note(text=labels["application_unavailable"])]
    return [
        Note(text=labels["application_interest_removal_note"]),
        Row(
            label=labels["application_field_interest_to_delete"],
            value=json.dumps(
                {
                    "id": str(removed.expected.id),
                    "status": removed.expected.status.value,
                    "subject": removed.expected.subject,
                    **removed.configuration.model_dump(mode="json"),
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


def interest_update_preview(
    draft: ApplicationActionDraftContent,
    labels: dict[str, str],
    format_dt: Callable[[str | None], str],
) -> list[PreviewLine]:
    before = InterestUpdatePatch.model_validate(draft.before).interest_configuration
    after = InterestUpdatePatch.model_validate(draft.intent).interest_configuration
    if before.expected != after.expected or before.changes != after.changes:
        return [Note(text=labels["application_unavailable"])]
    return [
        Note(text=labels["application_interest_update_note"]),
        Row(
            label=labels["application_field_interest_configuration"],
            value=json.dumps(
                {
                    "id": str(after.expected.id),
                    "status": after.expected.status.value,
                    labels["application_before"]: {
                        **before.configuration.model_dump(mode="json"),
                        "subject": before.expected.subject,
                    },
                    labels["application_after"]: {
                        **after.configuration.model_dump(mode="json"),
                        "subject": (
                            None
                            if before.configuration.topic != after.configuration.topic
                            else after.expected.subject
                        ),
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


def interest_creation_preview(
    draft: ApplicationActionDraftContent,
    labels: dict[str, str],
    format_dt: Callable[[str | None], str],
) -> list[PreviewLine]:
    creation = InterestCreatePatch.model_validate(draft.intent).interest_to_create
    if draft.before != {"interest_to_create": None} or creation.id != draft.command_id:
        return [Note(text=labels["application_unavailable"])]
    return [
        Note(text=labels["application_interest_creation_note"]),
        Row(
            label=labels["application_field_interest_to_create"],
            value=json.dumps(
                {"id": str(creation.id), **creation.configuration.model_dump(mode="json")},
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
