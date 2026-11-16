"""The writing-style cards: what a learning reads and replaces, what a forgetting removes."""

from collections.abc import Callable

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.writing_style_schemas import (
    WritingStyleForgetPatch,
    WritingStyleLearnPatch,
    WritingStyleRecord,
)
from src.domains.agents.drafts.card_spec import Note, PreviewLine, Row


def _record_rows(
    record: WritingStyleRecord, labels: dict[str, str], format_dt: Callable[[str | None], str]
) -> list[PreviewLine]:
    return [
        Row(
            label=labels["application_writing_style_learned_on"],
            value=format_dt(record.learned_at),
            key="date",
        ),
        Row(
            label=labels["application_writing_style_mails_read"],
            value=str(record.mails_read),
        ),
    ]


def _expiry(
    draft: ApplicationActionDraftContent,
    labels: dict[str, str],
    format_dt: Callable[[str | None], str],
) -> Row:
    return Row(
        label=labels["application_expiry"],
        value=format_dt(draft.expires_at.isoformat()),
        key="date",
    )


def writing_style_learning_preview(
    draft: ApplicationActionDraftContent,
    labels: dict[str, str],
    format_dt: Callable[[str | None], str],
) -> list[PreviewLine]:
    """A learning's card: how many sent e-mails it reads, and what it replaces."""
    scope = WritingStyleLearnPatch.model_validate(draft.intent).writing_style_learning
    lines: list[PreviewLine] = [
        Note(text=labels["application_writing_style_learn_note"]),
        Row(
            label=labels["application_writing_style_mails_to_read"],
            value=str(scope.mails_to_read),
        ),
    ]
    if scope.replaces is None:
        lines.append(Note(text=labels["application_writing_style_nothing_learned"]))
    else:
        lines.append(Note(text=labels["application_writing_style_replaces"]))
        lines.extend(_record_rows(scope.replaces, labels, format_dt))
    lines.append(_expiry(draft, labels, format_dt))
    return lines


def writing_style_forgetting_preview(
    draft: ApplicationActionDraftContent,
    labels: dict[str, str],
    format_dt: Callable[[str | None], str],
) -> list[PreviewLine]:
    """A forgetting's card: the record it removes."""
    record = WritingStyleForgetPatch.model_validate(draft.intent).writing_style_record
    return [
        Note(text=labels["application_writing_style_forget_note"]),
        *_record_rows(record, labels, format_dt),
        _expiry(draft, labels, format_dt),
    ]
