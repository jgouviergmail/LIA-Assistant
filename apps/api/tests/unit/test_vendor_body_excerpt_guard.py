"""Guard: a vendor's response body never leaves an HTTP client as an excerpt (ADR-317).

A refused body may quote the request — the line being voiced, the words being
transcribed, the place searched — so an error, or a log line above DEBUG,
carries the refusal's facts (its status, the vendor's bounded code), never a
slice of its text. Measured on 2026-10-14: the ElevenLabs and OpenAI
transcription clients put up to 512 characters of the vendor's answer in their
errors, the ElevenLabs speech client and voice listing 200 in their messages,
while a FastAPI-style 422 echoes the very field it refused, the text included.
Those clients now read their refusals through ``domains/voice/vendor_refusal.py``
(ADR-345).

The scan reads every module of ``src`` that imports an HTTP client (httpx,
aiohttp) and refuses a SLICE of a ``.text`` — read directly
(``response.text[:200]``) or through the local it was bound to
(``detail = response.text`` then ``detail[:200]``). A slice handed to a DEBUG
line passes: contents are allowed there. What it does not see: a body
interpolated WHOLE (``f"… {response.text}"``) — in these modules a ``.text`` is
also an XML element's or a result's, and read whole it cannot be told from them
without types.

There is no remaining allowance: every HTTP client must keep the vendor's
words out of public failures and operational log levels.
"""

from __future__ import annotations

import ast
from functools import cache
from pathlib import Path

import pytest

from tests._ast_bindings import binding

pytestmark = pytest.mark.unit

SRC = Path(__file__).resolve().parents[2] / "src"

_HTTP_CLIENTS = frozenset({"httpx", "aiohttp"})


def _imports_an_http_client(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(
            alias.name.split(".")[0] in _HTTP_CLIENTS for alias in node.names
        ):
            return True
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] in _HTTP_CLIENTS:
            return True
    return False


def _is_body(node: ast.expr) -> bool:
    """``x.text`` (httpx), or ``await x.text()`` (aiohttp)."""
    if isinstance(node, ast.Attribute):
        return node.attr == "text"
    return (
        isinstance(node, ast.Await)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Attribute)
        and node.value.func.attr == "text"
    )


def _debug_nodes(tree: ast.AST) -> set[int]:
    """Every node inside the arguments of a DEBUG line, where contents are allowed."""
    inside: set[int] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "debug"
        ):
            for argument in [*node.args, *(keyword.value for keyword in node.keywords)]:
                inside.update(id(child) for child in ast.walk(argument))
    return inside


def excerpts(source: str) -> list[int]:
    """The lines of every body excerpt of a module, DEBUG lines excepted.

    Args:
        source: A module's source.

    Returns:
        The line of each slice of a response body, in source order; none when
        the module imports no HTTP client.
    """
    tree = ast.parse(source)
    if not _imports_an_http_client(tree):
        return []
    aliases = {
        name for name, value in filter(None, map(binding, ast.walk(tree))) if _is_body(value)
    }
    allowed = _debug_nodes(tree)
    return sorted(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Subscript)
        and isinstance(node.slice, ast.Slice)
        and (
            _is_body(node.value) or (isinstance(node.value, ast.Name) and node.value.id in aliases)
        )
        and id(node) not in allowed
    )


@cache
def _measured() -> dict[str, list[int]]:
    found: dict[str, list[int]] = {}
    for path in sorted(SRC.rglob("*.py")):
        if lines := excerpts(path.read_text(encoding="utf-8")):
            found[path.relative_to(SRC).as_posix()] = lines
    return found


def test_no_new_module_slices_a_vendor_body() -> None:
    unexpected = _measured()
    listing = "\n".join(f"  {module}: lines {lines}" for module, lines in unexpected.items())
    assert not unexpected, (
        "A vendor's body leaves these clients as an excerpt — carry the refusal's facts "
        f"instead (domains/voice/vendor_refusal.py), or move the line to DEBUG:\n{listing}"
    )


class TestTheScanItself:
    def test_a_direct_slice_is_found(self) -> None:
        source = "import httpx\ndef f(response):\n    raise ValueError(response.text[:512])\n"
        assert excerpts(source) == [3]

    def test_the_local_a_body_was_bound_to_is_followed(self) -> None:
        source = (
            "import httpx\n"
            "def f(response):\n"
            "    detail = response.text\n"
            "    raise ValueError(detail[:200])\n"
        )
        assert excerpts(source) == [4]

    def test_an_aiohttp_body_is_found(self) -> None:
        source = (
            "import aiohttp\n"
            "async def f(response):\n"
            "    raise ValueError((await response.text())[:200])\n"
        )
        assert excerpts(source) == [3]

    def test_a_debug_line_may_hold_an_excerpt(self) -> None:
        source = (
            "import httpx\n"
            "def f(response, logger):\n"
            "    logger.debug('step', body_preview=response.text[:500])\n"
            "    logger.warning('step', body_preview=response.text[:500])\n"
        )
        assert excerpts(source) == [4]

    def test_a_module_without_an_http_client_is_not_read(self) -> None:
        assert excerpts("def f(message):\n    return message.text[:50]\n") == []

    def test_a_slice_of_anything_else_passes(self) -> None:
        source = (
            "import httpx\ndef f(response):\n    return response.content[:4], str(response)[:9]\n"
        )
        assert excerpts(source) == []
