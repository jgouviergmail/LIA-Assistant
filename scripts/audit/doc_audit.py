#!/usr/bin/env python3
"""Documentation NAVIGATION audit: broken links, stale code paths, orphans.

Scans the documentation base (``docs/**/*.md`` plus the root documents listed in
``ROOT_DOCUMENTS``) and reports three drift classes:

1. **Broken relative links** — markdown ``[text](target)`` links whose target,
   resolved relative to the containing file, does not exist. Inside a git
   checkout, existence means "present in the git index, exact case" so the
   verdict matches a fresh CI clone (case drift and locally-present-but-
   untracked targets are findings); outside git it falls back to the disk.
   Links inside fenced code blocks and inline code spans are ignored (they
   are code, not navigation).
2. **Stale code paths** — inline references to source files
   (``src/...``, ``apps/api/...``, ``apps/web/...``, ``scripts/...``,
   ``infrastructure/...``) that no longer exist. Common doc shorthands are
   resolved before flagging: a bare ``src/...`` or ``infrastructure/...`` path
   is also tried under ``apps/api/`` and ``apps/api/src/``.
3. **Orphans** — LIVING documents no tracked document links to. A document
   nobody links to is a document nobody opens, and it is the shape every stale
   duplicate here took first (see :func:`find_orphans`). Entry points and two
   reasoned prefixes are exempt (:data:`ORPHAN_EXEMPT_PREFIXES`).

What a document *states* is a different question, answered by the companion
module ``doc_facts.py``: a well-formed sentence that is false is invisible to a
link checker. Both run under ``task lint:docs``.

Findings are classified so that historical documents are never treated as
regressions:

- **LIVING** — living documentation; findings here are actionable drift.
- **HISTORICAL** — dated documents (``docs/architecture/ADR-*``,
  ``docs/superpowers/``); by convention these are never retouched.
- **ROADMAP** — planning documents whose paths are intentionally
  prospective (``NANOBOT_INTEGRATION_ROADMAP.md``).

One escalation refines the HISTORICAL leniency (audit F024): a broken link
whose target is *another ADR file* (``ADR-<n>-*.md`` / ``ADR_INDEX.md``),
found inside an ADR whose number is present in ``ADR_INDEX.md`` (an
*actively-indexed* ADR), is promoted back to LIVING. ADR cross-links are
navigation between living decisions, so a dangling one is real drift — while
the annotated stale *code* paths (``*.py``) and deleted session/optim
documents that ADRs legitimately reference stay HISTORICAL (tolerated).

Exit code is 1 when at least one LIVING broken link or orphan is found. Stale
code paths alone do not fail the run unless ``--fail-on-stale`` is passed (the
remaining ones are deliberate placeholders such as ``my_service_client.py`` or
annotated examples); ``task lint:docs`` always passes that flag.

Usage (from the repo root):
    python scripts/audit/doc_audit.py [REPO_ROOT] [--fail-on-stale]
                                      [--include-unstaged]

``--include-unstaged`` answers "what will CI say once I commit this?" —
see :func:`tracked_paths`. The default stays the fresh clone's verdict.

Standard library only — no dependencies.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
CODE_PATH_RE = re.compile(
    r"(?<![\w/.-])((?:apps/(?:api|web)/|src/|scripts/|infrastructure/)[\w./-]+"
    r"\.(?:py|tsx|ts|txt|yaml|yml|json|sh|md|mmd|html|sql|toml))(?![\w-])"
)
# Illustrative placeholder paths in creation guides / templates (``my_service``,
# ``mon_type``, ``xxx_...``, ``YYYY_MM_DD-...``, ``apps/web/.../x.ts``). They
# never point at a real file by design, so they are not documentation drift and
# must not be counted as stale.
_PLACEHOLDER_RE = re.compile(
    r"(?:^|/)(?:my_|mon_|ton_|votre_|vos_|your_|new_card|new_service|example_)"
    r"|/(?:my_domain|my_feature|mon_domaine)(?:/|\.|$)"
    r"|xxx|YYYY|MM_DD|/\.\.\.(?:/|$)|_here(?:\.|/|$)|<[a-z_]+>",
    re.IGNORECASE,
)
# The doc itself may explicitly flag a path as non-existent — a removed file, an
# example/uncommitted script, a "create this" instruction, a not-found note, or
# a rename history. Such a path is honest documentation, not drift, so a line
# carrying one of these markers is skipped.
_ANNOTATION_RE = re.compile(
    r"\[obsolete\]|obsol[eè]te|deprecated|d[ée]pr[ée]ci"
    r"|n'existe\s+(?:plus|pas)|removed|supprim|introuvable"
    r"|exemple|example|non\s+commit|not\s+committed|illustrat"
    r"|create\s+new|to\s+create|to\s+be\s+created|[cç]r[ée]er|\bcreer\b|à\s+cr[ée]er"
    r"|non\s+trouv|not\s+found|anciennement|formerly|renomm|renamed|remplac"
    r"|propos[ée]|proposed|planifi|planned|futur|hypoth"
    r"|save\s+as|enregistr|generate",
    re.IGNORECASE,
)


def _line_at(text: str, pos: int) -> str:
    """Return the full source line containing ``pos``."""
    start = text.rfind("\n", 0, pos) + 1
    end = text.find("\n", pos)
    return text[start:] if end == -1 else text[start:end]


def _prev_nonblank_line(text: str, pos: int) -> str:
    """Return the nearest non-blank line above the one containing ``pos``.

    Commands are commonly annotated on the comment line just above them
    (``# ... (exemple)`` / ``# Convert ... (script non commité)``), so the
    annotation lookup considers that line too.
    """
    line_start = text.rfind("\n", 0, pos) + 1
    cursor = line_start
    while cursor > 0:
        prev_end = cursor - 1  # the '\n' terminating the previous line
        prev_start = text.rfind("\n", 0, prev_end) + 1
        candidate = text[prev_start:prev_end]
        if candidate.strip():
            return candidate
        cursor = prev_start
    return ""


EXTERNAL_PREFIXES = ("http://", "https://", "mailto:", "#", "tel:")

#: Living documents that sit outside ``docs/`` and must be audited with it.
#: ``CONTRIBUTING.md`` and ``AGENTS.md`` joined the list on 2026-08-27: they were
#: outside every scan, and both were quoting a stale enforced coverage floor
#: (80% and 43% against a real 67%) that no gate could see. ``AGENTS.md`` is the
#: instruction file a second AI agent reads, so a wrong rule there is acted on.
ROOT_DOCUMENTS: tuple[str, ...] = (
    "README.md",
    "CLAUDE.md",
    "CONTRIBUTING.md",
    "AGENTS.md",
    "SECURITY.md",
    "apps/web/CLAUDE.md",
)

HISTORICAL_MARKERS = ("docs/architecture/ADR-", "docs/superpowers/")
ROADMAP_BASENAMES = {"NANOBOT_INTEGRATION_ROADMAP.md"}
ADR_INDEX_REL = "docs/architecture/ADR_INDEX.md"

# ``ADR-007`` in any surrounding text → the zero-padded canonical number.
_ADR_NUMBER_RE = re.compile(r"ADR-(\d+)")
# A link *target* whose final path segment is another ADR document.
_ADR_DOC_LINK_RE = re.compile(r"(?:^|/)(?:ADR-\d+[\w.-]*|ADR_INDEX)\.md$", re.IGNORECASE)

#: Entry points: reached by a human or a tool, not by a link from another
#: document, so "nobody links to it" is their normal state.
ENTRY_POINTS: frozenset[str] = frozenset(
    {
        "README.md",
        "CLAUDE.md",
        "AGENTS.md",
        "CONTRIBUTING.md",
        "SECURITY.md",
        "apps/web/CLAUDE.md",
        "docs/INDEX.md",
    }
)

#: Directory prefixes exempt from the orphan rule, each with its reason.
#:
#: ``docs/knowledge/`` is a PRODUCT surface, not developer navigation: the files
#: are indexed into the system RAG space at boot
#: (``src/domains/rag_spaces/system_indexer.py``, default
#: ``RAG_SPACES_SYSTEM_KNOWLEDGE_DIR_DEFAULT = "docs/knowledge"``) and reach
#: users as answers. Requiring an inbound markdown link would be asking the
#: wrong question of them.
ORPHAN_EXEMPT_PREFIXES: dict[str, str] = {
    "docs/knowledge/": (
        "System RAG corpus indexed at startup and served to users as answers, "
        "not a document reached by navigation."
    ),
    "docs/runbooks/alerts/": (
        "Reached from a firing alert's `runbook` annotation (verified by "
        "test_alerts_core_guard), not from a markdown link."
    ),
}

Finding = tuple[str, int, str]


def classify_document(rel_posix: str) -> str:
    """Classify a document as LIVING, HISTORICAL or ROADMAP.

    Public because ``doc_facts.py`` audits the same corpus for a different drift
    class and must agree on what "living" means. Two definitions would diverge,
    which is precisely the defect both modules exist to catch.

    Args:
        rel_posix: Document path relative to the repository root, POSIX form.

    Returns:
        ``"LIVING"``, ``"HISTORICAL"`` or ``"ROADMAP"``.
    """
    if any(rel_posix.startswith(marker) for marker in HISTORICAL_MARKERS):
        return "HISTORICAL"
    if rel_posix.rsplit("/", 1)[-1] in ROADMAP_BASENAMES:
        return "ROADMAP"
    return "LIVING"


def _adr_number(text: str) -> str | None:
    """Return the zero-padded ADR number found in ``text`` (e.g. ``007``), if any."""
    match = _ADR_NUMBER_RE.search(text)
    return match.group(1).zfill(3) if match else None


def _indexed_adr_numbers(root: Path) -> frozenset[str]:
    """Zero-padded ADR numbers referenced in ``ADR_INDEX.md`` (the active set).

    Returns an empty set when the index is absent, which disables the F024
    escalation entirely (fail-safe: never invents a regression).
    """
    index = root / ADR_INDEX_REL
    if not index.exists():
        return frozenset()
    text = index.read_text(encoding="utf-8", errors="replace")
    return frozenset(m.group(1).zfill(3) for m in _ADR_NUMBER_RE.finditer(text))


def _is_indexed_adr(rel_posix: str, indexed: frozenset[str]) -> bool:
    """True when ``rel_posix`` is an ADR file whose number is actively indexed."""
    if not rel_posix.startswith("docs/architecture/ADR-"):
        return False
    number = _adr_number(rel_posix.rsplit("/", 1)[-1])
    return number is not None and number in indexed


def _is_adr_doc_link(target: str) -> bool:
    """True when a link target points at another ADR document (not code)."""
    path_part = target.split("#")[0]
    return bool(_ADR_DOC_LINK_RE.search(path_part))


def blank_code_regions(text: str) -> str:
    """Replace fenced code blocks and inline code with spaces, preserving line numbers.

    Shared with ``doc_facts.py`` (see :func:`classify_document` for why the
    helpers are public rather than copied).

    Args:
        text: Raw markdown.

    Returns:
        The same text, same length and line numbering, with code regions blanked.
    """

    def _blank(match: re.Match[str]) -> str:
        return re.sub(r"[^\n]", " ", match.group(0))

    text = re.sub(r"```.*?```", _blank, text, flags=re.DOTALL)
    return re.sub(r"`[^`\n]+`", _blank, text)


def _with_pending_changes(root: Path, tracked: set[str]) -> set[str]:
    """Apply the working tree's additions and deletions to ``tracked``.

    ``git status --porcelain -uall -z`` lists untracked-but-not-ignored files
    (``??``) and deletions (``D`` in either column) — exactly the delta
    ``git add -A`` would produce. A rename is reported as its two halves, so a
    moved document is added under its new path and dropped from its old one
    without special handling.

    Args:
        root: Repository root.
        tracked: Paths currently in the index.

    Returns:
        The previewed path set. Unreadable status leaves ``tracked`` untouched:
        a preview that guesses is worse than one that declines.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all", "-z"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):  # pragma: no cover - defensive
        return tracked

    previewed = set(tracked)
    for entry in proc.stdout.split("\0"):
        if len(entry) < 4:
            continue
        index_state, worktree_state, path = entry[0], entry[1], entry[3:]
        if index_state == "?" and worktree_state == "?":
            previewed.add(path)
        elif "D" in (index_state, worktree_state):
            previewed.discard(path)
        elif index_state in {"A", "R", "C"} or worktree_state in {"A", "R", "C"}:
            previewed.add(path)
    return previewed


def tracked_paths(
    root: Path, *, include_unstaged: bool = False
) -> tuple[frozenset[str], frozenset[str]] | None:
    """Git-tracked files and directories (POSIX, exact case), or ``None``.

    Link-existence checks must mirror a fresh CI checkout, not the author's
    disk (F024 wave 2): a case-insensitive filesystem (Windows/macOS) resolves
    links whose case has drifted from the tracked name, and a locally present
    but git-ignored/untracked file (private runbooks) resolves links that are
    broken in every clone. The git index is authoritative on both. Outside a
    git checkout (e.g. the guard tests' tmp_path fixtures) this returns
    ``None`` and the disk remains the only source of truth.

    ``include_unstaged`` previews the COMMIT instead of the clone: tracked files
    PLUS what ``git add -A`` would stage, MINUS what it would delete. It exists
    because the strict default produces a recurring false alarm — every move or
    addition reports LIVING findings that vanish on ``git add``, and that
    simulation had been written by hand, twice, as a throwaway script.

    It is deliberately NOT "just read the disk": that shortcut also reveals
    gitignored documents. ``docs/runbooks/CLOUDFLARE_TUNNEL.md`` holds
    production access details, and reporting it as an orphan invites a
    maintainer to "fix" it by publishing a link broken in every clone.

    Args:
        root: Repository root.
        include_unstaged: Preview the next commit rather than the index.

    Returns:
        ``(files, directories)`` as POSIX paths, or ``None`` outside git.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    paths = {path for path in proc.stdout.split("\0") if path}
    if include_unstaged:
        paths = _with_pending_changes(root, paths)
    files = frozenset(paths)
    dirs: set[str] = set()
    for path in files:
        parent = path
        while "/" in parent:
            parent = parent.rsplit("/", 1)[0]
            if parent in dirs:
                break
            dirs.add(parent)
    # Frozen on the way out: the declared return type promises immutability, and
    # both callers treat the pair as a read-only index. MyPy caught the mismatch
    # only once doc_facts made this function public — `scripts/` is outside
    # `task lint:backend`'s mypy scope, so it had never been type-checked.
    return files, frozenset(dirs)


def doc_files(root: Path, tracked: tuple[frozenset[str], frozenset[str]] | None) -> list[Path]:
    """Collect the documentation files under audit.

    Inside a git checkout, untracked/ignored local documents are excluded so a
    local-only file neither produces findings absent from CI nor masks any.
    """
    files = sorted(root.glob("docs/**/*.md"))
    for extra in ROOT_DOCUMENTS:
        candidate = root / extra
        if candidate.exists():
            files.append(candidate)
    if tracked is None:
        return files
    tracked_files = tracked[0]
    return [doc for doc in files if doc.relative_to(root).as_posix() in tracked_files]


def _target_exists(
    root: Path, candidate: Path, tracked: tuple[frozenset[str], frozenset[str]] | None
) -> bool:
    """True when a link target exists — in the git index when available.

    The candidate is normalized LEXICALLY (``os.path.normpath``), never through
    ``Path.resolve``: on a case-insensitive filesystem ``resolve()`` folds the
    link's case to the on-disk name, which would hide exactly the case drift
    this check exists to catch.
    """
    if tracked is None:
        try:
            return candidate.resolve().exists()
        except OSError:
            return False
    tracked_files, tracked_dirs = tracked
    normalized = Path(os.path.normpath(str(candidate)))
    try:
        rel = normalized.relative_to(root).as_posix()
    except ValueError:
        # Escapes the repository — the index cannot answer; fall back to disk.
        try:
            return candidate.resolve().exists()
        except OSError:
            return False
    return rel in tracked_files or rel in tracked_dirs


def _check_links(
    root: Path,
    doc: Path,
    text_nocode: str,
    tracked: tuple[frozenset[str], frozenset[str]] | None,
) -> list[Finding]:
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
        if not _target_exists(root, candidate, tracked):
            line_no = text_nocode[: match.start()].count("\n") + 1
            findings.append((rel, line_no, target))
    return findings


def _check_code_paths(
    root: Path,
    doc: Path,
    text: str,
    tracked: tuple[frozenset[str], frozenset[str]] | None,
) -> list[Finding]:
    """Return stale inline code-path references in one document.

    Existence follows the same contract as links (``_target_exists``): inside a
    git checkout the git index is authoritative, so a locally present but
    git-ignored file (secrets, generated config) referenced without an
    annotation is stale — it is absent from every fresh clone.
    """
    findings: list[Finding] = []
    rel = doc.relative_to(root).as_posix()
    for match in CODE_PATH_RE.finditer(text):
        path = match.group(1).rstrip(".")
        if _PLACEHOLDER_RE.search(path):
            continue  # illustrative placeholder, not a real (stale) reference
        if _ANNOTATION_RE.search(_line_at(text, match.start())) or _ANNOTATION_RE.search(
            _prev_nonblank_line(text, match.start())
        ):
            continue  # the doc itself flags the path as absent/example/to-create
        candidates = (
            root / path,
            root / "apps" / "api" / path,
            root / "apps" / "api" / "src" / path,
            root / "apps" / "api" / "tests" / path,
            root / "apps" / "web" / path,
            root / "apps" / "web" / "src" / path,
        )
        if not any(_target_exists(root, candidate, tracked) for candidate in candidates):
            line_no = text[: match.start()].count("\n") + 1
            findings.append((rel, line_no, path))
    return findings


def is_orphan_exempt(rel_posix: str) -> bool:
    """True when a document is not expected to have an inbound markdown link."""
    if rel_posix in ENTRY_POINTS:
        return True
    return any(rel_posix.startswith(prefix) for prefix in ORPHAN_EXEMPT_PREFIXES)


def find_orphans(root: Path, *, include_unstaged: bool = False) -> list[str]:
    """LIVING documents no tracked document links to.

    A document nobody links to is a document nobody finds: it drifts unread,
    and it is the shape every stale duplicate in this repository took before it
    became one (``docs/metrics/CODE_METRICS_2025-01-21.md``, 19 months stale;
    ``docs/runbooks/redis/RedisConnectionPoolExhaustion.md``, a second runbook
    for one alert that contradicted the maintained one). Broken links are
    caught above; unreachable documents were not caught at all.

    HISTORICAL documents are excluded: a superseded ADR or a dated plan is a
    record, and records are not navigation.

    Args:
        root: Repository root.

    Returns:
        Orphan paths, sorted.
    """
    tracked = tracked_paths(root, include_unstaged=include_unstaged)
    docs = doc_files(root, tracked)
    linked: set[str] = set()

    for doc in docs:
        text = blank_code_regions(doc.read_text(encoding="utf-8", errors="replace"))
        for match in LINK_RE.finditer(text):
            target = match.group(2)
            if target.startswith(EXTERNAL_PREFIXES):
                continue
            path_part = target.split("#")[0].replace("%20", " ")
            if not path_part.endswith(".md"):
                continue
            candidate = (
                root / path_part.lstrip("/")
                if path_part.startswith("/")
                else doc.parent / path_part
            )
            try:
                linked.add(Path(os.path.normpath(str(candidate))).relative_to(root).as_posix())
            except ValueError:  # escapes the repository — never one of ours
                continue

    return sorted(
        rel
        for rel in (doc.relative_to(root).as_posix() for doc in docs)
        if classify_document(rel) == "LIVING" and not is_orphan_exempt(rel) and rel not in linked
    )


def audit(root: Path, *, include_unstaged: bool = False) -> dict[str, dict[str, list[Finding]]]:
    """Scan the documentation base and return classified drift findings.

    The returned mapping has two tables (``broken`` links and ``stale`` code
    paths), each keyed by section (``LIVING`` / ``HISTORICAL`` / ``ROADMAP``).
    The F024 escalation is applied here: broken ADR→ADR links inside an
    actively-indexed ADR move from HISTORICAL to LIVING.
    """
    broken: dict[str, list[Finding]] = {"LIVING": [], "HISTORICAL": [], "ROADMAP": []}
    stale: dict[str, list[Finding]] = {"LIVING": [], "HISTORICAL": [], "ROADMAP": []}
    indexed = _indexed_adr_numbers(root)
    tracked = tracked_paths(root, include_unstaged=include_unstaged)

    for doc in doc_files(root, tracked):
        rel_posix = doc.relative_to(root).as_posix()
        section = classify_document(rel_posix)
        text = doc.read_text(encoding="utf-8", errors="replace")
        links = _check_links(root, doc, blank_code_regions(text), tracked)
        if section == "HISTORICAL" and _is_indexed_adr(rel_posix, indexed):
            for finding in links:
                target = finding[2]
                broken["LIVING" if _is_adr_doc_link(target) else "HISTORICAL"].append(finding)
        else:
            broken[section].extend(links)
        stale[section].extend(_check_code_paths(root, doc, text, tracked))

    return {"broken": broken, "stale": stale}


def main(argv: list[str]) -> int:
    """Run the audit and print per-class reports."""
    args = [arg for arg in argv[1:] if not arg.startswith("--")]
    fail_on_stale = "--fail-on-stale" in argv
    include_unstaged = "--include-unstaged" in argv
    root = Path(args[0]).resolve() if args else Path.cwd()
    if not (root / "docs").is_dir():
        print(f"error: no docs/ directory under {root}", file=sys.stderr)
        return 2

    report = audit(root, include_unstaged=include_unstaged)
    if include_unstaged:
        print("(preview: tracked files plus what `git add -A` would stage)")
        print()
    broken, stale = report["broken"], report["stale"]

    for title, table in (("BROKEN LINKS", broken), ("STALE CODE PATHS", stale)):
        for section in ("LIVING", "HISTORICAL", "ROADMAP"):
            findings = table[section]
            print(f"=== {title} [{section}]: {len(findings)} ===")
            for rel, line_no, target in findings:
                print(f"{rel}:{line_no}: {target}")
            print()

    orphans = find_orphans(root, include_unstaged=include_unstaged)
    print(f"=== ORPHANS (LIVING, no inbound link): {len(orphans)} ===")
    for rel in orphans:
        print(rel)
    print()

    failed = bool(broken["LIVING"]) or bool(orphans) or (fail_on_stale and bool(stale["LIVING"]))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
