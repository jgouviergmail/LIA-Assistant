"""Execute the entrypoint's worker resolution as a shell, under conflicting inputs."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("env_workers", "args", "expected"),
    [
        ("4", ["--reload"], "1:absent"),
        ("4", ["--workers", "1"], "4:absent"),
        ("1", ["--workers=4"], "1:present"),
        ("1", ["--workers", "4"], "1:present"),
        ("4", [], "4:present"),
        ("4", ["--workers=4", "--reload"], "1:absent"),
    ],
)
def test_metrics_follow_effective_workers(
    tmp_path: Path, env_workers: str, args: list[str], expected: str
) -> None:
    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    shell = str(git_bash) if os.name == "nt" and git_bash.is_file() else shutil.which("bash")
    if not shell:
        pytest.skip("bash is required to execute the container entrypoint")
    source = (repo_root_or_skip() / "apps/api/docker-entrypoint.sh").read_text(encoding="utf-8")
    block = source[
        source.index('_workers="${WEB_CONCURRENCY') : source.index("# Start application")
    ]
    env = {**os.environ, "WEB_CONCURRENCY": env_workers, "PROMETHEUS_MULTIPROC_DIR": "metrics"}
    script = (
        block + '\nprintf "%s:%s\\n" "$WEB_CONCURRENCY" "${PROMETHEUS_MULTIPROC_DIR:+present}"\n'
    )
    result = subprocess.run(
        [shell, "-c", script, "worker-test", *args],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    )
    actual = result.stdout.strip().splitlines()[-1]
    if actual.endswith(":"):
        actual += "absent"
    assert actual == expected
