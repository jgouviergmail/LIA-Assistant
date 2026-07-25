"""End-to-end skill execution through the real ``SkillScriptExecutor.execute``.

The rlimit/socket tests exercise the ``preexec_fn`` primitive in isolation.
This test drives the FULL ``execute()`` chain — script resolution, stdin
payload, temp cwd chmod, privilege drop, env filtering, stdout capture — to
prove the A1/A2 hardening did not regress legitimate skill execution.

Uses a real on-disk skill (temp dir) via a patched ``SkillsCache`` so no DB
is required.

Every test here pins ``SKILLS_SCRIPT_SANDBOX=subprocess``: this module
characterizes the in-process path specifically. The container path (SEC-001,
the production default) is covered by ``test_executor_container_sandbox.py``,
which must not depend on a reachable Docker daemon.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest

from src.domains.skills.executor import SkillScriptExecutor


@pytest.fixture(autouse=True)
def _force_subprocess_sandbox(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the in-process path for this module.

    ``get_settings()`` is ``@lru_cache``d, so setting an environment variable
    after the first call changes nothing — the cached instance is the only
    thing ``execute()`` ever sees, and patching it is the only lever.
    """
    from src.core.config import get_settings

    monkeypatch.setattr(get_settings(), "skills_script_sandbox", "subprocess")


@pytest.fixture
def skill_root() -> Iterator[Path]:
    """A world-traversable skill storage root (mirrors real skill dirs).

    Real skill storage is world-readable end-to-end (system skills are 0777,
    normal user imports are 0755/0644 via umask), so a privilege-dropped uid
    can read the script. pytest's ``tmp_path`` roots are 0700, which would NOT
    reproduce production — hence a dedicated mkdtemp under /tmp (1777) with the
    whole tree chmod'd 0755.
    """
    root = Path(tempfile.mkdtemp(prefix="skillroot_"))
    os.chmod(root, 0o755)
    yield root
    shutil.rmtree(root, ignore_errors=True)


def _make_skill(skill_root: Path, script_body: str) -> dict:
    """Create a real, world-readable skill dir; return a SkillsCache row."""
    skill_dir = skill_root / "probe-skill"
    (skill_dir / "scripts").mkdir(parents=True)
    source = skill_dir / "SKILL.md"
    source.write_text("# probe\n")
    script = skill_dir / "scripts" / "run.py"
    script.write_text(script_body)
    # Mirror real skill-storage perms (world-traversable dirs + readable file).
    for path in (skill_dir, skill_dir / "scripts"):
        os.chmod(path, 0o755)
    os.chmod(script, 0o644)
    return {"name": "probe-skill", "source_path": str(source)}


@pytest.mark.asyncio
async def test_execute_runs_script_and_captures_output(skill_root: Path) -> None:
    """A benign skill runs through execute() and its stdout is returned."""
    body = (
        "import sys, json\n"
        "payload = json.load(sys.stdin)\n"
        "print(json.dumps({'echo': payload['parameters'].get('x')}))\n"
    )
    skill = _make_skill(skill_root, body)

    with patch("src.domains.skills.cache.SkillsCache.get_by_name_for_user", return_value=skill):
        result = await SkillScriptExecutor.execute(
            skill_name="probe-skill",
            script_name="run.py",
            parameters={"x": 42},
            user_id="u1",
        )

    assert result.success, result.error
    assert json.loads(result.output.strip()) == {"echo": 42}


@pytest.mark.asyncio
async def test_execute_can_write_output_file_under_sandbox(skill_root: Path) -> None:
    """A skill that writes to its cwd still works (temp dir chmod under drop)."""
    body = (
        "with open('artifact.txt', 'w') as fh:\n"
        "    fh.write('generated')\n"
        "print('WROTE_OK')\n"
    )
    skill = _make_skill(skill_root, body)

    with patch("src.domains.skills.cache.SkillsCache.get_by_name_for_user", return_value=skill):
        result = await SkillScriptExecutor.execute(
            skill_name="probe-skill", script_name="run.py", user_id="u1"
        )

    assert result.success, result.error
    assert result.output.strip() == "WROTE_OK"


@pytest.mark.skipif(
    not (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="privilege drop only engages when the API runs as root",
)
@pytest.mark.asyncio
async def test_execute_drops_privileges_when_root(skill_root: Path) -> None:
    """When root, the executed script actually runs as the unprivileged uid."""
    from src.core.config import settings

    body = "import os\nprint(f'UID_{os.getuid()}')\n"
    skill = _make_skill(skill_root, body)

    with patch("src.domains.skills.cache.SkillsCache.get_by_name_for_user", return_value=skill):
        result = await SkillScriptExecutor.execute(
            skill_name="probe-skill", script_name="run.py", user_id="u1"
        )

    assert result.success, result.error
    assert result.output.strip() == f"UID_{settings.skills_script_unprivileged_uid}"


@pytest.mark.skipif(
    not (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="privilege drop only engages when the API runs as root",
)
@pytest.mark.asyncio
async def test_execute_denies_docker_socket_when_root(skill_root: Path) -> None:
    """When root, a skill run via execute() cannot open the Docker socket."""
    if not os.path.exists("/var/run/docker.sock"):
        pytest.skip("no docker socket mounted")

    body = (
        "import socket\n"
        "s = socket.socket(socket.AF_UNIX)\n"
        "try:\n"
        "    s.connect('/var/run/docker.sock')\n"
        "    print('SOCKET_OPENED')\n"
        "except (PermissionError, FileNotFoundError):\n"
        "    print('SOCKET_DENIED')\n"
    )
    skill = _make_skill(skill_root, body)

    with patch("src.domains.skills.cache.SkillsCache.get_by_name_for_user", return_value=skill):
        result = await SkillScriptExecutor.execute(
            skill_name="probe-skill", script_name="run.py", user_id="u1"
        )

    assert result.success, result.error
    assert result.output.strip() == "SOCKET_DENIED"
