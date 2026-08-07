#!/usr/bin/env python3
"""CI/local parity guard — the workflow may orchestrate, not implement.

The recurring failure this closes: a gate is added to `.github/workflows/ci.yml`
as an inline command, nothing locally can run it, and it is discovered by a red
build after every local gate went green. It happened with the marker-coverage
gate, the frontend complexity ratchet, the per-file coverage thresholds and the
whole code-hygiene block.

The fix is structural rather than conventional: `ci.yml` calls `task <name>` and
the logic lives in the Taskfile, so the CI runs *literally* the command a
developer runs. This guard enforces that shape:

1. every `run:` step is either a `task ...` call or matches a declared
   infrastructure pattern (checkout, venv creation, dependency install…);
2. every task the workflow calls actually exists in the Taskfile;
3. anything genuinely CI-only is listed here WITH a reason, so the exception is
   a decision on the record and not an oversight.

Usage:
    python scripts/audit/check_ci_parity.py
    python scripts/audit/check_ci_parity.py --workflow .github/workflows/ci.yml
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
TASKFILE = REPO_ROOT / "Taskfile.yml"

# Commands that legitimately belong to the workflow rather than the Taskfile:
# provisioning the runner. They set up the environment a task then runs in, and
# reproducing them locally is meaningless — the local machine IS the setup.
INFRASTRUCTURE_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"^python -m venv", "runner provisioning: create the interpreter the tasks use"),
    (r"^source \.venv/bin/activate", "runner provisioning: activate that interpreter"),
    (r"^\.?v?e?n?v?/?\.?venv/bin/pip install", "runner provisioning: install into the venv"),
    (r"^pip install", "runner provisioning: install a build-time dependency"),
    (r"^pnpm install", "runner provisioning: install workspace dependencies"),
    (r"^npm ci", "runner provisioning: install the isolated E2E package"),
    (r"^cp \.env\.test \.env", "runner provisioning: supply a settings file the local dev already has"),
    (r"^psql ", "runner provisioning: create PostgreSQL extensions the local image ships with"),
)

# Genuine CI-only steps. Each needs a reason: this is the list a reviewer reads
# to know what a local run does NOT cover.
CI_ONLY: dict[str, str] = {
    "VER=3.0.0": (
        "promtool binary install. The local equivalent is `task test:alerts`, which "
        "runs the SAME pinned version (v3.0.0) on the same files through a container "
        "because promtool is not installed on a dev machine. Mechanism differs, "
        "checked artifact does not. The pin MUST track the Prometheus image in "
        "docker-compose.{dev,prod}.yml: the PromQL engine changed between majors, "
        "and the same rules on the same data returned SUCCESS on 2.53.2 and FAILED "
        "on 3.0.0 — validating on a different engine than production is not validation."
    ),
    "promtool check rules": (
        "see above — native binary here, container in `task test:alerts`."
    ),
    "promtool test rules": (
        "see above — native binary here, container in `task test:alerts`."
    ),
    "bash ../../scripts/db/check_migrations_replay.sh": (
        "the replay runs INSIDE the API container in CI; the local equivalent is "
        "`task db:migrate:replay-check`, a deliberate cross-platform Python port "
        "(F048) because the bash wrapper could not run on the Windows dev host."
    ),
    "python -B scripts/install/tests_py310.py": (
        "the installer's 3.10-floor gate (ADR-215) must run under the BARE "
        "actions/setup-python 3.10 interpreter with no repo venv — running it "
        "through a task would route it into apps/api/.venv (3.12) and prove "
        "nothing. Local equivalent: any python >= 3.10 runs the same file."
    ),
    "pytest tests/unit/ -q --no-cov -p no:cacheprovider": (
        "Python 3.13 forward-compatibility run (F041). The dev machine and every "
        "other job are on 3.12; reproducing this locally would mean maintaining a "
        "second interpreter for a check whose whole point is the version change."
    ),
    "BAK_FILES=": "superseded by `task lint:hygiene` — remove if it reappears",
}


def _load_task_names() -> set[str]:
    """Every task name declared in the Taskfile.

    Parsed textually rather than with a YAML load: the Taskfile uses Task's own
    `{{.VAR}}` templating, which is not valid YAML in every position.

    Returns:
        The set of declared task names.
    """
    names: set[str] = set()
    for line in TASKFILE.read_text(encoding="utf-8").splitlines():
        if match := re.match(r"^  ([a-z][a-z0-9:_-]*):\s*$", line):
            names.add(match.group(1))
    return names


def _iter_run_steps(workflow: Path):
    """Yield ``(job, step_name, command)`` for every `run:` step.

    Args:
        workflow: Path to the workflow file.

    Yields:
        One tuple per shell command line in a `run:` block.
    """
    data = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    for job_name, job in (data.get("jobs") or {}).items():
        for step in job.get("steps") or []:
            if "run" not in step:
                continue
            step_name = step.get("name", "<unnamed>")

            # Join shell line-continuations first: a multi-line `pytest ... \`
            # is ONE command, and splitting on newlines would report each of its
            # arguments as an unexplained implementation.
            joined = re.sub(r"\\\s*\n\s*", " ", step["run"].strip())

            for raw in joined.splitlines():
                command = raw.strip()
                if command and not command.startswith("#"):
                    yield job_name, step_name, command


def main() -> int:
    """Check that the workflow only orchestrates.

    Returns:
        1 when an unexplained implementation is found in the workflow.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow", default=str(DEFAULT_WORKFLOW))
    args = parser.parse_args()

    workflow = Path(args.workflow)
    declared = _load_task_names()

    offenders: list[str] = []
    missing_tasks: list[str] = []
    task_calls = 0
    infra = 0
    ci_only = 0

    for job, step, command in _iter_run_steps(workflow):
        if command.startswith("task "):
            task_calls += 1
            for name in command.removeprefix("task ").split():
                if name.startswith("-"):
                    continue
                if name not in declared:
                    missing_tasks.append(f"{job} / {step}: `task {name}` is not in the Taskfile")
            continue

        # A step whose NAME announces provisioning is infrastructure whatever it
        # runs — installing a toolchain is the runner's job, not a gate. Judging
        # by name rather than by command keeps the rule readable and avoids
        # enumerating every flavour of curl/tar/PATH manipulation.
        if re.match(r"^(Install|Create|Set up|Setup) ", step):
            infra += 1
            continue

        if any(re.search(pattern, command) for pattern, _ in INFRASTRUCTURE_PATTERNS):
            infra += 1
            continue

        if any(marker in command for marker in CI_ONLY):
            ci_only += 1
            continue

        offenders.append(f"{job} / {step}: {command[:100]}")

    print(f"Workflow: {workflow.relative_to(REPO_ROOT)}")
    print(f"  task calls        : {task_calls}")
    print(f"  infrastructure    : {infra}")
    print(f"  declared CI-only  : {ci_only}")
    print(f"  unexplained       : {len(offenders)}")

    if missing_tasks:
        print("\nWorkflow calls tasks that do not exist:")
        for line in missing_tasks:
            print(f"  {line}")

    if offenders:
        print("\nThese steps implement logic the workflow should only orchestrate:")
        for line in offenders:
            print(f"  {line}")
        print(
            "\nMove the command into a Taskfile task and call it, so a developer can "
            "run the same gate before pushing. If it genuinely cannot run locally, "
            "add it to CI_ONLY in this script WITH a reason."
        )

    if offenders or missing_tasks:
        return 1
    print("\nParity holds: the workflow orchestrates, the Taskfile implements.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
