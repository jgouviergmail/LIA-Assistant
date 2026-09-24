"""A person's exchange rhythm: their choice, else the instance's default (ADR-311).

The rhythm decides what shape a ReAct turn's prompt takes. Frequent exchanges
bind every tool, place the turn's context after the question and drop the
history by blocks, so that the next turn reads this one back from the provider's
cache. Occasional exchanges keep the relevance selection, whose cost does not
depend on how soon the next turn comes. The account stores the person's choice;
an account that never chose follows ``REACT_CROSS_TURN_CACHE_ENABLED``, the
operator's default. Reads are forgiving, so a value nobody wrote falls back to
that default.
"""

from __future__ import annotations

import pytest

from src.core.config import settings
from src.core.exchange_rhythm import ExchangeRhythm, effective_exchange_rhythm

pytestmark = pytest.mark.unit


class TestTheChoice:
    @pytest.mark.parametrize("instance_default", [True, False])
    @pytest.mark.parametrize("chosen", list(ExchangeRhythm))
    def test_the_person_s_choice_wins_over_the_instance_default(
        self, monkeypatch: pytest.MonkeyPatch, chosen: ExchangeRhythm, instance_default: bool
    ) -> None:
        monkeypatch.setattr(settings, "react_cross_turn_cache_enabled", instance_default)

        assert effective_exchange_rhythm(chosen.value) is chosen


class TestTheDefault:
    @pytest.mark.parametrize(
        ("instance_default", "expected"),
        [(True, ExchangeRhythm.FREQUENT), (False, ExchangeRhythm.OCCASIONAL)],
    )
    @pytest.mark.parametrize("stored", [None, "", "weekly"])
    def test_no_readable_choice_follows_the_instance_default(
        self,
        monkeypatch: pytest.MonkeyPatch,
        stored: str | None,
        instance_default: bool,
        expected: ExchangeRhythm,
    ) -> None:
        monkeypatch.setattr(settings, "react_cross_turn_cache_enabled", instance_default)

        assert effective_exchange_rhythm(stored) is expected


class TestTheVocabulary:
    def test_it_names_exactly_two_rhythms_as_they_are_stored(self) -> None:
        assert [rhythm.value for rhythm in ExchangeRhythm] == ["frequent", "occasional"]


class TestTheOneReader:
    """The instance setting is a DEFAULT, read in one place (ADR-311).

    Three modules used to read it, each on its own call: the selector at setup, the
    history and the layout on every call. A person's choice must win over it for
    all three together, and within a turn, so the loop reads the turn's state and
    only the rhythm's resolution reads the setting.
    """

    def test_only_the_resolution_reads_the_instance_setting(self) -> None:
        import ast
        from pathlib import Path

        src = Path(__file__).resolve().parents[3] / "src"
        readers = sorted(
            path.relative_to(src).as_posix()
            for path in src.rglob("*.py")
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            if isinstance(node, ast.Attribute) and node.attr == "react_cross_turn_cache_enabled"
        )

        assert readers == ["core/exchange_rhythm.py"]


class TestTheFrontendMirror:
    """The settings screen offers exactly the rhythms the API accepts (ADR-184's rule)."""

    def test_the_web_list_is_the_backend_vocabulary(self) -> None:
        import re
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[4] / "web" / "src" / "lib" / "exchange-rhythm.ts"
        ).read_text(encoding="utf-8")
        declared = re.search(r"EXCHANGE_RHYTHMS = \[([^\]]*)\] as const", source)

        assert declared is not None, "EXCHANGE_RHYTHMS moved: update this contract test"
        offered = re.findall(r"'([a-z]+)'", declared.group(1))
        assert offered == [rhythm.value for rhythm in ExchangeRhythm]
