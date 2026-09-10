"""What a removal tells each side about the work that came back (ADR-276 lot 5).

The connection notification already existed; this lot gives it the one fact the
severance itself does not carry — what happened to the work in flight. It is
appended to the EXISTING sentence rather than sent as a second notification: two
messages a second apart about one event is noise, and the peers path already
reaches both sides.

Three rules, each pinned below: nothing is added when nothing moved (« 0 ticket
came back » is noise), the count is the RECIPIENT's own (a pair usually holds
work both ways), and every language has both a singular and a plural — a « 1
tickets » is the kind of seam a reader notices immediately.
"""

from __future__ import annotations

import pytest

from src.core.i18n_proactive import ProactiveMessages

pytestmark = pytest.mark.unit

LANGUAGES = ("fr", "en", "es", "de", "it", "zh-CN")


class TestTheSentenceIsAddedOnlyWhenSomethingMoved:
    @pytest.mark.parametrize("language", LANGUAGES)
    def test_no_ticket_no_extra_sentence(self, language: str) -> None:
        plain = ProactiveMessages.peer_removed_body("Marie", language)
        with_zero = ProactiveMessages.peer_removed_body("Marie", language, released=0)

        assert plain == with_zero

    @pytest.mark.parametrize("language", LANGUAGES)
    def test_one_ticket_adds_a_singular_sentence(self, language: str) -> None:
        plain = ProactiveMessages.peer_removed_body("Marie", language)
        one = ProactiveMessages.peer_removed_body("Marie", language, released=1)

        assert one.startswith(plain)
        assert len(one) > len(plain)
        assert "1" in one

    @pytest.mark.parametrize("language", LANGUAGES)
    def test_several_tickets_read_differently_from_one(self, language: str) -> None:
        one = ProactiveMessages.peer_removed_body("Marie", language, released=1)
        many = ProactiveMessages.peer_removed_body("Marie", language, released=4)

        assert "4" in many
        # Chinese has no plural form, so the two sentences differ only by the
        # number; every other language must inflect.
        if language == "zh-CN":
            assert one.replace("1", "4") == many
        else:
            assert one.replace("1", "4") != many

    def test_the_name_still_reaches_the_sentence(self) -> None:
        assert "Marie" in ProactiveMessages.peer_removed_body("Marie", "fr", released=2)


class TestChineseTypography:
    def test_no_latin_space_between_two_chinese_sentences(self) -> None:
        """Chinese sets no space after 。 — a Latin space there reads as a
        seam between two texts glued together, which is what it was."""
        body = ProactiveMessages.peer_removed_body("玛丽", "zh-CN", released=2)

        assert "。 " not in body
        assert "。2 个工单" in body
