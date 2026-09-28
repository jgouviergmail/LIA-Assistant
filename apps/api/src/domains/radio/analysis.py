"""The expert's reading of one story, turned into facts the analysis segment may voice.

The analysis format is a conversation: the anchor sets a story out, the expert
reads it — its context, its history, what the facts show, what to watch, how it
could evolve. The expert's material comes from a specialised model (the
analyst) that reads the article's FULL text; the writer then voices it, and the
verifier only lets an expert line through when it cites an analysis fact.

The analyst may bring background the article does not hold — that is what an
expert is for — but not FIGURES: every number or date a point states must be
one the article states (the same canonical comparison the script verifier
uses, so « 3,9 » and « 3.9 » agree and « 0,5 » never passes for « 5 »). A point
that breaks it is dropped, never corrected: a model that misremembers one date
may misremember the sentence around it.

Pure: the analyst's answer and the article are inputs.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from src.domains.radio.constants import FACT_TEXT_MAX_CHARS
from src.domains.radio.facts import FactKind, RadioFact, Sensitivity, SourceRef
from src.domains.radio.numbers import readings_of, stated_numbers


class AnalysisAngle(StrEnum):
    """What a point of the analysis looks at."""

    CONTEXT = "context"
    HISTORY = "history"
    FACTS = "facts"
    VIGILANCE = "vigilance"
    OUTLOOK = "outlook"


class AnalysisPoint(BaseModel):
    """One point of the expert's reading."""

    model_config = ConfigDict(frozen=True)

    angle: AnalysisAngle = Field(description="What the point looks at.")
    text: str = Field(description="The point, in two to four sentences.")


class AnalysisDraft(BaseModel):
    """An expert's reading of one story."""

    model_config = ConfigDict(frozen=True)

    points: list[AnalysisPoint] = Field(
        default_factory=list, description="The points, most useful first."
    )


def _figures_supported(text: str, article_readings: frozenset[str]) -> bool:
    return all(number.readings & article_readings for number in stated_numbers(text))


def analysis_facts(
    draft: AnalysisDraft,
    *,
    article: str,
    source: SourceRef,
    story_key: str,
    max_points: int,
) -> tuple[RadioFact, ...]:
    """The analysis facts ``a1`` to ``aN`` the writer may give the expert.

    Args:
        draft: What the analyst returned.
        article: The article's text (and headline) the analyst read.
        source: The article, shown next to every expert line.
        story_key: The story's ledger key (the analysis is never aired twice).
        max_points: The most points kept, in the analyst's order.

    Returns:
        The points whose figures the article states, bounded, as facts.
    """
    article_readings = readings_of(article)
    kept: list[AnalysisPoint] = []
    for point in draft.points:
        text = " ".join(point.text.split())
        if not text or not _figures_supported(text, article_readings):
            continue
        kept.append(AnalysisPoint(angle=point.angle, text=text[:FACT_TEXT_MAX_CHARS]))
        if len(kept) == max_points:
            break
    return tuple(
        RadioFact(
            id=f"a{index}",
            kind=FactKind.ANALYSIS,
            text=f"{point.angle.value}: {point.text}"[:FACT_TEXT_MAX_CHARS],
            key=f"{story_key}#a{index}",
            sensitivity=Sensitivity.PUBLIC,
            source=source,
        )
        for index, point in enumerate(kept, start=1)
    )


__all__ = [
    "AnalysisAngle",
    "AnalysisDraft",
    "AnalysisPoint",
    "analysis_facts",
]
