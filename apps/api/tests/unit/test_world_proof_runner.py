"""The disposable proof must neither capture secrets nor remove shared resources."""

import importlib.util
import tarfile
from pathlib import Path
from types import ModuleType
from urllib.error import HTTPError

import pytest

SCRIPT = Path(__file__).resolve().parents[4] / "scripts/world-proof.py"


def load_runner() -> ModuleType:
    """Load the CLI without running it or contacting Docker."""
    spec = importlib.util.spec_from_file_location("world_proof_runner", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_snapshot_refuses_secrets_and_outside_source_paths(tmp_path: Path) -> None:
    runner = load_runner()
    root = tmp_path / "repo"
    root.mkdir()
    (root / "src").mkdir()
    (root / "src/app.py").write_text("value = 1", encoding="utf-8")
    (root / ".env").write_text("PRIVATE", encoding="utf-8")
    archive = tmp_path / "snapshot.tar"
    runner.snapshot(root, [Path("src/app.py"), Path(".env")], archive)
    with tarfile.open(archive) as source:
        assert source.getnames() == ["src/app.py"]
    with pytest.raises(ValueError, match="outside"):
        runner.snapshot(root, [Path("../outside")], archive)


def test_cleanup_refuses_a_container_owned_by_another_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = load_runner()
    calls: list[tuple[str, ...]] = []

    def docker(*args: str) -> str:
        calls.append(args)
        return '[{"Config":{"Labels":{"lia.task":"shared-development"}}}]'

    monkeypatch.setattr(runner, "docker", docker)
    with pytest.raises(RuntimeError, match="ownership"):
        runner.remove_owned("world-qa-api")
    assert not any("rm" in call for call in calls)


def test_generated_proof_environment_is_isolated_and_never_copies_provider_keys() -> None:
    runner = load_runner()
    first, second = runner.proof_environment(), runner.proof_environment()
    assert first["WORLD_NAMESPACE"] == "world-qualification-proof"
    assert "@world-proof-postgres:5432/world_qualification" in first["DATABASE_URL"]
    assert "@world-proof-redis:6379/0" in first["REDIS_URL"]
    assert first["SECRET_KEY"] != second["SECRET_KEY"]
    assert first["FERNET_KEY"] != second["FERNET_KEY"]
    assert not any(name.startswith(("OPENAI_", "ANTHROPIC_", "GOOGLE_")) for name in first)


def test_network_creation_failure_erases_temporary_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = load_runner()

    def docker(*args: str) -> str:
        if args[0] == "compose":
            return '{"services":{}}'
        if args[:2] == ("network", "create"):
            raise RuntimeError("network unavailable")
        return ""

    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "exists", lambda *_: False)
    monkeypatch.setattr(runner, "docker", docker)
    with pytest.raises(RuntimeError, match="network unavailable"):
        runner.start("development", 3012, "api", "web")
    assert not (tmp_path / ".tmp/world-proof/runtime.env").exists()


def test_web_readiness_waits_through_build_and_requires_the_inert_auth_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = load_runner()
    statuses = iter((503, 401))
    reads: list[str] = []
    waits: list[float] = []

    def urlopen(url: str, *, timeout: int) -> None:
        assert timeout == 2
        reads.append(url)
        raise HTTPError(url, next(statuses), "proof fixture", None, None)

    monkeypatch.setattr(runner, "urlopen", urlopen, raising=False)
    monkeypatch.setattr(runner.time, "sleep", waits.append)
    runner.wait_web("http://127.0.0.1:3012")
    assert reads == ["http://127.0.0.1:3012/api/v1/world-proof/me"] * 2
    assert waits == [1]


def test_web_readiness_has_a_bounded_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = load_runner()
    times = iter((0, 601))
    monkeypatch.setattr(runner.time, "monotonic", lambda: next(times))
    with pytest.raises(RuntimeError, match="did not become ready"):
        runner.wait_web("http://127.0.0.1:3012")
