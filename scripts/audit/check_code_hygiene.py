#!/usr/bin/env python3
"""Code-hygiene checks — one implementation, runnable locally and in CI.

These checks used to live as inline bash inside `.github/workflows/ci.yml`,
which made them impossible to run before pushing: a developer could satisfy
every local gate and still red the build on a `.bak` file or a second Alembic
head. Porting them here makes `task lint:hygiene` and the CI job execute the
*same* code — the CI step becomes a call, not a second implementation.

Python rather than bash on purpose: the development machine is Windows and the
runner is Linux, so a bash-only check is a check that only one of the two can
run. Everything below is plain stdlib and platform-agnostic.

Severity follows the original CI wiring exactly — three checks are advisory and
do not fail the build. Promoting one is a deliberate decision, not a side effect
of this port.

Usage:
    python scripts/audit/check_code_hygiene.py            # all checks
    python scripts/audit/check_code_hygiene.py --list     # names only
    python scripts/audit/check_code_hygiene.py --only bak_files
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
API_SRC = REPO_ROOT / "apps" / "api" / "src"
WEB_SRC = REPO_ROOT / "apps" / "web" / "src"

# GitHub Actions renders `::error::`/`::warning::` as annotations; locally they
# would just be noise. Selected by an explicit `--github` flag rather than by
# reading GITHUB_ACTIONS: the pre-commit hook scans committed code for env-var
# references and requires each one to appear in .env.example, and a CI runner
# variable has no business being documented as LIA configuration.
_annotate = False


@dataclass
class CheckResult:
    """Outcome of a single hygiene check.

    Attributes:
        name: Stable identifier, usable with ``--only``.
        title: Human-readable description.
        failed: True when the check found something.
        fatal: True when a finding must fail the build.
        details: Offending lines, shown under the title.
    """

    name: str
    title: str
    failed: bool = False
    fatal: bool = True
    details: list[str] = field(default_factory=list)


def _iter_python_sources(root: Path) -> list[Path]:
    """Every Python file under a root, skipping caches and virtualenvs.

    Args:
        root: Directory to walk.

    Returns:
        Sorted list of Python files.
    """
    skip = {"__pycache__", ".venv", "node_modules", ".git"}
    return sorted(
        p for p in root.rglob("*.py") if not any(part in skip for part in p.parts)
    )


def _iter_web_sources() -> list[Path]:
    """Every TypeScript/TSX source of the frontend, tests excluded.

    Returns:
        Sorted list of frontend source files.
    """
    skip = {"node_modules", "__tests__", ".next"}
    return sorted(
        p
        for suffix in ("*.ts", "*.tsx")
        for p in WEB_SRC.rglob(suffix)
        if not any(part in skip for part in p.parts)
    )


def check_chat_deep_link_navigation() -> CheckResult:
    """A chat deep link is opened by the browser, never by `router.push` (ADR-192).

    Measured in production on 2026-08-01: the App Router restores the search
    params of the entry it already holds for a route, so a client-side push
    landed on the PREVIOUS deep link's URL — the first 360° of a session
    replayed itself for every later one, and a `?draft=` prefill could come back
    as an auto-sent `?intent=`.

    The whole guarantee rests on every producer going through
    ``openChatDeepLink``; one call site reverting to ``router.push`` silently
    reopens the defect for that surface alone, which is exactly the kind of
    regression no test elsewhere would notice.

    Scanned on the WHOLE file, not line by line, and in three shapes — the
    first version matched only ``router.push(chatIntentHref(`` on a single
    line, and therefore saw none of the ways this actually gets written:

    1. the call split across lines (Prettier does this by itself as soon as the
       arguments are long, which is how every existing call site is formatted);
    2. the href held in a variable first, the natural result of any refactor;
    3. ``replace`` instead of ``push`` — same client-side navigation, same
       restored search params, same defect.

    A guard that answers OK on the shape the codebase actually uses is worse
    than no guard: it is a promise nobody re-checks.
    """
    result = CheckResult(
        "chat_deep_link",
        "Chat deep link pushed through the client router instead of openChatDeepLink",
    )
    href_call = r"chat(?:Intent|Draft)Href\s*\("
    # `[^()]*` keeps the match inside ONE argument list — it cannot run past the
    # closing paren into an unrelated later call.
    direct = re.compile(rf"\.(?:push|replace)\(\s*[^()]*{href_call}", re.DOTALL)
    assigned = re.compile(rf"(?:const|let|var)\s+(\w+)\s*(?::[^=]+)?=\s*{href_call}")

    for path in _iter_web_sources():
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(REPO_ROOT)
        offenders = list(direct.finditer(text))
        # Shape 2: any identifier this file built from a deep-link helper, then
        # handed to the client router.
        for name in {match.group(1) for match in assigned.finditer(text)}:
            offenders += re.finditer(
                rf"\.(?:push|replace)\(\s*{re.escape(name)}\s*[,)]", text
            )
        for match in offenders:
            lineno = text.count("\n", 0, match.start()) + 1
            snippet = " ".join(match.group(0).split())[:80]
            result.details.append(f"{rel}:{lineno}: {snippet}")
    result.details.sort()
    result.failed = bool(result.details)
    return result


def check_bak_files() -> CheckResult:
    """No editor/backup leftovers committed to the tree."""
    result = CheckResult("bak_files", "Backup files (.bak) in the repository")
    skip = {".git", "node_modules", ".venv", ".next"}
    for path in REPO_ROOT.rglob("*.bak"):
        if any(part in skip for part in path.parts):
            continue
        result.details.append(str(path.relative_to(REPO_ROOT)))
    result.failed = bool(result.details)
    return result


def check_sync_store_calls() -> CheckResult:
    """LangGraph store calls on an async path must use the async API.

    `runtime.store.put/get/delete/search` are the synchronous variants; on an
    async path they block the event loop, SSE included. The async spellings are
    `aput`/`aget`/`adelete`/`asearch`.
    """
    result = CheckResult("sync_store", "Synchronous Store calls in async context")
    pattern = re.compile(r"runtime\.store\.(put|get|delete|search)\(")
    for path in _iter_python_sources(API_SRC):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line) and "await " not in line:
                rel = path.relative_to(REPO_ROOT)
                result.details.append(f"{rel}:{lineno}: {line.strip()}")
    result.failed = bool(result.details)
    return result


def check_redis_setex_serialization() -> CheckResult:
    """`setex` should store serialized values, not raw Python objects."""
    result = CheckResult(
        "redis_setex",
        "Redis setex() without json.dumps()",
        fatal=False,
    )
    for path in _iter_python_sources(API_SRC):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if ".setex(" in line and "json.dumps(" not in line:
                rel = path.relative_to(REPO_ROOT)
                result.details.append(f"{rel}:{lineno}: {line.strip()}")
    result.failed = bool(result.details)
    return result


def check_raw_http_exception() -> CheckResult:
    """Backend errors go through the centralized taxonomy (rule #18, ADR-124).

    Advisory for now, exactly as the CI step was: the tree reached zero sites,
    and the warning absorbs in-flight branches. Promoting it to fatal is a
    one-line change here — and a deliberate decision, not a side effect.
    """
    result = CheckResult(
        "raw_http_exception",
        "Raw 'raise HTTPException' (use src/core/exceptions.py)",
        fatal=False,
    )
    for path in _iter_python_sources(API_SRC):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "raise HTTPException" in line:
                rel = path.relative_to(REPO_ROOT)
                result.details.append(f"{rel}:{lineno}: {line.strip()}")
    result.failed = bool(result.details)
    return result


def check_alembic_single_head(versions: Path | None = None) -> CheckResult:
    """The migration chain must have exactly one head.

    Two heads mean two branches of the chain were created in parallel; alembic
    refuses to upgrade until they are merged, and the failure surfaces at deploy
    time rather than at review time.
    """
    result = CheckResult("alembic_head", "Alembic migration heads")
    if versions is None:
        versions = REPO_ROOT / "apps" / "api" / "alembic" / "versions"
    if not versions.is_dir():
        result.details.append(f"versions directory not found: {versions}")
        result.failed = True
        return result

    rev_re = re.compile(r"^revision[^=]*=\s*[\"']([^\"']+)", re.MULTILINE)
    down_re = re.compile(r"^down_revision[^=]*=\s*[\"']([^\"']+)", re.MULTILINE)

    revisions: dict[str, str] = {}
    duplicates: list[str] = []
    parents: set[str] = set()
    for path in sorted(versions.glob("*.py")):
        content = path.read_text(encoding="utf-8")
        if match := rev_re.search(content):
            rev = match.group(1)
            if rev in revisions:
                duplicates.append(f"{rev} ({revisions[rev]}, {path.name})")
            revisions[rev] = path.name
        if match := down_re.search(content):
            parents.add(match.group(1))

    heads = [rev for rev in revisions if rev not in parents]
    if duplicates:
        # A reused id makes alembic raise CycleDetected at upgrade time — and it
        # made THIS check report "no revisions found" as a pass (2026-09-03).
        result.failed = True
        result.details = [f"duplicate revision id: {dup}" for dup in duplicates]
    elif len(heads) > 1:
        result.failed = True
        result.details = [f"{head} ({revisions[head]})" for head in sorted(heads)]
    elif len(heads) == 1:
        result.details = [f"single head: {heads[0]} ({revisions[heads[0]]})"]
    else:
        # Zero heads is never "nothing to check": with revisions present it means
        # every revision is somebody's parent, i.e. the chain loops on itself.
        result.failed = True
        result.details = ["no head: empty versions directory or a cycle in the chain"]
    return result


def check_compose_entrypoint_needs_no_exec_bit() -> CheckResult:
    """A bind-mounted script must be run BY an interpreter, never executed.

    A compose `entrypoint: /docker-entrypoint.sh` needs the file on the HOST to
    carry the executable bit, because a bind mount brings the host's mode with
    it — no Dockerfile `chmod +x` can help, since nothing was copied into the
    image. That bit has to survive a Windows checkout (NTFS has no exec bit)
    and then rsync or scp before it reaches the server.

    It did not, on 2026-08-31: production refused to start Alertmanager with
    `exec: "/docker-entrypoint.sh": permission denied`, after the atomic swap
    had already replaced the live directory. The file is `100755` in git; the
    transport is where the bit was lost.

    `entrypoint: ["/bin/sh", "/docker-entrypoint.sh"]` needs only READ
    permission and removes the whole class. `docker-compose.dev.yml` already
    knew the shape (`command: sh /generate-certs.sh`); one service did not.
    """
    result = CheckResult(
        "compose_entrypoint_exec_bit",
        "Compose entrypoint/command executing a bind-mounted script directly",
    )
    # A bare scalar ending in `.sh`: no interpreter in front, no list form.
    pattern = re.compile(r"^\s*(entrypoint|command):\s*(\S+\.sh)\s*$")
    for path in sorted(REPO_ROOT.glob("docker-compose*.yml")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            match = pattern.match(line)
            if not match:
                continue
            rel = path.relative_to(REPO_ROOT)
            result.details.append(
                f"{rel}:{lineno}: {match.group(1)}: {match.group(2)} "
                f'-- run it through an interpreter: ["/bin/sh", "{match.group(2)}"]'
            )
    result.failed = bool(result.details)
    return result


def check_env_example_completeness() -> CheckResult:
    """Settings fields should be documented in `.env.example`.

    Advisory, as in CI: the heuristic reads UPPER_CASE class attributes and
    `env=` aliases out of the config modules, which over-reports on purpose
    rather than hiding a genuinely undocumented variable.
    """
    result = CheckResult(
        "env_example",
        "Config variables missing from .env.example",
        fatal=False,
    )
    env_example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    documented = set(re.findall(r"^([A-Z][A-Z_0-9]+)=", env_example, re.MULTILINE))

    referenced: set[str] = set()
    config_dir = API_SRC / "core" / "config"
    for path in config_dir.glob("*.py"):
        content = path.read_text(encoding="utf-8")
        referenced |= set(re.findall(r"env=[\"']([A-Z][A-Z_0-9]+)[\"']", content))
        referenced |= set(re.findall(r"^    ([A-Z][A-Z_0-9]+):", content, re.MULTILINE))

    missing = sorted(
        name
        for name in referenced - documented
        if len(name) > 2 and not name.startswith("MODEL_")
    )
    result.failed = bool(missing)
    result.details = missing
    return result


CHECKS = (
    check_chat_deep_link_navigation,
    check_bak_files,
    check_sync_store_calls,
    check_redis_setex_serialization,
    check_raw_http_exception,
    check_alembic_single_head,
    check_compose_entrypoint_needs_no_exec_bit,
    check_env_example_completeness,
)


def _emit(result: CheckResult) -> None:
    """Print one check's outcome, annotated when running in GitHub Actions."""
    if not result.failed:
        # ASCII only: this runs on a Windows console whose default code page
        # mangles typographic dashes, and an audit tool that prints mojibake
        # invites people to stop reading its output.
        detail = f" - {result.details[0]}" if result.details else ""
        print(f"  OK   {result.title}{detail}")
        return

    level = "error" if result.fatal else "warning"
    prefix = f"::{level}::" if _annotate else f"[{level.upper()}] "
    print(f"{prefix}{result.title} ({len(result.details)}):")
    for line in result.details:
        print(f"    {line}")


def main() -> int:
    """Run the hygiene checks.

    Returns:
        1 when a fatal check found something, 0 otherwise.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", help="run a single check by name")
    parser.add_argument(
        "--github",
        action="store_true",
        help="emit ::error::/::warning:: workflow annotations",
    )
    parser.add_argument("--list", action="store_true", help="list check names")
    args = parser.parse_args()

    global _annotate
    _annotate = args.github

    if args.list:
        for check in CHECKS:
            print(check().name)
        return 0

    selected = list(CHECKS)
    if args.only:
        selected = [c for c in CHECKS if c().name == args.only]
        if not selected:
            print(f"unknown check: {args.only}", file=sys.stderr)
            return 2

    print("Code hygiene checks")
    failures = 0
    for check in selected:
        result = check()
        _emit(result)
        if result.failed and result.fatal:
            failures += 1

    if failures:
        print(f"\n{failures} fatal check(s) failed.")
        return 1
    print("\nAll hygiene checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
