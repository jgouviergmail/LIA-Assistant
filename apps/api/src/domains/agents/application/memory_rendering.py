"""Complete localized memory confirmations contain only source UI values."""

import json
from collections.abc import Callable

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.memory_bulk_schemas import MemoryBulkDeletePatch
from src.domains.agents.application.memory_create_schemas import MemoryCreatePatch
from src.domains.agents.application.memory_pin_schemas import MemoryPinPatch
from src.domains.agents.application.memory_removal_schemas import MemoryDeletePatch
from src.domains.agents.application.memory_update_schemas import MemoryUpdatePatch
from src.domains.agents.drafts.card_spec import Note, PreviewLine, Row


def _memory_bulk_removal_preview(
    draft: ApplicationActionDraftContent,
    labels: dict[str, str],
    format_dt: Callable[[str | None], str],
) -> list[PreviewLine]:
    selected = MemoryBulkDeletePatch.model_validate(draft.intent).memories_to_delete
    return [
        Note(text=labels["application_memory_bulk_note"]),
        Row(
            label=labels["application_field_memories_to_delete"],
            value=json.dumps(
                selected.model_dump(mode="json", exclude={"selection_digest"}), ensure_ascii=False
            ),
            key="details",
        ),
        Row(
            label=labels["application_expiry"],
            value=format_dt(draft.expires_at.isoformat()),
            key="date",
        ),
    ]


def _memory_removal_preview(
    draft: ApplicationActionDraftContent,
    labels: dict[str, str],
    format_dt: Callable[[str | None], str],
) -> list[PreviewLine]:
    selected = MemoryDeletePatch.model_validate(draft.intent).memory_to_delete
    return [
        Note(text=labels["application_memory_removal_note"]),
        Row(
            label=labels["application_field_memory_to_delete"],
            value=json.dumps(
                {
                    "id": str(selected.id),
                    "content": selected.content,
                    "category": selected.category,
                    "pinned": labels[
                        (
                            "application_memory_pinned"
                            if selected.pinned
                            else "application_memory_unpinned"
                        )
                    ],
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


def _memory_update_preview(
    draft: ApplicationActionDraftContent,
    labels: dict[str, str],
    format_dt: Callable[[str | None], str],
) -> list[PreviewLine]:
    previous = MemoryUpdatePatch.model_validate(draft.before).memory_configuration
    selected = MemoryUpdatePatch.model_validate(draft.intent).memory_configuration
    return [
        Note(text=labels["application_memory_update_note"]),
        Row(
            label=labels["application_field_memory_configuration"],
            value=json.dumps(
                {
                    "id": str(selected.expected.id),
                    "pinned": labels[
                        (
                            "application_memory_pinned"
                            if selected.expected.pinned
                            else "application_memory_unpinned"
                        )
                    ],
                    labels["application_before"]: previous.configuration.model_dump(mode="json"),
                    labels["application_after"]: selected.configuration.model_dump(mode="json"),
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


def _memory_creation_preview(
    draft: ApplicationActionDraftContent,
    labels: dict[str, str],
    format_dt: Callable[[str | None], str],
) -> list[PreviewLine]:
    selected = MemoryCreatePatch.model_validate(draft.intent).memory_to_create
    if draft.before != {"memory_to_create": None} or selected.id != draft.command_id:
        return [Note(text=labels["application_unavailable"])]
    return [
        Note(text=labels["application_memory_creation_note"]),
        Row(
            label=labels["application_field_memory_to_create"],
            value=json.dumps(
                {
                    "id": str(selected.id),
                    **selected.configuration.model_dump(mode="json"),
                    "pinned": labels[
                        (
                            "application_memory_pinned"
                            if selected.pinned
                            else "application_memory_unpinned"
                        )
                    ],
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


def _memory_pin_preview(
    draft: ApplicationActionDraftContent,
    labels: dict[str, str],
    format_dt: Callable[[str | None], str],
) -> list[PreviewLine]:
    previous = MemoryPinPatch.model_validate(draft.before).memory_pin
    selected = MemoryPinPatch.model_validate(draft.intent).memory_pin
    if previous.pinned != previous.expected.pinned:
        return [Note(text=labels["application_unavailable"])]
    return [
        Note(text=labels["application_memory_pin_note"]),
        Row(
            label=labels["application_field_memory_pin"],
            value=json.dumps(
                {
                    "id": str(selected.expected.id),
                    "content": selected.expected.content,
                    "category": selected.expected.category,
                    labels["application_before"]: labels[
                        (
                            "application_memory_pinned"
                            if previous.pinned
                            else "application_memory_unpinned"
                        )
                    ],
                    labels["application_after"]: labels[
                        (
                            "application_memory_pinned"
                            if selected.pinned
                            else "application_memory_unpinned"
                        )
                    ],
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
