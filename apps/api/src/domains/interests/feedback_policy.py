"""One source policy computes feedback effects for both previews and persistence."""

from typing import get_args

from src.domains.interests.models import InterestStatus
from src.domains.interests.schemas import InterestFeedbackKind


def feedback_signal_changes(
    positive: int, negative: int, status: str, feedback: InterestFeedbackKind
) -> tuple[int, int, str]:
    if feedback == "thumbs_up":
        return positive + 2, negative, status
    if feedback == "thumbs_down":
        return positive, negative + 2, status
    if feedback == "block":
        return positive, negative, InterestStatus.BLOCKED.value
    raise ValueError("Select a source feedback verdict")


if set(get_args(InterestFeedbackKind)) != {"thumbs_up", "thumbs_down", "block"}:
    raise AssertionError("New source feedback verdicts require a reviewed effect policy")
