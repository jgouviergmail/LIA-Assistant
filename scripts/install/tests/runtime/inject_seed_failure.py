"""Seed-failure injection (ADR-215, G3 row 11) — stdlib only.

``--arm`` appends a guaranteed-failing SQL statement to the LAST seed file
(the verifier) so the single-transaction wrapper must roll back everything;
``--disarm`` restores the original bytes. The harness then asserts zero
partial-domain counts and a clean successful retry.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

TARGET = Path("infrastructure/database/seeds/verify_reference_seeds.sql")
MARKER = b"\n-- INJECTED-FAILURE (disposable qualification)\nSELECT 1/0;\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["arm", "disarm"])
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    target = args.root / TARGET
    body = target.read_bytes()
    if args.action == "arm":
        if MARKER in body:
            print("already armed")
            return 0
        target.write_bytes(body + MARKER)
        print("armed: verify_reference_seeds.sql now fails the transaction")
        return 0
    if MARKER not in body:
        print("already disarmed")
        return 0
    target.write_bytes(body.replace(MARKER, b""))
    print("disarmed: original seed restored")
    return 0


if __name__ == "__main__":
    sys.exit(main())
