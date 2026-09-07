"""The account-less billing paths reach the deployment's ledger.

Companion to ``test_instance_budget_cost_coverage``, whose reachability class
frames the escape route as « a billing path with its own session writes
straight to ``user_statistics`` ». That framing could not see these three: they
write to nothing at all, so there was no per-account row to notice missing.

Each test observes the LEDGER boundary — ``InstanceBudgetService.record_spend``
— rather than asserting that a helper was called. The property is « the
deployment's ceiling was told », and pinning one implementation would pass just
as happily on a successor that told nobody.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


class _Answer:
    """A model reply carrying usage, in the shape LangChain returns."""

    def __init__(self, content: str) -> None:
        self.content = content
        self.usage_metadata = {"input_tokens": 900, "output_tokens": 120}

    @property
    def text(self) -> str:
        return str(self.content)


class _Client:
    """A chat client that answers with a fixed payload."""

    model_name = "gpt-5.6-luna"

    def __init__(self, content: str) -> None:
        self._content = content

    async def ainvoke(self, *_: object, **__: object) -> _Answer:
        return _Answer(self._content)


def _ledger(recorded: list[Decimal]) -> Any:
    return patch(
        "src.domains.usage_limits.instance_budget.InstanceBudgetService.record_spend",
        AsyncMock(side_effect=lambda _s, *, cost_eur, **__: recorded.append(cost_eur)),
    )


def _priced() -> Any:
    return patch(
        "src.domains.usage_limits.instance_spend.get_cached_cost_usd_eur",
        return_value=(0.02, 0.018),
    )


def _session() -> Any:
    @asynccontextmanager
    async def _context():  # type: ignore[no-untyped-def]
        yield AsyncMock()

    return patch("src.domains.usage_limits.instance_spend.get_db_context", _context)


def _open_ceiling() -> Any:
    return patch(
        "src.domains.usage_limits.service.UsageLimitService.instance_budget_block",
        AsyncMock(return_value=None),
    )


class TestCatalogueTranslationsReachTheLedger:
    """The 84 calls that left no trace anywhere (measured 2026-09-07)."""

    async def test_a_personality_translation_is_recorded(self) -> None:
        from src.domains.personalities.translation_service import PersonalityTranslationService

        recorded: list[Decimal] = []
        payload = '{"title": "Titre", "description": "Description"}'
        with (
            _ledger(recorded),
            _priced(),
            _session(),
            _open_ceiling(),
            patch(
                "src.domains.personalities.translation_service.get_llm",
                return_value=_Client(payload),
            ),
        ):
            await PersonalityTranslationService.translate_personality(
                source_title="Title",
                source_description="Description",
                source_language="en",
                target_language="fr",
                personality_code=f"probe-{len(recorded)}-reach",
            )

        assert recorded == [Decimal("0.018")]

    async def test_a_skill_description_translation_is_recorded(self) -> None:
        from src.domains.skills.description_translation import _translate_description_all_langs

        recorded: list[Decimal] = []
        payload = '{"en": "a", "fr": "b", "de": "c", "es": "d", "it": "e", "zh": "f"}'
        with (
            _ledger(recorded),
            _priced(),
            _session(),
            _open_ceiling(),
            patch(
                "src.infrastructure.llm.factory.get_llm",
                return_value=_Client(payload),
            ),
        ):
            await _translate_description_all_langs("A skill", None)

        assert recorded == [Decimal("0.018")]


class TestTheCeilingCanRefuseAccountLessSpend:
    """A bound that cannot say no is a measurement, not a ceiling."""

    async def test_an_exhausted_instance_refuses_a_translation(self) -> None:
        from src.core.exceptions import UsageLimitExceededError
        from src.domains.personalities.translation_service import PersonalityTranslationService

        called: list[object] = []
        with (
            patch(
                "src.domains.personalities.translation_service.is_instance_spend_blocked",
                AsyncMock(return_value=True),
            ),
            patch(
                "src.domains.personalities.translation_service.get_llm",
                side_effect=lambda *a, **k: called.append(a) or _Client("{}"),
            ),
            pytest.raises(UsageLimitExceededError),
        ):
            await PersonalityTranslationService.translate_personality(
                source_title="Title",
                source_description="Description",
                source_language="en",
                target_language="de",
                personality_code="probe-refusal",
            )

        assert called == [], "the model was called after the ceiling refused"
