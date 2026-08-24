#!/usr/bin/env python
"""Print the reviewable catalogue diff against the vendored snapshot.

Read-only: this script never writes to the database. The initial correction
ships as a versioned migration, and the continuous sync is a later lot.

The comparison itself lives in
``src.infrastructure.llm.catalogue.sync_diff`` so the CLI, the tests and the
migration share one implementation.

Usage:
    cd apps/api
    python scripts/llm_catalogue/sync.py
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.infrastructure.llm.catalogue.field_mapping import (  # noqa: E402
    RETIREMENT_NOTICE,
)
from src.infrastructure.llm.catalogue.status import (  # noqa: E402
    CatalogueStatus,
    catalogue_status,
)
from src.infrastructure.llm.catalogue.sync_diff import (  # noqa: E402
    CatalogueRow,
    FieldChange,
    compute_diff,
)


async def load_rows() -> list[CatalogueRow]:
    """Read the active catalogue rows the diff compares."""
    from sqlalchemy import select

    from src.domains.llm.models import LLMModel
    from src.infrastructure.database.session import get_db_context
    from src.infrastructure.llm.catalogue.status import rows_from_models

    async with get_db_context() as db:
        found = list((await db.execute(select(LLMModel).where(LLMModel.is_active))).scalars().all())
    return rows_from_models(found)


def _render(title: str, changes: list[FieldChange]) -> None:
    print(f"\n{title} ({len(changes)})")
    for c in changes:
        print(
            f"  {c.model_name:34s} {c.field:28s} " f"{c.current!r} -> {c.proposed!r}  [{c.source}]"
        )


def _render_retirements(status: CatalogueStatus) -> None:
    """Report every retiring model and, of those, which ones may be deactivated.

    The states are different questions, not severities. ``retired`` means the
    evidence is uncontradicted and the row may stop being offered; ``announced``
    and ``flagged`` mean a build should warn while the model still answers.
    """
    retired = [entry for entry in status.retiring if entry.state == "retired"]
    print()
    print(
        f"RETIRING ({len(status.retiring)}) - date within {RETIREMENT_NOTICE.days}d "
        f"or status=deprecated; {len(retired)} of them uncontradicted"
    )
    for entry in status.retiring:
        print(
            f"  {entry.model_name:34s} {entry.state:9s} "
            f"date={entry.deprecation_date} seen_by={list(entry.seen_by)}"
        )


async def _main() -> None:
    from src.infrastructure.database.session import get_db_context

    rows = await load_rows()
    changes = compute_diff(rows)
    async with get_db_context() as db:
        status = await catalogue_status(db)
    print(f"catalogue rows compared: {len(rows)}")
    print(f"provenance: {status.provenance}")
    _render(
        "AUTO   - provenance=declared, no human decision at stake",
        [c for c in changes if c.severity == "auto"],
    )
    _render("REVIEW - a human curated this row", [c for c in changes if c.severity == "review"])
    _render_retirements(status)


def main() -> None:
    """Entry point."""
    asyncio.run(_main())


if __name__ == "__main__":
    main()
