"""Hermetic fakes of the end-to-end installer flows (B01/B13).

A recording runner, an opener that always answers ready, a clock that never
sleeps, a scripted terminal and a bundle copied from the repository: what the
install, resume and reconfiguration tests drive ``run_install`` with.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from scripts.install.deploy import CommandResult
from scripts.install.model import IOAdapter
from scripts.install.run_context import Deps
from scripts.install.tests.conftest import REPO_ROOT

PASSWORD = "Xx12!!abcdA9$Z"
ANSWERS = {
    "wizard_language": "en",
    "exposure": "lan",
    "server_host": "192.168.1.50",
    "admin_email": "admin@ops.tld",
    "admin_name": "Ops",
    "default_language": "fr",
    "observability": "no",
    "skill_sandbox": "no",
    "personal_radio": "no",
    "speaking_avatar": "no",
    "world": "no",
    "admin_password": PASSWORD,
    "provider_key_deepseek": "dk-CANARY-11",
    "provider_key_openai": "sk-CANARY-22",
}


class _Runner:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def __call__(self, argv, *, stdin=None, env=None):
        self.calls.append({"argv": list(argv), "stdin": stdin})
        return CommandResult(0, "", "")

    def joined(self) -> list[str]:
        return [" ".join(call["argv"]) for call in self.calls]


class _Opener:
    def __call__(self, request, *, timeout):
        class _Resp:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

        return _Resp()


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class _IO:
    def __init__(
        self,
        secrets: dict[str, str] | None = None,
        public: dict[str, str] | None = None,
    ) -> None:
        self.printed: list[str] = []
        self._secrets = dict(secrets or {})
        self._public = public
        self.secret_prompts: list[str] = []
        self.input_prompts: list[str] = []

    def adapter(self) -> IOAdapter:
        def _input(prompt: str) -> str:
            self.input_prompts.append(prompt)
            if self._public is None:
                raise AssertionError(f"unexpected interactive prompt: {prompt}")
            return self._public.get(prompt[1:].split("]", 1)[0], "")

        def _getpass(prompt: str) -> str:
            self.secret_prompts.append(prompt)
            key = prompt[1:].split("]", 1)[0]
            return self._secrets[key]

        return IOAdapter(
            input_fn=_input, getpass_fn=_getpass, print_fn=self.printed.append
        )


def _bundle(tmp_path: Path) -> Path:
    root = tmp_path / "bundle"
    seeds = root / "infrastructure" / "database" / "seeds"
    seeds.mkdir(parents=True)
    for seed in (REPO_ROOT / "infrastructure" / "database" / "seeds").glob("*.sql"):
        shutil.copy(seed, seeds / seed.name)
    shutil.copy(
        REPO_ROOT / "infrastructure" / "caddy" / "Caddyfile.template",
        _mk(root / "infrastructure" / "caddy") / "Caddyfile.template",
    )
    shutil.copy(REPO_ROOT / ".env.min.prod.example", root / ".env.min.prod.example")
    for name in ("docker-compose.prod.yml", "docker-compose.skill-sandbox.yml"):
        shutil.copy(REPO_ROOT / name, root / name)
    return root


def _mk(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _answers_file(root: Path, values: dict[str, str] | None = None) -> Path:
    path = root / "answers.env"
    payload = values if values is not None else ANSWERS
    path.write_text("".join(f"{k}={v}\n" for k, v in payload.items()), encoding="utf-8")
    import os

    if os.name == "posix":
        path.chmod(0o600)
    return path


def _deps(
    root: Path,
    io: _IO | None = None,
    runner: _Runner | None = None,
    docker_socket: Path | None = None,
) -> Deps:
    return Deps(
        root=root,
        io=(io or _IO()).adapter(),
        runner=runner or _Runner(),
        opener=_Opener(),
        clock=_Clock(),
        docker_socket=docker_socket,
    )
