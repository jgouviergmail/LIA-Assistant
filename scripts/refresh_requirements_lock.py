"""Refresh the API's three Python lockfiles under the cooldown, never backwards.

``task deps:refresh`` moves every version the manifests allow (dependency
programme, lot 4), subject to decision D4: a move waits after its release —
``PATCH_DAYS`` for a patch, ``MINOR_DAYS`` for a minor, ``MAJOR_DAYS`` for a
major — and no version ever goes lower than the lock it started from (doctrine
5). It is the one command that could move a version backwards: in the review's
dry run, ``uv pip compile --upgrade --exclude-newer`` with a 14-day window took
``pyjwt`` from 2.15.1 back to 2.14.0 (F7).

How it holds:

- uv's window filters ARTIFACTS by their upload time. The window of a locked
  package is therefore never earlier than the last artifact of the version it
  holds: a window can hold a version back, never take it back — a fix adopted
  three days ago stays where it is.
- Every package is resolved under the patch window; one that moves by a minor
  or a major gets that kind's window, and the three locks are resolved again,
  until no move asks for a longer window than it was resolved under. A package
  whose next major is younger than ``MAJOR_DAYS`` is held entirely — its minors
  and patches with it — until that major is old enough or a manifest caps it.
- A final plain ``task deps:lock`` keeps those versions and lists every artifact
  of each, so the result is exactly what ``deps:lock`` writes; the age of every
  new version is then checked against its kind, from PyPI's own dates.
- Any failure, and any version lower than before, restores the three lockfiles
  byte for byte.

Security fixes never wait: they move through ``task deps:upgrade -- <pkg>``
with a floor in their manifest (D4). The wake-word toolbox keeps its own locks
and task (``task wake:deps:lock``).

Usage: ``task deps:refresh`` — network: PyPI's JSON API and the index uv reads.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen

from packaging.version import Version

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_requirements_lock  # noqa: E402 - the sibling script, found through the line above
from check_requirements_lock import parse_lock  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
API_DIR = ROOT / "apps" / "api"
LOCKS = ("requirements.lock.txt", "requirements-dev.lock.txt", "requirements-sandbox.lock.txt")

#: D4 — how long a release waits before a refresh adopts it, by kind of move.
#: Held equal to Dependabot's npm cooldown by tests/unit/test_requirements_refresh.py.
PATCH_DAYS = 5
MINOR_DAYS = 14
MAJOR_DAYS = 60
WINDOW_DAYS = {"patch": PATCH_DAYS, "minor": MINOR_DAYS, "major": MAJOR_DAYS}
#: Windows only lengthen, so the loop settles; this bounds a resolver that does not.
MAX_PASSES = 6
_FETCH_WORKERS = 16
_FETCH_ATTEMPTS = 2

Pins = dict[str, set[str]]
Compile = Callable[[list[str]], None]
Fetch = Callable[[str, str], dict[str, Any]]


class RefreshError(RuntimeError):
    """The refresh cannot complete; the lockfiles are as they were."""


@dataclass(frozen=True)
class Move:
    """One package whose locked version changed."""

    name: str
    old: str
    new: str
    kind: str


@dataclass
class Outcome:
    """What a completed refresh changed."""

    moves: list[Move] = field(default_factory=list)
    added: dict[str, str] = field(default_factory=dict)
    removed: list[str] = field(default_factory=list)
    passes: int = 0


def read_pins(api_dir: Path) -> Pins:
    """Every package of the three lockfiles with the versions they pin (canonical names)."""
    pins: Pins = {}
    for lock in LOCKS:
        for name, versions in parse_lock(api_dir / lock).items():
            pins.setdefault(name, set()).update(versions)
    return pins


def kind_of_move(old: str, new: str) -> str | None:
    """``patch``, ``minor``, ``major``, ``down``, or ``None`` when the version is the same.

    Below 1.0 a minor is a major, as semantic versioning reads it.
    """
    before, after = Version(old), Version(new)
    if after == before:
        return None
    if after < before:
        return "down"
    a, b = (*before.release, 0, 0)[:2], (*after.release, 0, 0)[:2]
    if before.epoch != after.epoch or a[0] != b[0] or (a[0] == 0 and a[1] != b[1]):
        return "major"
    return "minor" if a[1] != b[1] else "patch"


def _package_kind(old: set[str], new: set[str]) -> str | None:
    # A package can be pinned twice under disjoint markers (a universal fork):
    # its lowest and highest pins are compared, and the worse move counts.
    pairs = (
        (min(old, key=Version), min(new, key=Version)),
        (max(old, key=Version), max(new, key=Version)),
    )
    kinds = {kind for before, after in pairs if (kind := kind_of_move(before, after)) is not None}
    if "down" in kinds:
        return "down"
    # The worse move is the one that waits longer.
    return max(kinds, key=WINDOW_DAYS.__getitem__) if kinds else None


def last_upload(payload: dict[str, Any]) -> datetime:
    """When the last artifact of a release reached PyPI (its JSON API answer for that version)."""
    stamps = [entry["upload_time_iso_8601"] for entry in payload.get("urls") or []]
    if not stamps:
        raise LookupError("the release has no artifact")
    return max(datetime.fromisoformat(stamp) for stamp in stamps)


def fetch_release(name: str, version: str) -> dict[str, Any]:
    """PyPI's JSON for one release."""
    request = Request(
        f"https://pypi.org/pypi/{quote(name)}/{quote(version)}/json",
        headers={"User-Agent": "lia-deps-refresh"},
    )
    with urlopen(request, timeout=30) as response:  # noqa: S310 - a fixed https URL
        data: dict[str, Any] = json.load(response)
    return data


def _uploads(pairs: Iterable[tuple[str, str]], fetch: Fetch) -> dict[tuple[str, str], datetime]:
    def attempt(pair: tuple[str, str]) -> datetime | str:
        error = ""
        for _ in range(_FETCH_ATTEMPTS):
            try:
                return last_upload(fetch(*pair))
            except Exception as exc:  # noqa: BLE001 - every failure is named below
                error = type(exc).__name__
        return error

    ordered = sorted(set(pairs))
    with ThreadPoolExecutor(_FETCH_WORKERS) as pool:
        answers = dict(zip(ordered, pool.map(attempt, ordered), strict=True))
    failed = [
        f"{name}=={version} ({answer})"
        for (name, version), answer in answers.items()
        if isinstance(answer, str)
    ]
    if failed:
        raise RefreshError(
            f"PyPI did not date {len(failed)} of {len(ordered)} releases: {', '.join(failed)}"
        )
    return {pair: answer for pair, answer in answers.items() if isinstance(answer, datetime)}


def _stamp(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def exclusion_args(
    pins: Pins, uploads: dict[tuple[str, str], datetime], windows: dict[str, int], now: datetime
) -> list[str]:
    """uv's arguments: the patch window for all, a package's own when it differs.

    A package's window never ends before the last artifact of what it holds.
    """
    default = _stamp(now - timedelta(days=PATCH_DAYS))
    args = ["--upgrade", "--exclude-newer", default]
    for name in sorted(pins):
        held = max(uploads[(name, version)] for version in pins[name]) + timedelta(seconds=1)
        window = now - timedelta(days=windows.get(name, PATCH_DAYS))
        cutoff = _stamp(max(window, held))
        if cutoff != default:
            args += ["--exclude-newer-package", f"{name}={cutoff}"]
    return args


def _moves(old: Pins, new: Pins) -> tuple[list[Move], list[Move]]:
    moves: list[Move] = []
    down: list[Move] = []
    for name in sorted(old.keys() & new.keys()):
        kind = _package_kind(old[name], new[name])
        if kind is None:
            continue
        move = Move(
            name,
            ", ".join(sorted(old[name], key=Version)),
            ", ".join(sorted(new[name], key=Version)),
            kind,
        )
        (down if kind == "down" else moves).append(move)
    return moves, down


def _resolve(
    api_dir: Path,
    compile_locks: Compile,
    old: Pins,
    uploads: dict[tuple[str, str], datetime],
    now: datetime,
) -> tuple[Pins, list[Move], int]:
    windows: dict[str, int] = {}
    for passes in range(1, MAX_PASSES + 1):
        compile_locks(exclusion_args(old, uploads, windows, now))
        new = read_pins(api_dir)
        moves, down = _moves(old, new)
        if down:
            raise RefreshError(
                "the resolution would move versions backwards: "
                + "; ".join(f"{m.name} {m.old} -> {m.new}" for m in down)
                + ". Floor them in their manifest if they are fixes, or hold what pulls them down."
            )
        longer = {
            m.name: WINDOW_DAYS[m.kind]
            for m in moves
            if WINDOW_DAYS[m.kind] > windows.get(m.name, PATCH_DAYS)
        }
        if not longer:
            return new, moves, passes
        windows.update(longer)
    raise RefreshError(f"no stable resolution after {MAX_PASSES} passes: windows {windows}")


def refresh(api_dir: Path, compile_locks: Compile, fetch: Fetch, now: datetime) -> Outcome:
    """Move every version the manifests allow under the cooldown, or change nothing.

    Args:
        api_dir: The directory holding the three lockfiles.
        compile_locks: Runs ``task deps:lock`` with these extra uv arguments.
        fetch: PyPI's JSON for one release (name, version).
        now: The instant the cooldown is measured from.

    Returns:
        The moves, additions and removals the three lockfiles now carry.

    Raises:
        RefreshError: Nothing could be refreshed; the lockfiles are unchanged.
    """
    originals = {lock: (api_dir / lock).read_bytes() for lock in LOCKS}
    old = read_pins(api_dir)
    uploads = _uploads(((n, v) for n, vs in old.items() for v in vs), fetch)
    try:
        new, moves, passes = _resolve(api_dir, compile_locks, old, uploads, now)
        compile_locks([])
        if read_pins(api_dir) != new:
            raise RefreshError("the normalising deps:lock changed a version the windows chose")
        added = {
            name: ", ".join(sorted(new[name], key=Version))
            for name in sorted(new.keys() - old.keys())
        }
        fresh = {(m.name, v): m.kind for m in moves for v in new[m.name] - old[m.name]}
        fresh |= {(name, v): "patch" for name in added for v in new[name]}
        dated = _uploads(fresh, fetch)
        early = [
            f"{name}=={version} ({(now - dated[(name, version)]).days} d, a {kind} waits {WINDOW_DAYS[kind]})"
            for (name, version), kind in sorted(fresh.items())
            if now - dated[(name, version)] < timedelta(days=WINDOW_DAYS[kind])
        ]
        if early:
            raise RefreshError(
                "these versions cannot be held without moving back (a later release of an "
                f"older line): {'; '.join(early)}. Cap them in their manifest, or wait."
            )
    except BaseException:
        for lock, content in originals.items():
            (api_dir / lock).write_bytes(content)
        raise
    return Outcome(moves, added, sorted(old.keys() - new.keys()), passes)


def _task_deps_lock(extra: list[str]) -> None:
    result = subprocess.run(  # noqa: S603 - fixed program, arguments built above
        ["task", "deps:lock", f"UV_EXTRA={' '.join(extra)}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise RefreshError("task deps:lock failed:\n" + (result.stdout + result.stderr)[-4000:])


def render(outcome: Outcome) -> str:
    """The report the operator reads before reviewing ``git diff``."""
    lines = [
        f"deps:refresh - cooldown: patch {PATCH_DAYS} d, minor {MINOR_DAYS} d, major "
        f"{MAJOR_DAYS} d; never backwards ({outcome.passes} resolution pass(es))",
    ]
    for kind in ("major", "minor", "patch"):
        moved = [m for m in outcome.moves if m.kind == kind]
        lines += [f"  {kind:5} {m.name} {m.old} -> {m.new}" for m in moved]
    lines += [f"  added {name} {version}" for name, version in outcome.added.items()]
    lines += [f"  removed {name}" for name in outcome.removed]
    total = len(outcome.moves) + len(outcome.added) + len(outcome.removed)
    lines.append(
        f"{total} change(s) in the three lockfiles - read `git diff` line by line, "
        "then run the gates (dependency programme, lot 8)."
        if total
        else "Nothing to move: every allowed version is already locked or still cooling down."
    )
    return "\n".join(lines)


def main() -> int:
    """Refresh the lockfiles, or explain why nothing changed."""
    if check_requirements_lock.main() != 0:
        print("deps:refresh starts from lockfiles in sync with their manifests: run task deps:lock")
        return 1
    try:
        outcome = refresh(
            API_DIR, _task_deps_lock, fetch_release, datetime.now(UTC).replace(microsecond=0)
        )
    except RefreshError as error:
        print(f"::error::{error}")
        print("The three lockfiles are unchanged.")
        return 1
    print(render(outcome))
    return 0


if __name__ == "__main__":
    sys.exit(main())
