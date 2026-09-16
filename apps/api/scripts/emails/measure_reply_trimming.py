"""How well a trimmer keeps a person's own words in a reply — measured, not assumed (ADR-287).

The house trimmer (``normalizers/reply_trimming.py``) is pinned by a unit
test over a corpus of 48 bodies (eight families × six languages) plus two
guards where nothing may be cut. This script replays that SAME corpus and,
when a third-party candidate is importable in the running interpreter,
scores it beside the house one on the same bodies — so the choice between
the two is a number with a date, never a preference.

    task emails:corpus:measure
    <venv-with-the-candidate>/Scripts/python apps/api/scripts/emails/measure_reply_trimming.py

The house module is loaded by FILE PATH on purpose: it depends on the
standard library alone, while importing it through the package would pull
every connector client and the settings behind them — and the interpreter
holding the candidate is a throwaway venv that has none of that.

The candidate is ``mail-parser-reply`` (import name ``mailparser_reply``),
the maintained fork of GitHub's ``email_reply_parser`` with language packs.
Its adoption rule is written in ADR-287: 48/48 on the corpus AND an import
under the size ceiling below; otherwise the house trimmer stays.

Nothing here touches a network, a database or a person's data: the corpus is a
fixture.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import importlib.util
import json
import sys
import time
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[2]
HOUSE_MODULE = (
    REPO_ROOT / "src" / "domains" / "connectors" / "clients" / "normalizers" / "reply_trimming.py"
)
CORPUS_PATH = (
    REPO_ROOT
    / "tests"
    / "unit"
    / "domains"
    / "connectors"
    / "clients"
    / "normalizers"
    / "reply_trimming_corpus.json"
)
LANGUAGES = ("fr", "en", "de", "es", "it", "zh")

#: The candidate's distribution and import names.
CANDIDATE_DISTRIBUTION = "mail-parser-reply"
CANDIDATE_IMPORT = "mailparser_reply"
#: ADR-287's ceiling on what a trimmer may add to the API image, in bytes.
IMPORT_SIZE_CEILING_BYTES = 5 * 1024 * 1024

#: (body, subject) -> the person's own words. The candidate has no subject door.
Trimmer = Callable[[str, str | None], str]


def _load_house() -> ModuleType:
    spec = importlib.util.spec_from_file_location("house_reply_trimming", HOUSE_MODULE)
    if spec is None or spec.loader is None:  # pragma: no cover - a moved file
        raise SystemExit(f"cannot load {HOUSE_MODULE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_candidate() -> tuple[Trimmer | None, str]:
    """The candidate's trimmer and a one-line report of what it costs, or why it is absent."""
    started = time.perf_counter()
    try:
        module = importlib.import_module(CANDIDATE_IMPORT)
    except ImportError:
        return None, f"{CANDIDATE_DISTRIBUTION} is not importable here (pip install it to score it)"
    import_seconds = time.perf_counter() - started
    distribution = importlib.metadata.distribution(CANDIDATE_DISTRIBUTION)
    located = [Path(str(distribution.locate_file(entry))) for entry in distribution.files or ()]
    on_disk = sum(path.stat().st_size for path in located if path.is_file())
    parser = module.EmailReplyParser(languages=list(LANGUAGES))

    def trim(text: str, _subject: str | None) -> str:
        # The fair door: ``parse_reply`` keeps the signature by design, while
        # ``replies[0].body`` is the latest reply WITHOUT it — what the house
        # trimmer produces. Scoring the other door would measure a misuse.
        replies = parser.read(text=text).replies
        return text if not replies else replies[0].body

    verdict = "within" if on_disk <= IMPORT_SIZE_CEILING_BYTES else "OVER"
    report = (
        f"{CANDIDATE_DISTRIBUTION} {distribution.version}: {on_disk / 1024:.0f} KiB on disk "
        f"({verdict} the {IMPORT_SIZE_CEILING_BYTES // (1024 * 1024)} MiB ceiling), "
        f"requires {distribution.requires or 'nothing'}, import {import_seconds * 1000:.0f} ms"
    )
    return trim, report


def _same(actual: str, expected: str) -> bool:
    """Trailing whitespace is not a difference between two trimmers."""
    return actual.rstrip() == expected.rstrip()


def _score(name: str, trim: Trimmer, corpus: dict) -> dict[str, object]:
    families = corpus["families"]
    per_family: dict[str, int] = {}
    per_language: dict[str, int] = dict.fromkeys(LANGUAGES, 0)
    failures: list[str] = []
    for family, spec in families.items():
        hits = 0
        for language, body in spec["bodies"].items():
            if _same(trim(body, None), spec["kept"]):
                hits += 1
                per_language[language] += 1
            else:
                failures.append(f"{family}-{language}")
        per_family[family] = hits
    guards_kept = 0
    guard_names = [key for key in corpus["guards"] if not key.startswith("_")]
    for guard in guard_names:
        body = corpus["guards"][guard]
        if _same(trim(body, None), body):
            guards_kept += 1
        else:
            failures.append(f"guard:{guard}")
    forwards_kept = 0
    forwards = [
        (kind, language, case)
        for kind in ("by_subject", "by_banner")
        for language, case in corpus["forwards"][kind].items()
    ]
    for kind, language, case in forwards:
        if _same(trim(case["body"], case["subject"]), case["body"]):
            forwards_kept += 1
        else:
            failures.append(f"forward:{kind}-{language}")
    return {
        "name": name,
        "total": sum(per_family.values()),
        "of": sum(len(spec["bodies"]) for spec in families.values()),
        "per_family": per_family,
        "per_language": per_language,
        "guards_kept": guards_kept,
        "guards": len(guard_names),
        "forwards_kept": forwards_kept,
        "forwards": len(forwards),
        "failures": failures,
    }


def _print(score: dict[str, object]) -> None:
    print(
        f"\n== {score['name']}: {score['total']}/{score['of']} bodies, "
        f"{score['guards_kept']}/{score['guards']} guards kept, "
        f"{score['forwards_kept']}/{score['forwards']} forwards kept"
    )
    per_family: dict[str, int] = score["per_family"]  # type: ignore[assignment]
    for family, hits in per_family.items():
        print(f"   {family:<24} {hits}/{len(LANGUAGES)}")
    per_language: dict[str, int] = score["per_language"]  # type: ignore[assignment]
    print("   " + "  ".join(f"{lang}={hits}" for lang, hits in per_language.items()))
    failures: list[str] = score["failures"]  # type: ignore[assignment]
    if failures:
        print("   failed: " + ", ".join(failures))


def main() -> int:
    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    house = _load_house()
    print(f"corpus: {CORPUS_PATH.relative_to(REPO_ROOT)} — interpreter: {sys.executable}")
    _print(
        _score(
            "house trimmer",
            lambda body, subject: house.trim_quoted_reply(body, subject=subject),
            corpus,
        )
    )
    candidate, report = _load_candidate()
    print(f"\n{report}")
    if candidate is not None:
        _print(_score(CANDIDATE_DISTRIBUTION, candidate, corpus))
    return 0


if __name__ == "__main__":
    sys.exit(main())
