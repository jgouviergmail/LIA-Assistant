"""Systemic guard: no real infrastructure / personal info in the public repo.

LIA is open source. Real, infra-specific values — the production host/IP, the SSH
username, the maintainer's personal email, private internal identifiers — must
never appear in tracked files (tests, docs, configs, code). The convention is
placeholders (``<user>@<prod-host>``) and ``.env``-rendered templates; see the
v1.23.5 SSH scrub and the logwatch ``.template`` for the canonical examples.

The catch: a guard that hard-codes the forbidden values would *itself* leak them.
So the forbidden tokens live in a **git-ignored local denylist** that each
developer keeps on their machine — the guard reads it and blocks those exact
tokens (whole-word match) from any tracked file. The teeth are at pre-commit time
(where a leak would be introduced); the guard file, committed, stays clean.

The denylist (``apps/api/tests/.infra_denylist``, git-ignored — see
``.infra_denylist.example``) holds one token per line, ``#`` comments allowed.

Empty / absent denylist -> the scan is a no-op (skipped). Populate the local file
to arm it. Whole-word matching is deliberate: a short username token is blocked as
a standalone word (``user@host``, ``/home/user/``) without flagging it inside a
longer, legitimate identifier such as the public GitHub owner handle.

Context: 2026-07 — added after a current-tree-only "scrub" that left the values
recoverable from history and, worse, re-quoted in a changelog. This guard stops
the class from re-entering going forward.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from tests._repo_paths import repo_root_or_skip

REPO_ROOT = repo_root_or_skip()
DENYLIST_FILE = Path(__file__).resolve().parents[1] / ".infra_denylist"

# Text extensions where infra/personal info could plausibly hide. Binary assets
# and lockfiles are intentionally out of scope.
SCANNED_SUFFIXES: frozenset[str] = frozenset(
    {
        ".py",
        ".md",
        ".txt",
        ".rst",
        ".yml",
        ".yaml",
        ".json",
        ".toml",
        ".ini",
        ".cfg",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".sh",
        ".ps1",
        ".conf",
        ".template",
        ".tmpl",
        ".env",
        ".example",
        ".html",
        ".css",
        ".sql",
        ".sops",
        ".xml",
    }
)

# Files excluded from the scan: this guard and the committed denylist template
# (the template holds fake sample tokens by design).
EXCLUDED_RELPATHS: frozenset[str] = frozenset(
    {
        "apps/api/tests/unit/test_no_infra_info_guard.py",
        "apps/api/tests/.infra_denylist.example",
    }
)


def _load_denylist() -> list[str]:
    """Load forbidden tokens from the local git-ignored denylist file."""
    if not DENYLIST_FILE.is_file():
        return []
    tokens: list[str] = []
    for line in DENYLIST_FILE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            tokens.append(stripped)
    # De-duplicate while preserving order.
    return list(dict.fromkeys(tokens))


def _compile(tokens: list[str]) -> list[tuple[str, re.Pattern[str]]]:
    """Compile whole-word, case-sensitive matchers for each token.

    Case-sensitive on purpose (and consistent with the pre-commit hook's
    ``grep -Fw``): a lowercase username is infra to block, but the same letters
    used (uppercase) as an author's initials in an ADR ``Deciders`` line are
    legitimate attribution, not a leak.
    """
    return [(tok, re.compile(rf"\b{re.escape(tok)}\b")) for tok in tokens]


def _tracked_text_files() -> list[str]:
    """Repo-relative paths of committable files with a scanned extension.

    Tracked files AND untracked ones git does not ignore, because a leak is
    introduced in a file that is new. Scanning only ``ls-files`` meant the
    guard went green on a session that had written the deployment account's
    home directory into three brand-new files; they were caught by hand
    (2026-08-07). ``--others --exclude-standard`` adds exactly what a ``git
    add .`` would sweep in, and nothing that is gitignored — so a secrets file
    stays out of the scan, as it must.
    """
    listings = (
        ["git", "-C", str(REPO_ROOT), "ls-files", "-z"],
        ["git", "-C", str(REPO_ROOT), "ls-files", "-z", "--others", "--exclude-standard"],
    )
    files = []
    seen: set[str] = set()
    for command in listings:
        out = subprocess.run(command, capture_output=True, text=True, check=True).stdout
        for rel in out.split("\0"):
            if not rel or rel in seen:
                continue
            if Path(rel).suffix in SCANNED_SUFFIXES and rel not in EXCLUDED_RELPATHS:
                seen.add(rel)
                files.append(rel)
    return files


def _scan(text: str, matchers: list[tuple[str, re.Pattern[str]]]) -> list[tuple[int, str]]:
    """Return (line_number, token) hits for every matcher in ``text``."""
    hits: list[tuple[int, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for token, pattern in matchers:
            if pattern.search(line):
                hits.append((lineno, token))
    return hits


class TestNoInfraInfoInRepo:
    """No git-ignored-denylist token may appear in any tracked file."""

    def test_no_forbidden_tokens_in_tracked_files(self) -> None:
        tokens = _load_denylist()
        if not tokens:
            pytest.skip(
                "No infra denylist configured "
                "(copy apps/api/tests/.infra_denylist.example to .infra_denylist)"
            )
        try:
            files = _tracked_text_files()
        except (subprocess.SubprocessError, FileNotFoundError, OSError) as exc:
            pytest.skip(f"git ls-files unavailable ({exc}) — infra scan skipped")
        matchers = _compile(tokens)
        violations: list[str] = []
        for rel in files:
            try:
                text = (REPO_ROOT / rel).read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for lineno, token in _scan(text, matchers):
                violations.append(f"{rel}:{lineno} contains forbidden token '{token}'")
        assert not violations, (
            "Real infra/personal info found in tracked files — use placeholders "
            "(<user>@<prod-host>, .env-rendered templates) instead:\n  " + "\n  ".join(violations)
        )


class TestGuardSelfCheck:
    """The matcher must not rot: it catches standalone tokens, not substrings."""

    def test_matches_standalone_username(self) -> None:
        matchers = _compile(["jdo"])
        assert _scan("ssh jdo@host && cd /home/jdo/app", matchers)

    def test_ignores_token_inside_longer_word(self) -> None:
        # 'jdo' must not match inside a longer identifier (e.g. an owner handle).
        matchers = _compile(["jdo"])
        assert not _scan("owner jdomainexample pushed", matchers)

    def test_matches_ip_but_not_longer_ip(self) -> None:
        matchers = _compile(["203.0.113.7"])
        assert _scan('host = "203.0.113.7"', matchers)
        assert not _scan('host = "203.0.113.70"', matchers)
