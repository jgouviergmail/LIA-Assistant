"""Every Makefile target delegates to Task, or is a documented Make-only one (F022).

The Makefile is a thin compatibility shim over Task (the canonical build
interface). A target that re-implements a Task command instead of delegating
re-introduces the multiple-contracts divergence the audit flagged. This guard
parses the Makefile and asserts each target's recipe either invokes ``task ...``
or the target is in the explicit, documented Make-only allowlist below — so a new
divergent target fails CI, and the Make-only set stays intentional and reviewed.
"""

from __future__ import annotations

import re

from tests._repo_paths import repo_root_or_skip

MAKEFILE = repo_root_or_skip() / "Makefile"

# Intentionally Make-only: raw docker/rm/bash conveniences with NO Task
# equivalent. Keep in sync with the "Make-only conveniences" Makefile section.
_MAKE_ONLY = {
    "dev-rebuild",
    "prod-down",
    "prod-logs",
    "clean",
    "clean-models",
    "download-models",
    "prune",
    "shell-web",
    "help",
}


def _targets_and_recipes(text: str) -> dict[str, list[str]]:
    """Map each Makefile target to its list of recipe (tab-indented) lines."""
    targets: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        if line.startswith("\t"):  # recipe line for the current target
            if current is not None:
                targets[current].append(line.strip())
            continue
        m = re.match(r"^([a-z][a-z0-9_-]*)\s*:", line)
        if m and not line.startswith("."):  # a target (not .PHONY / .DEFAULT_GOAL)
            current = m.group(1)
            targets.setdefault(current, [])
        else:
            current = None
    return targets


def test_makefile_targets_delegate_or_are_documented_make_only() -> None:
    assert MAKEFILE.is_file(), "Makefile not found at repo root"
    targets = _targets_and_recipes(MAKEFILE.read_text(encoding="utf-8"))
    assert targets, "no Makefile targets parsed — parser regressed"

    offenders = []
    for target, recipe in targets.items():
        if target in _MAKE_ONLY:
            continue
        if not recipe:
            continue  # alias target (e.g. `dev: dev-up`) — delegates via its dep
        if not any(re.search(r"(^|\s)task\s", line) for line in recipe):
            offenders.append(f"{target}: {recipe}")

    assert not offenders, (
        "Makefile target(s) neither delegate to `task` nor are in the documented "
        "Make-only allowlist (F022) — delegate to the matching Task target or add "
        f"a justified Make-only entry: {offenders}"
    )


def test_make_only_allowlist_has_no_stale_entries() -> None:
    """Every allowlisted Make-only target must still exist (shrink-only)."""
    targets = set(_targets_and_recipes(MAKEFILE.read_text(encoding="utf-8")))
    stale = _MAKE_ONLY - targets
    assert not stale, f"Make-only allowlist references removed targets: {sorted(stale)}"
