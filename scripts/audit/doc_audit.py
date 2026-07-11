#!/usr/bin/env python3
"""Documentation drift audit: broken relative links and stale code-path references.

Scans the documentation base (``docs/**/*.md`` plus ``README.md``, ``CLAUDE.md``
and ``apps/web/CLAUDE.md``) and reports two drift classes:

1. **Broken relative links** — markdown ``[text](target)`` links whose target,
   resolved relative to the containing file, does not exist on disk. Links
   inside fenced code blocks and inline code spans are ignored (they are code,
   not navigation).
2. **Stale code paths** — inline references to source files
   (``src/...``, ``apps/api/...``, ``apps/web/...``, ``scripts/...``,
   ``infrastructure/...``) that no longer exist. Common doc shorthands are
   resolved before flagging: a bare ``src/...`` or ``infrastructure/...`` path
   is also tried under ``apps/api/`` and ``apps/api/src/``.

Findings are classified so that historical documents are never treated as
regressions:

- **LIVING** — living documentation; findings here are actionable drift.
- **HISTORICAL** — dated documents (``docs/architecture/ADR-*``,
  ``docs/superpowers/``); by convention these are never retouched.
- **ROADMAP** — planning documents whose paths are intentionally
  prospective (``NANOBOT_INTEGRATION_ROADMAP.md``).

Exit code is 1 when at least one LIVING broken link is found (stale code
paths alone do not fail the run: the remaining ones are deliberate
placeholders such as ``my_service_client.py`` or annotated examples).

Usage (from the repo root):
    python scripts/audit/doc_audit.py [REPO_ROOT] [--fail-on-stale]

Standard library only — no dependencies.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
CODE_PATH_RE = re.compile(
    r"(?<![\w/.-])((?:apps/(?:api|web)/|src/|scripts/|infrastructure/)[\w./-]+"
    r"\.(?:py|tsx|ts|txt|yaml|yml|json|sh|md|mmd|html|sql|toml))(?![\w-])"
)
EXTERNAL_PREFIXES = ("http://", "https://", "mailto:", "#", "tel:")

HISTORICAL_MARKERS = ("docs/architecture/ADR-", "docs/superpowers/")
ROADMAP_BASENAMES = {"NANOBOT_INTEGRATION_ROADMAP.md"}

Finding = tuple[str, int, str]


def _classify(rel_posix: str) -> str:
    """Classify a document as LIVING, HISTORICAL or ROADMAP."""
    if any(rel_posix.startswith(marker) for marker in HISTORICAL_MARKERS):
        return "HISTORICAL"
    if rel_posix.rsplit("/", 1)[-1] in ROADMAP_BASENAMES:
        return "ROADMAP"
    return "LIVING"


def _blank_code_regions(text: str) -> str:
    """Replace fenced code blocks and inline code with spaces, preserving line numbers."""

    def _blank(match: re.Match[str]) -> str:
        return re.sub(r"[^\n]", " ", match.group(0))

    text = re.sub(r"```.*?```", _blank, text, flags=re.DOTALL)
    return re.sub(r"`[^`\n]+`", _blank, text)


def _doc_files(root: Path) -> list[Path]:
    """Collect the documentation files under audit."""
    files = sorted(root.glob("docs/**/*.md"))
    for extra in (root / "README.md", root / "CLAUDE.md", root / "apps" / "web" / "CLAUDE.md"):
        if extra.exists():
            files.append(extra)
    return files


def _check_links(root: Path, doc: Path, text_nocode: str) -> list[Finding]:
    """Return broken relative links in one document."""
    findings: list[Finding] = []
    rel = doc.relative_to(root).as_posix()
    for match in LINK_RE.finditer(text_nocode):
        target = match.group(2)
        if target.startswith(EXTERNAL_PREFIXES):
            continue
        path_part = target.split("#")[0].replace("%20", " ")
        if not path_part:
            continue
        candidate = (
            root / path_part.lstrip("/") if path_part.startswith("/") else doc.parent / path_part
        )
        try:
            exists = candidate.resolve().exists()
        except OSError:
            exists = False
        if not exists:
            line_no = text_nocode[: match.start()].count("\n") + 1
            findings.append((rel, line_no, target))
    return findings


def _check_code_paths(root: Path, doc: Path, text: str) -> list[Finding]:
    """Return stale inline code-path references in one document."""
    findings: list[Finding] = []
    rel = doc.relative_to(root).as_posix()
    for match in CODE_PATH_RE.finditer(text):
        path = match.group(1).rstrip(".")
        candidates = (
            root / path,
            root / "apps" / "api" / path,
            root / "apps" / "api" / "src" / path,
            root / "apps" / "api" / "tests" / path,
            root / "apps" / "web" / path,
            root / "apps" / "web" / "src" / path,
        )
        if not any(candidate.exists() for candidate in candidates):
            line_no = text[: match.start()].count("\n") + 1
            findings.append((rel, line_no, path))
    return findings


def main(argv: list[str]) -> int:
    """Run the audit and print per-class reports."""
    args = [arg for arg in argv[1:] if not arg.startswith("--")]
    fail_on_stale = "--fail-on-stale" in argv
    root = Path(args[0]).resolve() if args else Path.cwd()
    if not (root / "docs").is_dir():
        print(f"error: no docs/ directory under {root}", file=sys.stderr)
        return 2

    broken: dict[str, list[Finding]] = {"LIVING": [], "HISTORICAL": [], "ROADMAP": []}
    stale: dict[str, list[Finding]] = {"LIVING": [], "HISTORICAL": [], "ROADMAP": []}

    for doc in _doc_files(root):
        rel_posix = doc.relative_to(root).as_posix()
        section = _classify(rel_posix)
        text = doc.read_text(encoding="utf-8", errors="replace")
        broken[section].extend(_check_links(root, doc, _blank_code_regions(text)))
        stale[section].extend(_check_code_paths(root, doc, text))

    for title, table in (("BROKEN LINKS", broken), ("STALE CODE PATHS", stale)):
        for section in ("LIVING", "HISTORICAL", "ROADMAP"):
            findings = table[section]
            print(f"=== {title} [{section}]: {len(findings)} ===")
            for rel, line_no, target in findings:
                print(f"{rel}:{line_no}: {target}")
            print()

    failed = bool(broken["LIVING"]) or (fail_on_stale and bool(stale["LIVING"]))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
