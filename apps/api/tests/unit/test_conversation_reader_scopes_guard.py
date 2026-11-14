"""Every direct message reader declares its target scope as well as row visibility."""

import ast
from pathlib import Path

import pytest

from src.domains.conversations.message_readers import MESSAGE_READERS

pytestmark = pytest.mark.unit
SRC = Path(__file__).parents[2] / "src"


def test_each_message_reader_names_its_conversation_scope() -> None:
    for module, declaration in MESSAGE_READERS.items():
        assert getattr(declaration, "conversations", None), module


def _unwrap(node: ast.AST, assignments: dict[str, ast.AST]) -> ast.AST:
    """Follow local query/result aliases, bounded against recursive assignments."""
    visited: set[str] = set()
    while isinstance(node, (ast.Name, ast.Await)):
        if isinstance(node, ast.Await):
            node = node.value
        elif node.id in assignments and node.id not in visited:
            visited.add(node.id)
            node = assignments[node.id]
        else:
            break
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if node.func.attr in {"execute", "scalars"} and node.args:
            return _unwrap(node.args[0], assignments)
    return node


def _is_column(node: ast.AST, column: str) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "Conversation"
        and node.attr == column
    )


def _singleton_without_target(query: ast.AST) -> bool:
    root = query
    while isinstance(root, ast.Call) and isinstance(root.func, ast.Attribute):
        root = root.func.value
    if not (
        isinstance(root, ast.Call)
        and isinstance(root.func, ast.Name)
        and root.func.id == "select"
        and any(
            isinstance(arg, ast.Name) and arg.id == "Conversation" or _is_column(arg, "id")
            for arg in root.args
        )
    ):
        return False
    predicates = [
        arg
        for node in ast.walk(query)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "where"
        for arg in node.args
    ]
    columns = {
        column
        for predicate in predicates
        for node in ast.walk(predicate)
        if isinstance(node, ast.Compare) and isinstance(node.ops[0], ast.Eq)
        for column in ("user_id", "id", "kind")
        if _is_column(node.left, column)
    }
    return "user_id" in columns and not columns.intersection({"id", "kind"})


def _account_singletons(source: str) -> list[int]:
    """Catch a multi-discussion SELECT consumed as the historical singleton."""
    found: list[int] = []
    for function in ast.walk(ast.parse(source)):
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        assignments: dict[str, ast.AST] = {}
        for node in ast.walk(function):
            if isinstance(node, ast.Assign):
                assignments.update(
                    (target.id, node.value)
                    for target in node.targets
                    if isinstance(target, ast.Name)
                )
            elif (
                isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value
            ):
                assignments[node.target.id] = node.value
        for node in ast.walk(function):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"scalar_one_or_none", "scalar_one"}
                and _singleton_without_target(_unwrap(node.func.value, assignments))
            ):
                found.append(node.lineno)
    return found


@pytest.mark.parametrize(
    "target", ["", ", Conversation.id == identity", ", Conversation.kind == kind"]
)
def test_singleton_detector_reads_the_query_through_aliases(target: str) -> None:
    source = f"""
async def load(db, owner, identity, kind):
    query = select(Conversation.id).where(Conversation.user_id == owner{target})
    reply = await db.execute(query)
    copied = reply
    return copied.scalar_one_or_none()
"""
    assert bool(_account_singletons(source)) is (not target)


def test_an_owned_message_lookup_is_not_a_conversation_singleton() -> None:
    assert not _account_singletons("""
async def load(db, owner, message):
    query = select(ConversationMessage).where(
        ConversationMessage.id == message,
        ConversationMessage.conversation_id.in_(
            select(Conversation.id).where(Conversation.user_id == owner)))
    reply = await db.execute(query)
    return reply.scalar_one_or_none()
""")


def test_no_reader_reintroduces_the_account_singleton_assumption() -> None:
    paths = list(SRC.rglob("*.py"))
    assert len(paths) > 1000
    failures = {
        str(path.relative_to(SRC)): lines
        for path in paths
        if (lines := _account_singletons(path.read_text(encoding="utf-8")))
    }
    assert not failures
