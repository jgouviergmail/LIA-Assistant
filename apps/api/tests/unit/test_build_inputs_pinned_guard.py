"""A production input names a version and a digest (dependency programme, doctrine 4).

A tag that moves is a different image per environment and per day: measured on
2026-09-30, the dev database under the same ``pgvector/pgvector:pg16`` as production
ran PostgreSQL 16.11 from a ten-month-old pull while the registry served 16.15, and on
2026-10-01 ``python:3.14-slim-trixie`` moved to Python 3.14.8 under every image naming
it. So, over what ships — the production compose chain the deploy runs (read where it
is declared, ``deploy_readiness_gate.sh``), the demonstrator's compose and the
Dockerfiles the release builds:

- every image carries a version AND a digest;
- every global install (``npm -g``, ``pip`` outside a hash-checked lockfile) a version;
- every download a checksum verified in the same instruction, and no moving URL (a
  ``latest`` path, a Hugging Face ``resolve/main``).

``apt-get`` packages are out of scope on purpose: they come from signed Debian
repositories, and their security updates are wanted at every build.

Today's debt is a shrink-only baseline (``build_inputs_baseline.json``): a new
violation fails, and so does a baseline entry that no longer occurs — fixing a pin
means deleting its line, never leaving it to excuse a later regression.
"""

from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath
from typing import Any, NamedTuple

import pytest
import yaml

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

REPO_ROOT = repo_root_or_skip()
BASELINE = Path(__file__).with_name("build_inputs_baseline.json")

#: Where the deploy declares the production compose chain (``COMPOSE_FILE`` default).
_CHAIN_DECLARATION = "scripts/deploy/lib/deploy_readiness_gate.sh"
_DEMONSTRATOR_COMPOSE = "docker-compose.demo-instance.yml"
#: The images the release builds (``release.yml``: api, sandbox, web).
_PRODUCTION_DOCKERFILES = (
    "apps/api/Dockerfile.prod",
    "apps/api/Dockerfile.sandbox",
    "apps/web/Dockerfile.prod",
)

_PINNED_IMAGE = re.compile(r"[^\s@]+:[^\s:@/]*\d[^\s:@/]*@sha256:[0-9a-f]{64}")
_URL = re.compile(r"https?://[^\s\"'|;]+")
#: A URL path naming a revision that moves under the same address.
_MOVING = re.compile(r"/latest\b|latest-v|/resolve/main\b")
_DOWNLOAD = re.compile(r"(?:^|[\s;&|(])(?:curl|wget)\s+[^&;|]*(?:https?://|\$\{?\w)")
#: curl/wget option values that are not the download (a User-Agent naming a URL).
_HEADER_VALUES = re.compile(r"\s(?:-A|--user-agent|-H|--header)\s+(?:\"[^\"]*\"|'[^']*'|\S+)")
_CHECKSUM = re.compile(r"\bsha(?:256|512)sum\b|--checksum")
#: ``pip`` options whose next token is their value, not a package.
_PIP_VALUED_OPTIONS = frozenset(
    {
        "-r",
        "--requirement",
        "-c",
        "--constraint",
        "-e",
        "--editable",
        "-i",
        "--index-url",
        "--extra-index-url",
        "--no-binary",
        "--only-binary",
        "-t",
        "--target",
        "--prefix",
        "--root",
    }
)


class Violation(NamedTuple):
    """One production build input that is not pinned."""

    file: str
    rule: str
    subject: str


def _compose_chain() -> list[str]:
    script = (REPO_ROOT / _CHAIN_DECLARATION).read_text(encoding="utf-8")
    match = re.search(r'COMPOSE_FILE:=([^}"]+)\}', script)
    assert match, f"{_CHAIN_DECLARATION} no longer declares the default COMPOSE_FILE chain"
    return match.group(1).split(":")


def _services(name: str) -> dict[str, Any]:
    data = yaml.safe_load((REPO_ROOT / name).read_text(encoding="utf-8")) or {}
    return {service: spec or {} for service, spec in (data.get("services") or {}).items()}


def _built_dockerfile(build: str | dict[str, Any]) -> str:
    """The Dockerfile a compose ``build:`` builds — the short form names only its context."""
    spec = {"context": build} if isinstance(build, str) else build
    return str(PurePosixPath(spec.get("context", ".")) / spec.get("dockerfile", "Dockerfile"))


def _compose_images(name: str, services: dict[str, Any]) -> list[Violation]:
    # ${LIA_*_IMAGE:-…} names an image this repository builds from a Dockerfile it reads.
    return [
        Violation(name, "image without a version and a digest", spec["image"])
        for spec in services.values()
        if spec.get("image")
        and not spec["image"].startswith("${")
        and not _PINNED_IMAGE.fullmatch(spec["image"])
    ]


def _instructions(text: str) -> list[str]:
    """Dockerfile instructions, continuation lines joined, comment lines dropped."""
    joined: list[str] = []
    current = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        continued = line.endswith("\\")
        current = f"{current} {line[:-1] if continued else line}".strip()
        if not continued:
            joined.append(current)
            current = ""
    if current:
        joined.append(current)
    return joined


def _unversioned_npm(command: str) -> list[str]:
    found: list[str] = []
    for segment in re.findall(r"\bnpm\s+(?:install|i)\b([^&;|]*)", command):
        tokens = segment.split()
        if not {"-g", "--global"} & set(tokens):
            continue
        found += [t for t in tokens if not t.startswith("-") and "@" not in t.lstrip("@")]
    return found


def _unversioned_pip(command: str) -> list[str]:
    found: list[str] = []
    for segment in re.findall(r"\bpip3?\s+install\b([^&;|]*)", command):
        tokens = segment.split()
        if "--require-hashes" in tokens:
            continue
        skip_next = False
        for token in tokens:
            if skip_next:
                skip_next = False
            elif token in _PIP_VALUED_OPTIONS:
                skip_next = True
            elif not token.startswith("-") and "==" not in token:
                found.append(token)
    return found


def _dockerfile_inputs(name: str, text: str) -> list[Violation]:
    found: list[Violation] = []
    stages: set[str] = set()
    for instruction in _instructions(text):
        keyword, _, rest = instruction.partition(" ")
        keyword = keyword.upper()
        if keyword == "FROM":
            words = [w for w in rest.split() if not w.startswith("--")]
            if len(words) >= 3 and words[1].upper() == "AS":
                stages.add(words[2].lower())
            if words[0].lower() not in stages and not _PINNED_IMAGE.fullmatch(words[0]):
                found.append(Violation(name, "image without a version and a digest", words[0]))
        elif keyword in {"ARG", "ENV"}:
            found += [
                Violation(name, "download from a moving URL", url)
                for url in _URL.findall(rest)
                if _MOVING.search(url)
            ]
        elif keyword == "RUN":
            found += [
                Violation(name, "global install without a version", package)
                for package in _unversioned_npm(rest) + _unversioned_pip(rest)
            ]
            command = _HEADER_VALUES.sub(" ", rest)
            if _DOWNLOAD.search(command):
                found += [
                    Violation(name, "download from a moving URL", url)
                    for url in _URL.findall(command)
                    if _MOVING.search(url)
                ]
                if not _CHECKSUM.search(command):
                    target = _URL.search(command) or re.search(r"\$\{\w+\}/[^\s\"'|;]*", command)
                    subject = target.group(0) if target else command[:80]
                    found.append(Violation(name, "download without a checksum", subject))
        elif keyword == "ADD" and (url := _URL.search(rest)) and "--checksum" not in rest:
            found.append(Violation(name, "download without a checksum", url.group(0)))
    return found


def _violations() -> list[Violation]:
    found: list[Violation] = []
    for name in [*_compose_chain(), _DEMONSTRATOR_COMPOSE]:
        found += _compose_images(name, _services(name))
    for name in _PRODUCTION_DOCKERFILES:
        found += _dockerfile_inputs(name, (REPO_ROOT / name).read_text(encoding="utf-8"))
    return sorted(set(found))


def test_the_guard_sees_each_kind_of_unpinned_input() -> None:
    dockerfile = (
        "FROM python:3.14-slim AS builder\n"
        "FROM builder AS tests\n"
        "FROM node:24.21.0@sha256:" + "a" * 64 + "\n"
        "ARG MODEL_URL=https://huggingface.co/org/model/resolve/main\n"
        "RUN npm install -g npm@12.1.0 \\\n"
        "    # a comment line inside the instruction\n"
        "    && npm install --allow-scripts=@x/cli -g @x/cli\n"
        "RUN pip install --require-hashes -r lock.txt && pip install -r reqs.txt requests\n"
        "RUN curl -fsSL https://example.org/tool.tgz -o tool.tgz && tar xzf tool.tgz\n"
        'RUN curl -fsSL -A "build (+https://example.org/repo)" -o f "${MODEL_URL}/f"\n'
        'RUN URL="https://example.org/db-${M}.gz"; if curl -fsSL "${URL}" -o db.gz; then :; fi\n'
        "RUN curl -fsSL -o f https://example.org/dist/latest/f && sha256sum -c f.sha256\n"
        "RUN apt-get update && apt-get install -y curl\n"
        "HEALTHCHECK CMD curl -f http://localhost:8000/health\n"
    )
    services = {
        "db": {"image": "pgvector/pgvector:pg16"},
        "proxy": {"image": "ironsh/iron-proxy:0.49.0@sha256:" + "b" * 64},
        "digest-only": {"image": "redis@sha256:" + "c" * 64},
        "api": {"image": "${LIA_API_IMAGE:-lia-api:local}"},
    }

    assert _dockerfile_inputs("D", dockerfile) == [
        Violation("D", "image without a version and a digest", "python:3.14-slim"),
        Violation(
            "D", "download from a moving URL", "https://huggingface.co/org/model/resolve/main"
        ),
        Violation("D", "global install without a version", "@x/cli"),
        Violation("D", "global install without a version", "requests"),
        Violation("D", "download without a checksum", "https://example.org/tool.tgz"),
        Violation("D", "download without a checksum", "${MODEL_URL}/f"),
        Violation("D", "download without a checksum", "https://example.org/db-${M}.gz"),
        Violation("D", "download from a moving URL", "https://example.org/dist/latest/f"),
    ]
    assert _compose_images("C", services) == [
        Violation("C", "image without a version and a digest", "pgvector/pgvector:pg16"),
        Violation("C", "image without a version and a digest", "redis@sha256:" + "c" * 64),
    ]
    assert _built_dockerfile("./apps/api") == "apps/api/Dockerfile"
    assert _built_dockerfile({"context": ".", "dockerfile": "apps/web/Dockerfile.prod"}) == (
        "apps/web/Dockerfile.prod"
    )


def test_production_build_inputs_never_add_to_the_debt() -> None:
    built = {
        _built_dockerfile(spec["build"])
        for name in [*_compose_chain(), _DEMONSTRATOR_COMPOSE]
        for spec in _services(name).values()
        if spec.get("build")
    }
    assert built, "the production compose files build nothing: the chain is read wrong"
    unread = sorted(built - set(_PRODUCTION_DOCKERFILES))
    assert (
        not unread
    ), f"a production compose file builds a Dockerfile this guard does not read: {unread}"

    current = {tuple(v) for v in _violations()}
    baseline = {tuple(entry) for entry in json.loads(BASELINE.read_text(encoding="utf-8"))}
    new = sorted(current - baseline)
    fixed = sorted(baseline - current)
    assert not new, f"new unpinned production input(s) — pin by version and digest: {new}"
    assert (
        not fixed
    ), f"fixed debt still listed — delete these entries from {BASELINE.name}: {fixed}"
