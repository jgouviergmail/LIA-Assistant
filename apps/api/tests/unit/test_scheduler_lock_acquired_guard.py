"""Systemic guard for the ``SchedulerLock`` acquisition contract (audit class B).

``SchedulerLock.__aenter__`` returns the lock *object* (always truthy) and sets
``self.acquired`` to whether the Redis ``SET NX`` succeeded. The correct — and
overwhelmingly dominant — usage is::

    async with SchedulerLock(redis, job_id) as lock:
        if not lock.acquired:
            return  # another worker holds the lock; skip silently
        ...

Finding F032 (2026-07 consolidated audit): one job bound the context to a name
and tested that name's truthiness directly (``as acquired: if not acquired``),
making the skip branch dead code — every uvicorn worker ran the job
concurrently, duplicating LLM cost. The scheduler lock only prevents duplicate
execution if the caller actually reads ``.acquired``.

This guard enforces the single contract statically: every ``async with
SchedulerLock(...)`` must (a) bind the context to a name and (b) reference
``<name>.acquired`` somewhere in the ``with`` body. It is intentionally strict —
a scheduler lock that is never checked is always a bug, whether the branch is
dead (F032) or simply absent.

If a genuinely new pattern ever needs an exemption, add the file with a written
justification — do not weaken the scan. A self-check test guards it against rot.
"""

import ast
from pathlib import Path

import pytest

SRC_DIR = Path(__file__).parents[2] / "src"

# No SchedulerLock use is exempt today. Add entries only with a written
# justification of why the ``.acquired`` gate does not apply.
SCHEDULER_LOCK_GUARD_ALLOWED_FILES: set[str] = set()


def _is_scheduler_lock_call(node: ast.expr) -> bool:
    """True when ``node`` constructs a ``SchedulerLock`` (bare or attribute)."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "SchedulerLock"
    if isinstance(func, ast.Attribute):
        return func.attr == "SchedulerLock"
    return False


def _references_acquired(body: list[ast.stmt], name: str) -> bool:
    """True when ``<name>.acquired`` appears anywhere in ``body``."""
    for stmt in body:
        for sub in ast.walk(stmt):
            if (
                isinstance(sub, ast.Attribute)
                and sub.attr == "acquired"
                and isinstance(sub.value, ast.Name)
                and sub.value.id == name
            ):
                return True
    return False


def _violations_in_source(source: str, label: str) -> list[str]:
    """Return human-readable violations of the SchedulerLock contract in ``source``."""
    tree = ast.parse(source)
    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncWith):
            continue
        for item in node.items:
            if not _is_scheduler_lock_call(item.context_expr):
                continue
            var = item.optional_vars
            if not isinstance(var, ast.Name):
                violations.append(
                    f"{label}:{node.lineno} — SchedulerLock context is not bound "
                    "to a name (cannot gate on .acquired)"
                )
                continue
            if not _references_acquired(node.body, var.id):
                violations.append(
                    f"{label}:{node.lineno} — SchedulerLock bound as "
                    f"'{var.id}' but '{var.id}.acquired' is never checked in the "
                    "with body (skip branch would be dead — see F032)"
                )
    return violations


def _iter_src_files() -> list[Path]:
    return sorted(SRC_DIR.rglob("*.py"))


def test_all_scheduler_lock_uses_check_acquired():
    """Every ``async with SchedulerLock(...)`` in src/ must gate on ``.acquired``."""
    all_violations: list[str] = []
    for path in _iter_src_files():
        rel = path.relative_to(SRC_DIR).as_posix()
        if rel in SCHEDULER_LOCK_GUARD_ALLOWED_FILES:
            continue
        violations = _violations_in_source(path.read_text(encoding="utf-8"), rel)
        all_violations.extend(violations)

    assert not all_violations, "SchedulerLock contract violations:\n" + "\n".join(all_violations)


def test_guard_detects_the_f032_pattern():
    """Self-check: the exact F032 anti-pattern is flagged; the correct one is not."""
    bad = (
        "async def job():\n"
        "    async with SchedulerLock(redis, 'x') as acquired:\n"
        "        if not acquired:\n"
        "            return\n"
        "        await work()\n"
    )
    good = (
        "async def job():\n"
        "    async with SchedulerLock(redis, 'x') as lock:\n"
        "        if not lock.acquired:\n"
        "            return\n"
        "        await work()\n"
    )
    assert _violations_in_source(bad, "bad.py"), "guard must flag the F032 pattern"
    assert not _violations_in_source(good, "good.py"), "guard must accept the correct pattern"


def test_guard_flags_unbound_scheduler_lock():
    """Self-check: using SchedulerLock without an ``as`` binding is also a violation."""
    unbound = (
        "async def job():\n" "    async with SchedulerLock(redis, 'x'):\n" "        await work()\n"
    )
    assert _violations_in_source(unbound, "unbound.py")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
