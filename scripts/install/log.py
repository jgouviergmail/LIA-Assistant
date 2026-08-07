"""Private, redacted installer log (B13).

Append-only, mode 0o600, one UTC-timestamped line per event. Every write
passes through redaction against the registered secrets; recorded argv are
redacted COPIES (the real command still receives the real values).
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Sequence
from datetime import datetime, timezone
from pathlib import Path

from scripts.install.redaction import redact


class InstallLog:
    """One installation's event log."""

    def __init__(self, path: Path, *, secrets: Iterable[str] = ()) -> None:
        self._path = path
        self._secrets: list[str] = [s for s in secrets if s]
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.touch()
        if os.name == "posix":
            path.chmod(0o600)

    def add_secret(self, value: str) -> None:
        """Register another ephemeral secret for all later writes."""
        if value:
            self._secrets.append(value)

    def write(self, event: str, **fields: str) -> None:
        """Append one redacted, timestamped event line.

        ``event`` is positional-only in spirit: field names like ``code``
        stay free for the caller (``log.write("input_error", code=...)``).
        """
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        parts = [timestamp, event]
        parts.extend(f"{key}={value}" for key, value in fields.items())
        line = redact(" ".join(parts), self._secrets)
        with open(self._path, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(line + "\n")

    def redact_argv(self, argv: Sequence[str]) -> list[str]:
        """A redacted COPY of ``argv`` safe to record; the original is untouched."""
        return [redact(arg, self._secrets) for arg in argv]
