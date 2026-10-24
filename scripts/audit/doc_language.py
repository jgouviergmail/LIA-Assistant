#!/usr/bin/env python3
"""Documentation language ratchet: no new French document, a French list that only shrinks.

Why
---
``CLAUDE.md`` required every document in English while a third of the corpus was
French: the V14 revision (run R22, 2026-10-22) counted 284 of 833 tracked Markdown
documents mostly in French, among them ``docs/INDEX.md``, ``docs/ARCHITECTURE.md``
and ``docs/guides/GUIDE_TESTING.md``. The rule had been adopted after the corpus
existed, with no transition rule and no instrument (audit AC-039). The owner amended
it on 2026-10-22: a NEW document is written in English; an existing French document
may still be edited in French; the list of French documents is frozen and may only
shrink; living maps, dated plans and audit reports are exempt by decision.

Detection
---------
Deterministic: the share of French function words among the French and English
function words of a document's prose. Code blocks, inline code and link targets are
blanked first (``doc_audit.blank_code_regions``, one implementation). A document is
French from a share of :data:`FRENCH_SHARE`; one with fewer than
:data:`MIN_FUNCTION_WORDS` function words is too short to classify and is never
reported — a stated limit, not an oversight. Calibrated on 2026-10-23 on the corpus
(792 documents, 727 classified), which is bimodal: 416 below 0.05, 209 above 0.95,
37 mixed between 0.3 and 0.7. The French entry points measure 0.79 to 0.995; the
English references (README, CLAUDE, CONTRIBUTING, AGENTS, docs/knowledge) at most
0.003.

Corpus
------
Every tracked Markdown document (the git index, or the next commit with
``--include-unstaged``, as ``doc_audit`` reads it), minus :data:`EXEMPT_PREFIXES`
(the owner's exemptions) and localized product content: a file per language such as
``how.fr.md`` is French by design, not documentation in the rule's sense.

Baseline
--------
``scripts/audit/doc_language_baseline.json`` lists the frozen French documents. The
check fails on a French document absent from it (write it in English) and on an
entry that is gone or no longer French (``--update`` removes it). ``--update`` never
adds an entry; a moved French document keeps its place with ``--rename OLD NEW``.

Usage (from the repository root, or anywhere with REPO_ROOT):
    python scripts/audit/doc_language.py [REPO_ROOT] [--include-unstaged]
        [--update [--rename OLD NEW]]

Standard library only. Imports its sibling ``doc_audit`` by name: run from
``scripts/audit/`` as a script, Python puts that directory first on the path.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from doc_audit import blank_code_regions, tracked_paths

__all__ = [
    "BASELINE_REL",
    "EXEMPT_PREFIXES",
    "FRENCH_SHARE",
    "MIN_FUNCTION_WORDS",
    "Outcome",
    "Verdict",
    "check",
    "corpus",
    "exemption_for",
    "load_baseline",
    "main",
    "measure",
    "update",
]

BASELINE_REL = "scripts/audit/doc_language_baseline.json"

#: A document is French from this share of French function words.
FRENCH_SHARE = 0.5
#: Below this many function words a document is too short to classify.
MIN_FUNCTION_WORDS = 40

#: Exempt by the owner's decision of 2026-10-22, with the reason.
EXEMPT_PREFIXES: dict[str, str] = {
    "docs/maps/": "living maps: written in French as their source, translated per language",
    "docs/superpowers/plans/": "dated plans: working records of their day",
    "docs/audit/": "audit reports and their protocol: exempt by decision",
}
_LOCALIZED = re.compile(r"\.(?:de|es|fr|it|zh)\.md$")
_LOCALIZED_REASON = "localized product content: one file per language, French by design"
_SKIPPED_DIRECTORIES = frozenset({".git", "node_modules"})

#: Function words of one language that the other does not use as words. Forms both
#: languages write are left out on purpose: « a », « on » (an English preposition
#: and a French pronoun), « as », and « plus », « par », « son », « sans » (English
#: « plus a step », « on par with », « sans-serif »).
FRENCH_WORDS = frozenset(
    "le la les des du de un une et est sont pour dans sur avec qui que ne pas ce "
    "cette ces sa ses au aux il elle ils nous vous mais ou où être avoir été fait peut "
    "tout très comme aussi donc leur leurs même entre lors chaque après avant quand "
    "déjà encore selon ainsi alors en".split()
)
ENGLISH_WORDS = frozenset(
    "the and is are of to in for with that this it be by not or from at an which when has "
    "have was were will can its their they we you but if all any each only also than then "
    "there these those into does do".split()
)
_WORD = re.compile(r"[A-Za-zÀ-ÿœŒ]+(?:['’][A-Za-zÀ-ÿœŒ]+)?")
_ELISION = re.compile(r"['’]")
_LINK_TARGET = re.compile(r"https?://\S+|\]\([^)]*\)")


@dataclass(frozen=True)
class Verdict:
    """The language measurement of one document."""

    path: str
    french: int
    english: int

    @property
    def classified(self) -> bool:
        """Whether the document has enough function words to be judged."""
        return self.french + self.english >= MIN_FUNCTION_WORDS

    @property
    def share(self) -> float:
        """The share of French function words (0.0 when there are none at all)."""
        total = self.french + self.english
        return self.french / total if total else 0.0

    @property
    def is_french(self) -> bool:
        """Whether the document is French under the published rule."""
        return self.classified and self.share >= FRENCH_SHARE


@dataclass(frozen=True)
class Outcome:
    """The ratchet's verdict on a repository."""

    french: tuple[Verdict, ...]
    new_french: tuple[Verdict, ...]
    stale: tuple[tuple[str, str], ...]


def measure(text: str) -> tuple[int, int]:
    """Count the French and English function words of a document's prose.

    Args:
        text: The Markdown source.

    Returns:
        ``(french, english)`` function-word counts.
    """
    prose = _LINK_TARGET.sub(" ", blank_code_regions(text))
    french = english = 0
    for token in _WORD.findall(prose):
        word = _ELISION.split(token.lower())[-1]
        french += word in FRENCH_WORDS
        english += word in ENGLISH_WORDS
    return french, english


def exemption_for(rel: str) -> str | None:
    """Why ``rel`` is outside the corpus, or None when it is inside.

    Args:
        rel: Repository-relative POSIX path.

    Returns:
        The written reason of the exemption, or None.
    """
    for prefix, reason in EXEMPT_PREFIXES.items():
        if rel.startswith(prefix):
            return reason
    return _LOCALIZED_REASON if _LOCALIZED.search(rel) else None


def corpus(root: Path, *, include_unstaged: bool = False) -> list[str]:
    """The Markdown documents the rule governs, sorted.

    Args:
        root: Repository root.
        include_unstaged: Read the next commit rather than the git index.

    Returns:
        Repository-relative POSIX paths of existing, non-exempt documents.
    """
    tracked = tracked_paths(root, include_unstaged=include_unstaged)
    if tracked is not None:
        candidates = {rel for rel in tracked[0] if rel.endswith(".md")}
    else:
        candidates = {
            path.relative_to(root).as_posix()
            for path in root.rglob("*.md")
            if not _SKIPPED_DIRECTORIES & set(path.relative_to(root).parts)
        }
    return sorted(
        rel for rel in candidates if exemption_for(rel) is None and (root / rel).is_file()
    )


def load_baseline(root: Path) -> frozenset[str]:
    """The frozen French documents.

    Args:
        root: Repository root.

    Returns:
        The baseline's documents.

    Raises:
        OSError: If the baseline cannot be read.
        ValueError: If it is not the expected JSON shape.
    """
    data: object = json.loads((root / BASELINE_REL).read_text(encoding="utf-8"))
    documents = data.get("documents") if isinstance(data, dict) else None
    if not isinstance(documents, list) or not all(isinstance(d, str) for d in documents):
        raise ValueError(f"{BASELINE_REL} must hold a list of paths under 'documents'")
    return frozenset(documents)


def _write_baseline(root: Path, documents: frozenset[str]) -> None:
    data = {
        "_doc": (
            "French documents frozen by the documentation language ratchet (AC-039a, "
            "CLAUDE.md). Shrink-only: scripts/audit/doc_language.py --update removes a "
            "translated or deleted document and never adds one."
        ),
        "documents": sorted(documents),
    }
    path = root / BASELINE_REL
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )


def _verdicts(root: Path, *, include_unstaged: bool) -> dict[str, Verdict]:
    verdicts = {}
    for rel in corpus(root, include_unstaged=include_unstaged):
        text = (root / rel).read_text(encoding="utf-8", errors="replace")
        verdicts[rel] = Verdict(rel, *measure(text))
    return verdicts


def check(root: Path, *, include_unstaged: bool = False) -> Outcome:
    """Compare the corpus with the baseline.

    Args:
        root: Repository root.
        include_unstaged: Read the next commit rather than the git index.

    Returns:
        Every French document, those the baseline does not freeze, and the
        baseline entries that must leave it (with the reason).
    """
    baseline = load_baseline(root)
    verdicts = _verdicts(root, include_unstaged=include_unstaged)
    french = tuple(v for v in verdicts.values() if v.is_french)
    new_french = tuple(v for v in french if v.path not in baseline)
    stale = []
    for rel in sorted(baseline):
        verdict = verdicts.get(rel)
        if verdict is None:
            stale.append((rel, "no longer in the corpus"))
        elif not verdict.is_french:
            stale.append((rel, f"no longer French ({verdict.share:.2f})"))
    return Outcome(french, new_french, tuple(stale))


def update(
    root: Path, *, include_unstaged: bool = False, rename: tuple[str, str] | None = None
) -> list[str]:
    """Shrink the baseline to the documents still French; never add one.

    Args:
        root: Repository root.
        include_unstaged: Read the next commit rather than the git index.
        rename: ``(old, new)`` to carry a moved French document's entry over.

    Returns:
        The entries removed.

    Raises:
        ValueError: If ``rename`` is not a move of a frozen French document.
    """
    baseline = set(load_baseline(root))
    verdicts = _verdicts(root, include_unstaged=include_unstaged)
    if rename is not None:
        old, new = rename
        moved = verdicts.get(new)
        if old not in baseline:
            raise ValueError(f"{old} is not a frozen French document")
        if (root / old).exists():
            raise ValueError(f"{old} still exists: a rename carries a MOVED document")
        if moved is None or not moved.is_french:
            raise ValueError(f"{new} is not a French document of the corpus")
        baseline = (baseline - {old}) | {new}
    removed = sorted(rel for rel in baseline if not (rel in verdicts and verdicts[rel].is_french))
    _write_baseline(root, frozenset(baseline - set(removed)))
    return removed


def main(argv: list[str] | None = None) -> int:
    """Run the ratchet; ``--update`` shrinks the baseline first.

    Args:
        argv: Command-line arguments (defaults to ``sys.argv[1:]``).

    Returns:
        0 when no new French document and no stale entry remain, 1 otherwise.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("root", nargs="?", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--include-unstaged", action="store_true")
    parser.add_argument("--update", action="store_true", help="remove stale entries")
    parser.add_argument("--rename", nargs=2, metavar=("OLD", "NEW"))
    args = parser.parse_args(argv)
    if args.rename and not args.update:
        parser.error("--rename needs --update")
    root: Path = args.root
    try:
        if args.update:
            rename = (args.rename[0], args.rename[1]) if args.rename else None
            for rel in update(root, include_unstaged=args.include_unstaged, rename=rename):
                print(f"doc_language: removed {rel}")
        outcome = check(root, include_unstaged=args.include_unstaged)
    except (OSError, ValueError) as exc:
        print(f"doc_language: error: {exc}")
        return 1
    print(
        f"doc_language: {len(outcome.french)} French documents, "
        f"{len(outcome.new_french)} new, {len(outcome.stale)} stale entries"
    )
    # A moved frozen document shows up as BOTH a new French document and a stale
    # entry: the update alone would drop the entry, so the rename is named first.
    moved_hint = "; if it moved, task docs:language:update -- --rename OLD NEW"
    for verdict in outcome.new_french:
        print(
            f"doc_language: error: {verdict.path} is a new French document "
            f"({verdict.share:.2f}); write it in English{moved_hint}"
        )
    for rel, reason in outcome.stale:
        print(f"doc_language: error: {rel}: {reason}; task docs:language:update{moved_hint}")
    return 1 if outcome.new_french or outcome.stale else 0


if __name__ == "__main__":
    sys.exit(main())
