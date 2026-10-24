"""The backend coverage floor is held by unit and integration together (AC-030b).

Measured 2026-10-23: the unit suite alone covered 78.98 % of ``src``, and the
SQL-bound domains sat far below the floor in it (sms 53.6 %, proactive
discussions 70.7 %) while their integration tests, on a real PostgreSQL, covered
them at 92.1 % and 82.4 %. A unit-only gate could only be met by simulating
PostgreSQL in unit tests, which the test rules forbid. The owner's decision of
2026-10-23: the floor applies to what the two suites execute together.

This guard holds the wiring that makes that true:

- each suite writes its OWN data file, outside coverage's parallel pattern
  (``<data file>.<suffix>``): every reporting command of coverage 7 combines such
  files implicitly and NON-strictly, then deletes them, so a stale xdist worker
  file would be counted and a missing suite would go unnoticed;
- the integration task's second collection appends to the first, the first never
  appends (a stale file must not leak in);
- ``test:backend:coverage`` combines exactly those two files, strictly (a missing
  one is an error, never a partial total), writes the ``coverage.xml`` the diff
  gate reads, then holds the floor;
- in CI, each suite's job uploads its file and the coverage job, which needs
  both, downloads exactly those artifacts before it runs the task;
- the report is rooted where pytest-cov roots it: ``coverage xml`` reads the
  measured tree from the configuration (``[tool.coverage.run] source``), which
  must name the tree every measuring command passes to ``--cov``; without it the
  report carries absolute paths under an empty root, and the diff gate refuses it.
"""

from __future__ import annotations

import re
import shlex
import tomllib

import pytest
import yaml

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

REPO_ROOT = repo_root_or_skip()
TASKFILE = REPO_ROOT / "Taskfile.yml"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
PYPROJECT = REPO_ROOT / "apps" / "api" / "pyproject.toml"

UNIT_TASK = "test:backend:unit:coverage"
INTEGRATION_TASK = "test:backend:integration"
COVERAGE_TASK = "test:backend:coverage"
#: What every pytest run that names no data file writes (pyproject's addopts measure).
DEFAULT_DATA_FILE = ".coverage"

_DATA_FILE = re.compile(r"\bCOVERAGE_FILE=(\S+)")
_PYTEST = re.compile(r"(?:^|\s)\.venv/(?:Scripts|bin)/pytest\s")


def _tasks() -> dict[str, dict[str, object]]:
    data = yaml.safe_load(TASKFILE.read_text(encoding="utf-8"))
    tasks = data["tasks"]
    assert isinstance(tasks, dict)
    return tasks


def _commands(task: str, *, platform: str = "windows") -> list[str]:
    """The task's commands for one platform, in order (Windows and Unix are alternatives)."""
    entries = _tasks()[task].get("cmds") or []
    assert isinstance(entries, list)
    commands: list[str] = []
    for entry in entries:
        if isinstance(entry, str):
            commands.append(entry)
        elif isinstance(entry, dict) and isinstance(entry.get("cmd"), str):
            platforms = entry.get("platforms")
            if platforms is None or platform in platforms:
                commands.append(entry["cmd"])
    return commands


def _pytest_commands(task: str, platform: str) -> list[str]:
    return [command for command in _commands(task, platform=platform) if _PYTEST.search(command)]


def _data_file_of(task: str, platform: str) -> str:
    """The one data file every pytest command of the task writes."""
    names: set[str] = set()
    for command in _pytest_commands(task, platform):
        match = _DATA_FILE.search(command)
        assert match, f"{task} [{platform}] measures without naming its data file: {command}"
        names.add(match.group(1))
    assert len(names) == 1, f"{task} [{platform}] writes several data files: {sorted(names)}"
    return names.pop()


def _floor() -> str:
    text = PYPROJECT.read_text(encoding="utf-8")
    values: set[str] = {match.group(1) for match in re.finditer(r"--cov-fail-under=(\d+)", text)}
    assert len(values) == 1, f"pyproject.toml must own exactly one floor, found {values}"
    return values.pop()


def _coverage_command(task: str, platform: str, action: str) -> tuple[int, list[str]]:
    """The position and arguments of the task's ``python -m coverage <action>`` command."""
    for index, command in enumerate(_commands(task, platform=platform)):
        words = shlex.split(command)
        if words[1:4] == ["-m", "coverage", action]:
            return index, words[4:]
    raise AssertionError(f"{task} [{platform}] runs no `coverage {action}`")


def _option(arguments: list[str], name: str) -> str | None:
    prefix = f"{name}="
    found = [argument[len(prefix) :] for argument in arguments if argument.startswith(prefix)]
    assert len(found) <= 1, f"{name} given twice: {arguments}"
    return found[0] if found else None


@pytest.mark.parametrize("platform", ["windows", "linux"])
def test_each_suite_writes_its_own_data_file(platform: str) -> None:
    unit = _data_file_of(UNIT_TASK, platform)
    integration = _data_file_of(INTEGRATION_TASK, platform)

    assert unit != integration
    assert DEFAULT_DATA_FILE not in (unit, integration), (
        "a suite writing coverage's default data file shares it with every other "
        "measured pytest run"
    )


@pytest.mark.parametrize("platform", ["windows", "linux"])
def test_no_data_file_falls_into_the_implicit_combination(platform: str) -> None:
    """A reporting command combines ``<its data file>.*`` without being asked."""
    _, combine = _coverage_command(COVERAGE_TASK, platform, "combine")
    combined = _option(combine, "--data-file")
    assert combined is not None and combined != DEFAULT_DATA_FILE

    for suite in (UNIT_TASK, INTEGRATION_TASK):
        data_file = _data_file_of(suite, platform)
        assert not data_file.startswith(f"{combined}."), (
            f"{data_file} matches the implicit pattern of {combined}: a report would "
            "combine and delete it"
        )
        assert not data_file.startswith(
            f"{DEFAULT_DATA_FILE}."
        ), f"{data_file} matches coverage's parallel pattern of the default data file"


@pytest.mark.parametrize("platform", ["windows", "linux"])
def test_the_unit_suite_measures_without_a_floor_of_its_own(platform: str) -> None:
    commands = _pytest_commands(UNIT_TASK, platform)

    assert commands, f"{UNIT_TASK} [{platform}] runs no pytest"
    for command in commands:
        assert "--no-cov" not in command and "--cov=src" in command
        assert (
            "--cov-fail-under=0" in command
        ), "pyproject's addopts carries the floor: the unit suite alone must not hold it"


@pytest.mark.parametrize("platform", ["windows", "linux"])
def test_the_integration_collections_measure_and_append_in_order(platform: str) -> None:
    commands = _pytest_commands(INTEGRATION_TASK, platform)

    assert len(commands) >= 2, f"{INTEGRATION_TASK} [{platform}] lost a collection"
    for command in commands:
        assert "--no-cov" not in command and "--cov=src" in command
        assert "--cov-fail-under=0" in command
    assert "--cov-append" not in commands[0], "the first collection must start a fresh file"
    for command in commands[1:]:
        assert "--cov-append" in command, "a later collection would erase the first"


@pytest.mark.parametrize("platform", ["windows", "linux"])
def test_the_coverage_task_combines_both_files_strictly_then_holds_the_floor(
    platform: str,
) -> None:
    combine_at, combine = _coverage_command(COVERAGE_TASK, platform, "combine")
    xml_at, xml = _coverage_command(COVERAGE_TASK, platform, "xml")
    report_at, report = _coverage_command(COVERAGE_TASK, platform, "report")
    combined = _option(combine, "--data-file")

    inputs = {argument for argument in combine if not argument.startswith("-")}
    assert inputs == {
        _data_file_of(UNIT_TASK, platform),
        _data_file_of(INTEGRATION_TASK, platform),
    }
    assert "--keep" in combine, "the suites' data must survive a second combination"
    assert "--append" not in combine, "a previous total must never join the new one"
    assert _option(xml, "--data-file") == combined and "coverage.xml" in xml
    assert _option(report, "--data-file") == combined
    assert _option(report, "--fail-under") == _floor()
    # The report keeps the floor's comparison exactly as pytest-cov makes it.
    assert _option(report, "--precision") is None
    # The xml exists for inspection even when the floor is not met.
    assert combine_at < xml_at < report_at


def _jobs() -> dict[str, dict[str, object]]:
    workflow = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    jobs = workflow["jobs"]
    assert isinstance(jobs, dict)
    return jobs


def _steps(job: dict[str, object]) -> list[dict[str, object]]:
    steps = job.get("steps") or []
    assert isinstance(steps, list)
    return steps


def _job_running(task: str) -> tuple[str, dict[str, object]]:
    found = [
        (name, job)
        for name, job in _jobs().items()
        if any(step.get("run") == f"task {task}" for step in _steps(job))
    ]
    assert len(found) == 1, f"`task {task}` must run in exactly one CI job, found {found}"
    return found[0]


def _uploaded(job: dict[str, object], data_file: str) -> dict[str, object]:
    for step in _steps(job):
        uses = step.get("uses")
        settings = step.get("with")
        if isinstance(uses, str) and uses.startswith("actions/upload-artifact@"):
            assert isinstance(settings, dict)
            if settings.get("path") == f"apps/api/{data_file}":
                return settings
    raise AssertionError(f"no step uploads apps/api/{data_file}")


def test_ci_combines_exactly_what_each_suite_uploaded() -> None:
    unit_job, unit = _job_running(UNIT_TASK)
    integration_job, integration = _job_running(INTEGRATION_TASK)
    coverage_job, coverage = _job_running(COVERAGE_TASK)

    needs = coverage.get("needs")
    needed = {needs} if isinstance(needs, str) else set(needs) if isinstance(needs, list) else set()
    assert {unit_job, integration_job} <= needed

    expected: set[str] = set()
    for job, suite in ((unit, UNIT_TASK), (integration, INTEGRATION_TASK)):
        settings = _uploaded(job, _data_file_of(suite, "linux"))
        # A dot-file is left out of an artifact unless asked for (upload-artifact v4.4).
        assert settings.get("include-hidden-files") is True
        assert settings.get("if-no-files-found") == "error"
        name = settings.get("name")
        assert isinstance(name, str)
        expected.add(name)

    steps = _steps(coverage)
    task_at = next(i for i, step in enumerate(steps) if step.get("run") == f"task {COVERAGE_TASK}")
    downloaded: set[str] = set()
    for step in steps[:task_at]:
        uses = step.get("uses")
        options = step.get("with")
        if isinstance(uses, str) and uses.startswith("actions/download-artifact@"):
            assert isinstance(options, dict) and options.get("path") == "apps/api"
            artifact = options.get("name")
            assert isinstance(artifact, str)
            downloaded.add(artifact)
    assert downloaded == expected


@pytest.mark.parametrize("platform", ["windows", "linux"])
def test_the_combined_report_is_rooted_where_the_diff_gate_reads(platform: str) -> None:
    configured = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["tool"]["coverage"]["run"]
    trees = {
        match.group(1)
        for suite in (UNIT_TASK, INTEGRATION_TASK)
        for command in _pytest_commands(suite, platform)
        for match in re.finditer(r"--cov=(\S+)", command)
    }

    assert configured.get("source") == sorted(trees) == ["src"]
