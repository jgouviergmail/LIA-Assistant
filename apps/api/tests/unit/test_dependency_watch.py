"""The dependency watch reads what the gates cannot see, and says what it did not read.

Dependency programme, lot 4 (ADR-331). ``scripts/audit/dependency_watch.py``
reads four sources the pull-request gates never consult — the repository-level
advisories of every locked package (the review found twenty that GitHub's
global database, hence pip-audit, pnpm audit and Dependabot, did not carry),
end-of-life dates, registry facts and the browser engine's support — and
holds every finding to a written, dated acceptance.

Every test here runs on answers recorded from the real services (trimmed to
the fields read), never on the network: a network answer must never turn a
pull request red (ADR-112).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Mapping
from datetime import date
from types import ModuleType
from typing import Any

import pytest

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

REPO_ROOT = repo_root_or_skip()
SCRIPT = REPO_ROOT / "scripts" / "audit" / "dependency_watch.py"
_MODULE_NAME = "_lia_dependency_watch"

TODAY = date(2026, 10, 2)


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


watch = _load()


class FakeWeb:
    """Recorded answers by URL; an unrecorded URL is a test error, not a silent miss."""

    def __init__(self, answers: Mapping[str, Any]) -> None:
        self.answers = dict(answers)
        self.asked: list[tuple[str, dict[str, str]]] = []

    def __call__(self, url: str, headers: Mapping[str, str]) -> Any:
        self.asked.append((url, dict(headers)))
        # A registry answers the same URL differently once a token is presented.
        authorized = url + "#authorized"
        answer = self.answers[
            authorized if "Authorization" in headers and authorized in self.answers else url
        ]
        if isinstance(answer, Exception):
            raise answer
        if isinstance(answer, watch.Answer):
            return answer
        return watch.Answer(200, json.dumps(answer).encode(), {})


# --------------------------------------------------------------------------- range reader

# The repository advisories of the review that matched a locked version only
# because their range is open-ended (« every version from X on ») while the
# patched field says where the fix landed — recorded from GitHub on 2026-10-02.
OPEN_ENDED_BUT_PATCHED = [
    ("aiohttp", "3.14.3", ">=3.10.6", "3.10.11"),
    ("aiohttp", "3.14.3", ">1.0.5", "3.9.2"),
    ("cbor2", "5.9.0", ">5.5.1", "5.6.2"),
    ("cryptography", "50.0.0", ">= 44.0.0", "50.0.0"),
    ("cryptography", "50.0.0", ">=0.5", "48.0.1"),
    ("cryptography", "50.0.0", ">=45.0.0", ">=46.0.7"),
    ("cryptography", "50.0.0", ">3.1", "3.3.2+"),
    ("pyjwt", "2.15.1", ">= 1.5.0", "2.4.0"),
    ("pyopenssl", "26.4.0", ">=22.0.0", ">=26.0.0"),
    ("starlette", "1.3.1", ">=0.13.5", "0.27.0"),
    ("tqdm", "4.67.3", ">= 4.4.0", "4.66.3"),
]

# Real hits of the same scan, and their release.
BOUNDED = [
    ("multidict", "6.7.1", ">= 6.7.0, <= 6.9.0", "6.9.1", True),
    ("multidict", "6.9.1", ">= 6.7.0, <= 6.9.0", "6.9.1", False),
    ("maxminddb", "3.1.1", "< 3.2.0", "3.2.0", True),
    ("mcp", "2.0.0", ">= 2.0.0a1, < 2.2.0", "2.2.0", True),
    ("@capacitor/android", "8.5.0", ">= 8.5.0, < 8.5.1", "8.5.1", True),
    ("@capacitor/android", "8.5.2", ">= 8.5.0, < 8.5.1", "8.5.1", False),
    ("@bufbuild/protobuf", "1.10.1", "<= 2.16.0", "2.16.0", True),
]


@pytest.mark.parametrize(("package", "locked", "vulnerable", "patched"), OPEN_ENDED_BUT_PATCHED)
def test_an_open_range_the_lock_is_past_is_no_hit(
    package: str, locked: str, vulnerable: str, patched: str
) -> None:
    assert not watch.range_contains(vulnerable, locked, patched), package


@pytest.mark.parametrize(("package", "locked", "vulnerable", "patched", "hit"), BOUNDED)
def test_a_bounded_range_is_read_as_written(
    package: str, locked: str, vulnerable: str, patched: str, hit: bool
) -> None:
    assert watch.range_contains(vulnerable, locked, patched) is hit, package


def test_an_open_range_with_no_fix_and_an_unreadable_range_are_kept() -> None:
    assert watch.range_contains(">= 1.0", "2.0.0", None)
    # Kept for a person to read rather than dropped by a parser that did not understand.
    assert watch.range_contains("all versions before the rewrite", "2.0.0", None)
    # vercel/next.js GHSA-cjq9-62q9-8jv4, verbatim: the fix is « 16.3.? ».
    assert watch.range_contains(">= 16.0.0 < 16.3.?", "16.3.8", "16.3.?")


# The shapes maintainers write by hand, recorded from the first real run of the
# watch (2026-10-02): a wildcard, a « + », an alternative, an npm prerelease, and
# one fix per release line.
HAND_WRITTEN = [
    ("@eslint/plugin-kit", "0.4.1", "*", "0.2.3", False),
    ("@eslint/plugin-kit", "0.2.2", "*", "0.2.3", True),
    ("mermaid", "11.16.1", "8+", "9.1.2", False),
    ("mermaid", "9.0.0", "8+", "9.1.2", True),
    ("glob", "13.0.6", ">=10.2.0 <10.5.0 || 11.0.x", "10.5.0, 11.1.0, 12.0.0", False),
    ("glob", "11.0.3", ">=10.2.0 <10.5.0 || 11.0.x", "10.5.0, 11.1.0, 12.0.0", True),
    ("glob", "10.3.0", ">=10.2.0 <10.5.0 || 11.0.x", "10.5.0, 11.1.0, 12.0.0", True),
    (
        "next",
        "16.3.8",
        ">=14.3.0-canary.77, >=15, >=16",
        "v16.0.7, v15.5.7, v15.4.8, 15.6.0-canary.58, 16.1.0-canary.12",
        False,
    ),
    (
        "next",
        "15.5.6",
        ">=14.3.0-canary.77, >=15, >=16",
        "v16.0.7, v15.5.7, v15.4.8, 15.6.0-canary.58, 16.1.0-canary.12",
        True,
    ),
]


def test_a_fix_not_yet_released_is_read_on_its_own_line() -> None:
    # vercel/next.js GHSA-4jqv-mc3x-m676, verbatim: one entry per release line,
    # each fix a placeholder. The 15.x entry is past for 16.3.8; the 16.x one is not.
    assert watch.range_contains(">= 15.0.0", "16.3.8", "15.5.?") is False
    assert watch.range_contains(">= 16.0.0", "16.3.8", "16.3.?") is True
    assert watch.range_contains(">= 15.0.0", "15.5.2", "15.5.?") is True
    assert watch.range_contains(">= 16.0.0 < 16.3.?", "16.4.0", "16.3.?") is False


def test_one_advisory_names_a_locked_version_once() -> None:
    advisory = {
        "ghsa_id": "GHSA-4jqv-mc3x-m676",
        "state": "published",
        "severity": "medium",
        "summary": "Cache poisoning",
        "vulnerabilities": [
            {
                "package": {"ecosystem": "npm", "name": "next"},
                "vulnerable_version_range": ">= 16.0.0",
                "patched_versions": "16.3.?",
            },
            {
                "package": {"ecosystem": "npm", "name": "next"},
                "vulnerable_version_range": ">= 16.1.0",
                "patched_versions": None,
            },
        ],
    }

    findings = watch.advisory_findings("npm", {"next": {"16.3.8"}}, [advisory])

    assert [(f.subject, f.ref) for f in findings] == [("npm:next@16.3.8", "GHSA-4jqv-mc3x-m676")]


def test_a_local_build_is_read_as_its_public_release() -> None:
    # The wake-word toolbox locks torch from the PyTorch CPU index: PyPI knows
    # 2.14.1, not 2.14.1+cpu, and an advisory's range speaks of the public release.
    assert watch._pypi_url("torch", "2.14.1+cpu") == "https://pypi.org/pypi/torch/2.14.1/json"
    assert watch.range_contains("< 2.14.1", "2.14.1+cpu", "2.14.1") is False
    assert watch.range_contains("<= 2.14.1", "2.14.1+cpu", None) is True


@pytest.mark.parametrize(("package", "locked", "vulnerable", "patched", "hit"), HAND_WRITTEN)
def test_a_hand_written_range_is_read_the_way_its_author_meant_it(
    package: str, locked: str, vulnerable: str, patched: str, hit: bool
) -> None:
    assert watch.range_contains(vulnerable, locked, patched) is hit, package


# --------------------------------------------------------------------------- registries

PYPI_MULTIDICT = {  # https://pypi.org/pypi/multidict/6.9.1/json, trimmed
    "info": {
        "name": "multidict",
        "version": "6.9.1",
        "project_urls": {
            "CI: GitHub": "https://github.com/aio-libs/multidict/actions",
            "Code of Conduct": "https://github.com/aio-libs/.github/blob/master/CODE_OF_CONDUCT.md",
            "Homepage": "https://github.com/aio-libs/multidict",
        },
        "home_page": "https://github.com/aio-libs/multidict",
        "yanked": False,
        "yanked_reason": None,
    }
}
NPM_PROTOBUF = {  # https://registry.npmjs.org/@bufbuild%2fprotobuf/1.10.1, trimmed
    "name": "@bufbuild/protobuf",
    "version": "1.10.1",
    "repository": {
        "url": "git+https://github.com/bufbuild/protobuf-es.git",
        "type": "git",
        "directory": "packages/protobuf",
    },
    "deprecated": None,
}
NPM_KATEX_DEPRECATED = {  # https://registry.npmjs.org/katex/0.18.11, trimmed
    "name": "katex",
    "version": "0.18.11",
    "repository": {"url": "git+https://github.com/KaTeX/KaTeX.git", "type": "git"},
    "deprecated": "Accidentally published with breaking changes. Use 0.19.0 instead.",
}


def test_a_repository_is_read_from_the_registry_metadata() -> None:
    assert watch.pypi_facts(PYPI_MULTIDICT) == ("aio-libs/multidict", None)
    assert watch.npm_facts(NPM_PROTOBUF) == ("bufbuild/protobuf-es", None)
    # npm's shorthand forms, and links that are not a project's repository.
    assert watch.github_repo("github:owner/name") == "owner/name"
    assert watch.github_repo("owner/name") == "owner/name"
    assert watch.github_repo("https://github.com/sponsors/someone") is None
    assert watch.github_repo("https://github.com/aio-libs/.github") is None
    assert watch.github_repo("https://gitlab.com/owner/name") is None


def test_a_yanked_or_deprecated_release_is_a_finding() -> None:
    yanked = {"info": {**PYPI_MULTIDICT["info"], "yanked": True, "yanked_reason": "broken wheel"}}

    assert watch.pypi_facts(yanked) == ("aio-libs/multidict", "broken wheel")
    assert watch.npm_facts(NPM_KATEX_DEPRECATED) == (
        "KaTeX/KaTeX",
        "Accidentally published with breaking changes. Use 0.19.0 instead.",
    )


# --------------------------------------------------------------------------- lockfiles

PNPM_LOCK = """lockfileVersion: '9.0'

importers:

  .:
    devDependencies:
      next:
        specifier: 16.3.8
        version: 16.3.8

packages:

  '@bufbuild/protobuf@1.10.1':
    resolution: {integrity: sha512-x}

  katex@0.18.9:
    resolution: {integrity: sha512-y}

  vite@8.1.5:
    resolution: {integrity: sha512-z}

snapshots:

  vite@8.1.5(@types/node@24.0.0):
    dependencies: {}
"""

E2E_LOCK = {
    "packages": {
        "": {"name": "lia-e2e"},
        "node_modules/@playwright/test": {"version": "1.60.0"},
        "node_modules/a/node_modules/playwright-core": {"version": "1.60.0"},
        "node_modules/linked": {"link": True},
    }
}


def test_the_locks_are_read_the_way_the_package_managers_write_them() -> None:
    assert watch.pnpm_locked(PNPM_LOCK) == {
        "@bufbuild/protobuf": {"1.10.1"},
        "katex": {"0.18.9"},
        "vite": {"8.1.5"},
    }
    assert watch.npm_lock_locked(E2E_LOCK) == {
        "@playwright/test": {"1.60.0"},
        "playwright-core": {"1.60.0"},
    }


# --------------------------------------------------------------------------- advisories

ADVISORIES_MULTIDICT = [  # GET /repos/aio-libs/multidict/security-advisories, trimmed
    {
        "ghsa_id": "GHSA-54p9-h82j-f925",
        "cve_id": None,
        "state": "published",
        "withdrawn_at": None,
        "severity": "medium",
        "summary": "Hash collision in the C implementation",
        "vulnerabilities": [
            {
                "package": {"ecosystem": "pip", "name": "multidict"},
                "vulnerable_version_range": ">= 6.7.0, <= 6.9.0",
                "patched_versions": "6.9.1",
            }
        ],
    },
    {  # withdrawn advisories never count
        "ghsa_id": "GHSA-0000-0000-0000",
        "state": "published",
        "withdrawn_at": "2026-01-01T00:00:00Z",
        "severity": "high",
        "summary": "withdrawn",
        "vulnerabilities": [
            {
                "package": {"ecosystem": "pip", "name": "multidict"},
                "vulnerable_version_range": "< 99",
                "patched_versions": None,
            }
        ],
    },
]


def test_an_advisory_names_the_locked_versions_it_contains() -> None:
    locked = {"multidict": {"6.7.1", "6.9.1"}}

    findings = watch.advisory_findings("pip", locked, ADVISORIES_MULTIDICT)

    assert [(f.kind, f.subject, f.ref) for f in findings] == [
        ("advisory", "pip:multidict@6.7.1", "GHSA-54p9-h82j-f925")
    ]


# --------------------------------------------------------------------------- end of life

GRAFANA_EOL = {  # https://endoflife.date/api/v1/products/grafana/, trimmed
    "result": {
        "releases": [
            {"name": "13.2", "eolFrom": "2027-05-18", "isEol": False},
            {"name": "11.3", "eolFrom": "2025-07-22", "isEol": True},
        ]
    }
}
DEBIAN_EOL = {
    "result": {
        "releases": [
            {"name": "13", "codename": "Trixie", "eolFrom": "2030-06-30", "isEol": False},
            {"name": "11", "codename": "Bullseye", "eolFrom": "2026-08-31", "isEol": True},
        ]
    }
}


def test_an_end_of_life_line_is_a_finding_and_an_unknown_cycle_is_unread() -> None:
    old = watch.Line("grafana", "11.3", "docker-compose.prod.yml")
    current = watch.Line("grafana", "13.2", "docker-compose.prod.yml")
    debian = watch.Line("debian", "trixie", "apps/api/Dockerfile.prod")

    assert watch.eol_finding(old, GRAFANA_EOL, TODAY) == watch.Finding(
        "end-of-life", "grafana 11.3", "end of life since 2025-07-22 (docker-compose.prod.yml)"
    )
    assert watch.eol_finding(current, GRAFANA_EOL, TODAY) is None
    assert watch.eol_finding(debian, DEBIAN_EOL, TODAY) is None  # a codename reads as its cycle
    with pytest.raises(LookupError):
        watch.eol_finding(watch.Line("grafana", "99.9", "x"), GRAFANA_EOL, TODAY)


# --------------------------------------------------------------------------- images

_HUB_TOKEN = (
    "https://auth.docker.io/token?service=registry.docker.io&scope=repository:library/redis:pull"
)
_CHALLENGE = {
    "WWW-Authenticate": 'Bearer realm="https://auth.docker.io/token",'
    'service="registry.docker.io",scope="repository:library/redis:pull"'
}


def _index(*platforms: str) -> dict[str, Any]:
    return {
        "mediaType": "application/vnd.oci.image.index.v1+json",
        "manifests": [
            {"platform": {"os": p.split("/")[0], "architecture": p.split("/")[1]}}
            for p in platforms
        ],
    }


def test_an_image_gone_or_without_arm64_is_a_finding() -> None:
    manifest = "https://registry-1.docker.io/v2/library/redis/manifests/7.4-alpine"
    web = FakeWeb(
        {
            manifest: watch.Answer(401, b"", _CHALLENGE),
            _HUB_TOKEN: {"token": "anonymous"},
        }
    )

    web.answers[manifest + "#authorized"] = _index("linux/amd64", "linux/arm64")
    assert watch.image_findings("redis:7.4-alpine", web) == []
    assert web.asked[-1][1]["Authorization"] == "Bearer anonymous"

    web.answers[manifest + "#authorized"] = _index("linux/amd64")
    assert watch.image_findings("redis:7.4-alpine", web) == [
        watch.Finding("image-no-arm64", "redis:7.4-alpine", "platforms: linux/amd64")
    ]

    web.answers[manifest + "#authorized"] = watch.Answer(404, b"", {})
    assert watch.image_findings("redis:7.4-alpine", web) == [
        watch.Finding("image-missing", "redis:7.4-alpine", "the registry answers 404")
    ]


def test_a_registry_that_gives_no_token_is_unread_never_a_missing_image() -> None:
    manifest = "https://registry-1.docker.io/v2/library/redis/manifests/7.4-alpine"
    web = FakeWeb({manifest: watch.Answer(401, b"", _CHALLENGE), _HUB_TOKEN: {}})

    with pytest.raises(LookupError):
        watch.image_findings("redis:7.4-alpine", web)


def test_a_credential_never_follows_a_redirect() -> None:
    """GitHub's token and a registry's token are sent to the host asked, never to a
    host a redirect names (a registry sends its blobs to a CDN)."""
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    seen: dict[str, str | None] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - the stdlib's name
            seen[self.path] = self.headers.get("Authorization")
            if self.path == "/first":
                self.send_response(302)
                self.send_header("Location", "/second")
                self.end_headers()
                return
            body = b"{}"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: object) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/first"
        answer = watch.http_get(url, {"Authorization": "Bearer secret", "Accept": "x"})
    finally:
        server.shutdown()
        server.server_close()
        thread.join()

    assert answer.status == 200
    assert seen == {"/first": "Bearer secret", "/second": None}


def test_an_image_reference_names_its_registry() -> None:
    assert watch.split_image("redis:7.4-alpine") == (
        "registry-1.docker.io",
        "library/redis",
        "7.4-alpine",
    )
    assert watch.split_image("grafana/grafana:11.3.0") == (
        "registry-1.docker.io",
        "grafana/grafana",
        "11.3.0",
    )
    assert watch.split_image("gcr.io/cadvisor/cadvisor:v0.49.1") == (
        "gcr.io",
        "cadvisor/cadvisor",
        "v0.49.1",
    )
    assert watch.split_image("ironsh/iron-proxy:0.49.0@sha256:" + "a" * 64) == (
        "registry-1.docker.io",
        "ironsh/iron-proxy",
        "sha256:" + "a" * 64,
    )


# --------------------------------------------------------------------------- browser

CHROME_EOL = {  # https://endoflife.date/api/v1/products/chrome/, trimmed
    "result": {
        "releases": [
            {"name": "154", "eolFrom": "2026-10-06", "isMaintained": True},
            {"name": "153", "eolFrom": "2026-09-22", "isMaintained": False},
            {"name": "152", "eolFrom": "2026-09-08", "isMaintained": False},
        ]
    }
}
POOL = """<a href="chromium_154.0.8037.92-1~deb13u1_amd64.deb">x</a>
<a href="chromium_152.0.7977.83-1~deb13u1_arm64.deb">x</a>
<a href="chromium_154.0.8037.92-1~deb12u1_arm64.deb">x</a>"""


def test_the_browser_engine_is_judged_against_chrome_support() -> None:
    findings = watch.browser_findings(CHROME_EOL, POOL, "13", TODAY)

    assert findings == [
        watch.Finding(
            "browser-engine",
            "chromium arm64",
            "Debian 13 security ships 152, out of Chrome's support since 2026-09-08; "
            "Chrome supports 154",
        )
    ]
    current = POOL.replace("152.0.7977.83", "154.0.8037.92")
    assert watch.browser_findings(CHROME_EOL, current, "13", TODAY) == []


def test_the_browser_engine_has_the_days_debian_takes_to_follow_chrome() -> None:
    # Chrome ships a major every two weeks and Debian's security archive follows
    # within days: a major out of support for less than the grace is no finding.
    lagging = POOL.replace("152.0.7977.83", "153.0.8010.12")

    assert watch.browser_findings(CHROME_EOL, lagging, "13", date(2026, 9, 30)) == []
    assert watch.browser_findings(CHROME_EOL, lagging, "13", date(2026, 10, 10)) != []


# --------------------------------------------------------------------------- acceptances


def test_every_finding_is_accepted_in_writing_and_every_acceptance_is_dated() -> None:
    findings = [
        watch.Finding(
            "end-of-life", "eslint 9", "end of life since 2026-08-06 (apps/web/package.json)"
        ),
        watch.Finding("advisory", "npm:x@1.0.0", "high: …", "GHSA-aaaa-bbbb-cccc"),
        watch.Finding("image-missing", "minio/minio:latest", "the registry answers 401"),
    ]
    acceptances = [
        {
            "kind": "end-of-life",
            "subject": "eslint 9",
            "reason": "r",
            "owner": "o",
            "review_by": "2026-12-31",
        },
        {
            "kind": "advisory",
            "subject": "npm:x@1.0.0",
            "ref": "GHSA-aaaa-bbbb-cccc",
            "reason": "r",
            "owner": "o",
            "review_by": "2026-09-30",
        },
        {
            "kind": "advisory",
            "subject": "npm:gone@0.1.0",
            "ref": "GHSA-x",
            "reason": "r",
            "owner": "o",
            "review_by": "2027-01-01",
        },
    ]

    verdict = watch.judge(findings, acceptances, TODAY)

    assert [f.subject for f in verdict.unaccepted] == ["minio/minio:latest"]
    assert [a["subject"] for a in verdict.expired] == ["npm:x@1.0.0"]
    assert [a["subject"] for a in verdict.stale] == ["npm:gone@0.1.0"]
    assert [f.subject for f, _ in verdict.accepted] == ["eslint 9"]
    assert not verdict.clean


def test_a_source_that_does_not_answer_is_named_never_silent() -> None:
    coverage = watch.Coverage("npm releases")
    coverage.count("katex@0.18.9", None)
    coverage.count("vite@8.1.5", "TimeoutError")

    assert (coverage.read, coverage.total) == (1, 2)
    assert coverage.unread == ["vite@8.1.5: TimeoutError"]
    assert "npm releases: 1 of 2 read" in watch.render_coverage([coverage])


# --------------------------------------------------------------------------- the real inputs


def test_the_inventory_reads_every_source_of_the_repository() -> None:
    """A watch that reads nothing passes forever (the doc_facts lesson)."""
    inventory = watch.inventory(REPO_ROOT)

    assert len(inventory.python) > 150
    assert len(inventory.npm) > 500
    assert len(inventory.images) > 15
    products = {line.product for line in inventory.lines}
    assert {
        "python",
        "nodejs",
        "postgresql",
        "redis",
        "grafana",
        "debian",
        "pnpm",
        "eslint",
    } <= products
    assert watch.Line("python", "3.10", ".github/workflows/ci.yml") in inventory.lines


def test_the_acceptance_file_is_well_formed() -> None:
    entries = json.loads(watch.ACCEPTED.read_text(encoding="utf-8"))
    keys = [(e["kind"], e["subject"], e.get("ref", "")) for e in entries]

    assert len(keys) == len(set(keys)), "one finding, one acceptance"
    for entry in entries:
        assert entry["kind"] in watch.KINDS, entry
        assert entry["reason"].strip() and entry["owner"].strip(), entry
        date.fromisoformat(entry["review_by"])
