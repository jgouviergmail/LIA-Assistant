"""Guard: a dispatch whose result nobody reads requires durability, or says why not (AC-003).

Why
---
``NotificationDispatcher.dispatch`` absorbs every channel failure and RETURNS its
verdict; it never raises. Five consumers wrote a durable « delivered » state without
reading that verdict: the telephony reaper, the call-return synthesis, the owner-call
relay, the peer message delivery and the diagnostics incident alert. A dispatch that
reached nobody was filed as delivered, and the reaper that exists to retry it never
saw it again (audit V13 AC-003, carried open by V14 and its revision).

``dispatch(..., require_durable=True)`` raises ``NotificationNotDelivered`` unless the
notification was archived, pushed or sent on an external channel — an SSE event
alone reaches an open tab or nobody (owner decision 2026-10-22). This guard holds the
rule over the whole tree: every ``dispatch`` whose result is discarded either requires
durability or is a declared best-effort notice, with the reason nothing durable
depends on it.
"""

from __future__ import annotations

import ast

import pytest

from tests._repo_paths import repo_root_or_skip

REPO_ROOT = repo_root_or_skip()
SRC = REPO_ROOT / "apps" / "api" / "src"

pytestmark = pytest.mark.unit

#: Best-effort notices: their result is discarded on purpose, and no durable state
#: is written from it.
BEST_EFFORT: dict[tuple[str, str], str] = {
    ("domains/meetings/processing.py", "_notify_ready"): (
        "The minutes live in the meeting row the moment it is ready; the notice is a "
        "convenience, and nothing records it as delivered."
    ),
    ("domains/peers/notifications.py", "dispatch_peer_events"): (
        "A notice of a connection event; the event itself is the connection's state, "
        "and one recipient's failure must not stop the others."
    ),
    ("infrastructure/scheduler/peer_message_delivery.py", "_notify_sender"): (
        "A notice to the SENDER; the delivery state is the recipient's, decided by "
        "the durable dispatch of the message itself."
    ),
    ("infrastructure/scheduler/phone_relay_runner.py", "_push_relay_ran"): (
        "A push and nothing else: the relayed turn already archived its rows in the chat."
    ),
    ("infrastructure/scheduler/scheduled_action_executor.py", "_send_approval_notification"): (
        "A proposal to run a routine: the next tick proposes again, nothing is filed."
    ),
    ("infrastructure/scheduler/voice_session_closing.py", "_notify_relay"): (
        "An SSE notice on the person's stream; the relayed rows are already in the chat."
    ),
}

#: Anti-vacuity: the five consumers that write a durable delivery state.
MIN_DURABLE_SITES = 5


def _builds_dispatcher(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "NotificationDispatcher"
    )


def _dispatcher_names(function: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    """Local names bound to ``NotificationDispatcher(...)``, whatever they are called."""
    names: set[str] = set()
    for node in ast.walk(function):
        if isinstance(node, ast.Assign) and _builds_dispatcher(node.value):
            names.update(target.id for target in node.targets if isinstance(target, ast.Name))
        elif (
            isinstance(node, ast.AnnAssign)
            and node.value is not None
            and _builds_dispatcher(node.value)
            and isinstance(node.target, ast.Name)
        ):
            names.add(node.target.id)
    return names


def _is_dispatcher(receiver: ast.expr, bound: set[str]) -> bool:
    if _builds_dispatcher(receiver):
        return True
    if isinstance(receiver, ast.Name) and receiver.id in bound:
        return True
    name = receiver.attr if isinstance(receiver, ast.Attribute) else getattr(receiver, "id", "")
    return "dispatcher" in name.lower()


def _requires_durable(call: ast.Call) -> bool:
    return any(
        keyword.arg == "require_durable"
        and isinstance(keyword.value, ast.Constant)
        and keyword.value.value is True
        for keyword in call.keywords
    )


def _discarded_in(tree: ast.Module) -> list[tuple[str, bool]]:
    """``(enclosing function, requires durability)`` per discarded dispatch of a module."""
    sites: list[tuple[str, bool]] = []
    for function in ast.walk(tree):
        if not isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        bound = _dispatcher_names(function)
        for node in ast.walk(function):
            if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Await)):
                continue
            call = node.value.value
            if (
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute)
                and call.func.attr == "dispatch"
                and _is_dispatcher(call.func.value, bound)
            ):
                sites.append((function.name, _requires_durable(call)))
    return sites


def _discarded_dispatches() -> list[tuple[str, str, bool]]:
    """``(module, enclosing function, requires durability)`` per discarded dispatch."""
    sites: list[tuple[str, str, bool]] = []
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        sites.extend((rel, function, durable) for function, durable in _discarded_in(tree))
    return sites


def test_every_discarded_dispatch_requires_durability_or_is_declared_best_effort() -> None:
    undeclared = [
        f"{module}::{function}"
        for module, function, durable in _discarded_dispatches()
        if not durable and (module, function) not in BEST_EFFORT
    ]

    assert not undeclared, (
        "these dispatches discard the verdict: pass require_durable=True when a durable "
        "state follows, or declare the notice best-effort with the reason:\n  "
        + "\n  ".join(undeclared)
    )


def test_a_best_effort_notice_never_requires_durability() -> None:
    """A site cannot be both: the declaration would hide a durable consumer."""
    both = [
        f"{module}::{function}"
        for module, function, durable in _discarded_dispatches()
        if durable and (module, function) in BEST_EFFORT
    ]
    assert not both


def test_every_best_effort_entry_still_names_a_site() -> None:
    sites = {(module, function) for module, function, _durable in _discarded_dispatches()}
    stale = sorted(set(BEST_EFFORT) - sites)
    assert not stale, f"remove these entries, they name no dispatch any more: {stale}"
    for reason in BEST_EFFORT.values():
        assert reason.strip()


def test_the_scan_sees_the_durable_consumers() -> None:
    durable = [site for site in _discarded_dispatches() if site[2]]
    assert len(durable) >= MIN_DURABLE_SITES, durable


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            "async def f(db):\n"
            "    notifier = NotificationDispatcher()\n"
            "    await notifier.dispatch(user=1, db=db)\n",
            [("f", False)],
        ),
        (
            "async def f(db):\n"
            "    await NotificationDispatcher().dispatch(user=1, db=db, require_durable=True)\n",
            [("f", True)],
        ),
        (
            "async def f(self, db):\n    await self.dispatcher.dispatch(user=1, db=db)\n",
            [("f", False)],
        ),
        (
            "async def f(db):\n"
            "    result = await NotificationDispatcher().dispatch(user=1, db=db)\n"
            "    return result\n",
            [],
        ),
        ("async def f(queue):\n    await queue.dispatch(1)\n", []),
    ],
    ids=["any-name", "durable", "attribute", "result-read", "not-a-dispatcher"],
)
def test_the_scanner_recognises_a_dispatcher_whatever_it_is_called(
    source: str, expected: list[tuple[str, bool]]
) -> None:
    """A dispatcher is what ``NotificationDispatcher(...)`` built, not a word in a name."""
    assert _discarded_in(ast.parse(source)) == expected
