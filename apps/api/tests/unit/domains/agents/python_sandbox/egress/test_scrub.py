"""A real key a network run's output repeats never leaves the run (point 6).

The script only ever holds a per-run token; the proxy swaps it for the person's
real key on the wire. But the service on the other side may QUOTE the key it
received — an error body, a debug echo — and the script prints what it got
back. That text reaches the model, the registers and the answer. Every real
key of the run is therefore removed from what comes back, as written and
URL-encoded, at both doors: a script's run and a skill's command.

Known limit, written: a key inside a compressed or encoded binary is not found.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch
from urllib.parse import quote
from uuid import uuid4

import pytest

from src.domains.agents.python_sandbox.egress.hosts import HostDecision
from src.domains.agents.python_sandbox.egress.registry import LiveRun
from src.domains.agents.python_sandbox.egress.run import NetworkRunPlan, execute_network_run
from src.domains.agents.python_sandbox.egress.scrub import (
    scrub_secret_bytes,
    scrub_secrets,
)
from src.domains.skills.command_bundle import CommandOutput, OutputFile
from src.domains.skills.command_network import CommandNetwork, run_on_network
from src.domains.skills.executor import EgressSpec, ScriptResult

pytestmark = pytest.mark.unit

# Split so that no key-shaped literal sits in the repository (secret scanning).
_REAL = "brave-" + "Zx9Yw8Vu7Ts6Rq5Po4/+="
_ENCODED = quote(_REAL, safe="")


def _plan() -> NetworkRunPlan:
    """A run whose one connector key is ``_REAL`` — what the proxy holds."""
    return NetworkRunPlan(
        run=LiveRun(run_id="run-1", user_id="u-1", hosts=("api.example.org",), credentials=()),
        secrets={"brave_search": _REAL},
        spec=EgressSpec(
            network="lia-sandbox",
            proxy_url="http://proxy:8080",
            ca_volume="ca",
            ca_dir="/ca",
            ca_file="/ca/ca.pem",
        ),
        decision=HostDecision(statuses={}, unknown=(), credentials=(), share_turn_data=True),
    )


@asynccontextmanager
async def _serving(_plan: Any, *, capability: str) -> AsyncIterator[SimpleNamespace]:
    yield SimpleNamespace(succeeded=False)


class TestTheScrub:
    def test_the_key_goes_as_written_and_url_encoded(self) -> None:
        text = f"401 invalid key {_REAL} for url=/v1?key={_ENCODED}"

        scrubbed = scrub_secrets(text, [_REAL])

        assert _REAL not in scrubbed and _ENCODED not in scrubbed
        assert scrubbed.startswith("401 invalid key ")

    def test_a_short_value_is_never_taken_for_a_key(self) -> None:
        """Scrubbing « abc » would eat every word containing it."""
        assert scrub_secrets("abc abcdef", ["abc"]) == "abc abcdef"

    def test_bytes_keep_their_length(self) -> None:
        """A file is masked in place: a binary's offsets stay where they were."""
        data = b"%PDF-1.7 key=" + _REAL.encode() + b" end"

        masked = scrub_secret_bytes(data, [_REAL])

        assert _REAL.encode() not in masked
        assert len(masked) == len(data)


class TestTheScriptRun:
    async def test_its_output_and_error_carry_no_key(self) -> None:
        echoed = ScriptResult(
            success=False,
            output=f"status 401: invalid key {_REAL}\nretry with key={_ENCODED}",
            error=f"auth failed for {_REAL}",
            execution_started=True,
        )
        with (
            patch("src.domains.agents.python_sandbox.egress.run.serving", new=_serving),
            patch(
                "src.domains.skills.executor.SkillScriptExecutor.execute_source",
                new=AsyncMock(return_value=echoed),
            ),
        ):
            result = await execute_network_run(
                _plan(), source="print(1)", payload={}, user_id=uuid4()
            )

        assert _REAL not in result.output and _ENCODED not in result.output
        assert result.error is not None and _REAL not in result.error
        assert result.success is False


class TestTheSkillCommand:
    async def test_stdout_stderr_and_files_carry_no_key(self) -> None:
        echoed = CommandOutput(
            exit_code=1,
            stdout=f"npm ERR! 403 token {_REAL}",
            stderr=f"url=https://registry/?key={_ENCODED}",
            stdout_truncated=False,
            stderr_truncated=False,
            files=(OutputFile(name="log.txt", data=f"key: {_REAL}\n".encode()),),
            skipped=(),
        )
        with patch("src.domains.skills.command_network.serving", new=_serving):
            output = await run_on_network(CommandNetwork(_plan()), AsyncMock(return_value=echoed))

        assert _REAL not in output.stdout
        assert _ENCODED not in output.stderr
        assert _REAL.encode() not in output.files[0].data
        assert output.exit_code == 1
