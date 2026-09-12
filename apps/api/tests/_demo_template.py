"""The demonstrator's env template, read as the declaration it is.

Two guards read it — the capability/egress coherence guard and the exposed
routes census — and neither may parse it on its own: two parsers of one file
disagree the day someone adds a quoted value. The template is the DEV one:
the production template must carry the same capability flags, which the
coherence guard asserts.
"""

from __future__ import annotations

from pathlib import Path

from tests._repo_paths import repo_root_or_skip

DEV_TEMPLATE = repo_root_or_skip() / ".env.demo-instance.example"
PROD_TEMPLATE = repo_root_or_skip() / ".env.demo-instance.prod.example"


def template_flags(path: Path = DEV_TEMPLATE) -> dict[str, str]:
    """Every ``KEY=value`` the template declares, comments and blanks skipped."""
    flags: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        flags[key.strip()] = value.strip()
    return flags


def capability_flags(path: Path = DEV_TEMPLATE) -> dict[str, bool]:
    """The ``*_ENABLED`` ceilings the template declares, as booleans."""
    return {
        key: value.lower() == "true"
        for key, value in template_flags(path).items()
        if key.endswith("_ENABLED")
    }
