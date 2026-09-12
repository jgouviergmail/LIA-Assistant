"""The production launcher supervises the workers without importing the app.

``uvicorn.main.run`` (0.48) calls ``config.load_app()`` in the SUPERVISOR before
spawning the workers, for an early "Error loading ASGI app" message, and throws
the result away. Measured on the production Raspberry Pi on 2026-09-12: the
supervisor held 437 MB (389 MB anonymous, every native library of the
application mapped) while serving no request; the demonstrator's held 407 MB.
``src.serve`` drives the same ``Config`` → ``Server`` → ``Multiprocess`` chain
minus that one call. These tests pin what the launcher must keep from the CLI
(every flag the image passes, the worker count from ``WEB_CONCURRENCY``, the
startup-failure exit code) and the one thing it must never do.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

import pytest

from src import serve
from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

SERVE_MODULE = Path(serve.__file__)
IMAGE_ARGV = [
    "src.main:app",
    "--host",
    "0.0.0.0",
    "--port",
    "8000",
    "--limit-max-requests",
    "10000",
    "--limit-max-requests-jitter",
    "1000",
    "--proxy-headers",
    "--forwarded-allow-ips",
    "*",
    "--timeout-graceful-shutdown",
    "20",
]


class _NeverImported:
    """Stands in for ``import_from_string``: the supervisor must not reach it."""

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError(f"the supervisor imported the application: {args} {kwargs}")


class _FakeMultiprocess:
    instances: list[_FakeMultiprocess] = []

    def __init__(self, config: Any, target: Any, sockets: list[Any]) -> None:
        self.config = config
        self.target = target
        self.sockets = sockets
        self.ran = False
        _FakeMultiprocess.instances.append(self)

    def run(self) -> None:
        self.ran = True


class _FakeServer:
    started = True

    def __init__(self, config: Any) -> None:
        self.config = config
        self.runs = 0

    def run(self, sockets: list[Any] | None = None) -> None:
        self.runs += 1


class TestTheFlagsTheImagePasses:
    def test_every_flag_of_the_image_maps_onto_uvicorn_config(self) -> None:
        config = serve.build_config(IMAGE_ARGV)

        assert config.app == "src.main:app"
        assert config.host == "0.0.0.0"
        assert config.port == 8000
        assert config.limit_max_requests == 10000
        assert config.limit_max_requests_jitter == 1000
        assert config.proxy_headers is True
        assert config.forwarded_allow_ips == "*"
        assert config.timeout_graceful_shutdown == 20

    def test_workers_follow_web_concurrency_like_the_cli(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("WEB_CONCURRENCY", "4")
        assert serve.build_config(IMAGE_ARGV).workers == 4

        monkeypatch.delenv("WEB_CONCURRENCY")
        assert serve.build_config(IMAGE_ARGV).workers == 1

    def test_an_explicit_worker_count_wins_over_the_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("WEB_CONCURRENCY", "4")
        assert serve.build_config([*IMAGE_ARGV, "--workers", "2"]).workers == 2

    def test_proxy_headers_default_on_like_the_cli_and_can_be_switched_off(self) -> None:
        without_flag = [flag for flag in IMAGE_ARGV if flag != "--proxy-headers"]
        assert serve.build_config(without_flag).proxy_headers is True
        assert serve.build_config([*without_flag, "--no-proxy-headers"]).proxy_headers is False


class TestTheSupervisorNeverImportsTheApplication:
    @pytest.fixture(autouse=True)
    def _fakes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _FakeMultiprocess.instances.clear()
        monkeypatch.setattr("uvicorn.config.import_from_string", _NeverImported())
        monkeypatch.setattr(serve, "Multiprocess", _FakeMultiprocess)
        monkeypatch.setattr(serve, "Server", _FakeServer)
        monkeypatch.setattr(serve.Config, "bind_socket", lambda self: "the-socket")

    def test_multi_worker_mode_binds_once_and_hands_the_workers_to_multiprocess(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("WEB_CONCURRENCY", "4")

        code = serve.main(["a.module.that.must.not.be.imported:app", "--port", "0"])

        assert code == 0
        (supervisor,) = _FakeMultiprocess.instances
        assert supervisor.ran is True
        assert supervisor.sockets == ["the-socket"]
        assert supervisor.config.workers == 4
        assert supervisor.target.__self__.config is supervisor.config
        assert supervisor.target.__func__ is _FakeServer.run

    def test_single_worker_mode_serves_in_process(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("WEB_CONCURRENCY", raising=False)

        code = serve.main(["a.module.that.must.not.be.imported:app", "--port", "0"])

        assert code == 0
        assert _FakeMultiprocess.instances == []

    def test_single_worker_startup_failure_keeps_uvicorn_exit_code(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("WEB_CONCURRENCY", raising=False)
        monkeypatch.setattr(_FakeServer, "started", False)

        assert serve.main(["a.module:app", "--port", "0"]) == serve.STARTUP_FAILURE


class TestTheLauncherStaysLight:
    """A launcher that imports ``src.*`` at module level pays what it exists to avoid."""

    def test_module_level_imports_never_reach_the_application(self) -> None:
        tree = ast.parse(SERVE_MODULE.read_text(encoding="utf-8"))
        offenders: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                offenders.extend(a.name for a in node.names if a.name.split(".")[0] == "src")
            elif isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "src":
                offenders.append(node.module or "")
        assert offenders == [], f"src.serve imports the application: {offenders}"

    def test_module_never_asks_uvicorn_to_load_the_app(self) -> None:
        tree = ast.parse(SERVE_MODULE.read_text(encoding="utf-8"))
        calls = [
            node.attr if isinstance(node, ast.Attribute) else node.id
            for node in ast.walk(tree)
            if (isinstance(node, ast.Attribute) and node.attr == "load_app")
            or (isinstance(node, ast.Name) and node.id == "import_from_string")
        ]
        assert calls == [], f"src.serve reaches the app import: {calls}"


class TestTheImageUsesIt:
    def test_dockerfile_prod_launches_through_the_light_supervisor(self) -> None:
        dockerfile = repo_root_or_skip() / "apps" / "api" / "Dockerfile.prod"
        if not dockerfile.is_file():
            pytest.skip("guard needs the full repository checkout (Dockerfile.prod).")
        text = dockerfile.read_text(encoding="utf-8")
        match = re.search(r"^CMD\s+(\[.+?\])\s*$", text, re.MULTILINE | re.DOTALL)
        assert match, "Dockerfile.prod must declare CMD in JSON exec form"
        tokens = re.findall(r'"([^"]*)"', match.group(1))

        assert tokens[:3] == ["python", "-m", "src.serve"], tokens
        assert tokens[3] == "src.main:app"
        assert "--workers" not in tokens, "WEB_CONCURRENCY governs the worker count"
        assert "--timeout-graceful-shutdown" in tokens
