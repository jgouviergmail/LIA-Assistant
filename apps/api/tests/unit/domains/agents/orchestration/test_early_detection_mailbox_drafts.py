"""A request about a mailbox DRAFT is never asked for a new e-mail's content.

The early detection runs before the planner on the English pivot. An intent to
send, reply or forward on the e-mail domain demands a recipient and a content —
right for a new e-mail, wrong for a draft that already holds both: « send all
my drafts » would have been answered « Who would you like to send this email
to? », and « prepare a reply to Paul » — where LIA writes the reply itself —
« What would you like to reply? ».
"""

from __future__ import annotations

import pytest

from src.domains.agents.orchestration.semantic_validator import (
    detect_early_insufficient_content,
)

pytestmark = pytest.mark.unit


def _intelligence(domain: str, intent: str) -> dict[str, object]:
    return {"domains": [domain], "immediate_intent": intent}


class TestADraftRequestIsNotAskedForContent:
    @pytest.mark.parametrize(
        ("request_text", "intent"),
        [
            ("send all my drafts", "send"),
            ("send the draft for Marie", "send"),
            ("send my last draft", "send"),
            ("prepare a reply to Paul", "reply"),
            ("prepare the forward of this email", "forward"),
        ],
    )
    def test_no_clarification(self, request_text: str, intent: str) -> None:
        result = detect_early_insufficient_content(
            _intelligence("email", intent), request_text, "fr"
        )

        assert result is None


class TestANewEmailIsStillAskedForWhatIsMissing:
    def test_a_send_without_recipient_asks_for_one(self) -> None:
        result = detect_early_insufficient_content(
            _intelligence("email", "send"), "send an email", "fr"
        )

        assert result is not None
        assert result.clarification_field == "recipient"

    def test_a_reply_without_content_asks_for_it(self) -> None:
        result = detect_early_insufficient_content(
            _intelligence("email", "reply"), "reply to Paul", "fr"
        )

        assert result is not None
        assert result.clarification_field == "body"

    def test_the_draft_words_do_not_silence_another_domain(self) -> None:
        """« prepare » is a draft word for e-mail only: a task still needs a title."""
        result = detect_early_insufficient_content(
            _intelligence("task", "create"), "prepare a task", "fr"
        )

        assert result is not None
        assert result.clarification_field == "title"
