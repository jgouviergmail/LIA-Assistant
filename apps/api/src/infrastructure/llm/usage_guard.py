"""One usage guard, shared by every door to a paid model.

Two chokepoints stand between this codebase and a provider:
``invoke_with_instrumentation`` and ``get_structured_output_with_retry``. Until
2026-09-07 only the first carried the usage check, and the second did not even
accept a ``user_id`` — so the relationship debrief, the telephony return
synthesis and the self-diagnosis all spent through a door no ceiling could
close.

That is ADR-248's rule pointing at a guard rather than a predicate: one rule,
two implementations, only one of which ran. The rule now has one
implementation, and :data:`LLM_CHOKEPOINTS` names every door that must call it
— checked structurally, so a third door cannot be added quietly.

Two refusals the guard must NOT make, both deliberate:

- **no owner, no ceiling.** Self-diagnosis and catalogue translations run for
  no account. Refusing them here would enforce a per-account bound against
  nobody, and would silence the subsystem that reports on the deployment. Their
  bound is the instance ledger (:mod:`domains.usage_limits.instance_spend`).
- **``"system"`` is not an account.** It is the placeholder some callers pass;
  resolving it would look up a ceiling for a user that does not exist.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog

from src.core.field_names import FIELD_USER_ID
from src.infrastructure.llm.instrumentation import extract_session_user_from_state

logger = structlog.get_logger(__name__)

#: Every function that hands work to a paid model, as ``(module, function)``
#: relative to ``src``. A door absent from this list is a door nobody checks;
#: ``test_usage_guard_at_every_chokepoint`` refuses both an omission and a
#: declared door that never calls the guard.
LLM_CHOKEPOINTS: tuple[tuple[str, str], ...] = (
    ("infrastructure/llm/invoke_helpers.py", "invoke_with_instrumentation"),
    # The INNERMOST door, not its retry wrapper: ``get_structured_output`` is
    # public and nine modules call it directly, bypassing the wrapper entirely
    # (``open_loop_extractor`` and ``evaluation_pipeline`` among them). Naming
    # the wrapper guarded one path and left its sibling open, in the same file.
    ("infrastructure/llm/structured_output.py", "get_structured_output"),
)


def resolve_owner(
    explicit_user_id: str | UUID | None = None,
    state: dict[str, Any] | None = None,
    config: Any | None = None,
) -> UUID | None:
    """Whose account this call belongs to, or None when it belongs to nobody.

    Args:
        explicit_user_id: What the caller passed, if anything.
        state: LangGraph state, which may carry the acting user.
        config: ``RunnableConfig``, whose metadata may carry it.

    Returns:
        The account, or None — including for the ``"system"`` placeholder and
        for anything that is not a valid UUID.
    """
    candidate: str | UUID | None = explicit_user_id

    if not candidate and state:
        _, extracted = extract_session_user_from_state(state)
        candidate = extracted

    if not candidate and config:
        metadata = (config.get("metadata") if hasattr(config, "get") else None) or {}
        candidate = metadata.get(FIELD_USER_ID)

    if not candidate or candidate == "system":
        return None
    if isinstance(candidate, UUID):
        return candidate
    try:
        return UUID(str(candidate))
    except ValueError:
        return None


async def enforce_usage_limit(
    user_id: str | UUID | None,
    *,
    layer: str,
    state: dict[str, Any] | None = None,
    config: Any | None = None,
) -> None:
    """Refuse the call when either ceiling that applies to it is exhausted.

    **Two bounds, and a model call answers to both.** Every euro spent on a
    model is paid with the deployment's own provider key — ``cost_bearers``
    puts the ``llm`` family on :attr:`CostBearer.INSTANCE` — so what the
    INSTANCE may spend in a day bounds every call, and what ONE account may
    consume bounds the calls that have an owner. Only what a person pays with
    their OWN connector key is outside this.

    Two early returns used to defeat that, and both are gone:

    - the feature flag returned before anything was asked, so an operator who
      set a daily budget while leaving per-user limits off enforced nothing
      here — although the chat router, going through ``check_user_allowed``,
      enforced it. ``check_user_allowed`` deliberately keeps the instance
      ceiling outside that flag; this gate must not short-circuit ahead of it.
    - an ownerless call returned too, on the reasoning that no per-account
      ceiling belongs to it. True, and beside the point: the deployment's key
      still paid.

    Args:
        user_id: The account, when the caller knows it.
        layer: Which door asked, for the enforcement metric.
        state: LangGraph state, consulted when ``user_id`` is absent.
        config: ``RunnableConfig``, consulted last.

    Raises:
        UsageLimitExceededError: 429, carrying the limit that was exceeded and,
            for a deployment pause, when it lifts.
    """
    from src.domains.usage_limits.enforcement import raise_for_blocked_verdict
    from src.domains.usage_limits.service import UsageLimitService

    owner = resolve_owner(user_id, state, config)

    if owner is None:
        # No account behind this call, so no per-account ceiling — but the
        # deployment's ledger still received the spend, and still bounds it.
        decision = await UsageLimitService.instance_budget_block()
        if decision is not None:
            raise_for_blocked_verdict(decision, layer=layer)
        return

    # Asks the instance ceiling first and the per-account one after, both in
    # the one implementation that owns them.
    verdict = await UsageLimitService.check_user_allowed(owner)
    if not verdict.allowed:
        raise_for_blocked_verdict(verdict, layer=layer)


__all__ = ["LLM_CHOKEPOINTS", "enforce_usage_limit", "resolve_owner"]
