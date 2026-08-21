"""The production stop budget must fit inside ``stop_grace_period``.

Uvicorn shuts down in two SEQUENTIAL phases (``uvicorn.server.Server.shutdown``):
it first waits for in-flight connections, bounded by ``--timeout-graceful-shutdown``,
and only THEN runs the lifespan shutdown, where ADR-117 drains chat producers and
generic background tasks. The two budgets ADD UP, and Docker SIGKILLs the container
once ``stop_grace_period`` elapses.

Without ``--timeout-graceful-shutdown`` the first phase has NO bound, and an open
SSE stream never completes on its own: the wait is infinite, the lifespan shutdown
never runs, and the drain ADR-117 pays for is never reached. Measured on production
over 7 days (2026-07-29 → 2026-08-05): 31 of ~42 stops ended in
``Container failed to exit within 1m30s of signal 15 - using the force``.

Reproduced in an isolated container (2026-08-05), uvicorn as PID 1, one open SSE
stream:

* without the flag  → ``Waiting for connections to close``, then SIGKILL at the
  Docker timeout;
* with the flag     → ``Task cancelled, timeout graceful shutdown exceeded`` and
  a clean exit.

The flag only works when uvicorn IS the signalled process: the entrypoint's
``exec "$@"`` is what makes that true, so this guard checks it too — a plain
``"$@"`` would leave the shell holding PID 1 and swallow SIGTERM, which is
precisely how the first de-risking run of this fix measured a false negative.
"""

from __future__ import annotations

import re

import pytest
import yaml

from src.core.constants import (
    DEFAULT_BACKGROUND_RUNS_DRAIN_TIMEOUT_SECONDS,
    DEFAULT_SHUTDOWN_BACKGROUND_TASKS_TIMEOUT_SECONDS,
)
from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

REPO_ROOT = repo_root_or_skip()
API_DOCKERFILE = REPO_ROOT / "apps" / "api" / "Dockerfile.prod"
API_ENTRYPOINT = REPO_ROOT / "apps" / "api" / "docker-entrypoint.sh"
COMPOSE_PROD = REPO_ROOT / "docker-compose.prod.yml"

# Seconds kept between the summed shutdown budget and the SIGKILL deadline, to
# cover interpreter teardown and the 0.1s poll granularity of uvicorn's loop.
SIGKILL_SAFETY_MARGIN_SECONDS = 5


def _api_cmd() -> list[str]:
    """The production CMD, as a token list (JSON exec form)."""
    text = API_DOCKERFILE.read_text(encoding="utf-8")
    match = re.search(r"^CMD\s+(\[.+?\])\s*$", text, re.MULTILINE | re.DOTALL)
    assert match, "Dockerfile.prod must declare CMD in JSON exec form"
    import json

    tokens: list[str] = json.loads(match.group(1))
    return tokens


def _flag_value(tokens: list[str], flag: str) -> str | None:
    """Value of ``--flag value`` in an exec-form CMD, or None when absent."""
    for index, token in enumerate(tokens):
        if token == flag:
            return tokens[index + 1] if index + 1 < len(tokens) else None
        if token.startswith(f"{flag}="):
            return token.split("=", 1)[1]
    return None


def _stop_grace_period_seconds() -> int:
    """``stop_grace_period`` of the api service, in seconds."""
    compose = yaml.safe_load(COMPOSE_PROD.read_text(encoding="utf-8"))
    raw = (compose.get("services") or {}).get("api", {}).get("stop_grace_period")
    assert raw is not None, "the api service must declare stop_grace_period"
    text = str(raw).strip()
    match = re.fullmatch(r"(?P<value>\d+)(?P<unit>[smh]?)", text)
    assert match, f"unsupported stop_grace_period format: {text!r}"
    factor = {"": 1, "s": 1, "m": 60, "h": 3600}[match.group("unit")]
    return int(match.group("value")) * factor


class TestGracefulShutdownBudget:
    """The connection-wait phase must be bounded, and the total must fit."""

    def test_cmd_bounds_the_connection_wait_phase(self) -> None:
        """An unbounded wait never reaches the lifespan drain (prod: 31 SIGKILLs)."""
        value = _flag_value(_api_cmd(), "--timeout-graceful-shutdown")

        assert value is not None, (
            "uvicorn must run with --timeout-graceful-shutdown: without it an open "
            "SSE stream blocks shutdown forever and Docker SIGKILLs the container "
            "before the ADR-117 drain ever runs."
        )
        assert (
            value.isdigit() and int(value) > 0
        ), f"--timeout-graceful-shutdown must be a positive number of seconds, got {value!r}"

    def test_summed_budget_fits_within_stop_grace_period(self) -> None:
        """Connection wait + lifespan drain + margin must precede SIGKILL."""
        value = _flag_value(_api_cmd(), "--timeout-graceful-shutdown")
        assert value is not None  # covered by the test above
        connection_wait = int(value)

        lifespan_drain = (
            DEFAULT_BACKGROUND_RUNS_DRAIN_TIMEOUT_SECONDS
            + DEFAULT_SHUTDOWN_BACKGROUND_TASKS_TIMEOUT_SECONDS
        )
        total = connection_wait + lifespan_drain + SIGKILL_SAFETY_MARGIN_SECONDS
        grace = _stop_grace_period_seconds()

        assert total <= grace, (
            f"shutdown budget {total}s (connection wait {connection_wait}s + lifespan "
            f"drain {lifespan_drain}s + {SIGKILL_SAFETY_MARGIN_SECONDS}s margin) exceeds "
            f"stop_grace_period {grace}s: the phases are SEQUENTIAL in "
            f"uvicorn.server.Server.shutdown, so raising one means lowering the other "
            f"or raising stop_grace_period."
        )


class TestUvicornReceivesTheSignal:
    """--timeout-graceful-shutdown is inert unless uvicorn is the signalled process."""

    def test_entrypoint_execs_the_command(self) -> None:
        """``exec`` replaces the shell, so uvicorn keeps PID 1 and gets SIGTERM."""
        body = API_ENTRYPOINT.read_text(encoding="utf-8")

        assert re.search(r'^\s*exec\s+"\$@"', body, re.MULTILINE), (
            'docker-entrypoint.sh must end with `exec "$@"`: without exec the shell '
            "stays PID 1, receives SIGTERM itself and uvicorn never starts its "
            "graceful shutdown — the flag then measures as a no-op."
        )
