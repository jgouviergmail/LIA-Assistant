"""Strict validation of reasoning_effort against a model's reasoning_widget.

Used by:
- LLMConfigService.upsert_override (admin API write path)
- bootstrap.validate_llm_defaults_against_matrix (boot-time fail-fast)

Raises HTTPException(422) with structured ctx so the frontend can surface
helpful "did you mean" hints in the error toast.

Philosophy A - raw truth: the UI exposes exactly what the API accepts; this
function enforces that contract on the write path.
"""

from __future__ import annotations

from typing import Any, Protocol

from fastapi import HTTPException

from src.core.reasoning_types import (
    ReasoningEffortBudget,
    ReasoningEffortEnum,
    ReasoningEffortToggleBudget,
    ReasoningEffortValue,
)


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
        HTTPException: 422 with a structured ``detail`` dict carrying ``type``,
            ``loc``, ``msg``, ``input`` and ``ctx`` so the frontend can surface
            actionable error toasts (e.g. "did you mean?" hints).
    """
    widget = caps.reasoning_widget

    if widget == "none":
        if value is not None:
            raise HTTPException(
                status_code=422,
                detail={
                    "type": "reasoning_not_supported",
                    "loc": ["body", "reasoning_effort"],
                    "msg": (
                        f"Model {caps.model_id} does not accept reasoning_effort. "
                        "Set reasoning_effort to null."
                    ),
                    "input": _serialize(value),
                    "ctx": {"model": caps.model_id, "widget": "none"},
                },
            )
        return

    if widget == "enum":
        if not isinstance(value, ReasoningEffortEnum):
            raise HTTPException(
                status_code=422,
                detail={
                    "type": "wrong_reasoning_effort_shape",
                    "loc": ["body", "reasoning_effort"],
                    "msg": (
                        f"Model {caps.model_id} expects an enum value "
                        '(shape: {"effort": "<string>"}).'
                    ),
                    "input": _serialize(value),
                    "ctx": {
                        "model": caps.model_id,
                        "widget": "enum",
                        "expected_shape": {"effort": "<str>"},
                    },
                },
            )
        allowed = caps.reasoning_enum_values or []
        if value.effort not in allowed:
            raise HTTPException(
                status_code=422,
                detail={
                    "type": "invalid_reasoning_effort",
                    "loc": ["body", "reasoning_effort"],
                    "msg": (
                        f"Reasoning effort {value.effort!r} is not supported by "
                        f"{caps.model_id}. Allowed values: {', '.join(allowed)}."
                    ),
                    "input": value.effort,
                    "ctx": {
                        "model": caps.model_id,
                        "provided": value.effort,
                        "allowed": list(allowed),
                        "widget": "enum",
                    },
                },
            )
        return

    if widget == "budget_int":
        if not isinstance(value, ReasoningEffortBudget):
            raise HTTPException(
                status_code=422,
                detail={
                    "type": "wrong_reasoning_effort_shape",
                    "loc": ["body", "reasoning_effort"],
                    "msg": (
                        f"Model {caps.model_id} expects a numeric budget "
                        '(shape: {"budget": <int>}).'
                    ),
                    "input": _serialize(value),
                    "ctx": {
                        "model": caps.model_id,
                        "widget": "budget_int",
                        "expected_shape": {"budget": "<int>"},
                    },
                },
            )
        rng = _normalize_range(caps.reasoning_budget_range)
        sentinels = {rng.get("off_sentinel"), rng.get("dynamic_sentinel")} - {None}
        if value.budget in sentinels:
            return
        lo = rng.get("min", 0)
        hi = rng.get("max", 0)
        if not (lo <= value.budget <= hi):
            raise HTTPException(
                status_code=422,
                detail={
                    "type": "invalid_reasoning_budget",
                    "loc": ["body", "reasoning_effort"],
                    "msg": (
                        f"Reasoning budget {value.budget} for {caps.model_id} is "
                        f"out of range [{lo}, {hi}] and not a sentinel."
                    ),
                    "input": value.budget,
                    "ctx": {
                        "model": caps.model_id,
                        "provided": value.budget,
                        "range": {"min": lo, "max": hi},
                        "sentinels": sorted(sentinels),
                        "widget": "budget_int",
                    },
                },
            )
        return

    if widget == "toggle_budget":
        if not isinstance(value, ReasoningEffortToggleBudget):
            raise HTTPException(
                status_code=422,
                detail={
                    "type": "wrong_reasoning_effort_shape",
                    "loc": ["body", "reasoning_effort"],
                    "msg": (
                        f"Model {caps.model_id} expects a toggle+budget "
                        '(shape: {"enabled": <bool>, "budget": <int|null>}).'
                    ),
                    "input": _serialize(value),
                    "ctx": {
                        "model": caps.model_id,
                        "widget": "toggle_budget",
                        "expected_shape": {
                            "enabled": "<bool>",
                            "budget": "<int|null>",
                        },
                    },
                },
            )
        if value.enabled and value.budget is not None:
            rng = _normalize_range(caps.reasoning_budget_range)
            lo = rng.get("min", 0)
            hi = rng.get("max", 0)
            if not (lo <= value.budget <= hi):
                raise HTTPException(
                    status_code=422,
                    detail={
                        "type": "invalid_reasoning_budget",
                        "loc": ["body", "reasoning_effort"],
                        "msg": (
                            f"Reasoning budget {value.budget} for {caps.model_id} "
                            f"is out of range [{lo}, {hi}]."
                        ),
                        "input": value.budget,
                        "ctx": {
                            "model": caps.model_id,
                            "provided": value.budget,
                            "range": {"min": lo, "max": hi},
                            "widget": "toggle_budget",
                        },
                    },
                )
        return

    # Unreachable when llm_models migration is in place. Defensive.
    raise RuntimeError(f"Unknown reasoning_widget: {widget!r}")


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


__all__ = ["validate_reasoning_effort"]
