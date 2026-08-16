"""Pure canonical Settings validation for the installer (ADR-215, B07).

Boots the REAL composed ``Settings`` against the current environment and
reports every validation error deterministically. No socket, database,
Redis, Docker, or provider operation ever happens here — the installer runs
it inside the API image with the entrypoint bypassed::

    docker compose -f docker-compose.prod.yml -f docker-compose.install.yml \
        run --rm --no-deps --entrypoint "" api python -m scripts.validate_settings

Issue text is sorted by ``(location, message)`` and NEVER contains a setting
value: a malformed secret must not leak through its own error report.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@dataclass(frozen=True)
class SettingsIssue:
    """One located validation failure (value-free by contract).

    Attributes:
        location: Dotted settings field path (e.g. ``fernet_key``).
        message: Pydantic's message for the failure, without input echo.
    """

    location: str
    message: str


def validate_current_settings() -> tuple[object | None, tuple[SettingsIssue, ...]]:
    """Construct a fresh composed ``Settings`` from the environment.

    Returns:
        ``(settings, ())`` when the environment is valid, else
        ``(None, issues)`` with issues sorted by (location, message).
    """
    from pydantic import ValidationError

    from src.core.config import Settings
    from src.infrastructure.database.connection_budget import (
        ConnectionBudgetError,
        enforce_connection_budget,
    )

    try:
        settings = Settings()
        # Same pure arithmetic the production lifespan fail-fasts on
        # (audit F004): an overcommitted pool profile must fail HERE, in the
        # installer's validate step, with the sizing message — not five
        # minutes later as a readiness_timeout with no detail (measured on
        # the v1.30.1 qualification: the minimal env template shipped no
        # pool sizing and every leg crash-looped on ConnectionBudgetError).
        try:
            enforce_connection_budget(settings)
        except ConnectionBudgetError as exc:
            return None, (SettingsIssue(location="connection_budget", message=str(exc)),)
        return settings, ()
    except ValidationError as exc:
        issues = tuple(
            sorted(
                (
                    SettingsIssue(
                        location=".".join(str(part) for part in err["loc"]),
                        message=str(err["msg"]),
                    )
                    for err in exc.errors(include_input=False, include_url=False)
                ),
                key=lambda issue: (issue.location, issue.message),
            )
        )
        return None, issues


def format_issues(issues: Sequence[SettingsIssue]) -> str:
    """Render issues as stable, value-free report lines.

    Args:
        issues: Located validation failures.

    Returns:
        One ``  - <location>: <message>`` line per issue.
    """
    return "\n".join(f"  - {issue.location}: {issue.message}" for issue in issues)


def main() -> int:
    """Validate and report; exit 0 only on a fully valid environment.

    Returns:
        0 when Settings boots, 1 with one line per error otherwise.
    """
    settings, issues = validate_current_settings()
    if settings is not None:
        print("OK: settings are valid")
        return 0
    print(f"INVALID: {len(issues)} setting error(s)")
    print(format_issues(issues))
    return 1


if __name__ == "__main__":
    sys.exit(main())
