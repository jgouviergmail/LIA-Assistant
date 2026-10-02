"""``task deps:refresh`` moves versions under the cooldown and never backwards.

Dependency programme, lot 4 (doctrine 5, decision D4). The refresh is the one
command that could move a version backwards: a 14-day window took ``pyjwt``
from 2.15.1 back to 2.14.0 in the dry run of the review (F7). These tests drive
``scripts/refresh_requirements_lock.py`` against a fake index and a fake
resolver — no network, no uv — and hold its four promises: a locked version is
never excluded by its window, each move waits the cooldown of its kind, a
version lower than before restores the three lockfiles byte for byte, and so
does any failure.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

REPO_ROOT = repo_root_or_skip()
SCRIPT = REPO_ROOT / "scripts" / "refresh_requirements_lock.py"
_MODULE_NAME = "_lia_refresh_requirements_lock"

NOW = datetime(2026, 10, 2, 12, 0, 0, tzinfo=UTC)


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


refresh_mod = _load()


def _days_ago(days: float) -> datetime:
    return NOW - timedelta(days=days)


class FakeIndex:
    """Releases per package, each with the upload of its last artifact."""

    def __init__(self, releases: dict[str, dict[str, datetime]]) -> None:
        self.releases = releases
        self.fetched: list[tuple[str, str]] = []

    def fetch(self, name: str, version: str) -> dict[str, Any]:
        self.fetched.append((name, version))
        uploaded = self.releases[name][version]
        stamp = uploaded.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        # The shape of PyPI's JSON for one release: one entry per artifact.
        return {
            "info": {"name": name, "version": version},
            "urls": [
                {"upload_time_iso_8601": stamp},
            ],
        }


def _write_locks(api_dir: Path, pins: dict[str, str]) -> None:
    body = "".join(
        f"{name}=={version} \\\n    --hash=sha256:00\n" for name, version in sorted(pins.items())
    )
    for lock in refresh_mod.LOCKS:
        (api_dir / lock).write_text("# header\n" + body, encoding="utf-8")


class FakeResolver:
    """Resolves each package to its newest release the exclusion arguments admit.

    Without ``--upgrade`` (the normalisation pass), it keeps what the locks hold,
    exactly as uv keeps the pins of an existing output file.
    """

    def __init__(self, api_dir: Path, index: FakeIndex, *, override: dict[str, str] | None = None):
        self.api_dir = api_dir
        self.index = index
        self.override = override or {}
        self.calls: list[list[str]] = []

    def __call__(self, extra: list[str]) -> None:
        self.calls.append(list(extra))
        if "--upgrade" not in extra:
            return
        default = datetime.fromisoformat(extra[extra.index("--exclude-newer") + 1])
        cutoffs: dict[str, datetime] = {}
        for i, arg in enumerate(extra):
            if arg == "--exclude-newer-package":
                name, _, stamp = extra[i + 1].partition("=")
                cutoffs[name] = datetime.fromisoformat(stamp)
        pins = {}
        for name, releases in self.index.releases.items():
            cutoff = cutoffs.get(name, default)
            admitted = [v for v, uploaded in releases.items() if uploaded < cutoff]
            pins[name] = max(admitted, key=refresh_mod.Version)
        pins.update(self.override)
        _write_locks(self.api_dir, pins)


@pytest.mark.parametrize(
    ("old", "new", "kind"),
    [
        ("1.2.3", "1.2.4", "patch"),
        ("1.2.3", "1.3.0", "minor"),
        ("1.2.3", "2.0.0", "major"),
        ("0.4.4", "0.4.5", "patch"),
        ("0.4.4", "0.5.0", "major"),  # below 1.0 a minor breaks, as semver reads it
        ("2.0.0", "1.9.9", "down"),
        ("1.0", "1.0.0", None),  # one version under PEP 440
        ("1.0.post1", "1.0.post2", "patch"),
        ("2026.2", "2026.4", "minor"),
    ],
)
def test_a_move_is_classified_the_way_the_cooldown_reads_it(
    old: str, new: str, kind: str | None
) -> None:
    assert refresh_mod.kind_of_move(old, new) == kind


def test_a_release_is_dated_by_its_last_artifact() -> None:
    # Recorded from PyPI (urllib3 2.8.0): the wheel and the sdist landed two
    # seconds apart, and the window filters ARTIFACTS — dating the release by
    # its first one would drop the second from the lock.
    payload = {
        "urls": [
            {"upload_time_iso_8601": "2026-09-15T19:29:34.577402Z"},
            {"upload_time_iso_8601": "2026-09-15T19:29:36.253420Z"},
        ]
    }

    assert refresh_mod.last_upload(payload) == datetime(2026, 9, 15, 19, 29, 36, 253420, tzinfo=UTC)
    with pytest.raises(LookupError):
        refresh_mod.last_upload({"urls": []})


def test_a_locked_version_is_never_excluded_by_its_window() -> None:
    pins = {"settled": {"1.0.0"}, "fresh-fix": {"2.15.1"}, "raised": {"3.0.0"}}
    uploads = {
        ("settled", "1.0.0"): _days_ago(400),
        ("fresh-fix", "2.15.1"): datetime(2026, 9, 29, 8, 0, 0, 500000, tzinfo=UTC),
        ("raised", "3.0.0"): _days_ago(400),
    }

    args = refresh_mod.exclusion_args(pins, uploads, {"raised": 60}, NOW)

    assert args == [
        "--upgrade",
        "--exclude-newer",
        "2026-09-27T12:00:00Z",  # the patch window, for every package by default
        "--exclude-newer-package",
        "fresh-fix=2026-09-29T08:00:01Z",  # after its own last artifact, never before
        "--exclude-newer-package",
        "raised=2026-08-03T12:00:00Z",  # the major window it asked for
    ]


def test_each_move_waits_the_cooldown_of_its_kind(tmp_path: Path) -> None:
    index = FakeIndex(
        {
            # A patch 10 days old: under the 5-day patch window, it moves.
            "patchy": {"1.0.0": _days_ago(300), "1.0.1": _days_ago(10)},
            # A minor 7 days old waits for 14: the previous patch moves instead.
            "minory": {"1.0.0": _days_ago(300), "1.0.5": _days_ago(20), "1.1.0": _days_ago(7)},
            # A major 30 days old waits for 60: nothing older than 60 days is newer.
            "majory": {"1.0.0": _days_ago(300), "2.0.0": _days_ago(30)},
            # Adopted 2 days ago (a security fix): the window never takes it back.
            "fresh-fix": {"2.14.0": _days_ago(90), "2.15.1": _days_ago(2)},
        }
    )
    _write_locks(
        tmp_path, {"patchy": "1.0.0", "minory": "1.0.0", "majory": "1.0.0", "fresh-fix": "2.15.1"}
    )
    resolver = FakeResolver(tmp_path, index)

    result = refresh_mod.refresh(tmp_path, resolver, index.fetch, NOW)

    assert refresh_mod.read_pins(tmp_path) == {
        "patchy": {"1.0.1"},
        "minory": {"1.0.5"},
        "majory": {"1.0.0"},
        "fresh-fix": {"2.15.1"},
    }
    assert {(m.name, m.old, m.new, m.kind) for m in result.moves} == {
        ("patchy", "1.0.0", "1.0.1", "patch"),
        ("minory", "1.0.0", "1.0.5", "patch"),
    }
    # The last call is the normalisation: no upgrade, no window — deps:lock itself.
    assert resolver.calls[-1] == []


def test_a_version_lower_than_before_restores_the_lockfiles(tmp_path: Path) -> None:
    index = FakeIndex(
        {"a": {"1.0.0": _days_ago(300), "1.1.0": _days_ago(100)}, "b": {"2.0.0": _days_ago(300)}}
    )
    _write_locks(tmp_path, {"a": "1.0.0", "b": "2.0.0"})
    before = {lock: (tmp_path / lock).read_bytes() for lock in refresh_mod.LOCKS}
    # The resolver takes b back to make room for a's new version.
    resolver = FakeResolver(tmp_path, index, override={"b": "1.9.0"})

    with pytest.raises(refresh_mod.RefreshError, match=r"b 2\.0\.0 -> 1\.9\.0"):
        refresh_mod.refresh(tmp_path, resolver, index.fetch, NOW)

    assert {lock: (tmp_path / lock).read_bytes() for lock in refresh_mod.LOCKS} == before


def test_any_failure_restores_the_lockfiles(tmp_path: Path) -> None:
    index = FakeIndex({"a": {"1.0.0": _days_ago(300), "1.0.1": _days_ago(100)}})
    _write_locks(tmp_path, {"a": "1.0.0"})
    before = {lock: (tmp_path / lock).read_bytes() for lock in refresh_mod.LOCKS}
    resolver = FakeResolver(tmp_path, index)

    def fails_after_writing(extra: list[str]) -> None:
        resolver(extra)  # the locks are already rewritten when uv fails
        raise refresh_mod.RefreshError("uv: no solution")

    with pytest.raises(refresh_mod.RefreshError, match="no solution"):
        refresh_mod.refresh(tmp_path, fails_after_writing, index.fetch, NOW)

    assert {lock: (tmp_path / lock).read_bytes() for lock in refresh_mod.LOCKS} == before


def test_an_unanswered_release_stops_the_refresh_before_any_write(tmp_path: Path) -> None:
    index = FakeIndex({"a": {"1.0.0": _days_ago(300)}})
    _write_locks(tmp_path, {"a": "1.0.0", "gone": "0.1.0"})
    calls: list[list[str]] = []

    with pytest.raises(refresh_mod.RefreshError, match=r"gone==0\.1\.0"):
        refresh_mod.refresh(tmp_path, calls.append, index.fetch, NOW)

    assert calls == []  # nothing was resolved, nothing was written


def test_the_cooldown_is_the_one_dependabot_applies() -> None:
    """D4 is written twice — here for Python, in dependabot.yml for npm — and held equal."""
    config = yaml.safe_load((REPO_ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8"))
    npm = [u["cooldown"] for u in config["updates"] if u["package-ecosystem"] == "npm"]

    assert npm, "dependabot.yml declares no npm cooldown"
    for cooldown in npm:
        assert (
            cooldown["semver-patch-days"],
            cooldown["semver-minor-days"],
            cooldown["semver-major-days"],
        ) == (refresh_mod.PATCH_DAYS, refresh_mod.MINOR_DAYS, refresh_mod.MAJOR_DAYS)
