"""The reply state says the same thing on every surface a model reads (ADR-379).

A model learns what ``reply_state`` means in four places: the catalogue manifest (the
planner), the tool's own description (the ReAct loop binds the schema, never the
manifest), and the block both answering prompts carry. A status one of them forgets is
a status a model guesses — and « the person has not answered » guessed from nothing is
the defect this programme closes. The vocabulary is the code's (``ReplyStatus``), and
this test keeps the four surfaces on it. A voice lookup reads a short line of its own
in place of the manifest: it names the field too.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import get_args

import pytest

from src.core.mail_reply_state import (
    NOT_CHECKED,
    REPLY_STATE_KEY,
    ReplyState,
    ReplyStatus,
    reply_state_text,
)
from src.domains.agents.emails.get_emails_manifest import (
    REPLY_STATE_DESCRIPTION,
    get_emails_catalogue_manifest,
)
from src.domains.agents.prompts import get_response_prompt
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.agents.telephony.live_tools import tool_descriptions
from src.domains.agents.tools.emails_tools import get_emails_tool

pytestmark = [pytest.mark.unit]

VOCABULARY = (*get_args(ReplyStatus), NOT_CHECKED)
_BLOCK = re.compile(r"<MailReplyState>.*?</MailReplyState>", re.DOTALL)


def _block(prompt_name: str) -> str:
    found = _BLOCK.search(load_prompt(prompt_name))
    assert found is not None, f"{prompt_name} carries no <MailReplyState> block"
    return found.group()


def _on_one_line(text: str) -> str:
    return " ".join(text.split())


class TestTheToolSaysItOnBothItsSurfaces:
    def test_the_planner_reads_it_in_the_manifest(self) -> None:
        assert REPLY_STATE_DESCRIPTION in get_emails_catalogue_manifest.description

    def test_the_react_loop_reads_the_same_words_in_the_tool_description(self) -> None:
        assert REPLY_STATE_DESCRIPTION in _on_one_line(get_emails_tool.description)

    @pytest.mark.parametrize("status", VOCABULARY)
    def test_every_status_the_code_produces_is_named(self, status: str) -> None:
        assert f"`{status}`" in REPLY_STATE_DESCRIPTION

    def test_an_optional_fact_is_no_published_output_path(self) -> None:
        """A published path exists on EVERY built item (ADR-184): the state is told only
        when the mailbox could tell, so the description says it and no path promises it."""
        paths = {output.path for output in get_emails_catalogue_manifest.outputs}
        assert not any(REPLY_STATE_KEY in path for path in paths)


class TestTheAnsweringPromptsSayItOnce:
    def test_the_two_prompts_carry_the_same_block(self) -> None:
        assert _block("response_system_prompt_base") == _block("react_agent_prompt")

    @pytest.mark.parametrize("status", VOCABULARY)
    def test_every_status_the_code_produces_is_explained(self, status: str) -> None:
        assert status in _block("response_system_prompt_base")

    def test_not_known_is_never_read_as_not_answered(self) -> None:
        """The rule the whole programme rests on, stated where the answer is written."""
        block = _on_one_line(_block("response_system_prompt_base"))
        assert "Never say the person has not answered" in block


class TestTheInitiativeNeverOffersWhatWasDone:
    def test_its_prompt_names_the_line_its_summary_writes(self) -> None:
        """The initiative reads a summary line (``reply_state_text``), and its prompt
        forbids offering an answer by NAMING that line: the two move together."""
        observed = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)
        state = ReplyState(
            status="unanswered", observed_at=observed, valid_until=observed + timedelta(minutes=2)
        )
        label = reply_state_text(state, now=observed).partition(":")[0]

        prompt = load_prompt("initiative_prompt")

        assert label and prompt.count(f'"{label}"') >= 2  # the suggestion and the chips


class TestTheAnswerIsToldWhichMailsWereAnswered:
    """The turn's answered mails are stated in a block of their own, the LAST of the
    context, and only when there are some (ADR-284: one instruction per context)."""

    DATA = "[email_a] [EXT] subject: Quote for the roof"
    LINES = "- [email_a] answered on 2026-11-10T13:40+00:00"

    def test_the_block_closes_the_context_after_the_persons_question(self) -> None:
        """Its place is measured (2026-11-11, the node's own chain): right after the data
        the block changed nothing; after the question it halved the wrong openings."""
        prompt = get_response_prompt(
            user_language="en",
            user_query="What do my mails ask of me?",
            data_for_filtering=self.DATA,
            answered_mail=self.LINES,
        )

        assert prompt.index("</UserQuery>") < prompt.index("<MailAlreadyAnswered>")
        assert prompt.rstrip().endswith(f"{self.LINES}\n</MailAlreadyAnswered>")

    def test_a_turn_with_no_answered_mail_carries_no_block(self) -> None:
        prompt = get_response_prompt(user_language="en", data_for_filtering=self.DATA)

        assert "MailAlreadyAnswered" not in prompt


class TestAVoiceLookupIsToldToo:
    def test_its_line_names_the_field_its_result_carries(self) -> None:
        """A phone or direct Live lookup hears the state's one line (``test_live_tools``
        holds that projection); the line describing the tool to the voice names the field."""
        assert f"`{REPLY_STATE_KEY}`" in tool_descriptions()["get_emails_tool"]
