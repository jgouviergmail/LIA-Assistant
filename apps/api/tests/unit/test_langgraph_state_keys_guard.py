"""AST guard: a graph node may only write keys declared in ``MessagesState``.

LangGraph merges a node's returned dict into the state through the schema's
channels. A key that is NOT declared in the ``MessagesState`` TypedDict has no
channel, so it is **dropped without a word** — no exception, no warning, no
trace in the checkpoint. CLAUDE.md flags it as a recurring trap:

    "Any key a node writes must be declared in ``MessagesState`` — undeclared
     keys are silently dropped by LangGraph (recurring trap: writing an object
     'mirror' of a dict field under an undeclared key; only the declared dict
     survives the checkpoint)."

The symptom appears far from the cause: a downstream node reads the field, gets
``None``, and takes the degraded branch. Only a static check catches it before
production, because writing the key is legal Python and the value even exists —
right up to the moment the state is persisted.

Scope: functions named ``*_node`` under ``src/domains/agents/nodes/`` (the graph
node convention — every callable registered via ``graph.add_node``) whose
``state`` parameter is annotated with a state TypedDict. Private helpers that
merely receive the state and return a domain payload are not state updates and
are out of scope.
"""

from __future__ import annotations

import ast

import pytest

from src.domains.agents.models import AgentMessagesState, MessagesState
from tests._repo_paths import find_apps_api_root

pytestmark = pytest.mark.unit

NODES_DIR = find_apps_api_root() / "src/domains/agents/nodes"

# Union of every declared state channel: a node may legitimately be typed on
# MessagesState while the graph runs the agent-level schema.
DECLARED_KEYS: frozenset[str] = frozenset(MessagesState.__annotations__) | frozenset(
    AgentMessagesState.__annotations__
)

# LangGraph reserved channels a node may address explicitly.
RESERVED_KEYS: frozenset[str] = frozenset({"__end__", "__interrupt__", "goto", "update"})

ALLOWED_KEYS = DECLARED_KEYS | RESERVED_KEYS


def _is_state_node(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """True for a graph node: named ``*_node`` and taking an annotated ``state``."""
    if not fn.name.endswith("_node"):
        return False
    return any(
        arg.arg == "state"
        and arg.annotation is not None
        and "MessagesState" in ast.unparse(arg.annotation)
        for arg in fn.args.args
    )


def _returned_state_keys(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    """String keys of every dict literal the node returns.

    Nested function definitions are skipped: a closure inside a node returns its
    own payload, not a state update.
    """
    keys: set[str] = set()
    nested = {
        inner
        for node in ast.walk(fn)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node is not fn
        for inner in ast.walk(node)
    }

    for node in ast.walk(fn):
        if node in nested:
            continue
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict):
            keys.update(
                key.value
                for key in node.value.keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            )
    return keys


def _scan() -> dict[str, set[str]]:
    """Map ``module::node`` to the undeclared keys it writes."""
    offenders: dict[str, set[str]] = {}
    for path in sorted(NODES_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for fn in ast.walk(tree):
            if not isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef) or not _is_state_node(fn):
                continue
            if undeclared := _returned_state_keys(fn) - ALLOWED_KEYS:
                offenders[f"{path.name}::{fn.name}"] = undeclared
    return offenders


class TestLangGraphStateKeysGuard:
    """Every state update must land in a declared channel."""

    def test_no_node_writes_an_undeclared_state_key(self) -> None:
        offenders = _scan()

        assert not offenders, (
            "These graph nodes write state keys that MessagesState does not "
            "declare — LangGraph drops them silently at checkpoint time:\n"
            + "\n".join(f"  {where}: {sorted(keys)}" for where, keys in offenders.items())
        )

    def test_the_scan_actually_reaches_the_nodes(self) -> None:
        """Oracle: an empty scan must mean "no violation", not "nothing scanned"."""
        scanned = [
            fn.name
            for path in NODES_DIR.rglob("*.py")
            for fn in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            if isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef) and _is_state_node(fn)
        ]

        assert len(scanned) >= 10, f"only {len(scanned)} node functions found: {scanned}"
        assert "response_node" in scanned

    def test_guard_flags_an_undeclared_key(self) -> None:
        """Oracle for the detector itself."""
        module = ast.parse(
            "async def demo_node(state: MessagesState, config):\n"
            "    return {'metadata': {}, 'not_a_declared_channel': 1}\n"
        )
        fn = next(
            node
            for node in ast.walk(module)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        )

        assert _is_state_node(fn) is True
        assert _returned_state_keys(fn) - ALLOWED_KEYS == {"not_a_declared_channel"}

    def test_guard_ignores_a_private_helper(self) -> None:
        module = ast.parse("def _helper(state: MessagesState):\n    return {'anything': 1}\n")
        fn = next(
            node
            for node in ast.walk(module)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        )

        assert _is_state_node(fn) is False

    def test_guard_ignores_a_closure_payload(self) -> None:
        """A dict returned by an inner function is not a state update."""
        module = ast.parse(
            "async def demo_node(state: MessagesState):\n"
            "    def inner():\n"
            "        return {'inner_only_key': 1}\n"
            "    return {'metadata': inner()}\n"
        )
        fn = next(
            node
            for node in ast.walk(module)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == "demo_node"
        )

        assert _returned_state_keys(fn) - ALLOWED_KEYS == set()


class TestStateSchemaIntegrity:
    """The declared channels themselves must stay coherent."""

    def test_reducer_managed_fields_are_declared(self) -> None:
        from src.domains.agents.utils.state_mutation import REDUCER_MANAGED_FIELDS

        undeclared = sorted(REDUCER_MANAGED_FIELDS - DECLARED_KEYS)
        assert (
            not undeclared
        ), f"REDUCER_MANAGED_FIELDS names channels that no state schema declares: {undeclared}"

    def test_messages_channel_carries_the_truncating_reducer(self) -> None:
        """The truncation reducer is what bounds checkpoint size."""
        from src.domains.agents.models import add_messages_with_truncate

        annotation = MessagesState.__annotations__["messages"]
        assert add_messages_with_truncate in getattr(annotation, "__metadata__", ())

    def test_agent_state_schema_shares_the_same_reducer(self) -> None:
        from src.domains.agents.models import add_messages_with_truncate

        annotation = AgentMessagesState.__annotations__["messages"]
        assert add_messages_with_truncate in getattr(annotation, "__metadata__", ())
