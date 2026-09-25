"""An image prompt rewritten with recognised techniques, never distorted (ADR-315).

A person who turned it on (Settings > AI image generation) gets each image
prompt rewritten by a small model of its own slot (``image_prompt_enhancement``)
before the image model runs: the same image, described the way image models
respond to — photographic terms for a realistic picture, the medium and its
technique for an illustration, a clear order, the text it must carry quoted.
The rules follow the vendors' own guides (OpenAI's image prompting guide, the
prompt rewriter Qwen ships with Qwen-Image) and live in the versioned prompt
``image_prompt_enhancement_prompt``.

What this module promises, and what its tests pin:

- the image is never lost to the enhancement: a ceiling refusal
  (``skipped_quota``), a model failure or a truncated answer (``failed``,
  ADR-275) and an answer that fails the checks (``rejected``) all hand the
  ORIGINAL prompt back — an improvement, never a gate;
- the checks are deterministic: an empty answer, one longer than the bound the
  prompt states (``IMAGE_PROMPT_ENHANCEMENT_MAX_CHARS``, ADR-184), or one that
  lost a text the request quoted, is discarded;
- one call per image, on the account's ceilings (``user_id``) and the turn's
  config, so the turn's tracker bills it (``LLM_SPEND_ROADS``: TURN);
- the rules travel as the system message and the request as the question
  (``single_call_messages``, ADR-309);
- nothing the person wrote is logged: lengths and outcomes only.

Only a GENERATION is enhanced: an edit instruction names what to change in an
existing image, and adding lighting or lens language to it would change what
the person asked to keep.
"""

from __future__ import annotations

import re
from contextlib import suppress
from dataclasses import dataclass
from typing import Final, Literal

import structlog
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from src.core.config import settings
from src.core.exceptions_domains import UsageLimitExceededError
from src.core.llm_config_helper import get_llm_config_for_agent, short_answer_config
from src.core.prompt_layout import single_call_messages
from src.domains.agents.prompts import load_prompt
from src.domains.usage_limits.enforcement import spend_blocked
from src.infrastructure.llm import get_llm
from src.infrastructure.llm.structured_output import get_structured_output
from src.infrastructure.observability.metrics_extractions import image_prompt_enhancement_total

logger = structlog.get_logger(__name__)

LLM_TYPE: Final = "image_prompt_enhancement"

#: How the enhancement settled — the metric's ``outcome`` label.
EnhancementOutcome = Literal["enhanced", "unchanged", "rejected", "failed", "skipped_quota"]
#: Why an answer was discarded (logged, never counted as a label of its own).
RejectionReason = Literal["empty", "too_long", "lost_text"]

#: The text an image must carry, between any of the quote pairs people type:
#: straight and curly double quotes, French guillemets, German low-high quotes,
#: Chinese and Japanese corner brackets. Single quotes are left out on purpose —
#: an apostrophe (« the cat's toy ») would open a quotation that never closes.
_QUOTED = re.compile(r'"([^"]+)"|“([^”]+)”|«([^»]+)»|„([^“”]+)[“”]|「([^」]+)」|『([^』]+)』')


class EnhancedImagePrompt(BaseModel):
    """What the model returns: the improved description, and nothing else."""

    prompt: str = Field(description="The improved description of the same image.")


@dataclass(frozen=True)
class PromptEnhancement:
    """The prompt the image model receives, and how the enhancement settled."""

    text: str
    outcome: EnhancementOutcome


def quoted_texts(prompt: str) -> list[str]:
    """The texts a request quotes — what the image must carry word for word.

    Args:
        prompt: An image request.

    Returns:
        Each quoted text, stripped, in order; empty quotations are ignored.
    """
    found = (next(group for group in match.groups() if group) for match in _QUOTED.finditer(prompt))
    return [text.strip() for text in found if text.strip()]


def rejection_reason(original: str, enhanced: str, *, max_chars: int) -> RejectionReason | None:
    """Why an enhanced prompt cannot replace the original, if it cannot.

    Args:
        original: The request as the image tool received it.
        enhanced: The model's rewrite.
        max_chars: The longest rewrite kept — the bound the prompt states.

    Returns:
        The reason, or None when the rewrite may be sent.
    """
    text = enhanced.strip()
    if not text:
        return "empty"
    if len(text) > max_chars:
        return "too_long"
    if any(quoted not in text for quoted in quoted_texts(original)):
        return "lost_text"
    return None


def _settle(
    original: str, outcome: EnhancementOutcome, text: str | None = None
) -> PromptEnhancement:
    # Best-effort: a metric must never cost the person their image.
    with suppress(Exception):
        image_prompt_enhancement_total.labels(outcome=outcome).inc()
    return PromptEnhancement(text=text if text is not None else original, outcome=outcome)


async def _rewrite(prompt: str, *, user_id: str, config: RunnableConfig | None) -> str:
    """One short structured call on the enhancement slot."""
    rules = load_prompt("image_prompt_enhancement_prompt")
    rendered = rules.format(max_chars=settings.image_prompt_enhancement_max_chars, prompt=prompt)
    # No reasoning, and the SLOT's own output cap: the administrator edits it on
    # the slot (ADR-244); the constant only seeds its default (ADR-285).
    llm = get_llm(LLM_TYPE, config_override=short_answer_config(LLM_TYPE))
    provider = get_llm_config_for_agent(settings, LLM_TYPE).provider
    answer = await get_structured_output(
        llm,
        single_call_messages(rendered),
        EnhancedImagePrompt,
        provider,
        node_name=LLM_TYPE,
        user_id=user_id,
        config=config,
    )
    return answer.prompt


async def enhance_image_prompt(
    prompt: str, *, user_id: str, config: RunnableConfig | None
) -> PromptEnhancement:
    """The prompt the image model receives: improved, or the original on any doubt.

    The caller decides whether to ask (the person's opt-in and
    ``image_generation.preferences.prompt_enhancement_offered``); this function
    never raises.

    Args:
        prompt: The image request, as the image tool received it.
        user_id: The account, for both ceilings (ADR-272).
        config: The turn's RunnableConfig — it carries the tracking callback, and
            a model call handed no config is a euro no ledger sees.

    Returns:
        The prompt to send and how the enhancement settled.
    """
    if await spend_blocked(user_id):
        return _settle(prompt, "skipped_quota")
    try:
        enhanced = await _rewrite(prompt, user_id=user_id, config=config)
    except UsageLimitExceededError:
        # The ceiling closed between the gate and the call: a refusal, not a failure.
        return _settle(prompt, "skipped_quota")
    except Exception as exc:
        # A refusal, never a lost image: the original goes to the image model (ADR-275).
        logger.warning("image_prompt_enhancement_failed", error_type=type(exc).__name__)
        return _settle(prompt, "failed")

    reason = rejection_reason(
        prompt, enhanced, max_chars=settings.image_prompt_enhancement_max_chars
    )
    if reason is not None:
        logger.info(
            "image_prompt_enhancement_rejected",
            reason=reason,
            original_length=len(prompt),
            enhanced_length=len(enhanced),
        )
        return _settle(prompt, "rejected")
    text = enhanced.strip()
    if text == prompt.strip():
        return _settle(prompt, "unchanged")
    logger.info("image_prompt_enhanced", original_length=len(prompt), enhanced_length=len(text))
    return _settle(prompt, "enhanced", text)


__all__ = [
    "EnhancedImagePrompt",
    "PromptEnhancement",
    "enhance_image_prompt",
    "quoted_texts",
    "rejection_reason",
]
