"""Check the exact uv writer version without a platform-specific shell tool."""

from __future__ import annotations

import argparse
import subprocess
import sys


def matches_uv_version(executable: str, expected: str) -> bool:
    """Run only the selected binary's version command, with bounded execution."""
    try:
        result = subprocess.run(
            [executable, "--version"],
            shell=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
            check=False,
        )
    except OSError:
        return False
    except subprocess.TimeoutExpired:
        return False
    lines = result.stdout.splitlines()
    if result.returncode != 0 or len(lines) != 1:
        return False
    fields = lines[0].split(maxsplit=2)
    return len(fields) >= 2 and fields[0] == "uv" and fields[1] == expected


def main(argv: list[str] | None = None) -> int:
    """Return nonzero unless the chosen executable reports the required version."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uv", required=True)
    parser.add_argument("--expected", required=True)
    args = parser.parse_args(argv)
    if not matches_uv_version(args.uv, args.expected):
        print(
            f"uv {args.expected} is required; selected binary failed the version check",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
