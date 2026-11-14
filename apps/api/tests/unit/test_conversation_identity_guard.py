"""Runtime plumbing never becomes a business FK or business conversation argument.

The scan follows local aliases of runtime reads to their consumers. Explicit
exceptions name actual non-business consumers, with a reason; stale exceptions
fail. Behavioral tests with distinct account/business/runtime UUIDs complement
this syntactic guard, which cannot prove arbitrary interprocedural dataflow.
"""

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
SRC = Path(__file__).parents[2] / "src"
RUNTIME_NAMES = {"thread_id", "runtime_id", "delivery_runtime_id"}
RUNTIME_KEYS = {"thread_id", "runtime_id", "FIELD_THREAD_ID", "FIELD_RUNTIME_ID"}

# Historical parameter spelling at these ephemeral, non-FK doors. No business
# repository or accounting collector is exempt. A new consumer needs review.
RUNTIME_CONSUMERS: dict[tuple[str, str], str] = {
    (
        "domains/agents/telephony/live_tools.py",
        "LiaRuntimeContext",
    ): "Direct voice contexts declare no bound runtime or business conversation.",
    (
        "domains/agents/tools/image_generation_tools.py",
        "store_pending_image",
    ): "Transient SSE card queue, drained by the exact root runtime.",
}
BUSINESS_PARSERS = {
    "domains/agents/interactive_page/page_sources.py": "Explicit conversation history lookup.",
    "domains/agents/tools/image_generation_tools.py": "Caller.source_conversation_id projection.",
    "domains/document_generation/service.py": "Nullable business provenance from its caller.",
    "domains/skills/command_outputs.py": "Nullable business provenance from the typed context.",
}


def _key(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return node.id if isinstance(node, ast.Name) else None


def _runtime_value(node: ast.AST, aliases: set[str]) -> bool:
    if isinstance(node, ast.Name) and node.id in aliases:
        return True
    if isinstance(node, ast.Attribute) and node.attr in RUNTIME_NAMES:
        return True
    if isinstance(node, ast.Subscript) and _key(node.slice) in RUNTIME_KEYS:
        return True
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and node.args
        and _key(node.args[0]) in RUNTIME_KEYS
    ):
        return True
    return any(_runtime_value(child, aliases) for child in ast.iter_child_nodes(node))


def _call_name(call: ast.Call) -> str:
    if isinstance(call.func, ast.Name):
        return call.func.id
    return call.func.attr if isinstance(call.func, ast.Attribute) else "<dynamic>"


def _parser_names(tree: ast.AST) -> set[str]:
    """Follow direct imports and their explicit aliases."""
    parsers = {"conversation_uuid"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            parsers.update(
                alias.asname or alias.name
                for alias in node.names
                if alias.name == "conversation_uuid"
            )
    return parsers


def _local_runtime_aliases(function: ast.AST) -> set[str]:
    """Reach a fixed point so a copied local cannot conceal the runtime read."""
    aliases = set(RUNTIME_NAMES)
    assignments = [
        node
        for node in ast.walk(function)
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr))
    ]
    while True:
        before = len(aliases)
        for node in assignments:
            value = node.value
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if value is not None and _runtime_value(value, aliases):
                aliases.update(target.id for target in targets if isinstance(target, ast.Name))
        if len(aliases) == before:
            return aliases


def _sink_name(node: ast.AST, aliases: set[str], parsers: set[str]) -> str | None:
    """Read the value supplied to a business consumer, not its variable spelling."""
    if isinstance(node, ast.Call):
        name = _call_name(node)
        values = [kw.value for kw in node.keywords if kw.arg == "conversation_id"]
        if name in parsers:
            values.extend(node.args)
        if any(_runtime_value(value, aliases) for value in values):
            return name
    if isinstance(node, ast.Dict):
        for key, value in zip(node.keys, node.values, strict=True):
            if key is None or _key(key) not in {"conversation_id", "FIELD_CONVERSATION_ID"}:
                continue
            if _runtime_value(value, aliases):
                return "<business-metadata>"
    return None


def _runtime_business_sinks(source: str) -> set[str]:
    tree = ast.parse(source)
    parsers = _parser_names(tree)
    found: set[str] = set()
    for function in ast.walk(tree):
        if isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            aliases = _local_runtime_aliases(function)
            for node in ast.walk(function):
                if (name := _sink_name(node, aliases, parsers)) is not None:
                    found.add(name)
    return found


def test_every_runtime_business_sink_is_a_declared_non_business_consumer() -> None:
    files = list(SRC.rglob("*.py"))
    assert len(files) > 1000, "The guard must actually walk the production source tree"
    found = {
        (path.relative_to(SRC).as_posix(), name)
        for path in files
        for name in _runtime_business_sinks(path.read_text(encoding="utf-8"))
    }
    assert found == RUNTIME_CONSUMERS.keys(), {
        "unreviewed": sorted(found - RUNTIME_CONSUMERS.keys()),
        "stale": sorted(RUNTIME_CONSUMERS.keys() - found),
    }
    assert all(RUNTIME_CONSUMERS.values())


def test_every_business_uuid_parser_caller_is_declared() -> None:
    found: set[str] = set()
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        aliases = _parser_names(tree)
        if any(
            isinstance(node, ast.Call) and _call_name(node) in aliases for node in ast.walk(tree)
        ):
            found.add(path.relative_to(SRC).as_posix())
    assert found == BUSINESS_PARSERS.keys()
    assert all(BUSINESS_PARSERS.values())


@pytest.mark.parametrize(
    "read",
    [
        'config["configurable"]["thread_id"]',
        'config.get("configurable", {}).get(FIELD_THREAD_ID)',
        "context.runtime_id",
        "context.thread_id",
        "context.delivery_runtime_id",
    ],
)
def test_a_new_alias_cannot_hide_a_runtime_in_a_business_write(read: str) -> None:
    source = f"""
from src.domains.attachments.thread_id import conversation_uuid as parse_business
def bad(config, context):
    raw = {read}
    copied = str(raw)
    repo.create(conversation_id=UUID(copied))
    parse_business(copied)
    return {{FIELD_CONVERSATION_ID: copied}}
"""
    assert _runtime_business_sinks(source) == {"create", "parse_business", "<business-metadata>"}


def test_business_source_and_runtime_session_remain_independent() -> None:
    assert not _runtime_business_sinks("""
def good(context):
    technical = context.thread_id
    source = context.source_conversation_id
    return retrieve(conversation_id=source, session_id=technical)
""")
