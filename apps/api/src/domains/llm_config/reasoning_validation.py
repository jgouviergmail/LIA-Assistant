"""Strict validation of reasoning_effort against a model's reasoning_widget.

Used by:
- LLMConfigService.upsert_override (admin API write path)
- bootstrap.validate_llm_defaults_against_matrix (boot-time fail-fast)

Raises StructuredValidationError (422) with structured ctx so the frontend
can surface helpful "did you mean" hints in the error toast.

Philosophy A - raw truth: the UI exposes exactly what the API accepts; this
function enforces that contract on the write path.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from fastapi import HTTPException

from src.core.exceptions import raise_structured_validation_error
from src.core.reasoning_types import (
    ReasoningEffortBudget,
    ReasoningEffortEnum,
    ReasoningEffortToggleBudget,
    ReasoningEffortValue,
)

if TYPE_CHECKING:
    from src.core.llm_agent_config import LLMAgentConfig


class _CapsLike(Protocol):
    """Duck-typed model capabilities.

    Read-only attributes via ``@property`` so the Protocol is compatible with
    both ``ModelProfile`` (frozen dataclass — read-only attributes) and
    ``SimpleNamespace`` test fakes (settable, but read-only is a strict
    superset of settable for type-checking).
    """

    @property
    def model_id(self) -> str: ...

    @property
    def reasoning_widget(self) -> str: ...

    @property
    def reasoning_enum_values(self) -> list[str] | None: ...

    @property
    def reasoning_budget_range(self) -> dict[str, Any] | Any | None: ...


def validate_reasoning_effort(
    caps: _CapsLike,
    value: ReasoningEffortValue,
) -> None:
    """Validate that ``value`` matches what ``caps`` accepts.

    Args:
        caps: Model capabilities - must expose ``model_id``, ``reasoning_widget``,
            ``reasoning_enum_values`` and ``reasoning_budget_range``.
        value: The reasoning_effort value submitted by the caller (admin API
            payload or boot-time default). May be ``None`` for non-reasoning models.

    Raises:
        StructuredValidationError: 422 with a structured ``detail`` dict
            carrying ``type``, ``loc``, ``msg``, ``input`` and ``ctx`` so the
            frontend can surface actionable error toasts (e.g. "did you
            mean?" hints).
    """
    widget = caps.reasoning_widget

    if widget == "none":
        if value is not None:
            raise_structured_validation_error(
                error_type="reasoning_not_supported",
                loc=["body", "reasoning_effort"],
                msg=(
                    f"Model {caps.model_id} does not accept reasoning_effort. "
                    "Set reasoning_effort to null."
                ),
                input_value=_serialize(value),
                ctx={"model": caps.model_id, "widget": "none"},
            )
        return

    if widget == "enum":
        if not isinstance(value, ReasoningEffortEnum):
            raise_structured_validation_error(
                error_type="wrong_reasoning_effort_shape",
                loc=["body", "reasoning_effort"],
                msg=(
                    f"Model {caps.model_id} expects an enum value "
                    '(shape: {"effort": "<string>"}).'
                ),
                input_value=_serialize(value),
                ctx={
                    "model": caps.model_id,
                    "widget": "enum",
                    "expected_shape": {"effort": "<str>"},
                },
            )
        allowed = caps.reasoning_enum_values or []
        if value.effort not in allowed:
            raise_structured_validation_error(
                error_type="invalid_reasoning_effort",
                loc=["body", "reasoning_effort"],
                msg=(
                    f"Reasoning effort {value.effort!r} is not supported by "
                    f"{caps.model_id}. Allowed values: {', '.join(allowed)}."
                ),
                input_value=value.effort,
                ctx={
                    "model": caps.model_id,
                    "provided": value.effort,
                    "allowed": list(allowed),
                    "widget": "enum",
                },
            )
        return

    if widget == "budget_int":
        if not isinstance(value, ReasoningEffortBudget):
            raise_structured_validation_error(
                error_type="wrong_reasoning_effort_shape",
                loc=["body", "reasoning_effort"],
                msg=(
                    f"Model {caps.model_id} expects a numeric budget " '(shape: {"budget": <int>}).'
                ),
                input_value=_serialize(value),
                ctx={
                    "model": caps.model_id,
                    "widget": "budget_int",
                    "expected_shape": {"budget": "<int>"},
                },
            )
        rng = _normalize_range(caps.reasoning_budget_range)
        sentinels = {rng.get("off_sentinel"), rng.get("dynamic_sentinel")} - {None}
        if value.budget in sentinels:
            return
        lo = rng.get("min", 0)
        hi = rng.get("max", 0)
        if not (lo <= value.budget <= hi):
            raise_structured_validation_error(
                error_type="invalid_reasoning_budget",
                loc=["body", "reasoning_effort"],
                msg=(
                    f"Reasoning budget {value.budget} for {caps.model_id} is "
                    f"out of range [{lo}, {hi}] and not a sentinel."
                ),
                input_value=value.budget,
                ctx={
                    "model": caps.model_id,
                    "provided": value.budget,
                    "range": {"min": lo, "max": hi},
                    "sentinels": sorted(sentinels),
                    "widget": "budget_int",
                },
            )
        return

    if widget == "toggle_budget":
        if not isinstance(value, ReasoningEffortToggleBudget):
            raise_structured_validation_error(
                error_type="wrong_reasoning_effort_shape",
                loc=["body", "reasoning_effort"],
                msg=(
                    f"Model {caps.model_id} expects a toggle+budget "
                    '(shape: {"enabled": <bool>, "budget": <int|null>}).'
                ),
                input_value=_serialize(value),
                ctx={
                    "model": caps.model_id,
                    "widget": "toggle_budget",
                    "expected_shape": {
                        "enabled": "<bool>",
                        "budget": "<int|null>",
                    },
                },
            )
        if value.enabled and value.budget is not None:
            rng = _normalize_range(caps.reasoning_budget_range)
            lo = rng.get("min", 0)
            hi = rng.get("max", 0)
            if not (lo <= value.budget <= hi):
                raise_structured_validation_error(
                    error_type="invalid_reasoning_budget",
                    loc=["body", "reasoning_effort"],
                    msg=(
                        f"Reasoning budget {value.budget} for {caps.model_id} "
                        f"is out of range [{lo}, {hi}]."
                    ),
                    input_value=value.budget,
                    ctx={
                        "model": caps.model_id,
                        "provided": value.budget,
                        "range": {"min": lo, "max": hi},
                        "widget": "toggle_budget",
                    },
                )
        return

    # Unreachable when llm_models migration is in place. Defensive.
    raise RuntimeError(f"Unknown reasoning_widget: {widget!r}")


# LIA-scale enum efforts whose reasoning output is small enough to coexist with
# a tight completion cap. Everything else that is ACTIVE (deepseek high/max —
# the only non-off values its admin matrix exposes —, OpenAI medium+, any
# enabled Qwen toggle, any non-off Gemini budget) produces reasoning tokens
# that are billed INSIDE the completion window and can consume it entirely.
_LIGHT_ENUM_EFFORTS = frozenset({"none", "off", "minimal", "low"})


def _reasoning_consumes_completion_budget(value: ReasoningEffortValue) -> bool:
    """True when ``value`` enables reasoning heavy enough to eat the completion cap.

    Shape-based on purpose (no provider matrix to rot): the stored shapes are
    already provider-discriminated by the model's ``reasoning_widget``.

    - ``ReasoningEffortEnum``: heavy unless the effort is in
      :data:`_LIGHT_ENUM_EFFORTS` (measured negligible on OpenAI
      minimal/low; DeepSeek V4 never stores those — its matrix exposes only
      off/high/max, and high/max map to substantial API-side thinking).
    - ``ReasoningEffortBudget`` (Gemini): heavy unless the budget is the
      documented off value (``0``); ``-1`` (dynamic) is heavy — the size is
      unknown, so the safe reading is "can be large".
    - ``ReasoningEffortToggleBudget`` (Qwen): heavy whenever enabled.
    """
    if value is None:
        return False
    if isinstance(value, ReasoningEffortEnum):
        return value.effort not in _LIGHT_ENUM_EFFORTS
    if isinstance(value, ReasoningEffortBudget):
        return value.budget != 0
    return value.enabled


def validate_thinking_token_budget(
    *,
    llm_type: str,
    effective: LLMAgentConfig,
    floor: int,
) -> None:
    """Reject a config whose thinking mode would starve the completion budget.

    Reasoning tokens are billed inside the completion window (``max_tokens``):
    with substantial thinking enabled and a small cap, the model spends the
    whole budget reasoning and the final answer comes out truncated or empty.
    Measured in production 2026-07-29: ``telephony_synthesis`` moved to
    ``deepseek-v4-flash`` at effort ``high`` while its effective ``max_tokens``
    stayed at the pre-thinking default of 600 — every post-call synthesis
    failed and the user received the raw English vendor summary. The admin UI
    could not warn: nothing related the two fields. This validator is that
    missing relation, evaluated on the EFFECTIVE config (override merged onto
    code defaults — leaving ``max_tokens`` empty inherits the default, which
    is exactly how the incident happened).

    Args:
        llm_type: The LLM type being saved (error context only).
        effective: The effective config (defaults + pending override merged
            with the same ``merge_config`` the runtime uses).
        floor: Minimum acceptable ``max_tokens`` when thinking is heavy
            (``settings.llm_thinking_max_tokens_floor``).

    Raises:
        StructuredValidationError: 422 with an explicit, actionable message
            and a machine-readable ``ctx`` (``thinking_budget_below_floor``)
            the frontend maps to a localized toast.
    """
    if not _reasoning_consumes_completion_budget(effective.reasoning_effort):
        return
    max_tokens = effective.max_tokens
    if max_tokens is None or max_tokens >= floor:
        return
    raise_structured_validation_error(
        error_type="thinking_budget_below_floor",
        loc=["body", "max_tokens"],
        msg=(
            f"Reasoning is enabled for {llm_type} ({effective.provider}/"
            f"{effective.model}) but the effective max_tokens is {max_tokens}, "
            f"below the safe floor of {floor}. Reasoning tokens consume the "
            "completion budget: with a cap this small the final answer is "
            "truncated or empty (in production this silently degraded every "
            "telephony call report to an unusable raw summary). Raise "
            f"max_tokens to at least {floor}, or turn reasoning off. Note: "
            "leaving max_tokens empty inherits the code default, which may be "
            "calibrated for a non-thinking model."
        ),
        input_value=max_tokens,
        ctx={
            "llm_type": llm_type,
            "provider": effective.provider,
            "model": effective.model,
            "effective_max_tokens": max_tokens,
            "floor": floor,
            "reasoning_effort": _serialize(effective.reasoning_effort),
        },
    )


def _normalize_range(rng: Any) -> dict[str, Any]:
    """Accept either a dict (JSONB column) or a Pydantic ReasoningBudgetRange instance."""
    if rng is None:
        return {}
    if isinstance(rng, dict):
        return rng
    if hasattr(rng, "model_dump"):
        return rng.model_dump()  # type: ignore[no-any-return]
    return {}


def _serialize(value: ReasoningEffortValue) -> Any:
    """Serialize a reasoning_effort value for inclusion in error payloads."""
    if value is None:
        return None
    return value.model_dump()


def reasoning_effort_matches_widget(
    caps: _CapsLike,
    value: ReasoningEffortValue,
) -> bool:
    """Non-raising twin of :func:`validate_reasoning_effort`.

    Used by callers that need to *reconcile* rather than *reject* — e.g. the
    effective-config merge (``core.llm_config_helper.merge_config``) drops an
    incompatible reasoning_effort instead of crashing the typed reasoning
    builder, and the admin UI normalizes the field when the model changes.

    Args:
        caps: Model capabilities — must expose ``model_id``, ``reasoning_widget``,
            ``reasoning_enum_values`` and ``reasoning_budget_range``.
        value: The reasoning_effort value to check. ``None`` is valid only for a
            ``"none"`` widget.

    Returns:
        ``True`` when ``value`` has the correct shape for the model's
        ``reasoning_widget`` and (where applicable) an allowed / in-range value;
        ``False`` otherwise — including the defensive case where ``caps`` carries
        an unknown ``reasoning_widget`` (an unvalidatable value is treated as
        not matching, so the caller falls back to the model default).
    """
    try:
        validate_reasoning_effort(caps, value)
        return True
    except HTTPException, RuntimeError:
        # HTTPException: StructuredValidationError(422) IS-A HTTPException —
        # the documented "value invalid for this widget" outcome.
        # RuntimeError: validate_reasoning_effort's defensive guard for an
        # unknown reasoning_widget — treat as not-matching rather than letting
        # it propagate and crash the LLM-resolution path.
        return False


__all__ = [
    "reasoning_effort_matches_widget",
    "validate_reasoning_effort",
    "validate_thinking_token_budget",
]
