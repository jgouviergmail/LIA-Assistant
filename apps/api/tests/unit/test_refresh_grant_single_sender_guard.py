"""ONE module exchanges a connector's refresh token: ``connectors/oauth_refresh_exchange.py``.

Four paths used to POST ``grant_type=refresh_token`` for a connector, each with its own
reading of the answer, and only one of them under a lock (audit AC-029). Two refreshes
of one token in flight are a hazard, not a waste: a provider that rotates its refresh
token answers the second one ``invalid_grant``, and that refusal disconnected a person
whose consent was intact. Every refresh now goes through the one door, and this guard
refuses a fifth sender — in any of the three shapes a token request is written in: a
form dict, a keyword argument, an encoded body.

An exception names its reason, and an exception that no longer sends is refused too.
"""

from __future__ import annotations

import ast
from functools import cache
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

_SRC = Path(__file__).resolve().parents[2] / "src"
_THE_SENDER = "domains/connectors/oauth_refresh_exchange.py"

#: Senders that are not a connector's, each with why it may stay outside the door.
_EXCEPTIONS: dict[str, str] = {
    "infrastructure/mcp/auth.py": (
        "the tokens of a third-party MCP server, refreshed under that server's own "
        "Redis lock: they belong to no connector and no grant the door holds"
    ),
}


def _is_text(node: ast.expr | None, value: str) -> bool:
    return isinstance(node, ast.Constant) and node.value == value


def refresh_grants_sent(tree: ast.AST) -> list[int]:
    """The lines of a module that send a refresh-token grant, in any written shape.

    Args:
        tree: The module's parsed source.

    Returns:
        Every line sending ``grant_type=refresh_token``, in source order.
    """
    lines: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            lines.extend(
                node.lineno
                for key, value in zip(node.keys, node.values, strict=True)
                if _is_text(key, "grant_type") and _is_text(value, "refresh_token")
            )
        elif isinstance(node, ast.keyword):
            if node.arg == "grant_type" and _is_text(node.value, "refresh_token"):
                lines.append(node.value.lineno)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if "grant_type=refresh_token" in node.value:
                lines.append(node.lineno)
    return sorted(lines)


@cache
def _senders() -> dict[str, tuple[int, ...]]:
    """Every sending module of ``src`` and its lines, scanned once per run."""
    found: dict[str, tuple[int, ...]] = {}
    for path in sorted(_SRC.rglob("*.py")):
        lines = refresh_grants_sent(ast.parse(path.read_text(encoding="utf-8")))
        if lines:
            found[path.relative_to(_SRC).as_posix()] = tuple(lines)
    return found


def test_only_the_refresh_door_exchanges_a_refresh_token() -> None:
    strangers = {
        module: lines
        for module, lines in _senders().items()
        if module != _THE_SENDER and module not in _EXCEPTIONS
    }

    assert not strangers, (
        "a module sends grant_type=refresh_token outside the one refresh door "
        f"(route it through connectors/oauth_refresh.py): {strangers}"
    )


def test_the_door_itself_is_found() -> None:
    """The scan reads the right tree: the one sender must be seen sending."""
    assert _THE_SENDER in _senders()


def test_every_exception_still_sends_one() -> None:
    stale = sorted(set(_EXCEPTIONS) - set(_senders()))

    assert not stale, f"exceptions that no longer send a refresh grant — remove them: {stale}"


@pytest.mark.parametrize(
    ("source", "sends"),
    [
        ('form = {"grant_type": "refresh_token", "refresh_token": token}', True),
        ('client.fetch_token(url, grant_type="refresh_token")', True),
        ('body = "grant_type=refresh_token&refresh_token=" + token', True),
        ('form = {"grant_type": "authorization_code", "code": code}', False),
        ('metadata = {"grant_types": ["authorization_code", "refresh_token"]}', False),
    ],
    ids=["form", "keyword", "encoded", "another_grant", "registration_metadata"],
)
def test_every_written_shape_of_a_refresh_grant_is_seen(source: str, sends: bool) -> None:
    assert bool(refresh_grants_sent(ast.parse(source))) is sends
