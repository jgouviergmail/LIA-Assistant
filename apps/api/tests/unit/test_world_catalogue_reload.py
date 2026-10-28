"""All development entry points must reload the authoritative World JSON catalogue."""

import json
import shlex

import pytest
import uvicorn
import yaml
from uvicorn.supervisors.watchfilesreload import FileFilter

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit
ROOT = repo_root_or_skip()


def commands() -> list[list[str]]:
    task = yaml.safe_load((ROOT / "Taskfile.yml").read_text(encoding="utf-8"))
    compose = yaml.safe_load((ROOT / "docker-compose.dev.yml").read_text(encoding="utf-8"))
    values = [shlex.split(entry["cmd"]) for entry in task["tasks"]["dev:api"]["cmds"]]
    values.append(shlex.split(compose["services"]["api"]["command"]))
    dockerfile = (ROOT / "apps/api/Dockerfile.dev").read_text(encoding="utf-8")
    values.append(
        json.loads(next(line[4:] for line in dockerfile.splitlines() if line.startswith("CMD ")))
    )
    return values


@pytest.mark.parametrize("command", commands())
def test_development_reloader_watches_authoritative_json_and_ignores_bytecode(command: list[str]):
    source = ROOT / "apps/api/src"
    includes = [word.split("=", 1)[1] for word in command if word.startswith("--reload-include=")]
    excludes = [word.split("=", 1)[1] for word in command if word.startswith("--reload-exclude=")]
    config = uvicorn.Config(
        "src.main:app",
        reload=True,
        reload_dirs=[str(source)],
        reload_includes=includes,
        reload_excludes=excludes,
    )
    accepts = FileFilter(config)
    assert accepts(source / "domains/world/assets/campus-v1.json")
    assert accepts(source / "domains/world/collision.py")
    assert not accepts(source / "domains/world/__pycache__/collision.pyc")
    # The planner rewrites this registry during a chat turn: watching it would
    # restart the worker mid-answer and drop every SSE, World and voice socket.
    assert not accepts(source / "domains/agents/registry/hallucinated_tools.json")
