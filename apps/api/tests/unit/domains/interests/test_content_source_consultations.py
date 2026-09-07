"""An interest sweep says which search engine it actually queried.

Owner correction, 2026-09-07: « une notification centre d'intérêt exécute des
outils ! ce n'est pas que de la génération de texte sur aucune base ».

That is exactly right, and it refuted the reason this surface had been filed
under ``NOT_A_READER``. The sweep queries Brave, Perplexity and Wikipedia —
through their CLIENTS, never through the ``@tool`` layer — so the tool gate
that fills the consultation register never sees them. The same Brave search is
therefore recorded when a person asks for it in a conversation, and invisible
when LIA runs it alone.

The first classification argued « it explores PUBLIC content ». That answers
« whose data », and the register answers a different question: **which
capability did LIA use**. Two of these three also cost money on the person's
own connector key, which makes the silence worse rather than better.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.domains.agents.effects.treatments import treatment_collector

pytestmark = pytest.mark.unit


class _Source:
    """A content source that answers, or raises."""

    def __init__(self, name: str, *, raises: bool = False, result: Any = None) -> None:
        self.source_name = name
        self._raises = raises
        self._result = result

    async def generate(self, **_kwargs: Any) -> Any:
        if self._raises:
            raise RuntimeError("provider down")
        return self._result


def _generator() -> Any:
    """The generator, without touching its constructor's dependencies."""
    from src.domains.interests.services.content_sources.content_generator import (
        InterestContentGenerator,
    )

    generator = InterestContentGenerator.__new__(InterestContentGenerator)
    generator._generate_content_embedding = AsyncMock(return_value=None)  # type: ignore[method-assign]
    return generator


def _context() -> Any:
    from src.domains.interests.services.content_sources.content_generator import (
        ContentGenerationContext,
    )

    return ContentGenerationContext(
        interest_id=uuid.uuid4(),
        topic="rugby",
        category="sport",
        user_id=uuid.uuid4(),
        user_language="fr",
        recent_notification_embeddings=[],
    )


class TestEveryEngineTheSweepQueriesIsRecorded:
    """One row per source that ran, under the capability it used."""

    async def test_a_search_engine_that_answered_is_recorded(self) -> None:
        from src.domains.interests.services.content_sources.base import ContentResult

        answer = ContentResult(content="…", source="brave", embedding=[0.1])
        with treatment_collector(run_id="interest-1") as rows:
            await _generator()._try_source(_Source("brave", result=answer), _context())

        assert [row.tool_name for row in rows] == ["interest:brave"]
        assert rows[0].outcome == "ok"

    async def test_an_engine_that_failed_is_not_recorded_as_a_read(self) -> None:
        with treatment_collector(run_id="interest-2") as rows:
            await _generator()._try_source(_Source("perplexity", raises=True), _context())

        assert [row.tool_name for row in rows] == ["interest:perplexity"]
        assert rows[0].outcome == "failed"

    async def test_an_engine_that_found_nothing_still_ran(self) -> None:
        """« Nothing to report » is not « I could not look »."""
        with treatment_collector(run_id="interest-3") as rows:
            await _generator()._try_source(_Source("wikipedia", result=None), _context())

        assert [row.tool_name for row in rows] == ["interest:wikipedia"]
        assert rows[0].outcome == "ok"

    async def test_the_sweep_is_lias_own_initiative(self) -> None:
        """Nobody asked for it — which is what puts it in the initiative tab."""
        with treatment_collector(run_id="interest-4") as rows:
            await _generator()._try_source(_Source("brave", result=None), _context())

        assert rows[0].source == "proactive"

    async def test_a_reflection_over_the_persons_own_interests_is_recorded_too(self) -> None:
        with treatment_collector(run_id="interest-5") as rows:
            await _generator()._try_source(_Source("llm_reflection", result=None), _context())

        assert [row.tool_name for row in rows] == ["interest:llm_reflection"]

    async def test_outside_a_run_nothing_is_recorded_and_nothing_raises(self) -> None:
        await _generator()._try_source(_Source("brave", result=None), _context())


class TestTheVocabularyIsReadable:
    """A consultation nobody can name is worse than none (ADR-263)."""

    def test_every_source_the_generator_can_run_is_declared(self) -> None:
        """Read from the sources themselves, never re-listed here."""
        from src.domains.interests.services.content_sources.brave_source import (
            BraveSearchContentSource,
        )
        from src.domains.interests.services.content_sources.llm_reflection_source import (
            LLMReflectionContentSource,
        )
        from src.domains.interests.services.content_sources.perplexity_source import (
            PerplexityContentSource,
        )
        from src.domains.interests.services.content_sources.wikipedia_source import (
            WikipediaContentSource,
        )
        from src.domains.shared.consultation_surfaces import CONSULTATION_SURFACES

        declared = set(CONSULTATION_SURFACES["interest"].domains)
        running = {
            BraveSearchContentSource.source_name,
            PerplexityContentSource.source_name,
            WikipediaContentSource.source_name,
            LLMReflectionContentSource.source_name,
        }
        assert running == declared, (
            "the sweep runs sources nothing declares (or declares sources it " "never runs)"
        )

    def test_each_engine_reads_as_the_capability_it_used(self) -> None:
        from src.domains.agents.effects.treatment_labels import UNKNOWN_DOMAIN, treatment_domain
        from src.domains.shared.consultation_surfaces import CONSULTATION_SURFACES

        surface = CONSULTATION_SURFACES["interest"]
        for section, domain in surface.domains.items():
            resolved = treatment_domain(surface.capability(section))
            assert resolved != UNKNOWN_DOMAIN, f"{section} headlines as Unknown"
            assert resolved == domain
