"""Guard: where the repository's Trivy comes from, and what its scan blocks on.

Why
---
``trivy-action`` installs through ``setup-trivy``, whose script fetches the archive from
``get.trivy.dev``, a host outside GitHub. That name left the DNS on 2026-11-03: every
run that missed the binary cache failed on curl's exit 6. ``Generate SBOM`` missed it on
every run, because ``cache: "false"`` also switches that cache off, and ``Trivy Scan``
stayed green only on an entry already evicted once. Both are required checks, and a cache
hides the dependency until the day it empties, so the shape is held here.

The image of ``security:scan:docker`` reads the same ``TRIVY_VERSION``. It used to pin its
own tag, so the repository ran two versions of its scanner (0.70.0 and 0.74.0).

The scan blocks on every finding. For a SARIF report the action drops ``severity`` unless
``limit-severities-for-sarif`` is true, so ``severity: CRITICAL,HIGH`` announced a threshold
nothing applied: three MEDIUM advisories failed the job all the same. That strictness is the
decision, so the declaration left, and what would narrow the gate is refused here.
"""

from __future__ import annotations

import re
from typing import TypedDict

import pytest
import yaml

from tests._repo_paths import repo_root_or_skip

REPO_ROOT = repo_root_or_skip()
WORKFLOWS = REPO_ROOT / ".github" / "workflows"

pytestmark = pytest.mark.unit

INSTALL_COMMAND = "task security:trivy:install"
SCAN_ACTION = "aquasecurity/trivy-action"
SETUP_ACTION = "aquasecurity/setup-trivy"
#: Anti-vacuity floor: the scan and the frontend SBOM of security.yml (2026-11-04).
MIN_EXPECTED_STEPS = 2
#: The Trivy image in any form: a tag, a digest, or neither. ``trivy-db`` is its database.
IMAGE_REFERENCE = re.compile(r"aquasec/trivy(?![\w-])[^\s\"']*")
#: The one form it may take, reading the version the workflows' binary reads.
PINNED_IMAGE = "aquasec/trivy:{{.TRIVY_VERSION}}"
#: Anti-vacuity floor: two images on two platform families in security:scan:docker (2026-11-04).
MIN_EXPECTED_IMAGE_RUNS = 4
#: What would bound the findings the gate blocks on, or read as if it did.
NARROWING_INPUTS = ("severity", "limit-severities-for-sarif", "ignore-unfixed")
#: Anti-vacuity floor: the filesystem scan of security.yml (2026-11-04).
MIN_EXPECTED_GATES = 1

#: The functional form, because ``with`` is a keyword.
Step = TypedDict(
    "Step",
    {"name": str, "uses": str, "run": str, "with": dict[str, str]},
    total=False,
)


class Job(TypedDict, total=False):
    """The part of a workflow job this guard reads."""

    steps: list[Step]


class Workflow(TypedDict):
    """The part of a workflow file this guard reads."""

    jobs: dict[str, Job]


class InstallTask(TypedDict):
    """The part of the install task this guard reads."""

    cmds: list[str]


class Taskfile(TypedDict):
    """The part of the Taskfile this guard reads."""

    vars: dict[str, str]
    tasks: dict[str, InstallTask]


def _trivy_step_count(workflow: Workflow) -> int:
    """Count the steps of ``workflow`` that run Trivy through the action."""
    return sum(
        step.get("uses", "").startswith(SCAN_ACTION)
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
    )


def _offenders(workflow: Workflow) -> list[str]:
    """Name every step of ``workflow`` that could reach the vendor's installer."""
    found: list[str] = []
    for job_name, job in workflow["jobs"].items():
        installed = False
        for step in job.get("steps", []):
            uses = step.get("uses", "")
            label = f"{job_name} / {step.get('name', uses)}"
            installed = installed or step.get("run", "").strip() == INSTALL_COMMAND
            if uses.startswith(SETUP_ACTION):
                found.append(f"{label}: installs through setup-trivy")
            if not uses.startswith(SCAN_ACTION):
                continue
            # GitHub reads an unquoted YAML `true` as the input "true".
            if str(step.get("with", {}).get("skip-setup-trivy")).lower() != "true":
                found.append(f"{label}: does not set skip-setup-trivy")
            if not installed:
                found.append(f"{label}: no earlier step runs `{INSTALL_COMMAND}`")
    return found


def _workflows() -> dict[str, Workflow]:
    """Every workflow of the repository, by file name."""
    return {
        path.name: yaml.safe_load(path.read_text(encoding="utf-8"))
        for path in sorted(WORKFLOWS.glob("*.yml"))
    }


def _taskfile() -> Taskfile:
    """The repository's Taskfile."""
    taskfile: Taskfile = yaml.safe_load((REPO_ROOT / "Taskfile.yml").read_text(encoding="utf-8"))
    return taskfile


def _install_commands() -> str:
    """What the install task runs."""
    return "\n".join(_taskfile()["tasks"]["security:trivy:install"]["cmds"])


def _image_references(text: str) -> list[str]:
    """Every reference to the Trivy image in ``text``."""
    return IMAGE_REFERENCE.findall(text)


def _stray_images(text: str) -> list[str]:
    """Every reference to the Trivy image in ``text`` that does not read the pinned version."""
    return [image for image in _image_references(text) if image != PINNED_IMAGE]


def _files_that_could_pin() -> dict[str, str]:
    """The Taskfile and every workflow, where a second pin would sit, by file name."""
    paths = [REPO_ROOT / "Taskfile.yml", *sorted(WORKFLOWS.glob("*.yml"))]
    return {path.name: path.read_text(encoding="utf-8") for path in paths}


def _gates(workflow: Workflow) -> list[tuple[str, dict[str, str]]]:
    """The label and the inputs of every step of ``workflow`` scanning into a SARIF report."""
    return [
        (f"{job_name} / {step.get('name', step['uses'])}", step.get("with", {}))
        for job_name, job in workflow["jobs"].items()
        for step in job.get("steps", [])
        if step.get("uses", "").startswith(SCAN_ACTION)
        and step.get("with", {}).get("format") == "sarif"
    ]


def _loose_gates(workflow: Workflow) -> list[str]:
    """Name every SARIF scan of ``workflow`` that would not block on every finding."""
    found: list[str] = []
    for label, inputs in _gates(workflow):
        # GitHub reads an unquoted YAML `1` as the input "1".
        if str(inputs.get("exit-code")) != "1":
            found.append(f"{label}: does not set exit-code 1")
        found.extend(f"{label}: sets {name}" for name in NARROWING_INPUTS if name in inputs)
    return found


def _action(uses: str = SCAN_ACTION, skip: str | None = None) -> Step:
    """A pinned ``uses:`` step, with ``skip-setup-trivy`` set to ``skip`` when given."""
    return {
        "name": "Scan",
        "uses": f"{uses}@abc",
        "with": {} if skip is None else {"skip-setup-trivy": skip},
    }


def _workflow(*steps: Step) -> Workflow:
    """A workflow holding one job made of ``steps``."""
    return {"jobs": {"scan": {"steps": list(steps)}}}


def _scan(inputs: dict[str, str]) -> Step:
    """A step running the action with ``inputs``."""
    return {"name": "Scan", "uses": f"{SCAN_ACTION}@abc", "with": inputs}


INSTALL_STEP: Step = {"name": "Install Trivy", "run": INSTALL_COMMAND}
#: What a gate is: a SARIF report, and a job that fails on what the report holds.
GATE: dict[str, str] = {"format": "sarif", "exit-code": "1"}
#: The same gate as a workflow spells it with no quotes.
UNQUOTED_GATE = f"""
jobs:
  scan:
    steps:
      - uses: {SCAN_ACTION}@abc
        with:
          format: sarif
          exit-code: 1
"""


class TestTheRepository:
    """What the workflows actually do."""

    def test_the_scan_sees_the_trivy_steps(self) -> None:
        steps = sum(_trivy_step_count(workflow) for workflow in _workflows().values())

        assert steps >= MIN_EXPECTED_STEPS

    def test_no_workflow_reaches_the_vendor_installer(self) -> None:
        found = {name: _offenders(workflow) for name, workflow in _workflows().items()}

        assert not {name: lines for name, lines in found.items() if lines}


class TestTheJudgement:
    """The verdict on workflows that would bring the dependency back."""

    def test_a_step_on_the_vendor_install_is_named(self) -> None:
        workflow = _workflow(INSTALL_STEP, _action())

        assert _offenders(workflow) == ["scan / Scan: does not set skip-setup-trivy"]

    def test_a_step_keeping_the_vendor_install_on_is_named(self) -> None:
        workflow = _workflow(INSTALL_STEP, _action(skip="false"))

        assert _offenders(workflow) == ["scan / Scan: does not set skip-setup-trivy"]

    def test_a_step_with_nothing_installed_before_it_is_named(self) -> None:
        workflow = _workflow(_action(skip="true"), INSTALL_STEP)

        assert _offenders(workflow) == [
            "scan / Scan: no earlier step runs `task security:trivy:install`",
        ]

    def test_setup_trivy_called_directly_is_named(self) -> None:
        workflow = _workflow(_action(uses=SETUP_ACTION))

        assert _offenders(workflow) == ["scan / Scan: installs through setup-trivy"]

    def test_the_expected_shape_passes(self) -> None:
        workflow = _workflow(INSTALL_STEP, _action(skip="true"))

        assert _offenders(workflow) == []


class TestTheInstallTask:
    """What the task downloads, and what it holds the download to."""

    def test_the_version_and_its_digest_are_pinned(self) -> None:
        variables = _taskfile()["vars"]

        assert re.fullmatch(r"\d+\.\d+\.\d+", str(variables["TRIVY_VERSION"]))
        assert re.fullmatch(r"[0-9a-f]{64}", str(variables["TRIVY_SHA256"]))

    def test_the_archive_comes_from_the_github_release(self) -> None:
        commands = _install_commands()

        assert "github.com/aquasecurity/trivy/releases/download/v{{.TRIVY_VERSION}}/" in commands
        assert "get.trivy.dev" not in commands

    def test_the_archive_is_held_to_the_pinned_digest(self) -> None:
        commands = _install_commands()

        assert "{{.TRIVY_SHA256}}" in commands
        assert "sha256sum --check --strict" in commands


class TestOneTrivy:
    """The image of the local scan reads the version the workflows' binary reads."""

    def test_the_scan_sees_the_image(self) -> None:
        references = sum(len(_image_references(text)) for text in _files_that_could_pin().values())

        assert references >= MIN_EXPECTED_IMAGE_RUNS

    def test_no_file_pins_an_image_of_its_own(self) -> None:
        found = {name: _stray_images(text) for name, text in _files_that_could_pin().items()}

        assert not {name: images for name, images in found.items() if images}

    @pytest.mark.parametrize(
        "image",
        [
            "aquasec/trivy:0.74.0",
            "aquasec/trivy:latest",
            "aquasec/trivy",
            "aquasec/trivy@sha256:abc",
        ],
    )
    def test_any_other_form_of_the_image_is_named(self, image: str) -> None:
        assert _stray_images(f'docker run "{image}" image lia-api') == [image]

    def test_the_pinned_image_passes(self) -> None:
        assert _stray_images(f"docker run {PINNED_IMAGE} image lia-api") == []

    def test_the_release_address_is_not_the_image(self) -> None:
        assert _image_references("github.com/aquasecurity/trivy/releases/download") == []

    def test_the_vulnerability_database_is_not_the_image(self) -> None:
        assert _image_references("TRIVY_DB_REPOSITORY: mirror.gcr.io/aquasec/trivy-db:2") == []


class TestTheGate:
    """The scan blocks on every finding, and no input reads as a bound on it."""

    def test_the_scan_sees_a_gate(self) -> None:
        gates = sum(len(_gates(workflow)) for workflow in _workflows().values())

        assert gates >= MIN_EXPECTED_GATES

    def test_no_workflow_narrows_the_gate(self) -> None:
        found = {name: _loose_gates(workflow) for name, workflow in _workflows().items()}

        assert not {name: lines for name, lines in found.items() if lines}

    @pytest.mark.parametrize(
        "name",
        ["severity", "limit-severities-for-sarif", "ignore-unfixed"],
    )
    def test_an_input_that_would_narrow_it_is_named(self, name: str) -> None:
        workflow = _workflow(_scan({**GATE, name: "true"}))

        assert _loose_gates(workflow) == [f"scan / Scan: sets {name}"]

    def test_a_threshold_that_would_apply_is_named_twice(self) -> None:
        inputs = {**GATE, "severity": "CRITICAL,HIGH", "limit-severities-for-sarif": "true"}

        assert _loose_gates(_workflow(_scan(inputs))) == [
            "scan / Scan: sets severity",
            "scan / Scan: sets limit-severities-for-sarif",
        ]

    @pytest.mark.parametrize("inputs", [{"format": "sarif"}, {**GATE, "exit-code": "0"}])
    def test_a_scan_that_would_not_fail_the_job_is_named(self, inputs: dict[str, str]) -> None:
        workflow = _workflow(_scan(inputs))

        assert _loose_gates(workflow) == ["scan / Scan: does not set exit-code 1"]

    def test_the_expected_shape_passes(self) -> None:
        assert _loose_gates(_workflow(_scan(GATE))) == []

    def test_an_unquoted_exit_code_passes(self) -> None:
        workflow: Workflow = yaml.safe_load(UNQUOTED_GATE)

        assert len(_gates(workflow)) == 1
        assert _loose_gates(workflow) == []

    def test_a_step_writing_another_report_is_no_gate(self) -> None:
        workflow = _workflow(_scan({"format": "cyclonedx", "severity": "CRITICAL,HIGH"}))

        assert _gates(workflow) == []

    def test_a_step_of_another_action_is_no_gate(self) -> None:
        step: Step = {"uses": "vendor/scanner@abc", "with": GATE}

        assert _gates(_workflow(step)) == []
