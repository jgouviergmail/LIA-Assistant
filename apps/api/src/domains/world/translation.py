"""One private, accounted translator call; malformed/cut answers never repair/retry."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final
from uuid import UUID

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langsmith import tracing_context
from pydantic import Field, field_validator

from src.core.config import settings
from src.core.i18n_types import Language
from src.core.llm_config_helper import (
    get_effective_context_window_for_slot,
    get_llm_config_for_agent,
)
from src.core.prompt_store import read_prompt_file
from src.domains.agents.effects.models import DecisionOutcome
from src.domains.chat.schemas import TokenSummaryDTO
from src.domains.chat.service import TrackingContext
from src.domains.world.message_attempts import TRANSLATION_SECONDS
from src.domains.world.messages import (
    TRANSLATION_BYTES,
    TRANSLATION_CHARS,
    StrictModel,
    literal_text,
)
from src.domains.world.translation_register import file_translation
from src.infrastructure.llm.factory import LLMType, get_llm
from src.infrastructure.llm.message_text import coerce_content_to_text
from src.infrastructure.llm.output_truncation import is_output_truncated
from src.infrastructure.llm.single_attempt import single_async_attempt
from src.infrastructure.llm.usage_guard import enforce_usage_limit
from src.infrastructure.observability.callbacks import TokenTrackingCallback

SLOT: Final[LLMType] = "world_message_translator"
PROMPT = "world_message_translator_prompt"


class TranslationInput(StrictModel):
    source_language: Language = Field(
        description="Canonical backend language code of the original human text."
    )
    target_language: Language = Field(
        description="Exact canonical backend language requested for this translation."
    )
    text: str = Field(
        description="Bounded literal human or translated text; never instructions or executable markup."
    )


class TranslationText(StrictModel):
    language: Language = Field(
        description="Canonical backend language code for this account or translated view."
    )
    text: str = Field(
        min_length=1,
        max_length=TRANSLATION_CHARS,
        description="Bounded literal human or translated text; never instructions or executable markup.",
    )

    @field_validator("text")
    @classmethod
    def clean_text(cls, value: str) -> str:
        """Validate translated correspondence as bounded literal text without repairing invalid output."""
        return literal_text(value, chars=TRANSLATION_CHARS, size=TRANSLATION_BYTES)


def translation_messages(text: str, *, source: Language, target: Language) -> list[BaseMessage]:
    """Build only literal text and source/target codes into the isolated translation prompt."""
    payload = TranslationInput(
        source_language=source, target_language=target, text=literal_text(text)
    )
    return [
        SystemMessage(read_prompt_file(PROMPT)),
        HumanMessage(payload.model_dump_json()),
    ]


@dataclass(frozen=True)
class TranslatedMessage:
    translation: TranslationText
    usage: TokenSummaryDTO


async def accounted_translation[T](
    messages: list[BaseMessage],
    parse: Callable[[str], T],
    *,
    user_id: UUID,
    request_id: UUID,
) -> tuple[T, TokenSummaryDTO]:
    """Translate once through the native payer budget and accounting path.

    Args:
        messages: System instructions and literal untrusted correspondence only.
        parse: Strict result validator; malformed output is never repaired or retried.
        user_id: Account paying for this explicitly consented request.
        request_id: Stable owned attempt identifier used for content-free accounting.

    Returns:
        Validated result and the native actual-token/cost receipt.

    Raises:
        ValueError: Context bounds, truncated output, tool calls or strict parsing
            prevent a usable translation.
        TimeoutError: The bounded provider attempt expires; accounting still closes.
    """
    await enforce_usage_limit(user_id, layer="world_translation")
    config = get_llm_config_for_agent(settings, SLOT)
    config = config.model_copy(
        update={
            "max_tokens": min(config.max_tokens, 2048),
            "timeout_seconds": min(
                config.timeout_seconds or TRANSLATION_SECONDS, TRANSLATION_SECONDS
            ),
        }
    )
    # A conservative byte upper bound avoids an extra remote token-count request.
    # Actual billed tokens, including reasoning/cache tokens, use the native callback.
    prompt_bound = sum(len(str(message.content).encode("utf-8")) for message in messages) * 2 + 512
    if prompt_bound + config.max_tokens > get_effective_context_window_for_slot(SLOT):
        raise ValueError("world_translation_context_limit")
    run_id = "world_message_" + request_id.hex
    started_at = datetime.now(UTC)
    called = False
    outcome = DecisionOutcome.INTERRUPTED
    try:
        async with (
            single_async_attempt(get_llm(SLOT, config_override=config)) as llm,
            TrackingContext(run_id, user_id, run_id, None) as tracker,
        ):
            # No content tracer, including an implicitly environment-enabled
            # LangSmith tracer. The native usage callback alone records spend.
            with tracing_context(enabled=False):
                async with asyncio.timeout(TRANSLATION_SECONDS):
                    called = True
                    response = await llm.ainvoke(
                        messages,
                        config={
                            "callbacks": [TokenTrackingCallback(tracker, run_id)],
                            "metadata": {
                                "langgraph_node": SLOT,
                                "user_id": str(user_id),
                            },
                        },
                    )
            usage = tracker.get_summary_dto()
            if is_output_truncated(response) or response.tool_calls:
                raise ValueError("world_translation_incomplete")
            parsed = parse(coerce_content_to_text(response.content))
        outcome = DecisionOutcome.ANSWERED
        return parsed, usage
    except Exception:
        outcome = DecisionOutcome.FAILED
        raise
    finally:
        # __aexit__ already closes the native accounting books, including errors.
        # Human correspondence has no debug panel retaining run-level records.
        try:
            if called:
                await file_translation(
                    user_id=user_id,
                    run_id=run_id,
                    started_at=started_at,
                    outcome=outcome,
                )
        finally:
            TrackingContext.cleanup_run_records(run_id)


def _parse_translation(raw: str, target: Language) -> TranslationText:
    """Require strict translated text in exactly the requested language."""
    parsed = TranslationText.model_validate_json(raw)
    if parsed.language != target:
        raise ValueError("world_translation_language")
    return parsed


async def translate_message(
    text: str, *, source: Language, target: Language, user_id: UUID, request_id: UUID
) -> TranslatedMessage:
    """Return one validated private translation and its native usage receipt."""
    parsed, usage = await accounted_translation(
        translation_messages(text, source=source, target=target),
        lambda raw: _parse_translation(raw, target),
        user_id=user_id,
        request_id=request_id,
    )
    return TranslatedMessage(parsed, usage)
