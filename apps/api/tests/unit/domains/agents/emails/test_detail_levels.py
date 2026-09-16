"""What a message carries at each detail level, and how a long body is served.

ADR-287: the assistant REASONS over e-mails — « résume mes non lus », « synthèse
des newsletters de la semaine », a morning routine — so one tool serves three
levels chosen by the question: ``metadata`` (no body, no model call), ``full``
(the clean body, paginated by PARAGRAPH under a token budget, never cut
mid-sentence, the continuation stated) and ``summary`` (a digest per message,
computed once and cached — the digest itself is ``emails/digest.py``'s job).
Before: every search downloaded every body and cut it at 1 500 characters,
which is how a professional assistant came to treat e-mails superficially.
"""

from __future__ import annotations

import pytest

from src.domains.agents.emails.detail_levels import (
    EmailDetail,
    apply_detail_level,
    coerce_detail,
    paginate_body,
)
from src.domains.agents.utils.token_utils import count_tokens

pytestmark = [pytest.mark.unit]


def _paragraph(index: int, words: int = 120) -> str:
    return " ".join(f"word{index}n{i}" for i in range(words)) + "."


class TestCoerceDetail:
    def test_the_three_levels_and_their_spellings(self) -> None:
        assert coerce_detail("metadata") is EmailDetail.METADATA
        assert coerce_detail("SUMMARY") is EmailDetail.SUMMARY
        assert coerce_detail(" full ") is EmailDetail.FULL
        assert coerce_detail(EmailDetail.SUMMARY) is EmailDetail.SUMMARY

    def test_anything_else_is_full(self) -> None:
        """The semantic validator does not enforce enums (ADR-184): the tool
        repairs an unknown value to the default rather than failing the step."""
        assert coerce_detail(None) is EmailDetail.FULL
        assert coerce_detail("bogus") is EmailDetail.FULL
        assert coerce_detail(3) is EmailDetail.FULL


class TestPaginateBody:
    def test_a_short_body_is_one_part_and_untouched(self) -> None:
        text, total = paginate_body("Hello.\n\nWorld.", part=1, part_tokens=1_000)
        assert (text, total) == ("Hello.\n\nWorld.", 1)

    def test_parts_break_at_paragraphs_never_mid_sentence(self) -> None:
        paragraphs = [_paragraph(i) for i in range(5)]
        body = "\n\n".join(paragraphs)
        per_paragraph = count_tokens(paragraphs[0])
        budget = per_paragraph * 2 + 10  # two paragraphs fit, the third does not

        first, total = paginate_body(body, part=1, part_tokens=budget)

        assert total == 3
        assert first.startswith(paragraphs[0])
        assert paragraphs[1] in first
        assert paragraphs[2] not in first
        assert "[continued: part 1/3" in first and "part=2" in first

    def test_the_last_part_carries_no_continuation(self) -> None:
        paragraphs = [_paragraph(i) for i in range(5)]
        body = "\n\n".join(paragraphs)
        budget = count_tokens(paragraphs[0]) * 2 + 10

        last, total = paginate_body(body, part=3, part_tokens=budget)

        assert total == 3
        assert last.startswith(paragraphs[4])
        assert "[continued" not in last

    def test_a_part_past_the_end_is_the_last_part(self) -> None:
        paragraphs = [_paragraph(i) for i in range(5)]
        body = "\n\n".join(paragraphs)
        budget = count_tokens(paragraphs[0]) * 2 + 10

        text, total = paginate_body(body, part=99, part_tokens=budget)

        assert total == 3
        assert text.startswith(paragraphs[4])

    def test_a_part_below_one_is_the_first_part(self) -> None:
        body = "\n\n".join(_paragraph(i) for i in range(3))
        text, _ = paginate_body(body, part=0, part_tokens=50)
        assert text.startswith(_paragraph(0)[:20])

    def test_an_oversized_paragraph_breaks_at_lines_then_travels_whole(self) -> None:
        """No paragraph is ever cut mid-sentence: a single paragraph larger than
        the budget breaks at its lines, and a single line larger than the budget
        is served whole — the budget is exceeded, never the sentence."""
        lines = [_paragraph(i, words=60) for i in range(4)]
        body = "\n".join(lines)  # one paragraph, four lines
        budget = count_tokens(lines[0]) + 5

        first, total = paginate_body(body, part=1, part_tokens=budget)

        assert total == 4
        assert first.startswith(lines[0])
        assert lines[1] not in first

        huge_line = _paragraph(9, words=400)
        whole, total_single = paginate_body(huge_line, part=1, part_tokens=20)
        assert total_single == 1
        assert whole == huge_line

    def test_an_empty_body_is_one_empty_part(self) -> None:
        assert paginate_body("", part=1, part_tokens=100) == ("", 1)


class TestApplyDetailLevel:
    def _emails(self) -> list[dict[str, object]]:
        return [
            {
                "id": "m1",
                "subject": "A",
                "snippet": "a…",
                "body": "\n\n".join(_paragraph(i) for i in range(4)),
            },
            {"id": "m2", "subject": "B", "snippet": "b…", "body": "Short."},
        ]

    def test_metadata_drops_the_body_and_keeps_the_snippet(self) -> None:
        emails = self._emails()
        apply_detail_level(emails, detail=EmailDetail.METADATA, part=1, part_tokens=1_000)
        assert all("body" not in e for e in emails)
        assert [e["snippet"] for e in emails] == ["a…", "b…"]

    def test_full_serves_one_part_and_says_how_many_there_are(self) -> None:
        emails = self._emails()
        budget = count_tokens(_paragraph(0)) * 2 + 10
        apply_detail_level(emails, detail=EmailDetail.FULL, part=1, part_tokens=budget)
        assert emails[0]["body_parts"] == 2
        assert emails[0]["body_part"] == 1
        assert "[continued: part 1/2" in str(emails[0]["body"])
        assert emails[1]["body"] == "Short."
        assert emails[1]["body_parts"] == 1

    def test_summary_keeps_the_body_only_where_no_digest_landed(self) -> None:
        """The digest step (emails/digest.py) runs BEFORE this and stamps
        ``digest_status``; a message it could not digest keeps its body so the
        model can still read it, a digested one sheds it."""
        emails = self._emails()
        emails[0]["digest_status"] = "computed"
        emails[1]["digest_status"] = "failed"
        apply_detail_level(emails, detail=EmailDetail.SUMMARY, part=1, part_tokens=1_000)
        assert "body" not in emails[0]
        assert emails[1]["body"] == "Short."

    def test_summary_with_no_digest_at_all_falls_back_to_full(self) -> None:
        emails = self._emails()
        apply_detail_level(emails, detail=EmailDetail.SUMMARY, part=1, part_tokens=1_000)
        assert all("body" in e for e in emails)
