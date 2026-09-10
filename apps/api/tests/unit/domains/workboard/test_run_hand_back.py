"""A run that passes the ball back hands the TICKET back (2026-09-09).

A question nobody holds is a question nobody answers: leaving a ``waiting`` or
``validating`` ticket assigned to LIA showed the person a ticket LIA holds while
nothing was going to happen until they replied. A FAILURE is not a hand-back —
nothing retries it, but nothing is asked of the person either, and the card must
keep saying that LIA is the one that stumbled.
"""

from __future__ import annotations

import pytest

from src.domains.workboard.constants import TicketStatus
from src.infrastructure.scheduler.workboard_runner import HANDED_BACK_STATUSES

pytestmark = pytest.mark.unit


class TestWhichColumnsGiveTheTicketBack:
    def test_a_question_a_confirmation_and_a_result_to_validate_do(self) -> None:
        assert HANDED_BACK_STATUSES == {
            TicketStatus.WAITING.value,
            TicketStatus.CONFIRMING.value,
            TicketStatus.VALIDATING.value,
        }

    def test_a_failure_does_not(self) -> None:
        # It leaves the ticket where the run found it, and nothing is asked of
        # the person until they say so.
        assert TicketStatus.IN_PROGRESS.value not in HANDED_BACK_STATUSES
        assert TicketStatus.TODO.value not in HANDED_BACK_STATUSES
