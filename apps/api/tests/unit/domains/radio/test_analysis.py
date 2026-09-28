"""The expert may bring background, never a figure the article does not state."""

from __future__ import annotations

import pytest

from src.domains.radio.analysis import AnalysisAngle, AnalysisDraft, AnalysisPoint, analysis_facts
from src.domains.radio.facts import FactKind, FactPack, Sensitivity, SourceRef
from src.domains.radio.formats import RadioFormat

pytestmark = pytest.mark.unit

ARTICLE = "Parliament adopted the 2027 budget by 312 votes; the deficit is 3.9% of output."
SOURCE = SourceRef(label="Example News", url="https://news.example.org/budget")


def point(angle: AnalysisAngle, text: str) -> AnalysisPoint:
    return AnalysisPoint(angle=angle, text=text)


def facts(*points: AnalysisPoint, max_points: int = 6) -> list[str]:
    draft = AnalysisDraft(points=list(points))
    kept = analysis_facts(
        draft, article=ARTICLE, source=SOURCE, story_key="news:1", max_points=max_points
    )
    return [fact.text for fact in kept]


def test_a_point_is_kept_when_its_figures_are_the_articles() -> None:
    kept = facts(point(AnalysisAngle.FACTS, "A deficit of 3,9 % is high for a 2027 budget."))
    assert kept == ["facts: A deficit of 3,9 % is high for a 2027 budget."]


def test_a_remembered_figure_drops_the_point_whole() -> None:
    kept = facts(
        point(AnalysisAngle.HISTORY, "The last budget passed by 280 votes in 2019."),
        point(AnalysisAngle.CONTEXT, "Budgets rarely pass on a first reading."),
    )
    assert kept == ["context: Budgets rarely pass on a first reading."]


def test_the_facts_are_the_analysis_material_of_the_segment() -> None:
    draft = AnalysisDraft(
        points=[
            point(AnalysisAngle.CONTEXT, "Budgets  rarely\npass on a first reading."),
            point(AnalysisAngle.VIGILANCE, "Watch the Senate vote."),
            point(AnalysisAngle.OUTLOOK, "A censure motion could follow."),
        ]
    )
    kept = analysis_facts(draft, article=ARTICLE, source=SOURCE, story_key="news:1", max_points=2)
    assert [f.id for f in kept] == ["a1", "a2"]
    assert kept[0].text == "context: Budgets rarely pass on a first reading."
    assert {f.kind for f in kept} == {FactKind.ANALYSIS}
    assert {f.sensitivity for f in kept} == {Sensitivity.PUBLIC}
    assert kept[0].source == SOURCE and kept[1].key == "news:1#a2"
    FactPack(format=RadioFormat.ANALYSIS, facts=kept)  # admitted by the news material


def test_an_empty_or_blank_answer_gives_nothing() -> None:
    assert facts() == []
    assert facts(point(AnalysisAngle.CONTEXT, "   ")) == []
