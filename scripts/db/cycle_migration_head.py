#!/usr/bin/env python
"""Exercise every direct rollback target of the single Alembic head, then restore it."""

from __future__ import annotations

from collections.abc import Callable

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory


def cycle_head(config: Config, *, emit: Callable[[str], None] = print) -> None:
    """Cycle every direct parent explicitly; a first revision rolls back to base.

    A relative ``-1`` has no unique meaning at a merge. Testing every direct
    parent avoids silently choosing a branch; sorting only makes the announced
    execution order reproducible. Each cycle restores the head before the next.
    """
    scripts = ScriptDirectory.from_config(config)
    heads = scripts.get_heads()
    if len(heads) != 1:
        raise RuntimeError(f"Expected a single Alembic head, found {len(heads)}: {heads}")
    head = scripts.get_revision(heads[0])
    if head is None:
        raise RuntimeError("Expected a single Alembic head, but its revision is missing")
    parents = head.down_revision
    targets = (
        ("base",)
        if parents is None
        else (parents,) if isinstance(parents, str) else tuple(sorted(parents))
    )
    emit(f"    head {head.revision}: cycle every direct parent target: {', '.join(targets)}")
    for target in targets:
        emit(f"    downgrade {head.revision} -> {target}; then upgrade to head")
        command.downgrade(config, target)
        command.upgrade(config, "head")


def main() -> None:
    """Use the current application's Alembic configuration and propagate any failure."""
    cycle_head(Config("alembic.ini"))


if __name__ == "__main__":
    main()
