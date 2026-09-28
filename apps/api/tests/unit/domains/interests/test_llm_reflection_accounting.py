"""A reflection's tokens are counted once, by the run that asked for it (ADR-272).

Measured on dev, 2026-09-27: every reflection was billed twice — under a run of
its own (``llm_reflection_*``, 49 runs in twelve days, none of them in the
decision register) and again inside the total the interest sweep and the
heartbeat enrichment hand to the runner (a 1 992-token reflection inside the
4 143-token row of the interest run that used it). The person's quota paid it
twice. Both callers already carry the tokens the content result declares, so
the source bills nothing itself.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage

from src.domains.interests.services.content_sources import llm_reflection_source as module

pytestmark = pytest.mark.unit


async def test_the_tokens_travel_with_the_content_and_nothing_is_billed_here(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def invoke(**_kwargs: Any) -> AIMessage:
        return AIMessage(
            content="A reflection long enough to be kept as the notification's content.",
            usage_metadata={"input_tokens": 1992, "output_tokens": 550, "total_tokens": 2542},
        )

    opened: list[tuple[Any, ...]] = []

    def accounting(*args: Any, **kwargs: Any) -> None:
        # Noted rather than raised: the source swallows what its accounting
        # raises, so a raise here would pass unseen.
        opened.append((args, kwargs))

    monkeypatch.setattr(module, "get_llm", lambda slot: object())
    monkeypatch.setattr(module, "invoke_with_instrumentation", invoke)
    monkeypatch.setattr("src.domains.chat.service.TrackingContext", accounting)

    result = await module.LLMReflectionContentSource().generate(
        topic="astronomy", user_language="en", user_id=str(uuid4())
    )

    assert result is not None
    assert (result.tokens_in, result.tokens_out) == (1992, 550)
    assert opened == [], "the reflection billed its tokens under a run of its own"
