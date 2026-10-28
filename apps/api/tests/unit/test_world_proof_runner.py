"""The disposable proof must neither capture secrets nor remove shared resources."""

import ast
import importlib.util
import tarfile
from pathlib import Path
from types import ModuleType, SimpleNamespace
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


def test_parallel_proof_instance_never_targets_default_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = load_runner()
    runner.configure_instance("interactions-01a17aa3")
    assert runner.NETWORK == "lia-world-qa-interactions-01a17aa3"
    assert runner.NAMES["api"] == "lia-world-qa-interactions-01a17aa3-api"
    calls: list[tuple[str, ...]] = []

    def docker(*args: str) -> str:
        calls.append(args)
        return '[{"Config":{"Labels":{"lia.task":"world-proof","lia.instance":"other"}}}]'

    monkeypatch.setattr(runner, "docker", docker)
    with pytest.raises(RuntimeError, match="ownership"):
        runner.remove_owned(runner.NAMES["api"])
    assert not any("rm" in call for call in calls)
    assert all("lia-world-qa-api" not in call for call in calls)


@pytest.mark.parametrize(
    "instance", ["../outside", "a:b", "UPPER", "", "a" * 33, "access", "api", "postgres"]
)
def test_proof_instance_rejects_ambiguous_or_escaping_names(instance: str) -> None:
    runner = load_runner()
    with pytest.raises(ValueError, match="instance"):
        runner.configure_instance(instance)


def test_the_default_proof_refuses_an_instance_resource(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = load_runner()
    calls: list[tuple[str, ...]] = []

    def docker(*args: str) -> str:
        calls.append(args)
        return '[{"Labels":{"lia.task":"world-proof","lia.instance":"interactions-01a17aa3"}}]'

    monkeypatch.setattr(runner, "docker", docker)
    with pytest.raises(RuntimeError, match="ownership"):
        runner.remove_owned(runner.ACCESS_NETWORK, "network")
    assert not any("rm" in call for call in calls)


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


@pytest.mark.parametrize("database", [0, 2, 14])
def test_integration_always_selects_disposable_redis_database(
    monkeypatch: pytest.MonkeyPatch, database: int
) -> None:
    runner = load_runner()
    captured: list[str] = []

    def docker(*args: str) -> str:
        captured.append(args[-1])
        return ""

    monkeypatch.setattr(runner, "require_owned", lambda _: None)
    monkeypatch.setattr(runner, "docker", docker)
    runner.integration()
    tree = ast.parse(captured[0])
    assignment = next(
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Subscript)
        and isinstance(node.targets[0].slice, ast.Constant)
        and node.targets[0].slice.value == "TEST_REDIS_URL"
    )
    expression = ast.Expression(assignment.value)
    selected = eval(
        compile(expression, "proof-redis-selection", "eval"),
        {
            "__builtins__": {},
            "os": SimpleNamespace(
                environ={"REDIS_URL": f"redis://world-proof-redis:6379/{database}"}
            ),
        },
    )
    assert selected == "redis://world-proof-redis:6379/15"
