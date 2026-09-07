"""Every door to a provider asks the same question before opening.

There are two chokepoints between this codebase and a paid model:
``invoke_with_instrumentation`` and ``get_structured_output_with_retry``. Only
the first carried the usage guard — the second did not even take a ``user_id``.

The consequence, measured on 2026-09-07: the relationship debrief, the
telephony return synthesis and the self-diagnosis all spend through the second
door, so no ceiling could refuse any of them. It is ADR-248's rule about the
ReAct stop condition, pointing at a guard instead of a predicate — one rule,
two implementations, and only one of them ran.

The structural test below is the part that lasts. Whoever adds a third door
must add it to :data:`LLM_CHOKEPOINTS` and wire the guard, or the build stops.
"""

from __future__ import annotations

import ast
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit

_SRC = Path(__file__).resolve().parents[4] / "src"


def _function_named(module: str, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    tree = ast.parse((_SRC / module).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{module}::{name} not found")


class TestEveryChokepointIsDeclaredAndGuarded:
    """The registry is the instrument; the wiring is checked against it."""

    def test_every_declared_chokepoint_calls_the_shared_guard(self) -> None:
        from src.infrastructure.llm.usage_guard import LLM_CHOKEPOINTS

        assert LLM_CHOKEPOINTS, "no chokepoint declared at all"
        for module, function in LLM_CHOKEPOINTS:
            node = _function_named(module, function)
            calls = {
                (
                    call.func.id
                    if isinstance(call.func, ast.Name)
                    else getattr(call.func, "attr", "")
                )
                for call in ast.walk(node)
                if isinstance(call, ast.Call)
            }
            assert "enforce_usage_limit" in calls, (
                f"{module}::{function} is a declared chokepoint but never calls "
                "enforce_usage_limit — a door that asks nothing bounds nothing"
            )

    def test_every_declared_chokepoint_accepts_an_owner(self) -> None:
        """A guard cannot bill a ceiling to a caller it cannot name.

        ``get_structured_output_with_retry`` took no ``user_id`` at all, which
        is why adding the guard to it required widening its signature rather
        than a one-line insertion.
        """
        from src.infrastructure.llm.usage_guard import LLM_CHOKEPOINTS

        for module, function in LLM_CHOKEPOINTS:
            node = _function_named(module, function)
            names = {arg.arg for arg in node.args.args} | {arg.arg for arg in node.args.kwonlyargs}
            assert (
                "user_id" in names or "config" in names
            ), f"{module}::{function} can name no owner, so no ceiling applies to it"


class TestTheGuardItself:
    """What it does, and — just as important — what it refuses to do."""

    async def test_an_account_over_its_limit_is_refused(self) -> None:
        from src.core.exceptions import UsageLimitExceededError
        from src.domains.usage_limits.schemas import UsageLimitStatus
        from src.domains.usage_limits.service import UsageLimitCheckResult
        from src.infrastructure.llm.usage_guard import enforce_usage_limit

        blocked = UsageLimitCheckResult(
            allowed=False,
            status=UsageLimitStatus.BLOCKED_LIMIT,
            blocked_reason="cycle cost exceeded",
            exceeded_limit="cycle_cost",
        )
        with (
            patch(
                "src.domains.usage_limits.service.UsageLimitService.check_user_allowed",
                AsyncMock(return_value=blocked),
            ),
            pytest.raises(UsageLimitExceededError),
        ):
            await enforce_usage_limit(str(uuid.uuid4()), layer="structured_output")

    async def test_a_call_with_no_owner_asks_no_per_account_ceiling(self) -> None:
        """Self-diagnosis has no account, so no per-account ceiling applies.

        Refusing on a ceiling that belongs to nobody would silence the very
        subsystem that reports on the deployment. Its bound is the INSTANCE
        ledger instead — asserted in ``TestBothCeilingsApply`` below, because
        the platform's own key paid for the call either way.
        """
        from src.infrastructure.llm.usage_guard import enforce_usage_limit

        checked: list[object] = []
        with (
            patch(
                "src.domains.usage_limits.service.UsageLimitService.check_user_allowed",
                AsyncMock(side_effect=lambda uid: checked.append(uid)),
            ),
        ):
            await enforce_usage_limit(None, layer="structured_output")

        assert checked == [], "a call with no owner consulted a per-account ceiling"

    async def test_the_system_placeholder_names_nobody(self) -> None:
        """``"system"`` is not an account; it must not resolve to one."""
        from src.infrastructure.llm.usage_guard import enforce_usage_limit

        checked: list[object] = []
        with (
            patch(
                "src.domains.usage_limits.service.UsageLimitService.check_user_allowed",
                AsyncMock(side_effect=lambda uid: checked.append(uid)),
            ),
        ):
            await enforce_usage_limit("system", layer="structured_output")

        assert checked == []

    async def test_the_gate_never_reads_the_feature_flag_itself(self) -> None:
        """``usage_limits_enabled`` bounds what ONE account consumes; what the
        INSTANCE spends is a different protection, and ``check_user_allowed``
        deliberately keeps it outside that flag.

        This gate used to read the flag and return immediately, which switched
        off the instance ceiling with it: an operator who set a daily budget
        while leaving per-user limits off enforced nothing here, although the
        chat router enforced it. So the gate reads no flag at all now — it
        always asks, and the one implementation that owns the flag applies it.
        The structural half of the assertion matters as much as the
        behavioural one: reintroducing a settings read here would restore the
        defect while every behavioural test kept passing.
        """
        import src.infrastructure.llm.usage_guard as guard_module
        from src.infrastructure.llm.usage_guard import enforce_usage_limit

        assert not hasattr(guard_module, "settings"), (
            "the shared gate imported settings again — the only thing it ever "
            "used them for was a short-circuit that also disabled the instance "
            "ceiling"
        )

        consulted: list[object] = []
        with patch(
            "src.domains.usage_limits.service.UsageLimitService.check_user_allowed",
            AsyncMock(side_effect=lambda uid: consulted.append(uid) or _allowed()),
        ):
            await enforce_usage_limit(str(uuid.uuid4()), layer="structured_output")

        assert consulted, "the gate returned without asking any ceiling"

    async def test_an_allowed_account_passes_through(self) -> None:
        from src.domains.usage_limits.schemas import UsageLimitStatus
        from src.domains.usage_limits.service import UsageLimitCheckResult
        from src.infrastructure.llm.usage_guard import enforce_usage_limit

        allowed = UsageLimitCheckResult(
            allowed=True, status=UsageLimitStatus.OK, blocked_reason=None, exceeded_limit=None
        )
        with (
            patch(
                "src.domains.usage_limits.service.UsageLimitService.check_user_allowed",
                AsyncMock(return_value=allowed),
            ),
        ):
            await enforce_usage_limit(str(uuid.uuid4()), layer="structured_output")


class TestWhoTheCallBelongsTo:
    """``resolve_owner`` decides who is billed, and who is never refused.

    Every branch here answers « whose ceiling applies? ». A resolution that
    silently returns None turns an enforced ceiling into no ceiling at all —
    the guard would run, find nobody, and let the call through — which is the
    exact failure mode this whole programme exists to close. It was the least
    covered part of the guard when measured on 2026-09-07.
    """

    def test_an_explicit_owner_wins(self) -> None:
        from src.infrastructure.llm.usage_guard import resolve_owner

        owner = uuid.uuid4()
        assert resolve_owner(owner) == owner

    def test_a_uuid_passed_as_text_is_accepted(self) -> None:
        from src.infrastructure.llm.usage_guard import resolve_owner

        owner = uuid.uuid4()
        assert resolve_owner(str(owner)) == owner

    def test_the_graph_state_answers_when_the_caller_does_not(self) -> None:
        """A node deep in the graph is handed a state, never a user id."""
        from src.infrastructure.llm.usage_guard import resolve_owner

        owner = uuid.uuid4()
        with patch(
            "src.infrastructure.llm.usage_guard.extract_session_user_from_state",
            return_value=(None, str(owner)),
        ):
            assert resolve_owner(None, {"messages": []}) == owner

    def test_the_run_config_answers_last(self) -> None:
        from src.core.field_names import FIELD_USER_ID
        from src.infrastructure.llm.usage_guard import resolve_owner

        owner = uuid.uuid4()
        assert resolve_owner(None, None, {"metadata": {FIELD_USER_ID: str(owner)}}) == owner

    def test_a_config_without_metadata_resolves_nobody_rather_than_raising(self) -> None:
        from src.infrastructure.llm.usage_guard import resolve_owner

        assert resolve_owner(None, None, {}) is None
        assert resolve_owner(None, None, object()) is None

    def test_the_state_is_consulted_before_the_config(self) -> None:
        """Declared order, and the only one where the two can disagree."""
        from src.core.field_names import FIELD_USER_ID
        from src.infrastructure.llm.usage_guard import resolve_owner

        from_state = uuid.uuid4()
        from_config = uuid.uuid4()
        with patch(
            "src.infrastructure.llm.usage_guard.extract_session_user_from_state",
            return_value=(None, str(from_state)),
        ):
            resolved = resolve_owner(
                None, {"messages": []}, {"metadata": {FIELD_USER_ID: str(from_config)}}
            )
        assert resolved == from_state

    def test_the_system_placeholder_is_not_an_account(self) -> None:
        """Resolving it would look up a ceiling for a user that does not exist."""
        from src.infrastructure.llm.usage_guard import resolve_owner

        assert resolve_owner("system") is None

    def test_something_that_is_not_an_identifier_resolves_to_nobody(self) -> None:
        """Never an exception: a malformed id must not take the call down."""
        from src.infrastructure.llm.usage_guard import resolve_owner

        assert resolve_owner("not-a-uuid") is None

    def test_nothing_at_all_resolves_to_nobody(self) -> None:
        from src.infrastructure.llm.usage_guard import resolve_owner

        assert resolve_owner(None, None, None) is None


def _allowed():
    from src.domains.usage_limits.schemas import UsageLimitStatus
    from src.domains.usage_limits.service import UsageLimitCheckResult

    return UsageLimitCheckResult(
        allowed=True, status=UsageLimitStatus.OK, blocked_reason=None, exceeded_limit=None
    )


def _instance_blocked():
    from src.domains.usage_limits.schemas import UsageLimitStatus
    from src.domains.usage_limits.service import UsageLimitCheckResult

    return UsageLimitCheckResult(
        allowed=False,
        status=UsageLimitStatus.BLOCKED_INSTANCE_BUDGET,
        blocked_reason="instance daily budget exhausted",
        exceeded_limit="instance_daily_budget",
    )


class TestBothCeilingsApply:
    """Every euro this platform spends on a model is paid with the deployment's
    own provider key (``cost_bearers``: the ``llm`` family bears
    ``CostBearer.INSTANCE``). So a model call answers to BOTH bounds — what one
    account may consume, and what the whole deployment may spend in a day —
    and only what a person pays with their OWN connector key is exempt.
    """

    async def test_an_ownerless_call_still_answers_to_the_instance_ceiling(self) -> None:
        from src.core.exceptions import UsageLimitExceededError
        from src.infrastructure.llm.usage_guard import enforce_usage_limit

        with (
            patch(
                "src.domains.usage_limits.service.UsageLimitService.instance_budget_block",
                AsyncMock(return_value=_instance_blocked()),
            ),
            pytest.raises(UsageLimitExceededError),
        ):
            await enforce_usage_limit(None, layer="structured_output")

    async def test_an_ownerless_call_passes_when_the_instance_may_spend(self) -> None:
        from src.infrastructure.llm.usage_guard import enforce_usage_limit

        with (
            patch(
                "src.domains.usage_limits.service.UsageLimitService.instance_budget_block",
                AsyncMock(return_value=None),
            ),
        ):
            await enforce_usage_limit(None, layer="structured_output")

    async def test_an_instance_pause_says_so_and_says_when_it_lifts(self) -> None:
        """The chat router already answered an instance pause with a stable
        error code and a computable ``retry_after``; the shared gate answered
        with neither. One rule, one answer — whichever door refused."""
        from src.core.constants import INSTANCE_BUDGET_EXHAUSTED_ERROR_CODE
        from src.core.exceptions import UsageLimitExceededError
        from src.infrastructure.llm.usage_guard import enforce_usage_limit

        with (
            patch(
                "src.domains.usage_limits.service.UsageLimitService.instance_budget_block",
                AsyncMock(return_value=_instance_blocked()),
            ),
            pytest.raises(UsageLimitExceededError) as raised,
        ):
            await enforce_usage_limit(None, layer="structured_output")

        detail = raised.value.detail
        payload = detail if isinstance(detail, dict) else {}
        assert payload.get("error_code") == INSTANCE_BUDGET_EXHAUSTED_ERROR_CODE
        assert raised.value.headers and "Retry-After" in raised.value.headers
