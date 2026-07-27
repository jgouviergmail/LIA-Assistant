"""Triviality detection must cover all six supported languages (L4).

Only French and English were covered, so a German "ja", a Spanish "gracias", an
Italian "grazie" or a Chinese "好的" was treated as a meaningful message: one
embedding plus up to four extraction LLM calls, per acknowledgement, forever.

The opposite risk is worse and is why L2 had to ship first: the patterns are
matched against ANY short message, and several acknowledgements are also real
surnames. A missed skip costs tokens; a wrong skip loses data.
"""

import pytest

from src.infrastructure.llm.user_message_embedding import is_trivial_message


@pytest.mark.unit
class TestAcknowledgementsAreTrivial:
    """One acknowledgement per supported language must be skipped."""

    @pytest.mark.parametrize(
        ("language", "message"),
        [
            ("fr", "ok"),
            ("fr", "merci"),
            ("fr", "d'accord"),
            ("en", "thanks"),
            ("en", "yes"),
            ("en", "sure"),
            ("de", "ja"),
            ("de", "nein"),
            ("de", "danke"),
            ("de", "alles klar"),
            ("de", "perfekt"),
            ("es", "sí"),
            ("es", "gracias"),
            ("es", "perfecto"),
            ("es", "de acuerdo"),
            ("it", "sì"),
            ("it", "grazie"),
            ("it", "va bene"),
            ("it", "perfetto"),
            ("zh", "好的"),
            ("zh", "谢谢"),
            ("zh", "收到"),
            ("zh", "明白"),
        ],
    )
    def test_acknowledgement_is_trivial(self, language: str, message: str):
        assert is_trivial_message(message) is True, f"{language}: {message!r}"

    @pytest.mark.parametrize(
        "message",
        ["OK", "Merci", "Danke!", "Gracias.", "GRAZIE", "Ja?", "好的。"],
    )
    def test_case_and_punctuation_variants(self, message: str):
        """Case folding and trailing punctuation must not defeat the match."""
        assert is_trivial_message(message) is True


@pytest.mark.unit
class TestMeaningfulMessagesSurvive:
    """The oracle in the other direction — nothing meaningful may be dropped."""

    @pytest.mark.parametrize(
        ("language", "message"),
        [
            ("fr", "je déménage"),
            ("en", "I moved out"),
            ("de", "ich ziehe um"),
            ("es", "me mudo a Lyon"),
            ("it", "mi trasferisco"),
            ("zh", "我搬到里昂了"),
        ],
    )
    def test_short_meaningful_message_is_not_trivial(self, language: str, message: str):
        assert is_trivial_message(message) is False, f"{language}: {message!r}"

    def test_long_message_is_never_trivial(self):
        """The length guard precedes the patterns."""
        assert is_trivial_message("ok " * 10) is False


@pytest.mark.unit
class TestSurnameCollisionsAreBounded:
    """The regression oracle for D7 — these tokens must stay OUT of the patterns.

    Each is a real surname. Adding it would make a contact of that name
    unreachable in every conversational path, and — before L2 — in person
    lookups too.
    """

    @pytest.mark.parametrize("surname", ["gut", "vale", "bene", "claro"])
    def test_excluded_surnames_are_not_matched(self, surname: str):
        assert is_trivial_message(surname) is False

    @pytest.mark.parametrize("surname", ["Gut", "Vale", "Bene", "Claro"])
    def test_excluded_surnames_capitalized(self, surname: str):
        assert is_trivial_message(surname) is False

    def test_person_lookups_are_immune_whatever_the_patterns(self):
        """L2 is what bounds the residual risk of the fr/en legacy tokens.

        "Fine" still matches — it is a shipped English acknowledgement — but a
        person lookup no longer routes through the heuristic at all.
        """
        import inspect

        from src.infrastructure.llm.user_message_embedding import get_or_compute_embedding

        signature = inspect.signature(get_or_compute_embedding)
        parameter = signature.parameters["is_conversational"]
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
        assert parameter.default is inspect.Parameter.empty, (
            "is_conversational must stay required: a default is what let a person "
            "name be judged a trivial acknowledgement."
        )
