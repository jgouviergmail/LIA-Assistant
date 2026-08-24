"""Strict validation of a reasoning intent against what a model accepts.

Used by:
- ``LLMConfigService.upsert_override`` (admin API write path)
- ``bootstrap.validate_llm_defaults_against_matrix`` (boot-time fail-fast)

Raises ``StructuredValidationError`` (422) with structured ``ctx`` so the
frontend can surface a helpful "did you mean" hint in the error toast.

**What this module stopped doing (ADR-245).** It used to cross-validate the
*shape* of a stored value against the model's ``reasoning_widget`` -- four
shapes, four widgets, and a mismatch raised at LLM instantiation time. There is
one shape now, and an unknown level is already refused by the ``Literal`` on
``ReasoningIntent.level``, so nothing here can be wrong about shape.

What remains is one question -- **is this level on the model's ladder?** -- and
it is answered by ``resolve_reasoning_profile``, the same function the
translator uses. The validator and the translator therefore cannot disagree,
which is what made the previous three-authority arrangement fail.

This validator *rejects* on the write path; it never coerces. Coercion belongs
to the runtime, where the model is known and a stale value must not become an
error. Philosophy A -- raw truth: the UI exposes exactly what the API accepts.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from src.core.exceptions import raise_structured_validation_error
from src.core.reasoning_intent import ReasoningIntent

if TYPE_CHECKING:
    from src.core.llm_agent_config import LLMAgentConfig
    from src.infrastructure.llm.reasoning.profiles import ReasoningProfile

#: Levels whose reasoning is measured negligible against the completion budget.
#: OpenAI ``minimal``/``low`` sit here; DeepSeek V4 never stores them (its
#: ladder exposes only none/high/max, and both of those mean substantial
#: API-side thinking).
_LIGHT_LEVELS = frozenset({"provider_default", "none", "minimal", "low"})


class _CapsLike(Protocol):
    """Duck-typed model capabilities — exactly what this module reads.

    Read-only attributes via ``@property`` so the Protocol accepts both
    ``ModelProfile`` (a frozen dataclass) and the ``SimpleNamespace`` fakes the
    test suite uses.

    It shrank with ADR-245: ``reasoning_widget`` and ``reasoning_budget_range``
    left it because nothing here reads them any more. A Protocol that demands
    more than it uses is a false contract — every caller pays for fields the
    callee ignores, and a reader cannot tell which ones still matter.
    """

    @property
    def model_id(self) -> str: ...

    @property
    def reasoning_enum_values(self) -> list[str] | None: ...


def _profile_for(caps: _CapsLike, provider: str | None) -> ReasoningProfile:
    """Resolve the model's profile, narrowed by whatever the catalogue declares.

    Args:
        caps: The model's capabilities row.
        provider: The provider the family is derived from.

    Returns:
        The resolved profile — the same one the runtime translator uses, which
        is what keeps this validator from becoming a second authority.
    """
    from src.infrastructure.llm.reasoning.profiles import resolve_reasoning_profile

    declared = getattr(caps, "reasoning_enum_values", None)
    return resolve_reasoning_profile(
        provider or "",
        getattr(caps, "model_id", "") or "",
        model_levels=tuple(declared) if declared else None,
    )


def validate_reasoning_effort(
    caps: _CapsLike,
    value: ReasoningIntent | None,
    provider: str | None = None,
) -> None:
    """Reject a level the model does not offer.

    Args:
        caps: Model capabilities — must expose ``model_id`` and, optionally,
            ``reasoning_enum_values`` (the catalogue's ladder narrowing).
        value: The submitted intent. ``None`` means "no override" and is always
            valid, for every model.
        provider: The model's provider, needed to derive its family. When
            omitted the family cannot be derived and nothing is rejected —
            absence of evidence is not a rejection.

    Raises:
        StructuredValidationError: 422 with a structured ``detail`` carrying
            ``type``, ``loc``, ``msg``, ``input`` and ``ctx`` so the frontend
            can surface an actionable toast.
    """
    if value is None:
        return
    if not provider:
        # The family is derived from (provider, model): without a provider it
        # cannot be derived, and an underived family is NOT evidence that the
        # model does not reason. Absence of evidence is never a rejection --
        # the runtime will resolve and coerce with the provider it does have.
        return

    profile = _profile_for(caps, provider)

    if profile.family == "none" and profile.source == "unknown":
        # No rule matched: the family is unknown, not absent. Rejecting the
        # operator's level here would refuse a level a local model may well
        # accept, on the strength of a rule table that has never heard of it.
        return

    if profile.family == "none":
        raise_structured_validation_error(
            error_type="reasoning_not_supported",
            loc=["body", "reasoning_effort"],
            msg=(
                f"Model {caps.model_id} does not accept a reasoning override. "
                "Set reasoning_effort to null."
            ),
            input_value=_serialize(value),
            ctx={"model": caps.model_id, "family": "none"},
        )

    # ``none`` is governed by ``can_disable``, not by ladder membership: a
    # catalogue row may narrow the ladder to the DEPTHS a model offers
    # (``claude-opus-4-6`` declares ["low","medium","high","max"]) without
    # meaning "and it can no longer be turned off". Rejecting an explicit
    # ``none`` there would refuse the one setting an operator most often wants,
    # and it is the same trap the coercion contract closes at runtime.
    explicit_off = value.level == "none" and profile.can_disable

    if value.level != "provider_default" and not explicit_off and value.level not in profile.levels:
        raise_structured_validation_error(
            error_type="invalid_reasoning_effort",
            loc=["body", "reasoning_effort"],
            msg=(
                f"Reasoning level {value.level!r} is not offered by "
                f"{caps.model_id}. Allowed: {sorted(profile.levels)}."
            ),
            input_value=_serialize(value),
            ctx={
                "model": caps.model_id,
                "family": profile.family,
                "allowed": list(profile.levels),
                "submitted": value.level,
            },
        )

    if value.budget_tokens is not None and not profile.supports_budget:
        raise_structured_validation_error(
            error_type="reasoning_budget_not_supported",
            loc=["body", "reasoning_effort"],
            msg=(
                f"Model {caps.model_id} expresses reasoning as a level, not a "
                "token budget. Remove budget_tokens."
            ),
            input_value=_serialize(value),
            ctx={"model": caps.model_id, "family": profile.family},
        )

    if (
        value.budget_tokens is not None
        and profile.budget_range is not None
        and not (profile.budget_range[0] <= value.budget_tokens <= profile.budget_range[1])
    ):
        low, high = profile.budget_range
        raise_structured_validation_error(
            error_type="invalid_reasoning_budget",
            loc=["body", "reasoning_effort"],
            msg=(
                f"Reasoning budget {value.budget_tokens} is outside what "
                f"{caps.model_id} accepts ({low}-{high})."
            ),
            input_value=_serialize(value),
            ctx={"model": caps.model_id, "min": low, "max": high},
        )


def _reasoning_consumes_completion_budget(value: ReasoningIntent | None) -> bool:
    """True when the intent enables reasoning heavy enough to eat the completion cap.

    One shape, so one rule: everything above the light band is heavy. An
    explicit token budget is heavy whatever its size — the caller asked for
    thinking, and the whole point of the guard below is that thinking is billed
    inside ``max_tokens``.
    """
    if value is None:
        return False
    if value.budget_tokens is not None and value.budget_tokens > 0:
        return True
    return value.level not in _LIGHT_LEVELS


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
    code defaults — leaving ``max_tokens`` empty inherits the default, which is
    exactly how the incident happened).

    Args:
        llm_type: The LLM type being saved (error context only).
        effective: The effective config (defaults + pending override merged
            with the same ``merge_config`` the runtime uses).
        floor: Minimum acceptable ``max_tokens`` when thinking is heavy
            (``settings.llm_thinking_max_tokens_floor``).

    Raises:
        StructuredValidationError: 422 with an explicit, actionable message and
            a machine-readable ``ctx`` (``thinking_budget_below_floor``) the
            frontend maps to a localized toast.
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


def _serialize(value: ReasoningIntent | None) -> dict[str, Any] | None:
    """Render an intent for inclusion in an error payload."""
    if value is None:
        return None
    from dataclasses import asdict

    return asdict(value)
