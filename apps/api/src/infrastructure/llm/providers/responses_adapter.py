"""OpenAI Responses API adapter — native ``ChatOpenAI`` + prompt-cache routing.

History: this module previously shipped a ~1800-line custom ``ResponsesLLM``
(BaseChatModel subclass) that reimplemented message conversion, streaming,
structured output, tool calling and usage extraction by hand — a workaround for
gaps in ``langchain-openai`` circa v1.0.0 (2026-03). Those gaps are gone:
``langchain-openai>=1.1`` ``ChatOpenAI(use_responses_api=True,
output_version="responses/v1")`` natively provides Responses-API caching,
multi-turn, native tool calls, structured output, reasoning-summary streaming
and standard ``usage_metadata`` — all validated on the real path in dev.

What remains genuinely custom (and worth keeping) is LIA's **prompt-cache-key
routing**: hashing only the *static prefix* of system prompts (before the
dynamic-context marker) so requests of the same prompt type share an OpenAI
``prompt_cache_key`` and hit the prefix cache. The native ``ChatOpenAI`` accepts
``prompt_cache_key`` per request but cannot derive it from the messages on its
own, so we keep a thin subclass (:class:`ChatOpenAICached`, ~1 method) that
injects the computed key into each request payload. Everything else is standard.

NOTE (documented trade-off): the thin subclass exists ONLY to preserve the
static-prefix cache-key optimisation. If that optimisation is ever dropped, this
module collapses to a plain ``ChatOpenAI(...)`` with zero custom code (the OpenAI
automatic prefix cache still works without an explicit key). See option "B2".

References:
    - https://platform.openai.com/docs/api-reference/responses
    - langchain-openai ChatOpenAI: use_responses_api / output_version / reasoning
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from langchain_core.messages import BaseMessage, SystemMessage
from langchain_openai import ChatOpenAI

from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


# Responses API eligibility: pattern-based detection instead of a hardcoded list.
# All GPT-4.1+, GPT-5.x and o-series models support the Responses API; only legacy
# models (gpt-4o, gpt-4-turbo, gpt-3.5) do NOT.
_RESPONSES_API_PATTERN = re.compile(r"^(gpt-4\.1|gpt-5|o[1-9])", re.IGNORECASE)

# Max static-prefix length hashed for the cache key (covers static instructions +
# semi-static context like the tool catalogue; OpenAI caches 1024+ token prefixes).
_MAX_PREFIX_LENGTH = 8192


def is_responses_api_eligible(model: str) -> bool:
    """Return True if ``model`` supports the OpenAI Responses API.

    GPT-4.1+, GPT-5.x and o-series are eligible; legacy models (gpt-4o,
    gpt-4-turbo, gpt-3.5) are not.

    Args:
        model: Model identifier.

    Returns:
        True if the model supports the Responses API.
    """
    return bool(_RESPONSES_API_PATTERN.match(model))


def _extract_static_prefix(content: str) -> str:
    """Extract the static (cacheable) prefix of a prompt, before the dynamic marker.

    Everything before the SINGLE canonical ``DYNAMIC_CONTEXT_MARKER`` is treated
    as static and cacheable. The marker is the one convention shared with the
    Anthropic ``cache_control`` split in ``factory.py`` — provider adapters must
    agree on where "static" ends, or the same prompt caches differently per
    provider. Legacy alternative markers (``## DYNAMIC CONTEXT``,
    ``<TemporalContext>``, …) were dropped: matching them cut the prefix at mere
    literal MENTIONS of those tags inside static instructions.

    Args:
        content: Full system-message content.

    Returns:
        The static prefix (trimmed, capped at ``_MAX_PREFIX_LENGTH``).
    """
    from src.core.constants import DYNAMIC_CONTEXT_MARKER

    marker_pos = content.find(DYNAMIC_CONTEXT_MARKER)
    static_prefix = content[:marker_pos].strip() if marker_pos != -1 else content.strip()
    if len(static_prefix) > _MAX_PREFIX_LENGTH:
        static_prefix = static_prefix[:_MAX_PREFIX_LENGTH]
    return static_prefix


def compute_prompt_cache_key(messages: list[BaseMessage], model: str) -> str:
    """Compute a stable ``prompt_cache_key`` from the static system-prompt prefix.

    OpenAI prefix-caches the first 1024+ identical tokens; routing requests of the
    same prompt type to the same ``prompt_cache_key`` improves the hit rate. Only
    the static portion of system messages is hashed (dynamic/user content is left
    to automatic prefix matching), so the key is stable across turns.

    Args:
        messages: The messages about to be sent.
        model: Model id (fallback grouping when there is no system message).

    Returns:
        A 32-char SHA256 hex digest used as the OpenAI ``prompt_cache_key``.
    """
    static_parts = [
        f"system:{_extract_static_prefix(str(msg.content))}"
        for msg in messages
        if isinstance(msg, SystemMessage)
    ]
    if not static_parts:
        static_parts.append(f"model:{model}")

    combined = "|".join(static_parts)
    cache_key = hashlib.sha256(combined.encode()).hexdigest()[:32]
    logger.debug(
        "cache_key_generated",
        cache_key=cache_key[:12] + "...",
        static_parts_count=len(static_parts),
        static_prefix_length=len(combined),
    )
    return cache_key


class ChatOpenAICached(ChatOpenAI):
    """``ChatOpenAI`` that injects a static-prefix-derived ``prompt_cache_key``.

    Thin subclass: it only overrides payload building to add a computed
    ``prompt_cache_key`` when the caller did not already supply one. All other
    behaviour (Responses API, tools, structured output, reasoning summaries,
    usage metadata, streaming) is the stock ``ChatOpenAI`` implementation.

    This is the ONLY custom OpenAI code remaining after the ResponsesLLM removal.
    """

    def _get_request_payload(
        self,
        input_: Any,
        *,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> dict:
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        # Only inject when not explicitly provided by the caller (per-invocation
        # prompt_cache_key always wins). Guarded so a payload-shape change upstream
        # can never break the LLM call.
        try:
            if "prompt_cache_key" not in payload:
                messages = self._convert_input(input_).to_messages()
                payload["prompt_cache_key"] = compute_prompt_cache_key(messages, self.model_name)
        except Exception as exc:  # pragma: no cover - defensive: never break the call
            logger.debug(
                "prompt_cache_key_injection_skipped",
                error=str(exc),
                error_type=type(exc).__name__,
            )
        return payload


def create_responses_llm(
    model: str,
    api_key: str,
    *,
    temperature: float = 0.7,
    max_tokens: int | None = None,
    top_p: float = 1.0,
    streaming: bool = False,
    reasoning_effort: str | None = None,
    organization: str | None = None,
    base_url: str | None = None,
) -> ChatOpenAICached:
    """Build a native ``ChatOpenAI`` (Responses API) with LIA cache-key routing.

    Args:
        model: OpenAI model id (gpt-4.1+, gpt-5.x, o-series).
        api_key: OpenAI API key.
        temperature: Sampling temperature (ignored by the API for reasoning models).
        max_tokens: Max output tokens (mapped to ``max_completion_tokens``).
        top_p: Nucleus sampling.
        streaming: Enable streaming.
        reasoning_effort: Reasoning effort for reasoning models (minimal/low/...).
            When set, reasoning-summary streaming is enabled so the live
            chain-of-thought can be surfaced (see reasoning_stream).
        organization: OpenAI organization id (optional).

    Returns:
        Configured :class:`ChatOpenAICached`.
    """
    kwargs: dict[str, Any] = {
        "model": model,
        "api_key": api_key,
        "use_responses_api": True,
        "output_version": "responses/v1",
        "streaming": streaming,
    }
    if organization:
        kwargs["organization"] = organization
    if base_url:
        # Hermetic qualification override (ADR-215): equals the SDK default
        # in normal operation, points at the fake provider in disposable runs.
        kwargs["base_url"] = base_url
    if max_tokens:
        kwargs["max_tokens"] = max_tokens

    if reasoning_effort:
        # Reasoning model: the API ignores sampling params; request a reasoning
        # summary so the thinking can be streamed to the UI.
        kwargs["reasoning"] = {"effort": reasoning_effort, "summary": "auto"}
    else:
        # Standard model: sampling params apply.
        kwargs["temperature"] = temperature
        kwargs["top_p"] = top_p

    logger.info(
        "creating_openai_responses_llm",
        model=model,
        streaming=streaming,
        reasoning_effort=reasoning_effort,
        msg="Using native ChatOpenAI (Responses API) with static-prefix cache key",
    )
    return ChatOpenAICached(**kwargs)
