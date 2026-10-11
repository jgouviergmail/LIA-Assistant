"""The combined stored correction must respect the real complete-entry boundary."""

import pytest
from pydantic import ValidationError as PydanticValidationError

from src.core.exceptions import ValidationError
from src.domains.journals.portrait_feedback_configuration import portrait_feedback_entry
from src.domains.journals.schemas import JournalPortraitFeedbackRequest

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "comment,excerpt",
    [(" " * 3, None), ("a" * 1900, "b" * 500)],
    ids=["blank", "combined_overflow"],
)
def test_empty_or_oversized_combined_correction_is_refused(
    comment: str, excerpt: str | None
) -> None:
    with pytest.raises((ValidationError, PydanticValidationError)):
        portrait_feedback_entry(
            JournalPortraitFeedbackRequest(comment=comment, highlighted_section=excerpt)
        )


def test_source_feedback_keeps_complete_comment_and_highlighted_section() -> None:
    entry = portrait_feedback_entry(
        JournalPortraitFeedbackRequest(
            comment="  Correction  ", highlighted_section="  Prior text  "
        )
    )
    assert entry.content == "User highlighted: «Prior text»\nUser feedback: Correction"
    assert entry.title == "User feedback on portrait" and entry.theme.value == "user_observations"
