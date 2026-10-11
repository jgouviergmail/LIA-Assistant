"""Source UI and native approval store exactly the same complete correction text."""

from src.core.exceptions import ValidationError
from src.domains.journals.constants import (
    JOURNAL_ENTRY_CONTENT_ABSOLUTE_MAX_LENGTH,
    JOURNAL_PORTRAIT_FEEDBACK_THEME,
)
from src.domains.journals.schemas import JournalEntryCreate, JournalPortraitFeedbackRequest


def portrait_feedback_entry(data: JournalPortraitFeedbackRequest) -> JournalEntryCreate:
    selected = JournalPortraitFeedbackRequest.model_validate(data.model_dump())
    comment = selected.comment.strip()
    if not comment:
        raise ValidationError(detail="A portrait correction requires a nonblank comment.")
    content = comment
    if selected.highlighted_section:
        content = (
            f"User highlighted: «{selected.highlighted_section.strip()}»\nUser feedback: {comment}"
        )
    if len(content) > JOURNAL_ENTRY_CONTENT_ABSOLUTE_MAX_LENGTH:
        raise ValidationError(
            detail="Feedback and highlighted excerpt exceed the supported complete-entry length."
        )
    return JournalEntryCreate(
        theme=JOURNAL_PORTRAIT_FEEDBACK_THEME, title="User feedback on portrait", content=content
    )
