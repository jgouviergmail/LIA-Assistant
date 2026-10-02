"""Dependency watch: what the pull-request gates cannot see, read on a schedule.

Dependency programme, lot 4 (ADR-331, doctrine 2: what a gate cannot see is not
safe, it is unseen). ``task deps:watch`` reads four sources the gates never
consult, against the exact versions the repository pins:

- the security advisories each dependency's OWN repository publishes. The review
  of 2026-09-30 found twenty whose range held a locked version and none of them
  in GitHub's global database — so pip-audit, pnpm audit, Trivy and Dependabot
  all answered « no known vulnerability »;
- the end-of-life dates of the product lines the repository pins
  (endoflife.date), each line derived from the file that pins it;
- registry facts: an image that no longer exists, or has no arm64 variant where
  production runs it (a Raspberry Pi), a deprecated npm release, a yanked PyPI
  release;
- the browser engine: the Chromium an image build installs from Debian
  (decision D8) against the majors Chrome still supports.

Every finding is accepted in ``dependency_watch_accepted.json`` — reason, owner,
review date — or the run fails; so does an acceptance past its date, or one that
matches nothing. A source that does not answer is named with what it did not
read: a partial scan is never reported as a clean one.

It never runs in a pull-request gate (ADR-112: a network answer must never turn a
pull request red): weekly in ``.github/workflows/dependency-watch.yml``, which
keeps ONE issue up to date, and at every release.

Usage: ``task deps:watch`` (``-- --report <file>`` also writes the Markdown).
GitHub's API is read with ``GITHUB_TOKEN``/``GH_TOKEN`` or ``gh auth token``:
anonymously it answers sixty requests an hour, a tenth of one scan.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, TypeVar
from urllib.parse import quote

import yaml
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "scripts" / "audit")]

import doc_facts  # noqa: E402 - the sibling registry of quoted versions (doctrine 1)
from check_requirements_lock import parse_lock  # noqa: E402

ACCEPTED = Path(__file__).with_name("dependency_watch_accepted.json")
KINDS = frozenset(
    {
        "advisory",
        "end-of-life",
        "image-missing",
        "image-no-arm64",
        "npm-deprecated",
        "pypi-yanked",
        "browser-engine",
    }
)

#: Every Python lockfile of the repository: the API's three, the wake-word toolbox's two.
_PYTHON_LOCKS = (
    "apps/api/requirements.lock.txt",
    "apps/api/requirements-dev.lock.txt",
    "apps/api/requirements-sandbox.lock.txt",
    "scripts/wake-word/requirements.lock.txt",
    "scripts/wake-word/requirements-gpu.lock.txt",
)
_PNPM_LOCK = "pnpm-lock.yaml"
_E2E_LOCK = "apps/web/e2e/package-lock.json"
_NESTED_COMPOSE = (
    "infrastructure/docker/compose.services.yml",
    "scripts/install/tests/runtime/docker-compose.disposable.yml",
)
_DOCKERFILES = (
    "apps/api/Dockerfile.prod",
    "apps/api/Dockerfile.sandbox",
    "apps/api/Dockerfile.dev",
    "apps/web/Dockerfile.prod",
    "apps/web/Dockerfile.dev",
    "scripts/wake-word/Dockerfile",
    "scripts/wake-word/Dockerfile.gpu",
)
#: What runs on the production host: the deploy chain is read where it is declared.
_CHAIN_DECLARATION = "scripts/deploy/lib/deploy_readiness_gate.sh"
_PRODUCTION = (
    "docker-compose.demo-instance.yml",
    "scripts/install/self_host_dependencies.json",
    "apps/api/Dockerfile.prod",
    "apps/api/Dockerfile.sandbox",
    "apps/web/Dockerfile.prod",
)
#: endoflife.date product, how many version components name its cycle, doc_facts key.
_FACT_LINES = (
    ("python", 2, "python"),
    ("nodejs", 1, "node"),
    ("nextjs", 1, "next"),
    ("react", 1, "react"),
    ("postgresql", 1, "postgres"),
    ("redis", 2, "redis"),
    ("prometheus", 2, "prometheus"),
    ("grafana", 2, "grafana"),
    ("grafana-loki", 2, "loki"),
)
#: An image repository whose tag names a product line, and how.
_IMAGE_LINES = (
    ("python", "debian", re.compile(r"-(bookworm|trixie|forky)\b")),
    ("caddy", "caddy", re.compile(r"^(\d+)")),
    ("ubuntu/squid", "squid", re.compile(r"^(\d+)\.")),
    ("ubuntu/squid", "ubuntu", re.compile(r"-(\d+\.\d+)_")),
)
_DEBIAN_POOLS = (
    "https://deb.debian.org/debian-security/pool/updates/main/c/chromium/",
    "https://deb.debian.org/debian/pool/main/c/chromium/",
)
_ACCEPT_MANIFEST = ", ".join(
    (
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.v2+json",
    )
)
_USER_AGENT = "lia-dependency-watch"
_WORKERS = 12
_GITHUB_WORKERS = 6
_MAX_PAGES = 10

T = TypeVar("T")
R = TypeVar("R")


# --------------------------------------------------------------------------- the web


@dataclass(frozen=True)
class Answer:
    """One HTTP answer: status, body, headers."""

    status: int
    body: bytes
    headers: Mapping[str, str]

    def json(self) -> Any:
        """The body as JSON."""
        return json.loads(self.body)

    def header(self, name: str) -> str:
        """A header, whatever the case the server wrote it in."""
        return next((v for k, v in self.headers.items() if k.lower() == name.lower()), "")


Get = Callable[[str, Mapping[str, str]], Answer]


def http_get(url: str, headers: Mapping[str, str]) -> Answer:
    """GET with one retry on a network failure or a server error.

    A credential is sent to the host asked and never to a host a redirect names:
    urllib forwards a request's own headers to wherever it is redirected, and a
    registry redirects its blobs to a CDN.
    """
    plain = {k: v for k, v in headers.items() if k.lower() != "authorization"}
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT, **plain})
    for name, value in headers.items():
        if name.lower() == "authorization":
            request.add_unredirected_header(name, value)
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - https
                return Answer(response.status, response.read(), dict(response.headers))
        except urllib.error.HTTPError as error:
            if error.code < 500 or attempt == 2:
                return Answer(error.code, error.read(), dict(error.headers or {}))
        except urllib.error.URLError, TimeoutError:
            if attempt == 2:
                raise
    raise AssertionError("unreachable")


def _json(get: Get, url: str, headers: Mapping[str, str] | None = None) -> Any:
    answer = get(url, headers or {})
    if answer.status != 200:
        raise LookupError(f"HTTP {answer.status}")
    return answer.json()


def _parallel(
    work: Callable[[T], R], items: list[T], workers: int = _WORKERS
) -> list[tuple[R | None, str | None]]:
    def attempt(item: T) -> tuple[R | None, str | None]:
        try:
            return work(item), None
        except Exception as error:  # noqa: BLE001 - every failure is named in the report
            return None, f"{type(error).__name__}: {str(error)[:80]}"

    with ThreadPoolExecutor(workers) as pool:
        return list(pool.map(attempt, items))


# --------------------------------------------------------------------------- findings


@dataclass(frozen=True, order=True)
class Finding:
    """Something a person must decide: fix it, or accept it in writing."""

    kind: str
    subject: str
    detail: str
    ref: str = ""


@dataclass
class Coverage:
    """How much of one source was read, and what was not."""

    label: str
    total: int = 0
    read: int = 0
    unread: list[str] = field(default_factory=list)

    def count(self, item: str, error: str | None) -> None:
        """Record one item read, or not read and why."""
        self.total += 1
        if error is None:
            self.read += 1
        else:
            self.unread.append(f"{item}: {error}")


def _quoted(text: str, limit: int = 140) -> str:
    # Third-party words (an advisory's summary, a deprecation notice) reach an
    # issue body: a code span renders no link, no image and no markup.
    flat = " ".join(text.split()).replace("`", "'")
    return f"`{flat[:limit]}{'…' if len(flat) > limit else ''}`"


# --------------------------------------------------------------------------- range reader

_TOKEN = re.compile(r"(<=|>=|==|<|>|=)?\s*v?(\d[\w.+*?-]*)")
_WILDCARD = re.compile(r"^(\d+(?:\.\d+)*)\.[xX*]$")
#: A fix not released yet, written by its line: ``16.3.?``.
_PLACEHOLDER = re.compile(r"(\d+(?:\.\d+)*)\.\?")
_UPPER_BOUNDS = frozenset({"<", "<=", "=", "=="})


def _next_line(parts: list[int]) -> Version:
    """The first release after a line: 11.0 -> 11.1, 16 -> 17."""
    return Version(".".join(map(str, [*parts[:-1], parts[-1] + 1])))


def _loose_version(text: str) -> Version | None:
    """A PEP 440 version, or the release part of an npm one (``14.3.0-canary.77``)."""
    text = text.strip().lstrip("vV").rstrip(",")
    for candidate in (text, re.split(r"[-+]", text, maxsplit=1)[0]):
        try:
            return Version(candidate)
        except InvalidVersion:
            continue
    return None


def _holds(version: Version, operator: str, bound: Version) -> bool:
    return {
        "<": version < bound,
        "<=": version <= bound,
        ">": version > bound,
        ">=": version >= bound,
    }.get(operator, version == bound)


def _bounds(alternative: str) -> list[tuple[str, Version]] | None:
    """The comparators of one alternative; ``None`` when one cannot be read."""
    bounds: list[tuple[str, Version]] = []
    for operator, raw in _TOKEN.findall(alternative):
        if wildcard := _WILDCARD.match(raw):  # 11.0.x: the 11.0 line
            base = [int(part) for part in wildcard.group(1).split(".")]
            bounds += [(">=", Version(".".join(map(str, base)))), ("<", _next_line(base))]
            continue
        if placeholder := _PLACEHOLDER.fullmatch(raw):  # < 16.3.?: below some 16.3 release
            base = [int(part) for part in placeholder.group(1).split(".")]
            if operator in ("<", "<="):
                bounds.append(("<", _next_line(base)))
            else:
                bounds.append((operator or ">=", Version(".".join(map(str, base)))))
            continue
        if raw.endswith("+") and not operator:  # 8+: from 8 on
            operator, raw = ">=", raw[:-1]
        version = _loose_version(raw)
        if version is None:
            return None
        bounds.append((operator or "=", version))
    return bounds


def _patched_on_its_line(version: Version, patched: str | None) -> bool:
    """Whether ``version`` is at or past the fix of its own release line.

    ``patched`` often lists one fix per line (``v16.0.7, v15.5.7, v15.4.8``): the
    fix of a version is the one on its major and minor, else on its major; a
    version on a line with no listed fix is patched only past every listed one.
    A fix announced but not released (``16.3.?``) patches nothing on its line.
    """
    text = patched or ""
    pending = [[int(p) for p in m.split(".")] for m in _PLACEHOLDER.findall(text)]
    raws = re.findall(r"\d[\w.+-]*", _PLACEHOLDER.sub(" ", text))
    fixes = [v for raw in raws if (v := _loose_version(raw))]
    if not fixes and not pending:
        return False
    release = [*version.release, 0]
    for width in (2, 1):
        same_line = [fix for fix in fixes if [*fix.release, 0][:width] == release[:width]]
        if same_line:
            return version >= min(same_line)
        if any(line[:width] == release[:width] for line in pending):
            return False
    return all(version > fix for fix in fixes) and all(
        version >= _next_line(line) for line in pending
    )


def range_contains(vulnerable: str, locked: str, patched: str | None) -> bool:
    """Whether an advisory's vulnerable range holds ``locked``.

    Ranges are written by hand: ``>= 6.7.0, <= 6.9.0``, ``*``, ``8+``,
    ``>=10.2.0 <10.5.0 || 11.0.x``, three open lower bounds for three release
    lines. A bounded alternative is read as written. An open one (« every version
    from X on », or no bound at all) is how a maintainer writes « until the fix »
    when the fix is in ``patched``: a version at or past the fix of its own line
    is no hit — the review's 28 false positives and the first run's were all of
    that shape. What cannot be read is kept for a person, unless the version is
    past its line's fix anyway.
    """
    parsed = _loose_version(locked)
    if parsed is None:
        return True
    version = Version(parsed.public)  # an advisory speaks of releases, not of local builds
    open_hit = unreadable = False
    for alternative in vulnerable.split("||"):
        bounds = _bounds(alternative)
        if bounds is None:
            unreadable = True
        elif any(op in _UPPER_BOUNDS for op, _ in bounds):
            if all(_holds(version, op, bound) for op, bound in bounds):
                return True
        else:  # open: from the lowest bound written (three lines, three bounds), or all
            lowest = min(bounds, key=lambda bound: bound[1], default=None)
            open_hit = open_hit or lowest is None or _holds(version, *lowest)
    return (open_hit or unreadable) and not _patched_on_its_line(version, patched)


# --------------------------------------------------------------------------- registries

_GITHUB_URL = re.compile(r"github\.com[/:]([\w.-]+)/([\w.-]+?)(?:\.git)?(?:[/#?]|$)")
_SHORTHAND = re.compile(r"^(?:github:)?([\w.-]+)/([\w.-]+?)(?:\.git)?$")
_NOT_A_PROJECT = frozenset({"sponsors", "orgs", "apps", "marketplace", "features"})
_SOURCE_KEYS = ("source", "repository", "github", "homepage")


def github_repo(*texts: str | None) -> str | None:
    """The first ``owner/name`` of a GitHub project among these links."""
    for text in texts:
        if not text:
            continue
        match = _GITHUB_URL.search(text)
        if match is None and "://" not in text:
            match = _SHORTHAND.match(text.strip())
        if match and match.group(1).lower() not in _NOT_A_PROJECT and match.group(2) != ".github":
            return f"{match.group(1)}/{match.group(2)}"
    return None


def pypi_facts(payload: Mapping[str, Any]) -> tuple[str | None, str | None]:
    """(repository, yank reason) from PyPI's JSON for one release."""
    info = payload.get("info") or {}
    urls: dict[str, str] = info.get("project_urls") or {}

    def rank(label: str) -> int:
        return next((i for i, key in enumerate(_SOURCE_KEYS) if key in label.lower()), 9)

    ranked = [url for _, url in sorted(urls.items(), key=lambda item: rank(item[0]))]
    repo = github_repo(*ranked, info.get("home_page"), info.get("download_url"))
    yanked = (info.get("yanked_reason") or "yanked") if info.get("yanked") else None
    return repo, yanked


def npm_facts(payload: Mapping[str, Any]) -> tuple[str | None, str | None]:
    """(repository, deprecation notice) from the npm registry's document for one release."""
    repository = payload.get("repository")
    url = repository.get("url") if isinstance(repository, dict) else repository
    bugs = payload.get("bugs")
    repo = github_repo(
        url if isinstance(url, str) else None,
        payload.get("homepage"),
        bugs.get("url") if isinstance(bugs, dict) else None,
    )
    deprecated = payload.get("deprecated")
    return repo, deprecated if isinstance(deprecated, str) and deprecated else None


UrlOf = Callable[[str, str], str]
FactsOf = Callable[[Mapping[str, Any]], tuple[str | None, str | None]]


def _pypi_url(name: str, version: str) -> str:
    # A local build (torch 2.14.1+cpu, from PyTorch's index) is its public release on PyPI.
    public = _loose_version(version)
    return f"https://pypi.org/pypi/{quote(name)}/{quote(public.public if public else version)}/json"


def _npm_url(name: str, version: str) -> str:
    return f"https://registry.npmjs.org/{quote(name, safe='@')}/{quote(version)}"


# --------------------------------------------------------------------------- lockfiles

_PNPM_PACKAGE = re.compile(r"^  '?((?:@[^@/'\s]+/)?[^@/'\s]+)@([^'(:\s]+)'?:\s*$")


def pnpm_locked(text: str) -> dict[str, set[str]]:
    """``name -> versions`` from the ``packages:`` section of a pnpm lockfile."""
    found: dict[str, set[str]] = {}
    section = ""
    for line in text.splitlines():
        if line and not line[0].isspace():
            section = line.split(":", 1)[0]
        elif section == "packages" and (match := _PNPM_PACKAGE.match(line)):
            found.setdefault(match.group(1), set()).add(match.group(2))
    return found


def npm_lock_locked(data: Mapping[str, Any]) -> dict[str, set[str]]:
    """``name -> versions`` from an npm ``package-lock.json`` (v2/v3)."""
    found: dict[str, set[str]] = {}
    for key, meta in (data.get("packages") or {}).items():
        if key and not meta.get("link") and "version" in meta:
            found.setdefault(key.rsplit("node_modules/", 1)[-1], set()).add(meta["version"])
    return found


# --------------------------------------------------------------------------- inventory


@dataclass(frozen=True)
class Line:
    """A product line the repository pins: endoflife.date's product and cycle."""

    product: str
    cycle: str
    source: str


@dataclass
class Inventory:
    """What the repository pins, read offline."""

    python: dict[str, set[str]]
    npm: dict[str, set[str]]
    images: dict[str, list[str]]
    production_images: set[str]
    lines: list[Line]


def _merge(into: dict[str, set[str]], more: Mapping[str, set[str]]) -> None:
    for name, versions in more.items():
        into.setdefault(name, set()).update(versions)


def _production_files(root: Path) -> set[str]:
    script = (root / _CHAIN_DECLARATION).read_text(encoding="utf-8")
    match = re.search(r'COMPOSE_FILE:=([^}"]+)\}', script)
    if match is None:
        raise LookupError(f"{_CHAIN_DECLARATION} no longer declares the COMPOSE_FILE chain")
    return {*match.group(1).split(":"), *_PRODUCTION}


def _image_references(root: Path) -> dict[str, list[str]]:
    refs: dict[str, list[str]] = {}

    def add(ref: str | None, where: str) -> None:
        if ref and "${" not in ref and not ref.startswith("lia-"):
            refs.setdefault(ref, []).append(where)

    composes = [p.name for p in sorted(root.glob("docker-compose*.yml"))] + list(_NESTED_COMPOSE)
    for name in composes:
        services = (yaml.safe_load((root / name).read_text(encoding="utf-8")) or {}).get("services")
        for spec in (services or {}).values():
            add((spec or {}).get("image"), name)
    for name in _DOCKERFILES:
        stages: set[str] = set()
        for line in (root / name).read_text(encoding="utf-8").splitlines():
            words = [w for w in line.split() if not w.startswith("--")]
            if len(words) >= 2 and words[0].upper() == "FROM":
                if words[1].lower() not in stages and words[1] != "scratch":
                    add(words[1], name)
                if len(words) >= 4 and words[2].upper() == "AS":
                    stages.add(words[3].lower())
    for path in sorted((root / ".github" / "workflows").glob("*.yml")):
        for job in (
            (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("jobs", {}).values()
        ):
            container = job.get("container")
            if isinstance(container, (str, dict)):  # `container: image` or a mapping
                image = container if isinstance(container, str) else container.get("image")
                add(image, f".github/workflows/{path.name}")
            for service in (job.get("services") or {}).values():
                add(service.get("image"), f".github/workflows/{path.name}")
    catalogue = root / "scripts/install/self_host_dependencies.json"
    for entry in json.loads(catalogue.read_text(encoding="utf-8")):
        add(entry["reference"], "scripts/install/self_host_dependencies.json")
    return refs


def _repo_and_tag(ref: str) -> tuple[str, str]:
    name = ref.split("@", 1)[0]
    if ":" in name.rsplit("/", 1)[-1]:
        name, _, tag = name.rpartition(":")
        return name, tag
    return name, "latest"


def _product_lines(root: Path, images: Mapping[str, list[str]]) -> list[Line]:
    lines: list[Line] = []
    facts = {fact.key: fact for fact in doc_facts.FACTS}
    for product, parts, key in _FACT_LINES:
        value = facts[key].resolve(root)
        lines.append(
            Line(product, ".".join(value.split(".")[:parts]), facts[key].source.split()[0])
        )
    ci = yaml.safe_load((root / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    for job in ci["jobs"].values():
        for step in job.get("steps") or []:
            if "setup-python" in str(step.get("uses", "")) and (step.get("with") or {}).get(
                "python-version"
            ):
                lines.append(
                    Line("python", str(step["with"]["python-version"]), ".github/workflows/ci.yml")
                )
    manager = json.loads((root / "package.json").read_text(encoding="utf-8"))["packageManager"]
    lines.append(Line("pnpm", manager.removeprefix("pnpm@").split(".")[0], "package.json"))
    web = json.loads((root / "apps/web/package.json").read_text(encoding="utf-8"))
    eslint = {**web.get("dependencies", {}), **web.get("devDependencies", {})}["eslint"]
    lines.append(Line("eslint", eslint.lstrip("^~>=<").split(".")[0], "apps/web/package.json"))
    for ref, places in sorted(images.items()):
        repo, tag = _repo_and_tag(ref)
        for image, product, pattern in _IMAGE_LINES:
            if repo == image and (match := pattern.search(tag)):
                lines.append(Line(product, match.group(1), places[0]))
    unique: dict[tuple[str, str], Line] = {}
    for line in lines:
        unique.setdefault((line.product, line.cycle), line)
    return list(unique.values())


def inventory(root: Path) -> Inventory:
    """Every pinned package, image and product line of the repository."""
    python: dict[str, set[str]] = {}
    for lock in _PYTHON_LOCKS:
        _merge(python, parse_lock(root / lock))
    npm = pnpm_locked((root / _PNPM_LOCK).read_text(encoding="utf-8"))
    _merge(npm, npm_lock_locked(json.loads((root / _E2E_LOCK).read_text(encoding="utf-8"))))
    images = _image_references(root)
    production = _production_files(root)
    in_production = {ref for ref, places in images.items() if production & set(places)}
    return Inventory(python, npm, images, in_production, _product_lines(root, images))


# --------------------------------------------------------------------------- advisories


def _canonical(ecosystem: str, name: str) -> str:
    return canonicalize_name(name) if ecosystem == "pip" else name.lower()


def advisory_findings(
    ecosystem: str, locked: Mapping[str, set[str]], advisories: Iterable[Mapping[str, Any]]
) -> list[Finding]:
    """The advisories of one repository whose range holds a locked version."""
    findings: list[Finding] = []
    named: set[str] = set()  # one advisory names a locked version once, whatever its entries
    wanted = {_canonical(ecosystem, name): versions for name, versions in locked.items()}
    for advisory in advisories:
        if advisory.get("state") != "published" or advisory.get("withdrawn_at"):
            continue
        named.clear()
        for vulnerability in advisory.get("vulnerabilities") or []:
            package = vulnerability.get("package") or {}
            if str(package.get("ecosystem", "")).lower() != ecosystem:
                continue
            name = _canonical(ecosystem, str(package.get("name", "")))
            patched = vulnerability.get("patched_versions")
            for version in sorted(wanted.get(name, ())):
                subject = f"{ecosystem}:{name}@{version}"
                if subject in named:
                    continue
                if range_contains(
                    vulnerability.get("vulnerable_version_range") or "", version, patched
                ):
                    named.add(subject)
                    detail = (
                        f"{advisory.get('severity', '?')}, patched in {patched or 'no release'}: "
                        + _quoted(advisory.get("summary") or "")
                    )
                    findings.append(
                        Finding("advisory", subject, detail, advisory.get("ghsa_id") or "")
                    )
    return findings


def _github_headers(token: str | None) -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    return headers | ({"Authorization": f"Bearer {token}"} if token else {})


def _repository_advisories(repo: str, get: Get, headers: Mapping[str, str]) -> list[Any] | None:
    """A repository's published advisories; ``None`` when the repository is gone."""
    url: str | None = f"https://api.github.com/repos/{repo}/security-advisories?per_page=100"
    collected: list[Any] = []
    for _ in range(_MAX_PAGES):
        assert url is not None
        answer = get(url, headers)
        if answer.status == 404:
            return None
        if answer.status != 200:
            limited = answer.header("X-RateLimit-Remaining") == "0"
            raise LookupError("rate limited" if limited else f"HTTP {answer.status}")
        collected += answer.json()
        next_page = re.search(r'<([^>]+)>;\s*rel="next"', answer.header("Link"))
        url = next_page.group(1) if next_page else None
        if url is None:
            return collected
    raise LookupError(f"more than {_MAX_PAGES} pages")


# --------------------------------------------------------------------------- end of life


def eol_finding(line: Line, payload: Mapping[str, Any], today: date) -> Finding | None:
    """A finding when the line is past its end of life; ``LookupError`` for an unknown cycle."""
    wanted = line.cycle.lower()
    release = next(
        (
            r
            for r in payload["result"]["releases"]
            if r["name"].lower() == wanted or str(r.get("codename") or "").lower() == wanted
        ),
        None,
    )
    if release is None:
        raise LookupError(f"endoflife.date knows no {line.product} cycle {line.cycle}")
    eol = release.get("eolFrom")
    if release.get("isEol") or (eol and date.fromisoformat(eol) <= today):
        since = f" since {eol}" if eol else ""
        return Finding(
            "end-of-life", f"{line.product} {line.cycle}", f"end of life{since} ({line.source})"
        )
    return None


# --------------------------------------------------------------------------- images


def split_image(ref: str) -> tuple[str, str, str]:
    """(registry host, repository, tag or digest) of an image reference."""
    name, _, digest = ref.partition("@")
    host = "registry-1.docker.io"
    parts = name.split("/")
    if len(parts) > 1 and ("." in parts[0] or ":" in parts[0] or parts[0] == "localhost"):
        host, name = parts[0], "/".join(parts[1:])
    if host == "docker.io":
        host = "registry-1.docker.io"
    repository, tag = _repo_and_tag(name)
    if host == "registry-1.docker.io" and "/" not in repository:
        repository = f"library/{repository}"
    return host, repository, digest or tag


def _registry_token(challenge: str, get: Get) -> str:
    params = dict(re.findall(r'(\w+)="([^"]*)"', challenge))
    if "realm" not in params:
        raise LookupError("the registry asks for credentials it does not describe")
    url = f"{params['realm']}?service={params.get('service', '')}&scope={params.get('scope', '')}"
    data = _json(get, url)
    token = data.get("token") or data.get("access_token")
    if not token:  # never read as a missing image: the registry did not answer the question
        raise LookupError("the registry gave no token")
    return str(token)


def image_findings(ref: str, get: Get, *, require_arm64: bool = True) -> list[Finding]:
    """An image the registry no longer serves, or serves without arm64 where it must."""
    host, repository, reference = split_image(ref)
    url = f"https://{host}/v2/{repository}/manifests/{reference}"
    headers = {"Accept": _ACCEPT_MANIFEST}
    answer = get(url, headers)
    if answer.status == 401:
        headers["Authorization"] = (
            f"Bearer {_registry_token(answer.header('WWW-Authenticate'), get)}"
        )
        answer = get(url, headers)
    if answer.status in (401, 403, 404):  # past a token: gone, or no longer public
        return [Finding("image-missing", ref, f"the registry answers {answer.status}")]
    if answer.status != 200:
        raise LookupError(f"HTTP {answer.status}")
    if not require_arm64:
        return []
    document = answer.json()
    if "manifests" in document:
        platforms = {
            f"{m['platform']['os']}/{m['platform']['architecture']}"
            for m in document["manifests"]
            if m.get("platform")
        } - {"unknown/unknown"}
    else:  # one image, one platform: its config says which
        config = _json(
            get, f"https://{host}/v2/{repository}/blobs/{document['config']['digest']}", headers
        )
        platforms = {f"{config.get('os')}/{config.get('architecture')}"}
    if "linux/arm64" in platforms:
        return []
    return [Finding("image-no-arm64", ref, "platforms: " + ", ".join(sorted(platforms)))]


# --------------------------------------------------------------------------- browser engine

_POOL_PACKAGE = re.compile(r"chromium_(\d+)\.[\d.]+-[\w.+]*~deb(\d+)u\d+_(amd64|arm64)\.deb")
#: Chrome ships a major every two weeks and Debian's security archive follows within
#: days: a major out of support for less than this is Debian catching up, not a finding.
_ENGINE_GRACE_DAYS = 14


def browser_findings(
    chrome: Mapping[str, Any], pool_listing: str, debian: str, today: date
) -> list[Finding]:
    """Whether the Chromium Debian ships for the base image is a major Chrome supports."""
    releases = {str(r["name"]): r for r in chrome["result"]["releases"]}
    supported = sorted(name for name, r in releases.items() if r.get("isMaintained"))
    newest: dict[str, int] = {}
    for major, release, arch in _POOL_PACKAGE.findall(pool_listing):
        if release == debian:
            newest[arch] = max(newest.get(arch, 0), int(major))
    findings = []
    for arch in ("amd64", "arm64"):
        major = newest.get(arch)
        ended = (releases.get(str(major)) or {}).get("eolFrom")
        if major is not None and str(major) in supported:
            continue
        if ended and (today - date.fromisoformat(ended)).days < _ENGINE_GRACE_DAYS:
            continue
        ships = f"ships {major}" if major else "ships no chromium"
        since = f", out of Chrome's support since {ended}" if major and ended else ""
        findings.append(
            Finding(
                "browser-engine",
                f"chromium {arch}",
                f"Debian {debian} security {ships}{since}; Chrome supports {', '.join(supported)}",
            )
        )
    return findings


# --------------------------------------------------------------------------- the scan


@dataclass
class Report:
    """Everything one run found, and how much it read."""

    findings: list[Finding]
    coverage: list[Coverage]
    without_repository: list[str]


def _registries(
    inv: Inventory, get: Get, findings: list[Finding], coverage: list[Coverage]
) -> tuple[dict[str, dict[str, dict[str, set[str]]]], list[str]]:
    repos: dict[str, dict[str, dict[str, set[str]]]] = {}
    without: set[str] = set()
    sources: tuple[tuple[str, dict[str, set[str]], str, UrlOf, FactsOf, str], ...] = (
        ("pip", inv.python, "PyPI releases", _pypi_url, pypi_facts, "pypi-yanked"),
        ("npm", inv.npm, "npm releases", _npm_url, npm_facts, "npm-deprecated"),
    )
    for ecosystem, locked, label, url_of, facts_of, kind in sources:
        cover = Coverage(label)
        pairs = sorted((name, version) for name, versions in locked.items() for version in versions)
        answers = _parallel(lambda pair: facts_of(_json(get, url_of(*pair))), pairs)
        for (name, version), (facts, error) in zip(pairs, answers, strict=True):
            cover.count(f"{name}@{version}", error)
            if facts is None:
                continue
            repo, flag = facts
            if flag:
                findings.append(Finding(kind, f"{ecosystem}:{name}@{version}", _quoted(flag)))
            if repo:
                repos.setdefault(repo.lower(), {}).setdefault(ecosystem, {}).setdefault(
                    name, set()
                ).add(version)
            else:
                without.add(f"{ecosystem}:{name}")
        coverage.append(cover)
    return repos, sorted(without)


def _advisories(
    repos: Mapping[str, dict[str, dict[str, set[str]]]], get: Get, token: str | None
) -> tuple[list[Finding], Coverage, list[str]]:
    findings: list[Finding] = []
    cover = Coverage("repository advisories")
    gone: list[str] = []
    headers = _github_headers(token)
    names = sorted(repos)
    answers = _parallel(lambda r: _repository_advisories(r, get, headers), names, _GITHUB_WORKERS)
    for repo, (listing, failure) in zip(names, answers, strict=True):
        cover.count(repo, failure)
        if failure is not None:
            continue
        if listing is None:  # the repository is gone: nothing of its own can be read
            gone += [f"{e}:{n}" for e, locked in repos[repo].items() for n in locked]
            continue
        for ecosystem, locked in repos[repo].items():
            findings += advisory_findings(ecosystem, locked, listing)
    return findings, cover, gone


def _end_of_life(
    lines: Iterable[Line], get: Get, today: date, products: dict[str, Any]
) -> tuple[list[Finding], Coverage]:
    findings: list[Finding] = []
    cover = Coverage("end-of-life lines")
    for line in lines:
        try:
            if line.product not in products:
                url = f"https://endoflife.date/api/v1/products/{line.product}/"
                products[line.product] = _json(get, url)
            finding = eol_finding(line, products[line.product], today)
        except Exception as failure:  # noqa: BLE001 - named in the report
            cover.count(f"{line.product} {line.cycle}", f"{type(failure).__name__}: {failure}")
            continue
        cover.count(f"{line.product} {line.cycle}", None)
        findings += [finding] if finding else []
    return findings, cover


def _images(inv: Inventory, get: Get) -> tuple[list[Finding], Coverage]:
    findings: list[Finding] = []
    cover = Coverage("images")
    refs = sorted(inv.images)
    answers = _parallel(
        lambda ref: image_findings(ref, get, require_arm64=ref in inv.production_images), refs
    )
    for ref, (found, failure) in zip(refs, answers, strict=True):
        cover.count(ref, failure)
        findings += found or []
    return findings, cover


def _browser_engine(
    inv: Inventory, get: Get, products: Mapping[str, Any], today: date
) -> tuple[list[Finding], Coverage]:
    cover = Coverage("browser engine")
    try:
        codename = next(line.cycle for line in inv.lines if line.product == "debian")
        debian = products.get("debian") or _json(
            get, "https://endoflife.date/api/v1/products/debian/"
        )
        release = next(
            r["name"]
            for r in debian["result"]["releases"]
            if str(r.get("codename", "")).lower() == codename
        )
        chrome = _json(get, "https://endoflife.date/api/v1/products/chrome/")
        pools = "".join(_text(get, pool) for pool in _DEBIAN_POOLS)
        findings = browser_findings(chrome, pools, release, today)
    except Exception as failure:  # noqa: BLE001 - named in the report
        cover.count("chromium", f"{type(failure).__name__}: {failure}")
        return [], cover
    cover.count("chromium", None)
    return findings, cover


def _text(get: Get, url: str) -> str:
    answer = get(url, {})
    if answer.status != 200:
        raise LookupError(f"HTTP {answer.status}")
    return answer.body.decode("utf-8", "replace")


def scan(inv: Inventory, get: Get, today: date, token: str | None) -> Report:
    """Read every source for what the inventory pins."""
    findings: list[Finding] = []
    coverage: list[Coverage] = []
    repos, without = _registries(inv, get, findings, coverage)
    found, cover, gone = _advisories(repos, get, token)
    findings += found
    coverage.append(cover)
    products: dict[str, Any] = {}
    for found, cover in (
        _end_of_life(inv.lines, get, today, products),
        _images(inv, get),
        _browser_engine(inv, get, products, today),
    ):
        findings += found
        coverage.append(cover)
    return Report(sorted(set(findings)), coverage, sorted({*without, *gone}))


# --------------------------------------------------------------------------- judgement


@dataclass
class Verdict:
    """The findings against the written acceptances."""

    accepted: list[tuple[Finding, dict[str, Any]]] = field(default_factory=list)
    unaccepted: list[Finding] = field(default_factory=list)
    expired: list[dict[str, Any]] = field(default_factory=list)
    stale: list[dict[str, Any]] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        """Nothing left to decide."""
        return not (self.unaccepted or self.expired or self.stale)


def judge(
    findings: Iterable[Finding], acceptances: Iterable[dict[str, Any]], today: date
) -> Verdict:
    """Each finding is accepted, or to decide; each acceptance is current and used."""
    by_key = {(a["kind"], a["subject"], a.get("ref", "")): a for a in acceptances}
    verdict = Verdict()
    used: set[tuple[str, str, str]] = set()
    for finding in findings:
        key = (finding.kind, finding.subject, finding.ref)
        acceptance = by_key.get(key)
        if acceptance is None:
            verdict.unaccepted.append(finding)
            continue
        used.add(key)
        if date.fromisoformat(acceptance["review_by"]) < today:
            verdict.expired.append(acceptance)
        else:
            verdict.accepted.append((finding, acceptance))
    verdict.stale = [a for key, a in by_key.items() if key not in used]
    return verdict


# --------------------------------------------------------------------------- report


def _cell(text: str) -> str:
    return text.replace("|", "\\|")


def render_coverage(coverage: Iterable[Coverage]) -> str:
    """One line per source: how much of it was read."""
    return "\n".join(f"- {c.label}: {c.read} of {c.total} read" for c in coverage)


def render(report: Report, verdict: Verdict, today: date) -> str:
    """The Markdown report (the weekly issue's body)."""
    unread = [item for c in report.coverage for item in (f"{c.label} — {u}" for u in c.unread)]
    to_decide = len(verdict.unaccepted) + len(verdict.expired) + len(verdict.stale)
    state = "nothing to decide" if verdict.clean else f"{to_decide} to decide"
    parts = [
        f"# Dependency watch — {today.isoformat()}",
        "",
        f"**{state}**, {len(unread)} item(s) not read. Run `task deps:watch` to reproduce; "
        "accept a finding in `scripts/audit/dependency_watch_accepted.json` (reason, owner, "
        "review date) or fix it.",
        "",
        "## Read",
        render_coverage(report.coverage),
        f"- {len(report.without_repository)} package(s) publish no GitHub repository: their own "
        "advisories cannot be read.",
    ]
    if verdict.unaccepted:
        parts += ["", "## To decide", "| Kind | Subject | Advisory | Detail |", "|---|---|---|---|"]
        parts += [
            f"| {f.kind} | {_cell(f.subject)} | {f.ref} | {_cell(f.detail)} |"
            for f in verdict.unaccepted
        ]
    if verdict.expired:
        parts += ["", "## Acceptances past their review date"]
        parts += [
            f"- {a['kind']} {a['subject']} {a.get('ref', '')}: {a['review_by']}"
            for a in verdict.expired
        ]
    if verdict.stale:
        parts += ["", "## Acceptances that match nothing (delete them)"]
        parts += [f"- {a['kind']} {a['subject']} {a.get('ref', '')}" for a in verdict.stale]
    if unread:
        parts += ["", "## Not read", *(f"- {_cell(item)}" for item in unread)]
    if verdict.accepted:
        parts += ["", "## Accepted", "| Kind | Subject | Review by | Reason |", "|---|---|---|---|"]
        parts += [
            f"| {f.kind} | {_cell(f.subject)} {f.ref} | {a['review_by']} | {_cell(a['reason'])} |"
            for f, a in verdict.accepted
        ]
    if report.without_repository:
        parts += ["", "<details><summary>Packages with no GitHub repository</summary>", ""]
        parts += [", ".join(report.without_repository), "", "</details>"]
    return "\n".join(parts) + "\n"


def _github_token() -> str | None:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        return token
    try:
        found = subprocess.run(  # noqa: S603, S607 - the GitHub CLI, when installed
            ["gh", "auth", "token"], capture_output=True, text=True, timeout=15, check=False
        )
    except OSError, subprocess.TimeoutExpired:
        return None
    return found.stdout.strip() or None


def main(argv: list[str] | None = None) -> int:
    """Run the watch; 1 when anything is left to decide or was not read."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--report", type=Path, help="also write the Markdown report here")
    args = parser.parse_args(argv)
    if isinstance(sys.stdout, io.TextIOWrapper):  # a Windows console is not UTF-8
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    today = datetime.now(UTC).date()
    report = scan(inventory(ROOT), http_get, today, _github_token())
    verdict = judge(report.findings, json.loads(ACCEPTED.read_text(encoding="utf-8")), today)
    text = render(report, verdict, today)
    print(text)
    if args.report:
        args.report.write_text(text, encoding="utf-8")
    complete = all(not c.unread for c in report.coverage)
    return 0 if verdict.clean and complete else 1


if __name__ == "__main__":
    sys.exit(main())
