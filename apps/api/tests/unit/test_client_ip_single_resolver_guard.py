"""Who is calling has ONE answer: ``core.client_ip.resolve_client_ip`` (ADR-213).

ADR-213 moved the rate limiters and the GeoIP enrichment onto the header the
caller cannot write, and nothing held the rest of the code to it. On 2026-09-23
twenty-one sites still read the connection peer, ``request.client.host``:

- every admin audit row. uvicorn runs with ``--proxy-headers
  --forwarded-allow-ips "*"``, so that peer is the LEFTMOST ``X-Forwarded-For``
  entry, the one the visitor writes. Behind a Next.js server action, it is the
  web container itself: the audit of the 2026-09-22 account deactivation
  recorded ``172.18.0.19``, the address of ``lia-web-prod``;
- the address a new session records for the devices view;
- a public rate-limit bucket that parsed ``X-Forwarded-For`` by hand and keyed
  on its leftmost entry, the exact bypass ADR-213 measured and closed
  elsewhere.

The scan reads code, not prose: docstrings may still NAME the header.
"""

import ast
from pathlib import Path

import pytest

SRC_DIR = Path(__file__).parents[2] / "src"

#: The resolver itself is the one place allowed to read the peer.
RESOLVER_FILES: frozenset[str] = frozenset({"core/client_ip.py"})

_FORWARDED_HEADER = "x-forwarded-for"


def _is_forwarded_header(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.lower() == _FORWARDED_HEADER
    )


def _iter_caller_address_reads(tree: ast.AST):
    """Yield ``(lineno, shape)`` for every read of the caller's address.

    Two shapes: the connection peer (``<anything>.client.host``) and a hand
    parse of ``X-Forwarded-For`` (a call or a subscript given that name).
    """
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and node.attr == "host"
            and isinstance(node.value, ast.Attribute)
            and node.value.attr == "client"
        ):
            yield node.lineno, ast.unparse(node)
        elif isinstance(node, ast.Call) and any(_is_forwarded_header(a) for a in node.args):
            yield node.lineno, ast.unparse(node)
        elif isinstance(node, ast.Subscript) and _is_forwarded_header(node.slice):
            yield node.lineno, ast.unparse(node)


class TestCallerAddressScan:
    """Sanity checks on the scan itself (a guard that cannot see its own examples
    guards nothing)."""

    def test_scan_detects_every_shape(self) -> None:
        snippet = (
            "a = request.client.host if request.client else None\n"
            "b = websocket.client.host\n"
            "c = request.headers.get('X-Forwarded-For', '')\n"
            "d = request.headers['x-forwarded-for']\n"
        )
        found = sorted(line for line, _ in _iter_caller_address_reads(ast.parse(snippet)))
        assert found == [1, 2, 3, 4], (
            f"The caller-address scan no longer detects its synthetic shapes (found lines "
            f"{found}, expected [1, 2, 3, 4]): fix it before trusting it."
        )

    def test_scan_ignores_the_resolver_and_prose(self) -> None:
        snippet = (
            '"""Cloudflare APPENDS to X-Forwarded-For; uvicorn keeps the leftmost."""\n'
            "ip = resolve_client_ip(request)\n"
            "name = settings.redis.hostname\n"
        )
        assert list(_iter_caller_address_reads(ast.parse(snippet))) == []


class TestOneAnswerToWhoIsCalling:
    """CI guard: outside the resolver, nothing in src/ reads the caller's address."""

    def test_no_module_reads_the_caller_address_itself(self) -> None:
        violations: list[str] = []
        for py_file in sorted(SRC_DIR.rglob("*.py")):
            rel_path = py_file.relative_to(SRC_DIR).as_posix()
            if rel_path in RESOLVER_FILES:
                continue
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            for lineno, shape in sorted(_iter_caller_address_reads(tree)):
                violations.append(f"src/{rel_path}:{lineno} — {shape}")

        if violations:
            pytest.fail(
                "The caller's address is read outside core/client_ip.py. Call "
                "resolve_client_ip(request): the peer is a proxy or a value the "
                "visitor chose (ADR-213, this module's docstring):\n"
                + "\n".join(f"  - {v}" for v in violations)
            )
