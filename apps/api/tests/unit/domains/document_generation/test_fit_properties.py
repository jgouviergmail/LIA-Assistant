"""What the width estimator must hold for every script, not just Latin.

``fit.py`` is calibrated against PowerPoint on 54 combinations, and every one of
those measurements is Latin. That is exactly how a full-width glyph came to be
counted at 0.46 em: a dense Chinese slide measured 238 pt where it takes 442 in
a 356 pt frame, and the overflow ORACLE agreed with the renderer because both
read the same function (ADR-274).

A calibration corpus cannot catch that class — it can only fail on a fixture
somebody wrote. These properties can, because they hold for any string in any
script, and they are checked over nine alphabets including the ones the
calibration never saw.

The direction of the safety matters and is asserted: over-estimating shrinks or
splits a line that would have fitted, which is ugly; UNDER-estimating overflows
the frame, which is the defect. So the bounds are one-sided on purpose.
"""

from __future__ import annotations

import random

import pytest

from src.domains.document_generation.fit import (
    AVG_CHAR_WIDTH_EM,
    FULL_WIDTH_EM,
    display_columns,
    text_width_em,
)

pytestmark = pytest.mark.unit

#: One entry per writing system the renderer has actually been handed, plus the
#: ambiguous-width punctuation that reads narrow in Latin and wide in CJK.
ALPHABETS: dict[str, str] = {
    "latin": "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ .,;:!?'-",
    "accents": "éèêëàâäîïôöùûüçñÿ",
    "cjk": "中文测试内容广告设计报告会议纪要项目管理",
    "kana": "こんにちはカタカナひらがなテスト",
    "hangul": "안녕하세요한국어테스트",
    "cyrillic": "абвгдеёжзийклмнопрстуфхцч",
    "arabic": "مرحبااختبارنص",
    "emoji": "😀🎯📊🚀✅❌",
    "ambiguous": "…—–«»§¶°±×÷←→",
}

SAMPLE = 300
SEED = 20260910


def _strings() -> list[tuple[str, str]]:
    """(alphabet name, string) — deterministic under SEED."""
    rng = random.Random(SEED)
    drawn: list[tuple[str, str]] = []
    names = list(ALPHABETS)
    for _ in range(SAMPLE):
        name = rng.choice(names)
        alphabet = ALPHABETS[name]
        drawn.append((name, "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 120)))))
    # Every alphabet at least once, whatever the draw did.
    drawn.extend((name, alphabet) for name, alphabet in ALPHABETS.items())
    return drawn


STRINGS = _strings()


class TestTheWidthEstimatorHoldsForEveryScript:
    """One sample, six properties."""

    def test_the_sample_covers_every_alphabet(self) -> None:
        assert {name for name, _ in STRINGS} == set(ALPHABETS)

    def test_a_non_empty_string_has_a_positive_width(self) -> None:
        for name, text in STRINGS:
            assert text_width_em(text) > 0, f"{name}: {text[:20]!r}"

    def test_adding_a_glyph_never_narrows_the_string(self) -> None:
        """Monotone: the fitter shrinks and splits on this, so it must not dip."""
        for name, text in STRINGS:
            before = text_width_em(text)
            for glyph in ALPHABETS[name][:3]:
                assert text_width_em(text + glyph) >= before, f"{name}: {text[:20]!r}"

    def test_the_width_stays_between_the_narrow_and_full_bounds(self) -> None:
        """No glyph may be counted narrower than narrow or wider than one em."""
        for name, text in STRINGS:
            width = text_width_em(text)
            assert len(text) * AVG_CHAR_WIDTH_EM - 1e-9 <= width, f"{name}: under the floor"
            assert width <= len(text) * FULL_WIDTH_EM + 1e-9, f"{name}: over the ceiling"

    def test_measuring_two_halves_measures_the_whole(self) -> None:
        """A line is fitted piece by piece; a cut must not change the total."""
        rng = random.Random(SEED)
        for name, text in STRINGS:
            cut = rng.randint(0, len(text))
            halves = text_width_em(text[:cut]) + text_width_em(text[cut:])
            assert abs(halves - text_width_em(text)) < 1e-9, f"{name}: {text[:20]!r}"

    def test_a_full_width_glyph_is_counted_as_one_em(self) -> None:
        """The measured defect, stated as the property that closes it."""
        for name in ("cjk", "kana", "hangul"):
            text = ALPHABETS[name]
            assert text_width_em(text) == pytest.approx(len(text) * FULL_WIDTH_EM)

    def test_pure_ascii_still_follows_the_latin_calibration(self) -> None:
        """The 54 PowerPoint measurements are Latin; they must keep holding."""
        for name, text in STRINGS:
            if not text.isascii():
                continue
            assert text_width_em(text) == pytest.approx(len(text) * AVG_CHAR_WIDTH_EM), name

    def test_the_column_count_reads_the_same_width(self) -> None:
        """``display_columns`` sizes table columns from the very same measure."""
        for name, text in STRINGS:
            expected = text_width_em(text) / AVG_CHAR_WIDTH_EM
            assert display_columns(text) == pytest.approx(expected), f"{name}: {text[:20]!r}"
