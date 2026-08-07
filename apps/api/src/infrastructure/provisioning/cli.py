"""Command-line entry point for demonstrator provisioning.

    python -m src.infrastructure.provisioning.cli [--force | --verify]

Prints one line an operator can read in a deploy log, and exits non-zero when
it refused — so a deployment script cannot mistake a refusal for success.

Created: 2026-08-06 (live-demonstrator programme, lot 4)
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from src.infrastructure.provisioning.demo_instance import (
    provision_demo_instance,
    verify_spend_ceiling,
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="provisioning",
        description="Mark this database as a public demonstrator's.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Write the marker even though the database already holds accounts. "
            "This arms a nightly purge on them: use it only on a database you "
            "are certain is disposable."
        ),
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help=(
            "Write nothing: only report whether this instance can measure what "
            "it spends. A daily ceiling reads a ledger the pricing catalogue "
            "feeds, so an unpriced model leaves it flat whatever is billed."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the provisioning — or only the read-only check — and report.

    Returns:
        0 when the marker is present (written or already there) or the
        ceiling can see the spend, 1 when either refused — a deploy script
        must not mistake a refusal for success.
    """
    args = _parse_args(argv)
    from src.infrastructure.database.registry import import_all_models

    import_all_models()

    if args.verify:
        unpriced = asyncio.run(verify_spend_ceiling())
        if unpriced is None:
            print("Spend ceiling armed: the configured model is priced by this catalogue.")
            return 0
        print(
            f"CEILING BLIND: '{unpriced}' has no active per-1M-token price here, so every "
            "call is recorded at 0 EUR and INSTANCE_DAILY_BUDGET_EUR can never fire. "
            "Point DEMO_INSTANCE_LLM_MODEL at a model this catalogue prices."
        )
        return 1

    report = asyncio.run(provision_demo_instance(force=args.force))
    print(report.summary())
    return 1 if report.refused_reason else 0


if __name__ == "__main__":  # pragma: no cover - process entry point
    sys.exit(main())
