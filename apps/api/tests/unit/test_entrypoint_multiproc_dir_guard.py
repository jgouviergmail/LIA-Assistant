"""An EMPTY ``PROMETHEUS_MULTIPROC_DIR`` must never reach the application.

``prometheus_client`` decides multiprocess mode on the **presence** of the
variable, not on its value::

    if 'PROMETHEUS_MULTIPROC_DIR' in os.environ:   # empty string counts
        ValueClass = MultiProcessValue()

so a declared-but-empty variable turns aggregation on with an empty directory,
every metric file resolves to a RELATIVE path, and the first gauge import dies
with ``PermissionError: 'gauge_mostrecent_7.db'`` inside a read-only ``/app``.

Measured in production on 2026-08-28 (v1.34.0 deploy): aligning ``.env.prod``
against ``.env.prod.example`` copied the example's empty
``PROMETHEUS_MULTIPROC_DIR=`` line into the live file. The entrypoint's own
fallback — "if the dir cannot be prepared, fall back to single-process metrics
rather than aborting startup" — was silently defeated, because that promise
assumed the variable would be ABSENT when disabled. `lia-api-prod` restarted in
a loop while every other container was healthy.

The fix is in the entrypoint, not in the env file: whenever multiprocess mode
is not armed, the variable is UNSET, so no value a deployment may carry can
reach the interpreter. This guard pins that behaviour on the script's text —
the shell logic itself is exercised end to end by the deploy.
"""

from __future__ import annotations

import re

import pytest

from tests._repo_paths import repo_root_or_skip

ENTRYPOINT = repo_root_or_skip() / "apps" / "api" / "docker-entrypoint.sh"


@pytest.fixture(scope="module")
def script() -> str:
    if not ENTRYPOINT.is_file():
        pytest.skip("guard needs the full repository checkout (docker-entrypoint.sh).")
    return ENTRYPOINT.read_text(encoding="utf-8")


@pytest.mark.unit
class TestMultiprocDirIsNeverEmptyAndPresent:
    def test_single_worker_path_unsets_the_variable(self, script: str) -> None:
        """One worker needs no aggregation — and must not inherit an empty value."""
        assert re.search(
            r"^\s*unset PROMETHEUS_MULTIPROC_DIR\s*$", script, re.MULTILINE
        ), "the entrypoint must unset PROMETHEUS_MULTIPROC_DIR when multiprocess is off"

    def test_failed_directory_preparation_also_unsets(self, script: str) -> None:
        """The documented fallback ('app still starts') must hold literally."""
        fallback = script[script.index("could not prepare") :]
        head = fallback[:400]
        assert "unset PROMETHEUS_MULTIPROC_DIR" in head, (
            "the WARN branch must unset the variable: leaving a declared-but-empty "
            "value turns multiprocess mode on with no directory"
        )

    def test_export_still_happens_on_the_success_path(self, script: str) -> None:
        """The fix must not disable multiprocess metrics for real deployments."""
        assert 'export PROMETHEUS_MULTIPROC_DIR="$_mp_dir"' in script


@pytest.mark.unit
class TestEnvExamplesDocumentTheHazard:
    def test_examples_warn_that_empty_is_not_absent(self) -> None:
        """A reader copying the example must know an empty value is not neutral."""
        root = repo_root_or_skip()
        for name in (".env.example", ".env.prod.example"):
            text = (root / name).read_text(encoding="utf-8", errors="replace")
            block = text[text.index("PROMETHEUS_MULTIPROC_DIR") - 400 :][:600]
            assert (
                "leave it absent" in block.lower() or "absent" in block.lower()
            ), f"{name}: PROMETHEUS_MULTIPROC_DIR needs the absent-vs-empty warning"
