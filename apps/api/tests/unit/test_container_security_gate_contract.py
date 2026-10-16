"""Container vulnerability findings must fail the local security gate, as in CI."""

import re
import shlex

import yaml

from tests._repo_paths import repo_root_or_skip


def test_every_container_scan_blocks_on_high_or_critical_findings() -> None:
    taskfile = yaml.safe_load((repo_root_or_skip() / "Taskfile.yml").read_text(encoding="utf-8"))
    task = taskfile["tasks"]["security:scan:docker"]
    commands = [entry["cmd"] for entry in task["cmds"]]
    assert commands
    for command in commands:
        args = shlex.split(command)
        assert "image" in args, "This gate must scan the built container, not just its source"
        assert "--exit-code" in args, "Trivy's default reports findings without failing the task"
        assert args[args.index("--exit-code") + 1] == "1"
        assert set(args[args.index("--severity") + 1].split(",")) == {"HIGH", "CRITICAL"}
        assert "--ignore-unfixed" not in args


def test_default_scan_targets_are_the_individual_build_tasks_artifacts() -> None:
    taskfile = yaml.safe_load((repo_root_or_skip() / "Taskfile.yml").read_text(encoding="utf-8"))
    tasks = taskfile["tasks"]
    scanner = tasks["security:scan:docker"]
    for variable, build_task in [("API_IMAGE", "build:api"), ("WEB_IMAGE", "build:web")]:
        build = shlex.split(tasks[build_task]["cmds"][0])
        image = build[build.index("-t") + 1]
        default = re.search(r'default "([^"]+)"', scanner["vars"][variable])
        assert default is not None
        assert (
            default.group(1) == image
        ), "The default gate must inspect what the build task produces"
