"""The sandbox image holds what the runs are promised, and nothing else (ADR-327 lot 2).

The declaration (``sandbox_toolbox``) is one side of a promise; the two build
inputs are the other. These tests hold them together on the files themselves —
the image is proven by ``task sandbox:libraries:check`` (CI's docker-build job):

- every library is a DIRECT entry of ``requirements-sandbox.txt``, and every
  entry there is declared (a pin nobody promised is a pin nobody checks);
- the Dockerfile installs the package of every declared command, from a base
  pinned by digest, copies nothing but the sandbox lock from the build context,
  verifies every hash, and runs unprivileged — and never installs a Docker
  client;
- Node comes from the official image, pinned by version AND digest in a stage
  of its own (Debian's Node 20 is past its upstream end of life and ignores
  ``HTTPS_PROXY`` in ``fetch``), and the declaration names the major it ships.
"""

from __future__ import annotations

import re
from importlib import import_module
from pathlib import Path

import pytest

from src.domains.agents.python_sandbox.libraries import LIBRARY_GROUPS
from src.domains.skills.sandbox_toolbox import (
    SANDBOX_COMMANDS,
    SANDBOX_LIBRARIES,
    SKILL_LIBRARIES,
    render_toolbox,
)

pytestmark = pytest.mark.unit

_API = Path(__file__).resolve().parents[4]
_MANIFEST = _API / "requirements-sandbox.txt"
_DOCKERFILE = _API / "Dockerfile.sandbox"
_DIRECT = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)", re.M)


def _canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _manifest_entries() -> set[str]:
    lines = [line.split("#", 1)[0] for line in _MANIFEST.read_text(encoding="utf-8").splitlines()]
    return {_canonical(m.group(1)) for line in lines if (m := _DIRECT.match(line))}


def _instructions() -> list[str]:
    """The Dockerfile's instructions, continuation lines joined, comments dropped."""
    text = _DOCKERFILE.read_text(encoding="utf-8")
    text = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    return [line.strip() for line in text.replace("\\\n", " ").splitlines() if line.strip()]


def _apt_packages() -> set[str]:
    packages: set[str] = set()
    for line in _instructions():
        if "apt-get install" in line:
            after = line.split("apt-get install", 1)[1].split("&&", 1)[0]
            packages |= {word for word in after.split() if not word.startswith("-")}
    return packages


class TestTheLibraries:
    def test_every_library_is_declared_once_in_a_known_group(self) -> None:
        names = [library.import_name for library in SANDBOX_LIBRARIES]
        assert len(names) == len(set(names))
        assert {library.group for library in SKILL_LIBRARIES} <= set(LIBRARY_GROUPS)

    def test_the_manifest_pins_exactly_what_is_declared(self) -> None:
        declared = {_canonical(library.distribution) for library in SANDBOX_LIBRARIES}
        entries = _manifest_entries()
        assert declared - entries == set(), "declared but not pinned directly"
        assert entries - declared == set(), "pinned but never declared, so never checked"

    def test_the_skill_libraries_import_on_the_lockfile_ci_installs(self) -> None:
        missing = []
        for library in SKILL_LIBRARIES:
            try:
                import_module(library.import_name)
            except ImportError:
                missing.append(library.import_name)
        assert not missing


_NODE_STAGE = re.compile(
    r"FROM node:(?P<major>\d+)\.\d+\.\d+-bookworm-slim@sha256:[0-9a-f]{64} AS node"
)


class TestTheDockerfile:
    def test_the_final_stage_is_the_apis_python_pinned_by_digest(self) -> None:
        """The last FROM is the image a run starts from: the API's own Python."""
        base = [line for line in _instructions() if line.startswith("FROM ")][-1]
        assert re.fullmatch(r"FROM python:3\.14-slim-trixie@sha256:[0-9a-f]{64}", base)

    def test_node_comes_from_the_official_image_pinned_by_version_and_digest(self) -> None:
        stages = [line for line in _instructions() if line.startswith("FROM ")]
        node = [line for line in stages if _NODE_STAGE.fullmatch(line)]
        assert len(node) == 1, stages
        copies = [line for line in _instructions() if line.startswith("COPY --from=node ")]
        assert copies, "nothing is copied out of the node stage"
        assert not any(
            "nodejs" in p or p == "npm" for p in _apt_packages()
        ), "Debian's Node must not be installed beside the pinned one"

    def test_the_declaration_names_the_node_major_the_image_ships(self) -> None:
        stage = next(m for m in map(_NODE_STAGE.fullmatch, _instructions()) if m)
        node = next(command for command in SANDBOX_COMMANDS if command.name == "node")
        assert node.use == f"Node.js {stage.group('major')}"

    def test_every_declared_command_has_its_package(self) -> None:
        wanted = {command.package for command in SANDBOX_COMMANDS if command.package}
        assert wanted <= _apt_packages()

    def test_no_docker_client_is_ever_installed(self) -> None:
        assert not any("docker" in package for package in _apt_packages())
        assert not any(
            "docker" in line.lower() for line in _instructions() if line.startswith("RUN")
        )

    def test_only_the_sandbox_lock_is_copied_in_from_the_build_context(self) -> None:
        """A copy from a stage brings a pinned image's files; the context brings the lock alone."""
        copies = [
            line
            for line in _instructions()
            if line.startswith(("COPY", "ADD")) and not line.startswith("COPY --from=")
        ]
        assert copies == ["COPY requirements-sandbox.lock.txt /tmp/requirements-sandbox.lock.txt"]
        stages = [line for line in _instructions() if line.startswith("COPY --from=")]
        assert stages and all(line.startswith("COPY --from=node ") for line in stages)

    def test_every_hash_is_verified(self) -> None:
        pip = [line for line in _instructions() if "pip install" in line]
        assert pip and all("--require-hashes" in line for line in pip)

    def test_the_libraries_need_no_pythonpath(self) -> None:
        """System-wide, so uid 65534 reads them (the 2026-08-29 incident)."""
        from src.core.constants import SKILLS_SCRIPT_SANDBOX_PYTHONPATH_DEFAULT

        pip = [line for line in _instructions() if "pip install" in line]
        assert not any("--user" in line for line in pip)
        assert SKILLS_SCRIPT_SANDBOX_PYTHONPATH_DEFAULT == ""

    def test_a_container_started_by_hand_is_not_root(self) -> None:
        assert "USER 65534:65534" in _instructions()


#: The clients a networked command runs (ADR-327 lot 3) and the variable each
#: reads its trusted CA from — without it, the client refuses the proxy's
#: certificate and the run fails on a host it was allowed to reach.
_NETWORK_CLIENTS = {
    "curl": "CURL_CA_BUNDLE",
    "git": "GIT_SSL_CAINFO",
    "npm": "NODE_EXTRA_CA_CERTS",
    "npx": "NODE_EXTRA_CA_CERTS",
    "node": "NODE_EXTRA_CA_CERTS",
    "pip": "PIP_CERT",
    "python3": "SSL_CERT_FILE",
}


def test_every_network_client_is_promised_and_trusts_the_proxy() -> None:
    from src.domains.skills.executor import EgressSpec, egress_args

    names = {command.name for command in SANDBOX_COMMANDS}
    assert set(_NETWORK_CLIENTS) <= names
    args = egress_args(
        EgressSpec(
            network="lia-sandbox",
            proxy_url="http://proxy:8080",
            ca_volume="ca",
            ca_dir="/ca",
            ca_file="/ca/ca.pem",
        )
    )
    for variable in set(_NETWORK_CLIENTS.values()):
        assert f"{variable}=/ca/ca.pem" in args
    # Node's own fetch and http clients follow HTTPS_PROXY only when told to
    # (measured on Node 24: without it, a fetch finds no route).
    assert "NODE_USE_ENV_PROXY=1" in args


def test_the_tools_schema_names_every_command_and_the_fresh_copy_rule() -> None:
    """The ReAct loop and the planner read the tool's schema, never the runner's
    prompt: what a command may call, and that every call starts from a fresh
    copy, must reach them there (ADR-184: the promise the tool keeps)."""
    from src.domains.skills.command_bundle import COMMAND_DESCRIPTION

    for command in SANDBOX_COMMANDS:
        assert command.name in COMMAND_DESCRIPTION, command.name
    assert "fresh copy" in COMMAND_DESCRIPTION and "ONE command" in COMMAND_DESCRIPTION


def test_the_runner_is_told_every_command_and_library() -> None:
    told = render_toolbox()
    for command in SANDBOX_COMMANDS:
        assert command.name in told
    for library in SANDBOX_LIBRARIES:
        assert library.import_name in told
