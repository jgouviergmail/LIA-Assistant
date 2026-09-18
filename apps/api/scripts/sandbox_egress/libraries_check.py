"""Import every library the sandbox promises, INSIDE the sandbox image (ADR-298).

The unit test proves the promise on the lockfile CI installs; this script
proves it on the image a run actually starts from — the only place a missing
system library (``lxml`` needs libxml2) or a slimmed production stage can be
seen. Run it against the image the deployment pins::

    task sandbox:libraries:check -- lia-api:local

It exits 1 naming every import that failed, so a promise the image cannot
keep reds the build rather than a person's run.
"""

from __future__ import annotations

import sys

from src.domains.agents.python_sandbox.libraries import PYTHON_SANDBOX_LIBRARIES, missing_libraries


def main() -> int:
    """Try every promised import; print the verdict; return the exit status."""
    missing = missing_libraries()
    total = len(PYTHON_SANDBOX_LIBRARIES)
    if missing:
        print(
            f"sandbox libraries: {total - len(missing)}/{total} import; MISSING: {', '.join(missing)}"
        )
        return 1
    print(f"sandbox libraries: {total}/{total} import")
    return 0


if __name__ == "__main__":
    sys.exit(main())
