"""Disposable Redis overrides, preflight and CI retain the test database boundary."""

import json
import os
import socket
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock
from urllib.parse import urlsplit

import pytest
import yaml
from dotenv import dotenv_values

from scripts import integration_preflight
from tests._repo_paths import repo_root_or_skip
from tests.redis_test_url import validated_test_redis_url

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "url",
    [
        "redis://127.0.0.1:16379/15",
        "rediss://test-user:test-only@redis.example:6379/15",
        "redis://[::1]:16379/15",
    ],
)
def test_accepts_explicit_disposable_redis_endpoint(url: str) -> None:
    assert validated_test_redis_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:16379/15",
        "redis:///15",
        "redis://127.0.0.1:16379/0",
        "redis://127.0.0.1:16379/1",
        "redis://127.0.0.1:16379",
        "redis://test-user:test-only@127.0.0.1:16379/15?db=0",
        "redis://127.0.0.1:16379/15#fragment",
        "redis://127.0.0.1:not-a-port/15",
        "",
        "redis://127.0.0.1:16379/15/",
    ],
)
def test_rejects_invalid_endpoint_without_echoing_credentials(url: str) -> None:
    with pytest.raises(ValueError, match="TEST_REDIS_URL") as raised:
        validated_test_redis_url(url)
    assert "test-only" not in str(raised.value)
    if url:
        assert url not in str(raised.value)


def test_absent_override_keeps_the_default_endpoint() -> None:
    assert validated_test_redis_url(None) is None


def test_ci_integration_provides_the_explicit_disposable_redis_service() -> None:
    workflow = yaml.safe_load(
        (repo_root_or_skip() / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    )
    job = workflow["jobs"]["test-backend-integration"]
    steps = [step for step in job["steps"] if step.get("run") == "task test:backend:integration"]
    assert len(steps) == 1
    effective_env = {**job.get("env", {}), **steps[0].get("env", {})}
    url = validated_test_redis_url(effective_env.get("TEST_REDIS_URL"))
    assert url is not None, "CI must explicitly supply the disposable Redis endpoint"
    parsed = urlsplit(url)
    is_loopback = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    assert is_loopback, "The host-runner job must use its own Redis service"
    assert parsed.scheme == "redis", "The provisioned CI service does not configure TLS"
    mapping = f"{parsed.port or 6379}:6379"
    assert mapping in job["services"]["redis"]["ports"]


def test_missing_redis_fails_before_database_discovery(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("TEST_REDIS_URL", raising=False)
    database_probe = MagicMock(side_effect=AssertionError("database must not be touched"))
    monkeypatch.setattr(integration_preflight, "_tcp_reachable", database_probe)
    monkeypatch.setattr(integration_preflight, "_check_testcontainers", database_probe)
    with pytest.raises(SystemExit) as raised:
        integration_preflight.main()
    assert raised.value.code == 1
    assert "REDIS-PREFLIGHT: FAILED" in capsys.readouterr().err
    database_probe.assert_not_called()


def test_invalid_redis_fails_without_probing_or_echoing_credentials(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    secret_url = "redis://test-user:canary-test-password@localhost:6379/0"
    monkeypatch.setenv("TEST_REDIS_URL", secret_url)
    probe = MagicMock(side_effect=AssertionError("invalid Redis URL must not be probed"))
    monkeypatch.setattr(integration_preflight, "_tcp_reachable", probe)
    with pytest.raises(SystemExit) as raised:
        integration_preflight._check_test_redis()
    assert raised.value.code == 1
    error = capsys.readouterr().err
    assert "REDIS-PREFLIGHT: FAILED" in error
    assert "canary-test-password" not in error and secret_url not in error
    probe.assert_not_called()


def test_unreachable_redis_fails_with_an_actionable_diagnostic(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("TEST_REDIS_URL", "redis://localhost:16379/15")
    probe = MagicMock(return_value=(False, "localhost:16379"))
    monkeypatch.setattr(integration_preflight, "_tcp_reachable", probe)
    with pytest.raises(SystemExit) as raised:
        integration_preflight._check_test_redis()
    assert raised.value.code == 1
    error = capsys.readouterr().err
    assert "REDIS-PREFLIGHT: FAILED" in error and "unreachable" in error
    probe.assert_called_once_with("redis://localhost:16379/15", default_port=6379)


def test_explicit_redis_is_probed_without_opening_the_application(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("TEST_REDIS_URL", "redis://localhost/15")
    probe = MagicMock(return_value=(True, "localhost:6379"))
    monkeypatch.setattr(integration_preflight, "_tcp_reachable", probe)
    integration_preflight._check_test_redis()
    probe.assert_called_once_with("redis://localhost/15", default_port=6379)
    assert "REDIS-PREFLIGHT: explicit-db (localhost:6379/15)" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("url", "default_port", "endpoint"),
    [
        ("postgresql+asyncpg://localhost/test", 5432, ("localhost", 5432)),
        ("redis://localhost/15", 6379, ("localhost", 6379)),
        ("redis://localhost:16379/15", 6379, ("localhost", 16379)),
        ("redis://[::1]:16379/15", 6379, ("::1", 16379)),
    ],
)
def test_tcp_probe_preserves_the_selected_service_and_explicit_port(
    monkeypatch: pytest.MonkeyPatch,
    url: str,
    default_port: int,
    endpoint: tuple[str, int],
) -> None:
    connect = MagicMock()
    monkeypatch.setattr(socket, "create_connection", connect)
    reachable, _ = integration_preflight._tcp_reachable(url, default_port=default_port)
    assert reachable
    connect.assert_called_once_with(endpoint, timeout=2)
    connect.return_value.__exit__.assert_called_once()


def test_tcp_probe_reports_connection_failure_without_url_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connect = MagicMock(side_effect=ConnectionRefusedError("connection refused"))
    monkeypatch.setattr(socket, "create_connection", connect)
    reachable, endpoint = integration_preflight._tcp_reachable(
        "redis://test-user:canary-test-password@localhost:16379/15", default_port=6379
    )
    assert not reachable
    assert endpoint == "localhost:16379"


def test_standalone_preflight_rejects_missing_redis_before_database_work(tmp_path: Path) -> None:
    env = os.environ.copy()
    env.pop("TEST_REDIS_URL", None)
    env.pop("PYTHONPATH", None)
    env["TEST_DATABASE_URL"] = (
        "postgresql+asyncpg://canary-user:canary-test-password@localhost:1/unused"
    )
    result = subprocess.run(
        [sys.executable, str(Path(integration_preflight.__file__).resolve())],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 1
    assert "REDIS-PREFLIGHT: FAILED" in result.stderr
    assert "DB-PREFLIGHT" not in result.stdout + result.stderr
    assert "canary-test-password" not in result.stdout + result.stderr
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize("job_name", ["test-backend", "test-backend-integration"])
def test_ci_redis_host_prerequisite_runs_before_other_steps(job_name: str) -> None:
    workflow = yaml.safe_load(
        (repo_root_or_skip() / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    )
    job = workflow["jobs"][job_name]
    assert "redis" in job["services"]
    first_step = job["steps"][0]
    assert first_step.get("name") == "Configure Redis host overcommit"
    assert first_step.get("run") == "sudo sysctl -w vm.overcommit_memory=1"


@pytest.mark.parametrize(
    "explicit_endpoints", [True, False], ids=["explicit-urls", "empty-template"]
)
def test_real_bootstrap_preserves_only_nonempty_explicit_test_endpoints(
    tmp_path: Path, explicit_endpoints: bool
) -> None:
    repository = repo_root_or_skip()
    api_root = repository / "apps/api"
    conftest_source = (api_root / "tests/conftest.py").read_text(encoding="utf-8")
    prefix, boundary, _ = conftest_source.partition("\n# ruff: noqa: E402")
    assert boundary, "Exercise environment loading and Redis validation before app imports"

    fake_api = tmp_path / "apps/api"
    fake_tests = fake_api / "tests"
    fake_tests.mkdir(parents=True)
    fake_conftest = fake_tests / "conftest.py"
    fake_conftest.write_text(prefix, encoding="utf-8")
    for package_file in ("__init__.py", "redis_test_url.py"):
        (fake_tests / package_file).write_text(
            (api_root / "tests" / package_file).read_text(encoding="utf-8"), encoding="utf-8"
        )
    (tmp_path / ".env").write_text(
        (repository / ".env.example").read_text(encoding="utf-8"), encoding="utf-8"
    )
    test_values = "DEBUG=false\n"
    if explicit_endpoints:
        # Explicit infrastructure must also survive load_dotenv(override=True).
        test_values += (
            "TEST_DATABASE_URL=postgresql+asyncpg://test:test@127.0.0.1:16544/unused_test\n"
            "TEST_REDIS_URL=redis://127.0.0.1:16380/15\n"
        )
    (fake_api / ".env.test").write_text(test_values, encoding="utf-8")

    # Simulate Task exporting a fresh template-based developer environment.
    # Retain only OS process support, never the calling test suite's endpoints.
    isolated_env = {
        key: os.environ[key]
        for key in ("SYSTEMROOT", "WINDIR", "COMSPEC", "PATH", "TEMP", "TMP")
        if key in os.environ
    }
    isolated_env.update(
        {
            key: value
            for key, value in dotenv_values(tmp_path / ".env", interpolate=False).items()
            if value is not None
        }
    )
    assert isolated_env["TEST_DATABASE_URL"] == ""
    assert isolated_env["TEST_REDIS_URL"] == ""
    expected_database = "postgresql+asyncpg://test:test@127.0.0.1:16543/bootstrap_test"
    expected_redis = "redis://127.0.0.1:16379/15"
    if explicit_endpoints:
        isolated_env.update(TEST_DATABASE_URL=expected_database, TEST_REDIS_URL=expected_redis)
    keys = (
        "TEST_DATABASE_URL",
        "TEST_REDIS_URL",
        "DATABASE_URL",
        "DEFAULT_CURRENCY",
        "SEMANTIC_EXPANSION_EVIDENCE_DRIVEN_ENABLED",
        "DEBUG",
        "REDIS_URL",
        "REDIS_CACHE_DB",
        "REDIS_SESSION_DB",
    )
    runner = (
        "import json, os, runpy, sys\n"
        "from pathlib import Path\n"
        "source = Path(sys.argv[1])\n"
        "sys.path.insert(0, str(source.parent.parent))\n"
        "runpy.run_path(str(source))\n"
        "print(json.dumps({key: os.environ.get(key) for key in sys.argv[2:]}))\n"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", runner, str(fake_conftest), *keys],
        cwd=tmp_path,
        env=isolated_env,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    effective = json.loads(result.stdout)
    assert effective["TEST_DATABASE_URL"] == (expected_database if explicit_endpoints else None)
    assert effective["TEST_REDIS_URL"] == (expected_redis if explicit_endpoints else None)
    for developer_key in (
        "DATABASE_URL",
        "DEFAULT_CURRENCY",
        "SEMANTIC_EXPANSION_EVIDENCE_DRIVEN_ENABLED",
    ):
        assert effective[developer_key] is None
    assert effective["DEBUG"] == "false"
    assert effective["REDIS_CACHE_DB"] == effective["REDIS_SESSION_DB"] == "15"
    if explicit_endpoints:
        assert effective["REDIS_URL"] == expected_redis
