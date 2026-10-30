"""The Today dashboard built once across WORKERS: four real processes, real Redis (base 15).

Ported from the 2026-10-28 simulation (spec 2026-10-21 §0ter D-H4, E12): four
processes stand in for uvicorn workers serving one page load — two ``/cards``
and two ``/synthesis`` arriving within a second — around the REAL
``BriefingService`` and ``run_shared_flight``, with fake sources timed like
production's medians. Before D1 a section missing at publication cost every
waiter the whole 10 s budget, then one rebuild each. The three scenarios:

- nominal: every waiter finishes within 0.5 s of the owner, every source once;
- one failed section: one read of it in total, no long wait (attempt marker);
- mails invalidated by a push at the owner's end: exactly one extra mail read,
  by ONE re-claiming waiter, no long wait (owner liveness + re-claim).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
import redis

from src.core.config import settings
from tests._repo_paths import find_apps_api_root

pytestmark = [pytest.mark.integration]

CHILD = Path(__file__).with_name("briefing_flight_child.py")
#: (role, delay before its request) — the simulation's arrival pattern, scaled down.
ROLES = (("cards_1", 0.0), ("synthesis_A", 0.012), ("cards_2", 0.016), ("synthesis_B", 0.19))
#: Read live by every build or reader by design: the SMS card is never cached,
#: and a reminder or a ticket changed a moment ago must show now.
ALWAYS_LIVE = {"sms", "reminders", "workboard"}
IMPORT_TIMEOUT_S = 120


def _run(scenario: str) -> list[dict[str, Any]]:
    user_id = str(uuid.uuid4())
    root = find_apps_api_root()
    children = [
        subprocess.Popen(
            [sys.executable, str(CHILD), role, str(delay), scenario, user_id],
            cwd=root,
            env={**os.environ, "PYTHONPATH": str(root)},
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        for role, delay in ROLES
    ]
    try:
        for child in children:
            assert child.stdout is not None
            line = child.stdout.readline()
            while line and line.strip() != "READY":
                line = child.stdout.readline()
            assert line.strip() == "READY", "a worker died while importing"
        start_at = f"{time.time() + 0.5}\n"
        for child in children:
            assert child.stdin is not None
            child.stdin.write(start_at)
            child.stdin.flush()
        events: list[dict[str, Any]] = []
        for child in children:
            out, _ = child.communicate(timeout=IMPORT_TIMEOUT_S)
            events += [json.loads(line) for line in out.splitlines() if line.startswith("{")]
            assert child.returncode == 0, "a worker failed"
        return sorted(events, key=lambda event: event["t"])
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
        _forget(user_id)


def _forget(user_id: str) -> None:
    """Remove this simulated account's keys from the test Redis (base 15 only)."""
    url = str(settings.redis_url).rsplit("/", 1)[0] + "/15"
    client = redis.Redis.from_url(url)
    try:
        for key in client.scan_iter(match=f"*{user_id}*"):
            client.delete(key)
    finally:
        client.close()


def _reads(events: list[dict[str, Any]]) -> Counter[str]:
    return Counter(e["section"] for e in events if e["ev"] == "fetch_start")


def _span(events: list[dict[str, Any]], role: str) -> tuple[float, float]:
    start = next(e["t"] for e in events if e["role"] == role and e["ev"] == "request_start")
    end = next(e["t"] for e in events if e["role"] == role and e["ev"] == "request_end")
    return start, end


def _cacheable(reads: Counter[str]) -> Counter[str]:
    return Counter({section: n for section, n in reads.items() if section not in ALWAYS_LIVE})


def test_nominal_waiters_finish_with_the_owner() -> None:
    events = _run("nominal")
    reads = _cacheable(_reads(events))

    assert set(reads.values()) == {1}, f"a source was read twice: {reads}"
    _owner_start, owner_end = _span(events, "cards_1")
    for role, _delay in ROLES[1:]:
        _start, end = _span(events, role)
        assert end - owner_end < 0.5, f"{role} finished {end - owner_end:.2f} s after the owner"


def test_one_failed_section_is_read_once_without_a_long_wait() -> None:
    events = _run("weather_error")
    reads = _cacheable(_reads(events))

    assert reads["weather"] == 1, f"the failing source was reopened: {reads}"
    _owner_start, owner_end = _span(events, "cards_1")
    for role, _delay in ROLES[1:]:
        _start, end = _span(events, role)
        assert end - owner_end < 0.5, f"{role} waited {end - owner_end:.2f} s past the owner"


def test_push_at_the_owners_end_costs_one_extra_read() -> None:
    events = _run("push_mid_build")
    reads = _cacheable(_reads(events))

    assert reads["mails"] == 2, f"mails read {reads['mails']} times, expected one re-read"
    assert {n for section, n in reads.items() if section != "mails"} == {1}
    longest = max(end - start for start, end in (_span(events, role) for role, _ in ROLES))
    _owner_start, owner_end = _span(events, "cards_1")
    assert longest < owner_end + 1.5, f"a request waited {longest:.2f} s (the old 10 s budget)"
