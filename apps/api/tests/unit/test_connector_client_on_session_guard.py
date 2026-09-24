"""No connector client is built on a ``ConnectorService`` bound to a session (ADR-304).

A client refreshes its OAuth token and invalidates its connector through the
service it was built with. Built on ``ConnectorService(db)``, those writes land
on ``db`` — so its owner had to keep the session, and its transaction, open for
as long as the client was used, provider calls included. That is the shape of
every ``idle in transaction`` measured in production on 2026-09-22 (11 to 330
seconds, the Drive push path pinned for 22 minutes).

A client is built on a ``ConnectorUnitOfWork`` instead: a
``DetachedConnectorService`` (or the door, ``connectors/active_client``) whose
units open, commit and release a session of their own, or the chat turn's
wrapper, whose units do the same. The credentials may still be READ on the
caller's session — only what the client is HANDED matters here.

The rule is exact, not a proxy: it names the constructor argument, so a job
that keeps a session and commits before each network call (the Drive folder
sync) is not flagged, and an allowlist would only be a list of defects.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SRC = Path(__file__).resolve().parents[2] / "src"

#: A connector client's constructor, or the registry's class held in a variable.
_CLIENT = re.compile(r"^[A-Z]\w*Client$")
_CLIENT_VARIABLES = frozenset({"client_class"})


def _name(func: ast.expr) -> str:
    if isinstance(func, ast.Name):
        return func.id
    return func.attr if isinstance(func, ast.Attribute) else ""


def _is_service_call(node: ast.expr) -> bool:
    return isinstance(node, ast.Call) and _name(node.func) == "ConnectorService"


def _clients_on_session_services(tree: ast.AST) -> list[tuple[int, str]]:
    """Every client handed ``ConnectorService(...)`` — directly or through a name."""
    found: list[tuple[int, str]] = []
    for function in ast.walk(tree):
        if not isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        service_names = {
            target.id
            for node in ast.walk(function)
            if isinstance(node, ast.Assign) and _is_service_call(node.value)
            for target in node.targets
            if isinstance(target, ast.Name)
        }
        for node in ast.walk(function):
            if not isinstance(node, ast.Call):
                continue
            name = _name(node.func)
            if not (_CLIENT.match(name) or name in _CLIENT_VARIABLES):
                continue
            handed = [*node.args, *(keyword.value for keyword in node.keywords)]
            if any(
                _is_service_call(arg) or (isinstance(arg, ast.Name) and arg.id in service_names)
                for arg in handed
            ):
                found.append((node.lineno, name))
    return found


def test_the_guard_sees_the_defect_it_names() -> None:
    """Both spellings of the defect are caught; a detached service is not."""
    through_a_name = ast.parse(
        "async def f(db, user_id, creds):\n"
        "    service = ConnectorService(db)\n"
        "    return GoogleDriveClient(user_id, creds, service)\n"
    )
    inline = ast.parse(
        "async def f(db, user_id, creds, client_class):\n"
        "    return client_class(user_id, creds, ConnectorService(db))\n"
    )
    detached = ast.parse(
        "async def f(db, user_id):\n"
        "    creds = await ConnectorService(db).get_connector_credentials(user_id, T)\n"
        "    return GoogleDriveClient(user_id, creds, DetachedConnectorService())\n"
    )
    assert _clients_on_session_services(through_a_name) == [(3, "GoogleDriveClient")]
    assert _clients_on_session_services(inline) == [(2, "client_class")]
    assert _clients_on_session_services(detached) == []


def test_no_connector_client_is_built_on_a_session_bound_service() -> None:
    offenders = {
        f"{path.relative_to(SRC).as_posix()}:{line}": name
        for path in sorted(SRC.rglob("*.py"))
        for line, name in _clients_on_session_services(ast.parse(path.read_text(encoding="utf-8")))
    }
    assert not offenders, (
        "a connector client built on ConnectorService(db) writes its token "
        "refreshes on db, so db — and its transaction — must stay open while the "
        "provider answers. Hand it a DetachedConnectorService, or open it through "
        f"connectors.active_client (ADR-304): {offenders}"
    )
