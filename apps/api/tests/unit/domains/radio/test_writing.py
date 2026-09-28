"""The two model calls: the prompt goes out in two parts, a refused answer gives nothing."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel

from src.core.constants import DYNAMIC_CONTEXT_MARKER
from src.domains.radio.analysis import AnalysisAngle, AnalysisDraft, AnalysisPoint
from src.domains.radio.facts import FactKind, FactPack, clock_fact
from src.domains.radio.formats import RadioFormat
from src.domains.radio.production import WritingRequest
from src.domains.radio.prompting import AnalysisRequest, StationVoice, load_templates
from src.domains.radio.script import ScriptDraft
from src.domains.radio.writing import ModelAnalyst, ModelScriptWriter
from src.infrastructure.llm.structured_output_errors import (
    StructuredOutputError,
    StructuredOutputTruncatedError,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 26, 9, 5, tzinfo=UTC)
STATION = StationVoice(station_name="LIA Radio", language_name="English", personality="Calm.")
TEMPLATES = load_templates()


class Door:
    """A structured door that records what it was sent and answers as told."""

    def __init__(self, answer: BaseModel | Exception) -> None:
        self.answer = answer
        self.sent: list[list[BaseMessage]] = []

    async def __call__[M: BaseModel](self, messages: list[BaseMessage], schema: type[M]) -> M:
        self.sent.append(messages)
        if isinstance(self.answer, Exception):
            raise self.answer
        assert isinstance(self.answer, schema)
        return self.answer


def request() -> WritingRequest:
    return WritingRequest(
        format=RadioFormat.OPENING,
        pack=FactPack(format=RadioFormat.OPENING, facts=(clock_fact(NOW),)),
        language="en",
        local_now=NOW,
        station_name="LIA Radio",
        station_id=True,
    )


def writer(door: Door) -> ModelScriptWriter:
    return ModelScriptWriter(
        template=TEMPLATES.writer, station=STATION, call=door, quote_max_chars=120
    )


async def test_the_static_part_is_the_system_message_the_segment_the_question() -> None:
    door = Door(ScriptDraft(title="Good morning", lines=[]))
    assert await writer(door).write(request()) == ScriptDraft(title="Good morning", lines=[])
    [(system, human)] = door.sent
    assert isinstance(system, SystemMessage) and isinstance(human, HumanMessage)
    assert DYNAMIC_CONTEXT_MARKER in str(system.content).splitlines()[-1]
    assert "opening" in str(human.content) and "LISTENER:" not in str(human.content)


@pytest.mark.parametrize(
    "refusal",
    [
        StructuredOutputTruncatedError("cut", provider="p", schema_name="ScriptDraft"),
        StructuredOutputError("bad", provider="p", schema_name="ScriptDraft"),
    ],
)
async def test_a_refused_answer_gives_no_script(refusal: StructuredOutputError) -> None:
    assert await writer(Door(refusal)).write(request()) is None


async def test_a_ceiling_refusal_is_not_taken_for_a_bad_script() -> None:
    class CeilingReached(Exception):
        pass

    with pytest.raises(CeilingReached):
        await writer(Door(CeilingReached())).write(request())


async def test_the_analysis_keeps_only_what_the_article_supports() -> None:
    door = Door(
        AnalysisDraft(
            points=[
                AnalysisPoint(angle=AnalysisAngle.FACTS, text="The vote was 312 to 250."),
                AnalysisPoint(angle=AnalysisAngle.HISTORY, text="It last happened in 1998."),
            ]
        )
    )
    analyst = ModelAnalyst(template=TEMPLATES.analyst, station=STATION, call=door)
    facts = await analyst.analyse(
        AnalysisRequest(
            title="Budget adopted",
            outlet="Example News",
            url="https://news.example.org/budget",
            published_at=NOW,
            article="Parliament adopted the budget by 312 votes to 250.",
        ),
        story_key="news:1",
        min_points=2,
        max_points=6,
    )
    assert [(f.id, f.kind) for f in facts] == [("a1", FactKind.ANALYSIS)]
    assert facts[0].source is not None and facts[0].source.label == "Example News"
    assert facts[0].source.story_key == "news:1"  # the article the analysis read


async def test_an_analysis_that_fails_gives_nothing() -> None:
    door = Door(StructuredOutputError("bad", provider="p", schema_name="AnalysisDraft"))
    analyst = ModelAnalyst(template=TEMPLATES.analyst, station=STATION, call=door)
    facts = await analyst.analyse(
        AnalysisRequest(
            title="T", outlet="O", url="https://x.example", published_at=NOW, article="A."
        ),
        story_key="news:1",
        min_points=2,
        max_points=6,
    )
    assert facts == ()
