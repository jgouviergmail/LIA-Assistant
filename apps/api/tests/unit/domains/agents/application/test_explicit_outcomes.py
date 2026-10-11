"""Waiting and partial failure can never be announced as completed success."""

import pytest
from pydantic import ValidationError

from src.domains.agents.application.outcomes import ApplicationExecutionOutcome, ApplicationPhase

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "phase",
    [
        ApplicationPhase.WAITING,
        ApplicationPhase.FAILED,
        ApplicationPhase.CONFLICT,
        ApplicationPhase.EXPIRED,
    ],
)
def test_incomplete_or_refused_action_cannot_report_success(phase: ApplicationPhase) -> None:
    with pytest.raises(ValidationError):
        ApplicationExecutionOutcome(success=True, phase=phase, committed=False)


@pytest.mark.parametrize("phase", [ApplicationPhase.PENDING, ApplicationPhase.CLAIMED])
def test_pending_or_claimed_state_is_not_an_execution_result(phase: ApplicationPhase) -> None:
    with pytest.raises(ValidationError):
        ApplicationExecutionOutcome(success=False, phase=phase)


def test_post_commit_failure_retains_the_saved_state_without_claiming_full_success() -> None:
    result = ApplicationExecutionOutcome(
        success=False,
        phase=ApplicationPhase.FAILED,
        committed=True,
        values={"font_size": 17},
        error_code="POST_COMMIT_FAILURE",
    )
    assert result.committed and not result.success
