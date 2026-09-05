"""Installing the gate on a tool, and running an effect through it (ADR-263).

``gated`` wraps a tool's coroutine at REGISTRATION. Everything else in this
module exists to make that wrapper cheap on the path most calls take (a read
pays one memoised dictionary lookup) and honest on the path that matters (a
mutation is claimed before it happens and closed from what came back).

The ledger sits behind ``_LEDGER`` — one small object with three methods — so
the wrapper has no database knowledge of its own and a unit test can prove the
ORDER of operations without a PostgreSQL.
"""

from __future__ import annotations

import functools
import inspect
import time
import uuid
from collections.abc import Awaitable, Callable, Coroutine
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Final

import structlog

from src.core.field_names import FIELD_INJECTED_RUNTIME
from src.domains.agents.effects.digest import args_digest
from src.domains.agents.effects.gate import (
    ERROR_CONFIRMATION_MISSING,
    GateAction,
    decide_effect,
)
from src.domains.agents.effects.integrity import IntegrityKind, record_integrity_event
from src.domains.agents.effects.labels import build_effect_label
from src.domains.agents.effects.outcome import ToolOutcome, read_outcome, succeeded_only
from src.domains.agents.effects.schemas import ClaimRequest, EffectSourceName
from src.domains.agents.effects.scope import EffectScope, current_scope
from src.domains.agents.effects.treatments import record_treatment
from src.infrastructure.observability.metrics_effects import (
    effect_already_performed_total,
    effect_claims_total,
    effect_ledger_failures_total,
    effect_outcomes_total,
    effect_refusals_total,
    effect_unrecorded_total,
)

#: The draft-executor contract, kept intact by the gate: a wrapper that changed
#: the signature would break the 19 executors and the registry's typing.
ExecutorFnT = Callable[[dict[str, Any], uuid.UUID, Any], Coroutine[Any, Any, dict[str, Any]]]

logger = structlog.get_logger(__name__)

#: Marker the boot-time completeness assert looks for. A tool whose coroutine
#: does not carry it was registered through a path that forgot the gate.
EFFECT_GATED_ATTR: Final[str] = "__effect_gated__"

#: The name the installed gate acts under. A renamed COPY of a gated tool
#: (``registration.py`` makes one per MCP server) would otherwise keep the
#: original's identity and be recorded — and policed — as another tool.
EFFECT_GATED_NAME_ATTR: Final[str] = "__effect_gated_name__"

_policy_cache: dict[str, str | None] = {}


def reset_policy_cache() -> None:
    """Forget the memoised policies (tests, and a catalogue reload)."""
    _policy_cache.clear()


def resolve_policy(tool_name: str) -> str | None:
    """The tool's declared policy, memoised after the first successful read.

    The registry takes a lock on every manifest read, and a read-only tool can
    be called dozens of times in one ReAct turn; the policy of a given tool
    never changes once the catalogue is loaded, so it is read once.

    A miss is NOT cached: tools register before the catalogue is loaded, so an
    early call must not freeze "unknown" for the life of the process.

    Args:
        tool_name: The registered tool name.

    Returns:
        The declared policy, or None for a tool with no manifest — 22 of them
        exist (the browser sub-tools the browser loop drives, and the legacy
        readers no planner can reach), and they pass through by design.
    """
    if tool_name in _policy_cache:
        return _policy_cache[tool_name]

    from src.domains.agents.registry import get_global_registry
    from src.domains.agents.registry.catalogue import MUTATION_POLICIES, ToolManifestNotFound

    try:
        policy = get_global_registry().get_tool_manifest(tool_name).mutation_policy
    except ToolManifestNotFound, RuntimeError, AttributeError:
        return None

    if policy is not None and policy not in MUTATION_POLICIES:
        # The declaration is unreadable — a corrupt manifest, or a test that
        # installed a mock registry. The gate must stay TOTAL: it reads UNKNOWN
        # and the tool keeps working, because a gate that can take the whole
        # assistant down when a declaration is odd is worse than the hole it
        # closes. Loud, never silent: the boot assert refuses such a value, so
        # reaching this line at runtime is itself the defect.
        logger.error(
            "effect_policy_unreadable",
            tool_name=tool_name,
            policy_type=type(policy).__name__,
        )
        return None

    _policy_cache[tool_name] = policy
    return policy


class EffectAlreadyClaimed(RuntimeError):
    """A confirmed draft could not run, and nothing is known of what did.

    Raised only by :func:`gated_executor`, and only when the claim was lost to
    a row that kept no result — a first attempt that FAILED, or a winner still
    in flight. The tool wrapper answers the same situation with a payload
    because a tool result is read by a model; a draft executor's return value
    is read by the CALLER as the action's outcome, and the caller reports
    ``success=True`` for any dict that comes back. Returning one would tell the
    user their email left when nothing here knows that it did.

    Carries no message: the caller localises the sentence (``str(exc)`` empty →
    the locale's own wording), because a user-visible string never lives in a
    Python literal.

    Attributes:
        status: The existing row's status, for the log line only.
    """

    def __init__(self, *, status: str | None) -> None:
        super().__init__()
        self.status = status


@dataclass(frozen=True)
class ClaimTicket:
    """The right to perform one effect, or the record of one already performed.

    Attributes:
        effect_id: The ledger row.
        claim_token: Owner token; None when the claim was LOST, which means the
            effect already happened and must not happen again.
        served_result: What the winning call recorded, when it is available —
            the resume serves this instead of re-executing.
        served_status: The existing row's status when the claim was LOST.
            « Already performed » and « a previous attempt failed » are two
            different facts, and answering the second with the first sends the
            user away waiting for a result that will never come.
    """

    effect_id: uuid.UUID
    claim_token: uuid.UUID | None
    served_result: Any = None
    served_status: str | None = None


class _Ledger:
    """The gate's only door to the database.

    Kept as a tiny object rather than free functions so a unit test can replace
    it whole and prove the ORDER of operations, and so the wrapper carries no
    session knowledge.
    """

    async def claim(self, request: ClaimRequest) -> ClaimTicket | None:
        """Claim the right to act, in its OWN committed transaction.

        The commit is the point: an email is not transactional, so a claim that
        stayed inside the caller's open transaction could be rolled back after
        the mail had left — the dual-write hole this ledger exists to close.

        Args:
            request: What is about to happen and under which authority.

        Returns:
            A ticket, or None when the ledger itself is unavailable — the
            caller decides what that means per policy.
        """
        from src.domains.agents.effects.repository import EffectLedgerRepository
        from src.infrastructure.database.session import get_db_context

        try:
            async with get_db_context() as db:
                outcome = await EffectLedgerRepository(db).claim(request)
                await db.commit()
                if outcome.claimed:
                    return ClaimTicket(effect_id=outcome.effect.id, claim_token=outcome.claim_token)
                served = EffectLedgerRepository.decrypted_result(outcome.effect)
                return ClaimTicket(
                    effect_id=outcome.effect.id,
                    claim_token=None,
                    served_result=served,
                    served_status=outcome.effect.status.value,
                )
        except Exception as exc:  # noqa: BLE001 - see the caller's policy split
            effect_ledger_failures_total.labels(operation="claim").inc()
            logger.error(
                "effect_ledger_claim_failed",
                tool_name=request.tool_name,
                error_type=type(exc).__name__,
                exc_info=True,
            )
            return None

    async def close(
        self, effect_id: uuid.UUID, claim_token: uuid.UUID, *, outcome: ToolOutcome
    ) -> None:
        """Close the row from an EXPLICIT result.

        Best-effort by design: the effect has already happened, so failing to
        write its ending must not turn a successful action into an exception
        for the user. The failure is logged and, from lot 3, counted.

        Args:
            effect_id: The claimed row.
            claim_token: Its owner token.
            outcome: What the tool returned.
        """
        from src.domains.agents.effects.repository import EffectLedgerRepository
        from src.infrastructure.database.session import get_db_context

        try:
            async with get_db_context() as db:
                repository = EffectLedgerRepository(db)
                if outcome.succeeded:
                    await repository.close_success(
                        effect_id,
                        claim_token,
                        provider_ref=outcome.provider_ref,
                        result_payload=outcome.payload,
                    )
                else:
                    await repository.close_failure(
                        effect_id, claim_token, error_code="tool_reported_failure"
                    )
                await db.commit()
        except Exception as exc:  # noqa: BLE001 - the effect already happened
            effect_ledger_failures_total.labels(operation="close").inc()
            logger.error(
                "effect_ledger_close_failed",
                effect_id=str(effect_id),
                error_type=type(exc).__name__,
                exc_info=True,
            )

    async def refuse(self, request: ClaimRequest, *, error_code: str) -> None:
        """Record an effect that was NOT performed for want of authority."""
        from src.domains.agents.effects.repository import EffectLedgerRepository
        from src.infrastructure.database.session import get_db_context

        try:
            async with get_db_context() as db:
                await EffectLedgerRepository(db).refuse(request, error_code=error_code)
                await db.commit()
        except Exception as exc:  # noqa: BLE001 - a refusal must never raise
            effect_ledger_failures_total.labels(operation="refuse").inc()
            logger.error(
                "effect_ledger_refuse_failed",
                tool_name=request.tool_name,
                error_type=type(exc).__name__,
                exc_info=True,
            )


_LEDGER = _Ledger()

#: Statuses a lost claim may carry that mean the effect did NOT succeed. A
#: ``claimed`` row is a winner still in flight, which is a different answer.
_NO_RETRY_STATUSES: Final[frozenset[str]] = frozenset({"failed", "abandoned", "refused"})


def _build_request(
    tool_name: str, policy: str, kwargs: dict[str, Any], scope: EffectScope | None
) -> ClaimRequest | None:
    """Build the claim, or None when there is no identity to attribute it to.

    Args:
        tool_name: The tool about to act.
        policy: Its declared policy.
        kwargs: The call arguments (digested, never stored in clear).
        scope: The authority the executor published, if any.

    Returns:
        The request, or None when no run context names a user — nothing can be
        written to a ledger whose every row belongs to someone.
    """
    from src.domains.agents.context.runtime_context import runtime_context_if_running

    context = runtime_context_if_running()
    if context is None:
        return None

    source: EffectSourceName = (
        scope.source if scope else ("scheduled" if context.is_automated_source else "user")
    )
    return ClaimRequest(
        user_id=context.user_id,
        thread_id=context.thread_id,
        run_id=scope.run_id if scope else context.thread_id,
        source=source,
        execution_mode=context.execution_mode,
        tool_name=tool_name,
        mutation_policy=policy,
        idempotency_key=(scope.idempotency_key if scope else f"unscoped:{uuid.uuid4().hex}"),
        args_digest=args_digest(tool_name, kwargs),
        # Built HERE because this is the only moment the arguments exist: the
        # row keeps a digest, never the call (ADR-263).
        label=build_effect_label(tool_name, kwargs),
        approval_kind=scope.approval_kind if scope else None,
        approval_ref=scope.approval_ref if scope else None,
        draft_digest=scope.draft_digest if scope else None,
    )


def _signature_of(coroutine: Callable[..., Awaitable[Any]]) -> inspect.Signature | None:
    """Read the tool's signature ONCE, at registration.

    Args:
        coroutine: The tool's own coroutine.

    Returns:
        Its signature, or None for a callable that has none — the gate stays
        total, it never refuses a tool because it could not introspect it.
    """
    try:
        return inspect.signature(coroutine)
    except TypeError, ValueError:
        return None


def _named_arguments(
    signature: inspect.Signature | None, args: tuple[Any, ...], kwargs: dict[str, Any]
) -> dict[str, Any]:
    """Give every argument its parameter name.

    A caller may spell a call positionally (``resolve_reference(ref, runtime,
    domain)``); the digest, the register and the replay must not depend on
    that choice — the same call made two ways is one effect.

    Args:
        signature: The tool's signature, when it has one.
        args: Positional arguments as passed.
        kwargs: Keyword arguments as passed.

    Returns:
        One dict keyed by parameter name. Unbindable positionals (a ``*args``
        tool, a mismatched call) are kept under ``_positional`` rather than
        dropped: evidence may be imperfect, never silently incomplete.
    """
    if not args:
        return _without_plumbing(kwargs)
    if signature is not None:
        # A ``*args`` tool, or a caller whose spelling does not match the
        # signature: fall through to the fallback below rather than lose the
        # arguments — evidence may be imperfect, never silently incomplete.
        with suppress(TypeError):
            return _without_plumbing(dict(signature.bind_partial(*args, **kwargs).arguments))
    return _without_plumbing({**kwargs, "_positional": list(args)})


def _without_plumbing(arguments: dict[str, Any]) -> dict[str, Any]:
    """Drop the arguments the EXECUTOR supplies, keeping the model's intent.

    ``ToolRuntime`` is injected per call and has no value identity, so ``str()``
    of it carries an address: two identical calls would produce two different
    digests, and the register could never say "this is the same call".

    Args:
        arguments: The call arguments, by name.

    Returns:
        The same mapping without the injected plumbing.
    """
    if FIELD_INJECTED_RUNTIME not in arguments:
        return arguments
    return {name: value for name, value in arguments.items() if name != FIELD_INJECTED_RUNTIME}


async def _pass_through(
    tool_name: str,
    policy: str | None,
    coroutine: Callable[..., Awaitable[Any]],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> Any:
    """Run a capability that changes nothing, and record that it was consulted.

    The path most calls take. Everything here is paid on every read, so it
    holds exactly one clock reading, one boolean and one list append — no
    database session, no payload rendering, no digest.

    A raised call is recorded and re-raised: the turn must see the exception,
    the register must see the consultation. ``CancelledError`` is deliberately
    NOT recorded — it is not an answer, and the turn it belongs to is being
    torn down.

    Args:
        tool_name: The capability being consulted.
        policy: Its declared policy, or None when it declares none.
        coroutine: The tool's own coroutine.
        args: Positional arguments, forwarded unchanged.
        kwargs: Keyword arguments, forwarded unchanged.

    Returns:
        Whatever the capability returned.

    Raises:
        Exception: Re-raised unchanged after the consultation is recorded.
    """
    started = time.perf_counter()
    try:
        result = await coroutine(*args, **kwargs)
    except Exception:
        record_treatment(tool_name, policy, succeeded=False, duration_ms=_elapsed_ms(started))
        raise
    record_treatment(
        tool_name,
        policy,
        succeeded=succeeded_only(result),
        duration_ms=_elapsed_ms(started),
    )
    return result


def _elapsed_ms(started: float) -> int:
    """Milliseconds since a ``perf_counter`` reading, never negative."""
    return max(0, int((time.perf_counter() - started) * 1000))


def _refusal_output(tool_name: str, error_code: str, message: str) -> dict[str, Any]:
    """The refusal the model reads, in the shape every tool error uses."""
    from src.domains.agents.tools.common import ToolErrorCode, ToolErrorModel

    return ToolErrorModel(
        code=ToolErrorCode.FORBIDDEN,
        message=f"{message} [{error_code}]",
        context={"tool": tool_name, "reason": error_code},
    ).to_response()


async def _refuse_or_ask(
    tool_name: str,
    decision: Any,
    request: ClaimRequest | None,
    scope: EffectScope | None,
    named: dict[str, Any],
) -> Any:
    """Record a refusal, and answer it — with a question when one can be asked.

    Args:
        tool_name: The tool that was stopped.
        decision: The gate's verdict, carrying the error code and message.
        request: The claim that would have been made, when an identity exists.
        scope: The authority in force, for the log line.
        named: The call arguments, by name — what a confirmation would replay.

    Returns:
        A confirmation draft when someone is there to answer, else the refusal
        the model reads.
    """
    effect_refusals_total.labels(reason=str(decision.error_code)).inc()
    if request is not None:
        await _LEDGER.refuse(request, error_code=str(decision.error_code))
    logger.info(
        "effect_refused",
        tool_name=tool_name,
        reason=decision.error_code,
        source=scope.source if scope else None,
    )
    if decision.error_code == ERROR_CONFIRMATION_MISSING:
        # Someone IS there to answer: ask, do not fail. The draft is the shape
        # both execution modes already confirm, so the card, the queueing and
        # the resume all come for free (ADR-263).
        from src.domains.agents.effects.confirmation import confirmation_draft

        return confirmation_draft(tool_name, named)
    return _refusal_output(tool_name, str(decision.error_code), str(decision.llm_message))


def _serve_lost_claim(tool_name: str, ticket: ClaimTicket) -> Any:
    """Answer a call whose effect another already performed.

    Serving the record is what makes one approval one execution — the measured
    defect this whole programme starts from.

    Args:
        tool_name: The tool that lost the claim.
        ticket: The lost claim, carrying whatever the winner recorded.

    Returns:
        The winner's result, or an honest statement when it has none yet.
    """
    served = "record" if ticket.served_result is not None else "none"
    effect_already_performed_total.labels(served=served).inc()
    logger.info("effect_already_performed", tool_name=tool_name, served=served)
    if ticket.served_result is None:
        # Lost to a call that kept no result. Repeating the effect is the one
        # thing we must not do, and ``None`` is not a tool result — but WHICH
        # fact this is matters: a failed first attempt sent the model waiting
        # for a result that will never arrive.
        if ticket.served_status in _NO_RETRY_STATUSES:
            return _refusal_output(
                tool_name,
                f"effect_{ticket.served_status}",
                "A previous attempt of this action under the same approval did "
                "not succeed, and it was not retried automatically. Tell the "
                "user, and ask before attempting it again.",
            )
        return _refusal_output(
            tool_name,
            "effect_already_performed",
            "This action was already performed under the same approval and was "
            "not repeated; its result is not available yet.",
        )
    return ticket.served_result


async def _perform_and_close(
    ticket: ClaimTicket, act: Callable[[], Awaitable[Any]], *, policy: str
) -> Any:
    """Run the claimed effect and close its row from what came back.

    One implementation for both gates: a tool call and a draft executor close
    their books the same way, and a second copy is how one of them stops
    closing them on the failure path.

    Args:
        ticket: The won claim — its token is the right to close the row.
        act: The effect itself.
        policy: The declared policy, for the outcome counter.

    Returns:
        Whatever the effect returned.

    Raises:
        Exception: Re-raised unchanged after the row is closed as failed.
    """
    claim_token = ticket.claim_token
    if claim_token is None:  # pragma: no cover - the caller checks first
        raise ValueError("a claim that was not won cannot be closed")
    try:
        result = await act()
    except Exception:
        effect_outcomes_total.labels(policy=policy, status="failed").inc()
        await _LEDGER.close(
            ticket.effect_id,
            claim_token,
            outcome=ToolOutcome(succeeded=False, provider_ref=None, payload=None),
        )
        raise

    outcome = read_outcome(result)
    effect_outcomes_total.labels(
        policy=policy, status="succeeded" if outcome.succeeded else "failed"
    ).inc()
    await _LEDGER.close(ticket.effect_id, claim_token, outcome=outcome)
    return result


def _count_claim(policy: str, request: ClaimRequest | None, ticket: ClaimTicket | None) -> None:
    """Count an effect that was actually claimed by THIS call.

    A lost claim is not a new effect: it is counted by ``_serve_lost_claim``
    under its own question ("how many duplicates did we stop?").

    Args:
        policy: The declared policy of the capability.
        request: The claim that was made, when there was an identity to make it.
        ticket: What the ledger answered.
    """
    if ticket is None or ticket.claim_token is None or request is None:
        return
    effect_claims_total.labels(
        policy=policy, source=request.source, execution_mode=request.execution_mode
    ).inc()


async def _unrecorded_or_refused(
    tool_name: str, policy: str, request: ClaimRequest | None, unscoped: bool
) -> dict[str, Any] | None:
    """Decide what an effect that could NOT be recorded is allowed to do.

    The owner's split (2026-09-03): what the user had to confirm is recorded or
    not done at all; what they never had to confirm must not be blocked by OUR
    bookkeeping — but the gap is counted and logged, never silent.

    Args:
        tool_name: The capability about to act.
        policy: Its declared policy.
        request: The claim that would have been made, when an identity existed.
        unscoped: Whether the call ran outside any published authority.

    Returns:
        A refusal payload when the effect must not happen, else None.
    """
    if policy == "confirm":
        effect_refusals_total.labels(reason="ledger_unavailable").inc()
        logger.error("effect_refused_ledger_unavailable", tool_name=tool_name)
        return _refusal_output(
            tool_name,
            "ledger_unavailable",
            "This action could not be recorded and was therefore not performed. "
            "Tell the user it must be retried.",
        )

    reason = "no_claim" if request is not None else "no_context"
    effect_unrecorded_total.labels(policy=policy, reason=reason).inc()
    logger.warning("effect_unrecorded", tool_name=tool_name, policy=policy, unscoped=unscoped)
    # The metric counts; the row says WHICH account and WHICH turn (ADR-263
    # lot 8). One detection, two destinations — never a second detector.
    await record_integrity_event(
        IntegrityKind.EFFECT_UNRECORDED,
        user_id=request.user_id if request is not None else None,
        run_id=request.run_id if request is not None else None,
        detail=f"{reason}:{policy}",
    )
    return None


def gated(
    tool_name: str, coroutine: Callable[..., Awaitable[Any]]
) -> Callable[..., Awaitable[Any]]:
    """Install the effect gate on one tool coroutine (ADR-263).

    Idempotent: wrapping an already-gated coroutine returns it unchanged, so a
    module reload or a second registration cannot nest two gates.

    Args:
        tool_name: The registered name, which is how the policy is resolved.
        coroutine: The tool's own coroutine.

    Returns:
        The gated coroutine, carrying :data:`EFFECT_GATED_ATTR`.
    """
    if getattr(coroutine, EFFECT_GATED_ATTR, False):
        if getattr(coroutine, EFFECT_GATED_NAME_ATTR, tool_name) == tool_name:
            return coroutine
        # A renamed copy of an already-gated tool: re-gate the ORIGINAL under
        # the new name rather than nesting a second gate that would claim the
        # same effect twice.
        coroutine = getattr(coroutine, "__wrapped__", coroutine)

    signature = _signature_of(coroutine)

    @functools.wraps(coroutine)
    async def _run_gated(*args: Any, **kwargs: Any) -> Any:
        policy = resolve_policy(tool_name)
        scope = current_scope()
        decision = decide_effect(policy, scope)

        if decision.action is GateAction.PASS_THROUGH:
            return await _pass_through(tool_name, policy, coroutine, args, kwargs)

        # The evidence, the digest and the replay all speak NAMES: a caller
        # that passed its arguments positionally (``resolve_reference`` has
        # one) must not produce a different record, nor an unreplayable draft.
        named = _named_arguments(signature, args, kwargs)
        request = _build_request(tool_name, str(policy), named, scope)

        if decision.action is GateAction.REFUSE:
            return await _refuse_or_ask(tool_name, decision, request, scope, named)

        # LEDGER: claim, act, close.
        ticket = await _LEDGER.claim(request) if request is not None else None
        _count_claim(str(policy), request, ticket)
        if ticket is None:
            refusal = await _unrecorded_or_refused(
                tool_name, str(policy), request, bool(decision.unscoped)
            )
            return refusal if refusal is not None else await coroutine(*args, **kwargs)

        if ticket.claim_token is None:
            return _serve_lost_claim(tool_name, ticket)

        return await _perform_and_close(
            ticket, lambda: coroutine(*args, **kwargs), policy=str(policy)
        )

    # ``functools.wraps`` sets ``__wrapped__``, which ``inspect`` follows: the
    # tool keeps its name, its docstring AND its readable source, so anything
    # that introspects a tool — including tests that assert on what a tool
    # calls — sees the tool rather than the gate.
    setattr(_run_gated, EFFECT_GATED_ATTR, True)
    setattr(_run_gated, EFFECT_GATED_NAME_ATTR, tool_name)
    return _run_gated


def assert_effect_gate_completeness() -> None:
    """Assert every registered capability actually goes through the gate (ADR-263).

    The gate is installed at registration, so this checks the property that
    installation is supposed to guarantee rather than trusting that it ran.
    It found the second registration path the day it was written: 114 of 122
    tools entered the registry through ``_collect_tools_from_module``, which
    wrote straight into the dictionary and never called the installer.

    Called from ``init_agent_registry`` after the tools are loaded, and from a
    unit test so CI catches it before a boot does (ADR-085 placement).

    Raises:
        AssertionError: Listing every capability that bypasses the gate.
    """
    from src.domains.agents.services.draft_executor_types import (
        EXECUTOR_REGISTRY,
        EXECUTORS_GATED_BY_THEIR_TOOL,
    )
    from src.domains.agents.tools.tool_registry import get_all_tools

    ungated = sorted(
        name
        for name, tool in get_all_tools().items()
        if not getattr(getattr(tool, "coroutine", None), EFFECT_GATED_ATTR, False)
    )
    ungated_executors = sorted(
        draft_type
        for draft_type, executor in EXECUTOR_REGISTRY.items()
        # The declared exemption: an executor whose effect is recorded by the
        # TOOL it replays. Gating it too would claim a second row for one
        # effect — and both claims would share the scope key, so the inner call
        # would be mistaken for a replay and never run at all.
        if draft_type not in EXECUTORS_GATED_BY_THEIR_TOOL
        and not getattr(executor, EFFECT_GATED_ATTR, False)
    )
    if ungated or ungated_executors:
        raise AssertionError(
            f"{len(ungated)} tool(s) and {len(ungated_executors)} draft executor(s) "
            f"bypass the effect gate — tools: {ungated}; executors: "
            f"{ungated_executors}. They were registered through a path that does "
            "not install it; route that path through "
            "``tool_registry._install_effect_gate`` or ``register_executor``."
        )


def gated_executor(draft_type: str, executor: ExecutorFnT) -> ExecutorFnT:
    """Install the effect gate on a draft executor (ADR-263).

    A draft executor is where a confirmed draft becomes a real effect — the
    email actually leaves. The tool that BUILT the draft passed through the
    gate untouched (it changed nothing); this is the call that must be claimed
    before it happens and closed from its result.

    The policy recorded is ``draft``, because that is the policy that applied:
    the user confirmed the draft they were shown.

    Args:
        draft_type: The draft family, used as the tool name in the ledger.
        executor: ``(draft_content, user_id, deps) -> result``.

    Returns:
        The gated executor, carrying :data:`EFFECT_GATED_ATTR`.
    """
    if getattr(executor, EFFECT_GATED_ATTR, False):
        return executor

    @functools.wraps(executor)
    async def _run_gated_executor(
        draft_content: dict[str, Any], user_id: uuid.UUID, deps: Any
    ) -> dict[str, Any]:
        scope = current_scope()
        request = _build_request(f"draft:{draft_type}", "draft", {"draft": draft_content}, scope)
        ticket = await _LEDGER.claim(request) if request is not None else None
        _count_claim("draft", request, ticket)
        if ticket is None:
            # No run context, or the ledger is down. A confirmed draft is the
            # user's explicit instruction: refusing it here would lose what
            # they asked for over OUR bookkeeping. It runs, and the gap is
            # loud rather than silent.
            draft_reason = "no_claim" if request is not None else "no_context"
            effect_unrecorded_total.labels(policy="draft", reason=draft_reason).inc()
            logger.warning("effect_unrecorded_draft", draft_type=draft_type)
            await record_integrity_event(
                IntegrityKind.EFFECT_UNRECORDED,
                user_id=user_id,
                run_id=request.run_id if request is not None else None,
                detail=f"{draft_reason}:draft",
            )
            served: dict[str, Any] = await executor(draft_content, user_id, deps)
            return served

        if ticket.claim_token is None:
            effect_already_performed_total.labels(
                served="record" if ticket.served_result is not None else "none"
            ).inc()
            logger.info(
                "effect_already_performed_draft",
                draft_type=draft_type,
                served_status=ticket.served_status,
            )
            if ticket.served_result is None:
                # Nothing was recorded, so nothing is known: an empty dict here
                # would reach the user as « done » (the caller reports success
                # for any dict). Raise, and let the caller say so in the
                # reader's language.
                raise EffectAlreadyClaimed(status=ticket.served_status)
            recorded: dict[str, Any] = ticket.served_result
            return recorded

        performed: dict[str, Any] = await _perform_and_close(
            ticket, lambda: executor(draft_content, user_id, deps), policy="draft"
        )
        return performed

    setattr(_run_gated_executor, EFFECT_GATED_ATTR, True)
    setattr(_run_gated_executor, EFFECT_GATED_NAME_ATTR, draft_type)
    return _run_gated_executor
