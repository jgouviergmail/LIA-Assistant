"""The vendored snapshot ages; a stale one warns, it never reds the build.

An old snapshot is a maintenance signal, not a defect: the design forbids any
network access on an execution path, so a build must stay green offline.
"""

from __future__ import annotations

import warnings
from datetime import UTC, datetime, timedelta

from src.infrastructure.llm.catalogue.snapshot_loader import snapshot_generated_at

MAX_AGE = timedelta(days=120)


def test_snapshot_age_is_reported() -> None:
    age = datetime.now(UTC) - snapshot_generated_at()
    if age > MAX_AGE:
        warnings.warn(
            f"the vendored catalogue snapshot is {age.days} days old — "
            "run `task llm:catalogue:fetch` and review the diff",
            stacklevel=1,
        )
    assert age.days >= 0, "the snapshot claims to come from the future"
