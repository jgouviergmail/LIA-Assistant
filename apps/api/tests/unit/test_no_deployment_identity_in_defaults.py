"""Configuration defaults must not carry one deployment's identity.

LIA is open source: a fresh clone has to work. A default that names a real
host, address or account does not configure the software, it configures ONE
installation of it — and everybody else inherits a value that is wrong for
them, usually silently.

This guard was earned. Aligning code defaults on a production env file
(2026-08-06) moved `session_cookie_domain` from None to a real domain. Two
consequences, neither visible in any test that existed:

- every instance not on that domain lost authentication entirely — the
  browser drops a cookie whose `Domain` does not match, so sign-in "worked"
  and the next request was anonymous;
- a parent domain is shared with every sibling host, so a throwaway public
  demonstrator would have handed its sessions to the main instance.

Deployment identity belongs in env files, host by host.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

CONFIG_DIR = Path(__file__).resolve().parents[2] / "src" / "core" / "config"
CONSTANTS = Path(__file__).resolve().parents[2] / "src" / "core" / "constants.py"

#: A default that looks like somebody's actual deployment.
_IDENTITY_PATTERNS = (
    # A real hostname: at least two labels, a public-looking TLD, and not one
    # of the placeholder domains reserved exactly for documentation.
    re.compile(r"\b[a-z0-9-]+\.(?:com|net|org|fr|io|dev|app|cloud)\b", re.IGNORECASE),
    # A private network address, i.e. someone's LAN.
    re.compile(r"\b(?:10|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b"),
    # An email address.
    re.compile(r"\b[\w.+-]+@[\w-]+\.[a-z]{2,}\b", re.IGNORECASE),
)

#: Values that LOOK like identity but name a public service the software
#: talks to, or a documentation placeholder. Each stays because removing it
#: would break the default it belongs to.
_ALLOWED = re.compile(
    r"(?:"
    r"example\.(?:com|org|net)"  # RFC 2606 placeholders
    r"|localhost"
    r"|api\.(?:openai|anthropic|deepseek|perplexity|search\.brave)\.com"
    r"|generativelanguage\.googleapis\.com"
    r"|(?:[a-z0-9-]+\.)*googleapis\.com"
    r"|(?:[a-z0-9-]+\.)*google\.com"
    r"|(?:[a-z0-9-]+\.)*microsoft(?:online)?\.com"
    r"|(?:[a-z0-9-]+\.)*live\.com"
    r"|(?:[a-z0-9-]+\.)*apple\.com"
    r"|(?:[a-z0-9-]+\.)*icloud\.com"
    r"|(?:[a-z0-9-]+\.)*mail\.me\.com"  # Apple iCloud IMAP/SMTP hosts
    r"|(?:[a-z0-9-]+\.)*github\.com"
    r"|(?:[a-z0-9-]+\.)*wikipedia\.org"
    r"|(?:[a-z0-9-]+\.)*wikimedia\.org"
    r"|(?:[a-z0-9-]+\.)*openstreetmap\.org"
    r"|(?:[a-z0-9-]+\.)*open-meteo\.com"
    r"|(?:[a-z0-9-]+\.)*meethue\.com"
    r"|(?:[a-z0-9-]+\.)*elevenlabs\.io"
    r"|(?:[a-z0-9-]+\.)*ollama\.com"
    r"|(?:[a-z0-9-]+\.)*qwen\.ai"
    r"|(?:[a-z0-9-]+\.)*aliyuncs\.com"
    r"|(?:[a-z0-9-]+\.)*langfuse\.com"
    r"|(?:[a-z0-9-]+\.)*sentry\.io"
    r"|(?:[a-z0-9-]+\.)*schema\.org"
    r"|(?:[a-z0-9-]+\.)*w3\.org"
    r"|(?:[a-z0-9-]+\.)*python\.org"
    r"|(?:[a-z0-9-]+\.)*pydantic\.dev"
    r"|noreply@"
    r"|frankfurter\.dev"  # public exchange-rate API
    r"|excalidraw\.com"  # public MCP server in the sample config
    r"|agentskills\.io"  # the skills standard this implements
    r"|openweathermap\.org"  # public weather API
    r"|lia-assistant\.com"  # the project's generic sender, not a host
    r")",
    re.IGNORECASE,
)


def _default_values(path: Path) -> list[tuple[int, str]]:
    """String values that are actually USED as defaults.

    Docstrings, `description=` texts and doctest examples are prose: naming
    `smtp.gmail.com` while explaining a format configures nothing. Only what
    the software would really run with is measured here — `Field(default=...)`,
    `Field(<positional>)` and module-level constants.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    values: list[tuple[int, str]] = []

    def _collect(node: ast.AST) -> None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            values.append((node.lineno, node.value))
        elif isinstance(node, (ast.List, ast.Tuple, ast.Set, ast.Dict)):
            for child in ast.iter_child_nodes(node):
                _collect(child)

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "Field":
            for keyword in node.keywords:
                if keyword.arg == "default":
                    _collect(keyword.value)
            for positional in node.args:
                _collect(positional)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if all(isinstance(t, ast.Name) and t.id.isupper() for t in targets):
                _collect(node.value)
    return values


def _offenders(path: Path) -> list[str]:
    offenders = []
    for lineno, value in _default_values(path):
        remaining = _ALLOWED.sub("", value)
        for pattern in _IDENTITY_PATTERNS:
            match = pattern.search(remaining)
            if match:
                offenders.append(f"{path.name}:{lineno}: {match.group(0)!r} in {value[:60]!r}")
                break
    return offenders


def test_config_defaults_carry_no_deployment_identity() -> None:
    offenders: list[str] = []
    for path in sorted(CONFIG_DIR.glob("*.py")):
        offenders.extend(_offenders(path))
    assert not offenders, (
        "configuration defaults name a real deployment:\n"
        + "\n".join(offenders)
        + "\n\nPut it in the env file: a default that names one host is wrong "
        "for every other, and a fresh clone must work."
    )


def test_constants_carry_no_deployment_identity() -> None:
    offenders = _offenders(CONSTANTS)
    assert not offenders, "constants name a real deployment:\n" + "\n".join(offenders)
