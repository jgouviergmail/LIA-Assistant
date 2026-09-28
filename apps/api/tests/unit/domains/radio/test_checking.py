"""The model verifier: a line it does not vouch for never airs, and a gutted script is refused."""

from __future__ import annotations

import pytest
from langchain_core.messages import BaseMessage
from pydantic import BaseModel

from src.core.constants import DYNAMIC_CONTEXT_MARKER
from src.domains.radio.checking import CheckDraft, LineVerdict, unsupported_positions
from src.domains.radio.facts import FactKind, FactPack, RadioFact, Sensitivity, SourceRef
from src.domains.radio.formats import RadioFormat, RadioRole
from src.domains.radio.prompting import StationVoice, load_templates, render_verifier_prompt
from src.domains.radio.script import LineKind, RadioDelivery, ScriptDraft, ScriptLine, ScriptPart
from src.domains.radio.verification import (
    Refusal,
    Violation,
    drop_unsupported,
    verify_script,
)
from src.domains.radio.writing import ModelLineChecker
from src.infrastructure.llm.structured_output_errors import StructuredOutputTruncatedError

pytestmark = pytest.mark.unit

TEMPLATE = load_templates().verifier
STATION = StationVoice(station_name="Radio 42", language_name="English", personality="Calm.")


def fact(index: int) -> RadioFact:
    return RadioFact(
        id=f"n{index}",
        kind=FactKind.NEWS,
        text=f"Story {index} happened on {index} September.",
        key=f"news:{index}",
        sensitivity=Sensitivity.PUBLIC,
        source=SourceRef(label="Example News", url=f"https://news.example.org/{index}"),
    )


PACK = FactPack(format=RadioFormat.BULLETIN, facts=tuple(fact(n) for n in range(1, 6)))


def line(part: ScriptPart, kind: LineKind, text: str, *refs: str) -> ScriptLine:
    return ScriptLine(
        role=RadioRole.ANCHOR,
        part=part,
        kind=kind,
        text=text,
        delivery=RadioDelivery(),
        refs=list(refs),
    )


DRAFT = ScriptDraft(
    title="News",
    lines=[
        line(ScriptPart.INTRO, LineKind.TRANSITION, "Here is the news."),
        *(
            line(ScriptPart.BODY, LineKind.FACT, f"Story {n} happened on {n} September.", f"n{n}")
            for n in range(1, 6)
        ),
        line(ScriptPart.OUTRO, LineKind.TRANSITION, "That was the news."),
    ],
)
VERIFIED = verify_script(DRAFT, PACK, language="en", quote_max_chars=120, station_name="LIA Radio")


def verdict(number: int, supported: bool) -> LineVerdict:
    return LineVerdict(line=number, evidence="", supported=supported)


def verdicts(*supported: bool) -> list[LineVerdict]:
    return [verdict(n, s) for n, s in enumerate(supported, start=1)]


def test_the_verdict_is_written_after_its_evidence() -> None:
    """A model writes the fields in order: the facts' word comes BEFORE the verdict.

    Measured 2026-09-27 on a fixed set (30 scripts, three passes): told to say what
    the facts hold first, the verifier rejected a supported line 19 % of the time
    instead of 26 %, and missed none of the planted claims.
    """
    assert list(LineVerdict.model_fields) == ["line", "evidence", "supported"]
    assert LineVerdict.model_fields["evidence"].is_required()


class TestVerdict:
    def test_the_transitions_are_never_checked(self) -> None:
        assert VERIFIED.accepted and len(VERIFIED.lines) == 7
        assert unsupported_positions(VERIFIED.lines, verdicts(True, True, True, True, True)) == (
            frozenset()
        )

    def test_a_line_left_without_a_verdict_is_not_vouched_for(self) -> None:
        assert unsupported_positions(VERIFIED.lines, verdicts(True, True, True)) == frozenset(
            {4, 5}
        )

    def test_two_verdicts_that_disagree_count_against_the_line(self) -> None:
        answer = [*verdicts(True, True, True, True, True), verdict(2, False)]
        assert unsupported_positions(VERIFIED.lines, answer) == frozenset({2})

    def test_a_number_naming_no_line_is_ignored(self) -> None:
        answer = [*verdicts(True, True, True, True, True), verdict(9, False)]
        assert unsupported_positions(VERIFIED.lines, answer) == frozenset()


class TestDropUnsupported:
    def test_one_line_in_five_is_dropped_and_the_script_stands(self) -> None:
        checked = drop_unsupported(DRAFT, PACK, VERIFIED, frozenset({3}), language="en")
        assert checked.accepted
        assert [line.text for line in checked.lines if line.refs] == [
            "Story 1 happened on 1 September.",
            "Story 2 happened on 2 September.",
            "Story 4 happened on 4 September.",
            "Story 5 happened on 5 September.",
        ]
        assert (3, Violation.NOT_SUPPORTED) in checked.dropped  # the DRAFT's place
        assert len(checked.origins) == len(checked.lines)

    def test_a_script_the_verifier_gutted_is_refused_never_aired_shortened(self) -> None:
        checked = drop_unsupported(DRAFT, PACK, VERIFIED, frozenset({1, 2}), language="en")
        assert checked.refusal is Refusal.TOO_MANY_DROPPED

    def test_nothing_flagged_changes_nothing(self) -> None:
        assert drop_unsupported(DRAFT, PACK, VERIFIED, frozenset(), language="en") is VERIFIED


class Door:
    def __init__(self, answer: BaseModel | Exception) -> None:
        self.answer = answer
        self.sent: list[list[BaseMessage]] = []

    async def __call__[M: BaseModel](self, messages: list[BaseMessage], schema: type[M]) -> M:
        self.sent.append(messages)
        if isinstance(self.answer, Exception):
            raise self.answer
        assert isinstance(self.answer, schema)
        return self.answer


class TestModelLineChecker:
    async def test_it_sends_the_cited_facts_and_the_numbered_lines_as_data(self) -> None:
        door = Door(CheckDraft(verdicts=verdicts(True, False, True, True, True)))
        checker = ModelLineChecker(template=TEMPLATE, station=STATION, call=door)
        assert await checker.unsupported(VERIFIED.lines, PACK) == frozenset({2})
        [(system, human)] = door.sent
        assert DYNAMIC_CONTEXT_MARKER in str(system.content).splitlines()[-1]
        question = str(human.content)
        # The station's name is the listener's: below the marker, so the static
        # prefix every listener shares stays one — and naming it claims nothing.
        assert "Radio 42" in question and "Radio 42" not in str(system.content)
        assert "1 (fact) [n1] Story 1 happened on 1 September." in question  # its kind shown
        assert "Here is the news." not in question  # a transition cites nothing
        assert question.count("<external_content") == 2  # facts AND lines are fenced

    async def test_only_the_facts_the_lines_cite_are_sent(self) -> None:
        short = verify_script(
            ScriptDraft(title="Brief", lines=[DRAFT.lines[1]]),
            PACK,
            language="en",
            quote_max_chars=120,
            station_name="LIA Radio",
        )
        prompt = render_verifier_prompt(TEMPLATE, short.lines, PACK, station_name="Radio 42")
        assert "Story 1 happened" in prompt and "Story 2 happened" not in prompt

    async def test_a_refused_verdict_is_no_verdict(self) -> None:
        refusal = StructuredOutputTruncatedError("cut", provider="p", schema_name="CheckDraft")
        checker = ModelLineChecker(template=TEMPLATE, station=STATION, call=Door(refusal))
        assert await checker.unsupported(VERIFIED.lines, PACK) is None

    async def test_a_script_citing_nothing_costs_no_call(self) -> None:
        door = Door(CheckDraft())
        transitions = VERIFIED.lines[:1]
        checker = ModelLineChecker(template=TEMPLATE, station=STATION, call=door)
        assert await checker.unsupported(transitions, PACK) == frozenset()
        assert door.sent == []
