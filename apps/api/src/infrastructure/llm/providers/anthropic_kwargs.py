"""The ``ChatAnthropic`` constructor kwargs, shaped for what each generation accepts.

Everything model-specific is read from the one declaration of the Claude
request surface (``core/claude_surface.py``, ADR-306); nothing here names a
model. Prompt caching is not armed here -- the breakpoints are placed on each
request payload by ``anthropic_payload.py`` -- and the credential is the
adapter's (``_require_api_key``), which calls :func:`prepare_anthropic_kwargs`.
"""

from __future__ import annotations

from typing import Any

from src.core.claude_surface import claude_surface, sampling_omitted
from src.core.constants import ANTHROPIC_PREFIX_MISMATCH_BEHAVIOR, ANTHROPIC_THINKING_BINDING_BETA
from src.infrastructure.llm.reasoning.translate import kwargs_for as reasoning_kwargs_for
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


def prepare_anthropic_kwargs(
    model: str, temperature: float | None, kwargs: dict[str, Any]
) -> float | None:
    """Shape the kwargs of one Claude client (mutated in place).

    Args:
        model: The Claude model name.
        temperature: The slot's temperature.
        kwargs: The constructor kwargs being assembled, the ``provider_config``
            escape hatch already merged in.

    Returns:
        The temperature the request carries: ``None`` when sampling must stay
        out of it, else the slot's value within Anthropic's 0.0-1.0 range.
    """
    # The one reasoning seam (ADR-245).
    reasoning_value = kwargs.pop("reasoning_effort", None)
    reasoning = reasoning_kwargs_for("anthropic", model, reasoning_value)
    if claude_surface(model).binds_thinking_to_conversation:
        _degrade_thinking_binding(kwargs, reasoning)
    kwargs.update(reasoning)
    _effort_into_output_config(kwargs)
    # Read AFTER the merge: the escape hatch can switch thinking on too, and it
    # used to leave the temperature in.
    thinking = kwargs.get("thinking")
    if reasoning:
        logger.info(
            "anthropic_effort_configured",
            model=model,
            effort=(kwargs.get("output_config") or {}).get("effort"),
            thinking=thinking.get("type") if isinstance(thinking, dict) else None,
        )

    # Never Anthropic parameters; ``top_p`` alongside ``temperature`` is a 400
    # from Claude 4.5 on, and refused outright from Opus 4.7 on.
    kwargs.pop("frequency_penalty", None)
    kwargs.pop("presence_penalty", None)
    kwargs.pop("top_p", None)

    if sampling_omitted(model, thinking):
        # Thinking on (« temperature may only be set to 1 when thinking is
        # enabled ») or a generation that refuses sampling: the API default
        # applies. The admin UI hides the field for the same reasons.
        return None
    if temperature is not None and temperature > 1.0:
        # Anthropic's range is 0.0-1.0, not OpenAI's 0.0-2.0.
        logger.warning("anthropic_temperature_capped", requested=temperature, capped_to=1.0)
        return 1.0
    return temperature


def _degrade_thinking_binding(kwargs: dict[str, Any], reasoning: dict[str, Any]) -> None:
    """Ask a binding Claude generation to DROP a stale thinking block, not refuse.

    Fable 5.1 and Opus 5.5 bind each thinking block to the conversation that
    produced it: once the history before the block changed -- the system prompt
    LIA rebuilds every turn is enough -- an account created from 2026-08-31 gets
    a 400 (measured on Opus 5.5, ADR-306). The payload policy already strips the
    prior turns' blocks; this is the net for what it cannot see, a history the
    state reducer trimmed in the middle of a tool loop. The control rides the
    ``thinking`` field -- always adaptive on these generations, so sending it
    when no depth was asked changes nothing else -- and requires its beta header.

    Args:
        kwargs: The constructor kwargs; their ``betas`` gain the header, after
            any an operator configured.
        reasoning: The rendered reasoning kwargs; their ``thinking`` gains the
            control (an operator's ``thinking`` is kept when none was rendered).
    """
    thinking = dict(reasoning.get("thinking") or kwargs.get("thinking") or {"type": "adaptive"})
    thinking["block_binding"] = {"prefix_mismatch_behavior": ANTHROPIC_PREFIX_MISMATCH_BEHAVIOR}
    reasoning["thinking"] = thinking
    betas = [beta for beta in kwargs.get("betas") or [] if beta != ANTHROPIC_THINKING_BINDING_BETA]
    kwargs["betas"] = [*betas, ANTHROPIC_THINKING_BINDING_BETA]


def _effort_into_output_config(kwargs: dict[str, Any]) -> None:
    """Carry a Claude ``effort`` inside ``output_config``, where it is visible.

    ``ChatAnthropic`` sends both spellings as the same ``output_config.effort``,
    but publishes only ``output_config`` to the callbacks: through its ``effort``
    field the depth never reached the Article-12 register (ADR-306). An
    ``output_config`` the ``provider_config`` escape hatch set (a task budget)
    is merged, never replaced.

    Args:
        kwargs: The constructor kwargs (mutated in place).
    """
    effort = kwargs.pop("effort", None)
    if effort is None:
        return
    existing = kwargs.get("output_config")
    kwargs["output_config"] = {**(existing if isinstance(existing, dict) else {}), "effort": effort}


__all__ = ["prepare_anthropic_kwargs"]
