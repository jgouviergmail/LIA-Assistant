"""What DeepSeek accepts as an output budget, per model family.

Extracted from ``adapter._create_deepseek_llm`` when the thinking family's cap
started reading the catalogue: the adapter is size-frozen, and the rule is
cohesive on its own -- three families, three ceilings, one authority.
"""

from __future__ import annotations

from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

#: The V3 ``deepseek-chat`` ceiling.
_V3_CHAT_MAX_OUTPUT = 8192
#: The V3 ``deepseek-reasoner`` ceiling, and the thinking family's fallback for
#: a model nobody has seeded yet -- the figure dates from the V4 launch; the
#: vendor now documents 384 K for ``deepseek-flash`` and a catalogue row that
#: knows better wins.
_LARGE_MAX_OUTPUT = 64000


def deepseek_output_cap(model: str, *, thinking_family: bool, reasoner_v3: bool) -> int:
    """The largest ``max_tokens`` this DeepSeek model accepts.

    For the thinking family the catalogue row is the authority (ADR-244) and
    the literal is only the fallback; the V3 names keep their documented
    ceilings.

    Args:
        model: The DeepSeek model name as configured.
        thinking_family: Whether ``model`` belongs to the thinking-toggle
            family (``is_deepseek_thinking_model``).
        reasoner_v3: Whether ``model`` is the V3 ``deepseek-reasoner``.

    Returns:
        The output ceiling in tokens.
    """
    if thinking_family:
        caps = ModelCapabilitiesCache.get(model)
        return caps.max_output_tokens if caps is not None else _LARGE_MAX_OUTPUT
    return _LARGE_MAX_OUTPUT if reasoner_v3 else _V3_CHAT_MAX_OUTPUT


def capped_max_tokens(
    model: str, max_tokens: int, *, thinking_family: bool, reasoner_v3: bool
) -> int:
    """Clamp ``max_tokens`` to what the model accepts, saying so when it does.

    Args:
        model: The DeepSeek model name as configured.
        max_tokens: The budget the slot asked for.
        thinking_family: See :func:`deepseek_output_cap`.
        reasoner_v3: See :func:`deepseek_output_cap`.

    Returns:
        ``max_tokens``, or the ceiling when the request exceeded it.
    """
    limit = deepseek_output_cap(model, thinking_family=thinking_family, reasoner_v3=reasoner_v3)
    if max_tokens <= limit:
        return max_tokens
    logger.warning(
        "deepseek_max_tokens_capped",
        requested=max_tokens,
        capped_to=limit,
        model=model,
        msg=f"max_tokens={max_tokens} exceeds DeepSeek limit, capped to {limit}",
    )
    return limit
