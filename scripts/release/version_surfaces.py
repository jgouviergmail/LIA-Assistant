"""Single declaration of every place a LIA release version or count lives.

Why this module exists
----------------------
A release used to be a checklist applied by hand across a dozen files. Every
surface that was forgotten drifted silently until a human noticed months later:
``story.*`` stranded at v1.21.17, ``docs/GETTING_STARTED.md`` at v1.21.21,
``apps/api/pyproject.toml`` at 1.21.9 while 1.24.0 shipped (audit F030), the
landing ADR count stranded at 183 from v1.27.0 to v1.27.4.

Three properties make that class of defect impossible rather than unlikely:

1. **One declaration, two consumers.** The CI guard
   (``apps/api/tests/unit/test_version_surface_consistency_guard.py``) and the
   bump script (``scripts/release/bump_surfaces.py``) read the SAME tables, so
   what a release must touch and what CI verifies cannot diverge.
2. **Discovery, not enumeration.** Guide stamps are found by pattern; a stamped
   guide that is neither tracked nor explicitly exempted raises
   :class:`UnknownStampError`. A guide added tomorrow reddens the build instead
   of drifting. Enumerating is exactly how the original list went stale.
3. **Named exemptions.** ``privacy.*``/``terms.*`` carry a deliberately frozen
   contractual stamp; the reason is written down next to the exemption, so
   nobody "fixes" it with a global sweep (the ``don't glob *.md`` lesson).

What this module deliberately does NOT own
------------------------------------------
- ``LANDING_STATS.tests`` — a real measurement (``pytest --collect-only`` +
  ``vitest list``). Fabricating it from a formula would publish a claim nobody
  measured; a count shown to the user is exact or it does not exist (ADR-185).
- ``LAST_UPDATED``, the README release theme and date — editorial content. The
  bump writes the timestamp when asked, but no machine can validate the prose.
- ``Re-measured at vX.Y.Z`` comments — historical traces. Rewriting them would
  assert a measurement that never happened.

Usage::

    from scripts.release.version_surfaces import canonical_version, version_occurrences
"""

from __future__ import annotations

import importlib.util
import json
import re
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "CountOccurrence",
    "CountSurface",
    "EXEMPT_GUIDE_STEMS",
    "GUIDES_DIR",
    "LAST_UPDATED_PATH",
    "GuideStamp",
    "MIN_EXPECTED_GUIDE_STAMPS",
    "Occurrence",
    "STAMPED_GUIDE_STEMS",
    "Surface",
    "SurfaceError",
    "UnknownStampError",
    "bump_version_surfaces",
    "canonical_version",
    "count_occurrences",
    "derived_counts",
    "discover_guide_stamps",
    "read_last_updated",
    "set_last_updated",
    "sync_derived_counts",
    "version_occurrences",
]

SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")
_VERSION = r"(?P<version>\d+\.\d+\.\d+)"
_COUNT = r"(?P<count>\d+)"

#: This repository, derived from this file rather than from a caller-supplied
#: root: sibling TOOLING is loaded from here, while the sources being measured
#: always come from the ``root`` argument.
_MODULE_ROOT = Path(__file__).resolve().parents[2]

GUIDES_DIR = "apps/web/src/data/guides"

#: Guide families stamped with the release version (18 files: 3 x 6 locales).
STAMPED_GUIDE_STEMS: tuple[str, ...] = ("how", "why", "story")

#: Stamped guides that must NOT follow the release, with the reason why.
EXEMPT_GUIDE_STEMS: dict[str, str] = {
    "privacy": (
        "Contractual text with its own policy date: the stamp records the "
        "version the policy was written against, not the current release."
    ),
    "terms": (
        "Contractual text with its own policy date: the stamp records the "
        "version the terms were written against, not the current release."
    ),
}

#: Anti-rot floor for the *real* repository (18 tracked stamps: 3 families x 6
#: locales). Enforced by the CI guard, not here: this module stays pure so it
#: can be exercised on small fixtures — same split as ``measure_sloc.py`` and
#: ``MIN_EXPECTED_FILES`` in the file-size ratchet guard.
MIN_EXPECTED_GUIDE_STAMPS = 18

#: The landing hero timestamp. Not a version and derived from nothing, so no
#: guard can validate it — the bump writes it when the caller supplies it.
LAST_UPDATED_PATH = "apps/web/src/lib/version.ts"

_LAST_UPDATED_RE = re.compile(
    r"^export const LAST_UPDATED = '(?P<timestamp>[^']+)';", re.MULTILINE
)
_LAST_UPDATED_VALUE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")

# A localized stamp line: ``**Application**: LIA v1.31.2``, ``**Application** :
# LIA v1.31.2`` (fr), ``**应用**：LIA v1.31.2`` (zh, full-width colon). The label
# is captured rather than listed so a seventh locale needs no code change.
_GUIDE_STAMP_RE = re.compile(
    rf"^\*\*(?P<label>[^*\n]+)\*\*[ \t]*[:：][ \t]*LIA v{_VERSION}",
    re.MULTILINE,
)


class SurfaceError(RuntimeError):
    """A declared surface cannot be read as expected."""


class UnknownStampError(SurfaceError):
    """A stamped guide is neither tracked nor explicitly exempted."""


@dataclass(frozen=True)
class Surface:
    """A file carrying the release version at a known place.

    Attributes:
        path: Repository-relative POSIX path.
        pattern: Regex exposing a ``version`` group; only that group is ever
            rewritten, so surrounding bytes survive untouched.
        label: Human-readable name used in failure messages.
        expected: Exact number of occurrences required. Matching a different
            number is an error, never a silent partial rewrite: a file that
            changed shape must be re-declared deliberately.
    """

    path: str
    pattern: re.Pattern[str]
    label: str
    expected: int = 1


@dataclass(frozen=True)
class CountSurface:
    """A file quoting a count that is derived from a source of truth.

    Attributes:
        path: Repository-relative POSIX path.
        pattern: Regex exposing a ``count`` group.
        source: Key into :func:`derived_counts`.
        label: Human-readable name used in failure messages.
        expected: Exact number of occurrences required.
    """

    path: str
    pattern: re.Pattern[str]
    source: str
    label: str
    expected: int = 1


@dataclass(frozen=True)
class Occurrence:
    """One version token found in a tracked surface."""

    path: str
    line: int
    version: str
    label: str


@dataclass(frozen=True)
class GuideStamp:
    """One discovered guide stamp, classified against the tracked/exempt sets."""

    path: str
    line: int
    version: str
    stem: str
    tracked: bool


@dataclass(frozen=True)
class CountOccurrence:
    """One derived count quoted by a surface."""

    path: str
    line: int
    value: int
    source: str
    label: str


#: Surfaces outside the guides. ``apps/api/pyproject.toml`` and both
#: ``package.json`` are also covered by ``test_version_drift_guard.py`` (F030,
#: manifest contract); they are declared here so the bump script writes them
#: from the same table that CI reads.
FIXED_SURFACES: tuple[Surface, ...] = (
    Surface(
        "package.json",
        re.compile(rf'^  "version": "{_VERSION}"', re.MULTILINE),
        "root package.json (single source of truth)",
    ),
    Surface(
        "apps/web/package.json",
        re.compile(rf'^  "version": "{_VERSION}"', re.MULTILINE),
        "web package.json",
    ),
    Surface(
        "apps/api/pyproject.toml",
        re.compile(rf'^version = "{_VERSION}"', re.MULTILINE),
        "backend pyproject.toml",
    ),
    Surface(
        "apps/web/public/firebase-messaging-sw.js",
        re.compile(rf"^const CACHE_VERSION = '{_VERSION}';", re.MULTILINE),
        "PWA service-worker cache version (ADR-146)",
    ),
    Surface(
        "docs/GETTING_STARTED.md",
        re.compile(rf"^\*\*Compatibility\*\*: LIA v{_VERSION}", re.MULTILINE),
        "GETTING_STARTED compatibility header",
    ),
    Surface(
        "README.md",
        re.compile(rf"<strong>Version {_VERSION}</strong>"),
        "README version block",
    ),
    # The `how` guides close on a provenance note naming the changelog range
    # the document was written against. It is a claim about coverage, and the
    # document IS extended every release — so the range belongs to the bump,
    # not to whoever remembers. It stopped at v1.33.0 for four releases while
    # the guide's own sections described v1.37.0 features. The separator is
    # part of the sentence, hence one declaration per locale.
    *(
        Surface(
            f"{GUIDES_DIR}/how.{locale}.md",
            re.compile(rf"v1\.0 {separator} v{_VERSION}"),
            f"how.{locale}.md provenance note (changelog range)",
        )
        for locale, separator in (
            ("en", "to"),
            ("fr", "à"),
            ("de", "bis"),
            ("es", "a"),
            ("it", "a"),
            ("zh", "至"),
        )
    ),
)

#: Surfaces quoting a derived count. The ``constants.ts`` patterns are anchored
#: on the ``LANDING_STATS`` literal shape (``  key: 123,``) so the explanatory
#: comment above it — which cites historical measurements — never matches.
COUNT_SURFACES: tuple[CountSurface, ...] = (
    CountSurface(
        "apps/web/src/components/landing/constants.ts",
        re.compile(rf"^  adrs: {_COUNT},", re.MULTILINE),
        "adr_files",
        "LANDING_STATS.adrs",
    ),
    CountSurface(
        "apps/web/src/components/landing/constants.ts",
        re.compile(rf"^  releases: {_COUNT},", re.MULTILINE),
        "changelog_releases",
        "LANDING_STATS.releases",
    ),
    # `metrics` sat next to two guarded neighbours and was not one: it read 486
    # against a real 490. A number that lives one line below a guarded number
    # is the least likely one anybody re-reads.
    CountSurface(
        "apps/web/src/components/landing/constants.ts",
        re.compile(rf"^  metrics: {_COUNT},", re.MULTILINE),
        "prometheus_metrics",
        "LANDING_STATS.metrics",
    ),
    CountSurface(
        "CLAUDE.md",
        re.compile(rf"\({_COUNT} ADR files"),
        "adr_files",
        "CLAUDE.md ADR-index pointer (file count)",
    ),
    CountSurface(
        "CLAUDE.md",
        re.compile(rf"ADR-{_COUNT} latest"),
        "adr_latest",
        "CLAUDE.md ADR-index pointer (latest number)",
    ),
    CountSurface(
        f"{GUIDES_DIR}/how.zh.md",
        re.compile(rf"{_COUNT} 篇 ADR"),
        "adr_files",
        "how.zh.md ADR count (the zh guide quotes an exact number, the 5 "
        "others say '100+')",
        expected=3,
    ),
    # The `how` guides carry the ADR count TWICE each: once in the reliability
    # row, once in the codebase-metrics table. Only the zh phrasing was
    # declared, so the table figure drifted to 242 in all six languages while
    # the guard stayed green. Declared per locale because the label is
    # translated and the digit grouping is part of the language.
    *(
        CountSurface(
            f"{GUIDES_DIR}/how.{locale}.md",
            re.compile(rf"\| {label} \| {_COUNT} \|"),
            "adr_files",
            f"how.{locale}.md codebase-metrics table (ADR count)",
        )
        for locale, label in (
            ("en", r"ADRs \(Architecture Decision Records\)"),
            ("fr", r"ADRs \(Architecture Decision Records\)"),
            ("de", r"ADRs \(Architecture Decision Records\)"),
            ("es", r"ADRs \(Architecture Decision Records\)"),
            ("it", r"ADR \(Architecture Decision Record\)"),
        )
    ),
    CountSurface(
        f"{GUIDES_DIR}/how.zh.md",
        re.compile(
            rf"\| ADR\uff08\u67b6\u6784\u51b3\u7b56\u8bb0\u5f55\uff09 \| {_COUNT} \u7bc7 \|"
        ),
        "adr_files",
        "how.zh.md codebase-metrics table (ADR count)",
    ),
    # Every "N ADRs" of the five non-zh `how` guides, not just the reliability
    # row. The row alone was declared, so the three PROSE occurrences of the
    # same number drifted to 245 against a real 248 — in the same file, three
    # lines below a guarded 248. A table guard cannot see a sentence: the zh
    # surface above matches the token itself, and this is its counterpart.
    # `expected=4` also means a sixth occurrence fails loudly instead of
    # joining silently, which is the guide-stamp doctrine applied to counts.
    *(
        CountSurface(
            f"{GUIDES_DIR}/how.{locale}.md",
            re.compile(rf"\b{_COUNT} ADRs\b"),
            "adr_files",
            f"how.{locale}.md ADR count (reliability row + 3 prose sentences)",
            expected=4,
        )
        for locale in ("en", "fr", "de", "es", "it")
    ),
    # The `story` guides' key-figures table joined on 2026-08-27. It is the most
    # public claim the project makes about itself, and it was the only counter
    # table under no guard at all: 240 ADRs and 222 releases, in six languages,
    # against a real 245 and 228. Six releases of silent drift on the page whose
    # own argument is that the result is measured.
    *(
        surface
        for locale, adr_label, release_label in (
            (
                "en",
                r"Documented architecture decisions \(ADR\)",
                r"Versions shipped at a steady pace",
            ),
            (
                "fr",
                r"D\u00e9cisions d'architecture document\u00e9es \(ADR\)",
                r"Versions livr\u00e9es \u00e0 rythme r\u00e9gulier",
            ),
            (
                "de",
                r"Dokumentierte Architekturentscheidungen \(ADR\)",
                r"In regelm\u00e4\u00dfigem Rhythmus gelieferte Versionen",
            ),
            (
                "es",
                r"Decisiones de arquitectura documentadas \(ADR\)",
                r"Versiones entregadas a ritmo regular",
            ),
            (
                "it",
                r"Decisioni di architettura documentate \(ADR\)",
                r"Versioni rilasciate a ritmo regolare",
            ),
            (
                "zh",
                r"\u5df2\u8bb0\u5f55\u7684\u67b6\u6784\u51b3\u7b56\uff08ADR\uff09",
                r"\u4ee5\u7a33\u5b9a\u8282\u594f\u4ea4\u4ed8\u7684\u7248\u672c",
            ),
        )
        for surface in (
            CountSurface(
                f"{GUIDES_DIR}/story.{locale}.md",
                re.compile(rf"\| {adr_label} \| \*\*{_COUNT}\*\* \|"),
                "adr_files",
                f"story.{locale}.md key figures (ADR count)",
            ),
            CountSurface(
                f"{GUIDES_DIR}/story.{locale}.md",
                re.compile(rf"\| {release_label} \| \*\*{_COUNT}\*\* \|"),
                "changelog_releases",
                f"story.{locale}.md key figures (release count)",
            ),
        )
    ),
    # Two ADR counters written in PROSE rather than in a table, which is exactly
    # why they escaped every surface: story's "among the N documented" (240 in
    # six languages against a real 245) and how.zh's "N 篇 MADR 格式的 ADR"
    # (242, one word outside the declared "N 篇 ADR" regex, while its five
    # siblings were corrected). A guard that only reads tables guards tables.
    *(
        CountSurface(
            f"{GUIDES_DIR}/story.{locale}.md",
            re.compile(pattern),
            "adr_files",
            f"story.{locale}.md structural-decisions sentence (ADR count)",
        )
        for locale, pattern in (
            ("en", rf"among the {_COUNT} documented"),
            ("fr", rf"parmi les {_COUNT} document\u00e9es"),
            ("de", rf"unter den {_COUNT} dokumentierten"),
            ("es", rf"entre las {_COUNT} documentadas"),
            ("it", rf"tra le {_COUNT} documentate"),
            (
                "zh",
                rf"\u5728 {_COUNT} \u4e2a\u5df2\u8bb0\u5f55\u7684\u51b3\u7b56\u4e2d",
            ),
        )
    ),
    CountSurface(
        f"{GUIDES_DIR}/how.zh.md",
        re.compile(rf"{_COUNT} \u7bc7 MADR"),
        "adr_files",
        "how.zh.md MADR sentence (ADR count)",
    ),
    # docs/INDEX.md joined on 2026-08-27: it quoted the ADR count TWICE, with two
    # different wrong values (229 in its metrics table, 243 in the architects'
    # table) against a real 245. An index that miscounts what it indexes is the
    # least trustworthy place for a number to live by hand.
    CountSurface(
        "docs/INDEX.md",
        re.compile(rf"^\| ADRs \| {_COUNT} ADR files", re.MULTILINE),
        "adr_files",
        "INDEX.md metrics table (ADR file count)",
    ),
    CountSurface(
        "docs/INDEX.md",
        re.compile(rf"ADR-{_COUNT} latest"),
        "adr_latest",
        "INDEX.md metrics table (latest ADR number)",
    ),
    CountSurface(
        "docs/INDEX.md",
        re.compile(rf"Architecture Decision Records \({_COUNT} ADR files\)"),
        "adr_files",
        "INDEX.md architects' table (ADR file count)",
    ),
    # The Prometheus metric count, quoted in eight places against ONE source.
    # Measured 2026-08-29 before declaring them: CLAUDE.md said 500+, README
    # said 483 in its metrics table and 425 in its observability section, the
    # six `how` guides said 473 twice each — five different numbers, all of
    # them read as facts, for a value the code owns. This is CLAUDE.md's own
    # rule #1 ("never restate a value the code owns") applied to itself.
    CountSurface(
        "CLAUDE.md",
        re.compile(rf"{_COUNT} Prometheus metrics defined in"),
        "prometheus_metrics",
        "CLAUDE.md observability pointer (metric count)",
    ),
    CountSurface(
        "README.md",
        re.compile(rf"\*\*{_COUNT}\*\* Prometheus metrics"),
        "prometheus_metrics",
        "README.md key-figures table (metric count)",
    ),
    CountSurface(
        "README.md",
        re.compile(rf"\*\*Prometheus\*\*: {_COUNT} custom metrics"),
        "prometheus_metrics",
        "README.md observability section (metric count)",
    ),
    # The README's own key-figures row drifted the same way: 242 ADRs against
    # a real 249, and 224 releases against a real count it never re-read.
    CountSurface(
        "README.md",
        re.compile(rf"\*\*{_COUNT}\*\* ADRs"),
        "adr_files",
        "README.md key-figures table (ADR count)",
    ),
    CountSurface(
        "README.md",
        re.compile(rf"\*\*{_COUNT}\*\* versions shipped"),
        "changelog_releases",
        "README.md key-figures table (release count)",
    ),
    # Anchored on the TABLE CELL (`| N ...`), not on the words alone: the same
    # guides legitimately say "23 Prometheus metrics files" (a file count) and
    # "11 Prometheus metrics in metrics_journals.py" (a per-module count). A
    # looser pattern swallowed all four and would have forced two unrelated
    # numbers to follow the global total.
    CountSurface(
        f"{GUIDES_DIR}/how.en.md",
        re.compile(rf"\| {_COUNT} (?:Prometheus metrics,|custom metrics \(RED)"),
        "prometheus_metrics",
        "how.en.md metric count (transparency row + Prometheus row)",
        expected=2,
    ),
    CountSurface(
        f"{GUIDES_DIR}/how.fr.md",
        re.compile(rf"\| {_COUNT} métriques (?:Prometheus,|custom \(RED)"),
        "prometheus_metrics",
        "how.fr.md metric count (transparency row + Prometheus row)",
        expected=2,
    ),
    CountSurface(
        f"{GUIDES_DIR}/how.de.md",
        re.compile(rf"\| {_COUNT} (?:Prometheus-Metriken,|benutzerdefinierte Metriken \(RED)"),
        "prometheus_metrics",
        "how.de.md metric count (transparency row + Prometheus row)",
        expected=2,
    ),
    CountSurface(
        f"{GUIDES_DIR}/how.es.md",
        re.compile(rf"\| {_COUNT} métricas (?:Prometheus,|custom \(RED)"),
        "prometheus_metrics",
        "how.es.md metric count (transparency row + Prometheus row)",
        expected=2,
    ),
    CountSurface(
        f"{GUIDES_DIR}/how.it.md",
        re.compile(rf"\| {_COUNT} metriche (?:Prometheus,|custom \(RED)"),
        "prometheus_metrics",
        "how.it.md metric count (transparency row + Prometheus row)",
        expected=2,
    ),
    CountSurface(
        f"{GUIDES_DIR}/how.zh.md",
        re.compile(rf"\| {_COUNT} (?:Prometheus 指标、|自定义指标（RED)"),
        "prometheus_metrics",
        "how.zh.md metric count (transparency row + Prometheus row)",
        expected=2,
    ),
    # The same guides restate the total once more, in PROSE, and that sentence
    # drifted for four releases (490 against a real 492) while every guarded
    # table cell stayed green: a guard that watches a table cannot see a
    # paragraph. Anchored on the words that follow the number so it cannot
    # collide with the table rows above.
    CountSurface(
        f"{GUIDES_DIR}/how.en.md",
        re.compile(rf"{_COUNT} defined; the"),
        "prometheus_metrics",
        "how.en.md metric count (coverage sentence)",
    ),
    CountSurface(
        f"{GUIDES_DIR}/how.fr.md",
        re.compile(rf"{_COUNT} définies ; les"),
        "prometheus_metrics",
        "how.fr.md metric count (coverage sentence)",
    ),
    CountSurface(
        f"{GUIDES_DIR}/how.de.md",
        re.compile(rf"{_COUNT} definiert; die"),
        "prometheus_metrics",
        "how.de.md metric count (coverage sentence)",
    ),
    CountSurface(
        f"{GUIDES_DIR}/how.es.md",
        re.compile(rf"{_COUNT} definidas; las"),
        "prometheus_metrics",
        "how.es.md metric count (coverage sentence)",
    ),
    CountSurface(
        f"{GUIDES_DIR}/how.it.md",
        re.compile(rf"{_COUNT} definite; le"),
        "prometheus_metrics",
        "how.it.md metric count (coverage sentence)",
    ),
    CountSurface(
        f"{GUIDES_DIR}/how.zh.md",
        re.compile(rf"{_COUNT} 项；其中"),
        "prometheus_metrics",
        "how.zh.md metric count (coverage sentence)",
    ),
    # And the blog article, which no guard had ever looked inside: it said
    # 473 against a real 492, in its TITLE — the most visible sentence of
    # the page — and again in its body. Each surface is anchored on the
    # words that follow it in its own sentence, because the bare phrase
    # also matches an unrelated "5 métriques Prometheus" in the same file:
    # the same collision the guide surfaces above already guard against.
    CountSurface(
        "apps/web/locales/en/translation.json",
        re.compile(rf"{_COUNT} Prometheus Metrics, 26"),
        "prometheus_metrics",
        "blog observability article title (en)",
    ),
    CountSurface(
        "apps/web/locales/en/translation.json",
        re.compile(rf"{_COUNT} Prometheus metrics covering"),
        "prometheus_metrics",
        "blog observability article body (en)",
    ),
    CountSurface(
        "apps/web/locales/fr/translation.json",
        re.compile(rf"{_COUNT} métriques Prometheus, 26"),
        "prometheus_metrics",
        "blog observability article title (fr)",
    ),
    CountSurface(
        "apps/web/locales/fr/translation.json",
        re.compile(rf"{_COUNT} métriques Prometheus couvrant"),
        "prometheus_metrics",
        "blog observability article body (fr)",
    ),
    CountSurface(
        "apps/web/locales/de/translation.json",
        re.compile(rf"{_COUNT} Prometheus-Metriken, 26"),
        "prometheus_metrics",
        "blog observability article title (de)",
    ),
    CountSurface(
        "apps/web/locales/de/translation.json",
        re.compile(rf"{_COUNT} Prometheus-Metriken für"),
        "prometheus_metrics",
        "blog observability article body (de)",
    ),
    CountSurface(
        "apps/web/locales/es/translation.json",
        re.compile(rf"{_COUNT} métricas Prometheus, 26"),
        "prometheus_metrics",
        "blog observability article title (es)",
    ),
    CountSurface(
        "apps/web/locales/es/translation.json",
        re.compile(rf"{_COUNT} métricas Prometheus que cubren"),
        "prometheus_metrics",
        "blog observability article body (es)",
    ),
    CountSurface(
        "apps/web/locales/it/translation.json",
        re.compile(rf"{_COUNT} metriche Prometheus, 26"),
        "prometheus_metrics",
        "blog observability article title (it)",
    ),
    CountSurface(
        "apps/web/locales/it/translation.json",
        re.compile(rf"{_COUNT} metriche Prometheus che coprono"),
        "prometheus_metrics",
        "blog observability article body (it)",
    ),
    CountSurface(
        "apps/web/locales/zh/translation.json",
        re.compile(rf"{_COUNT}个Prometheus指标、26"),
        "prometheus_metrics",
        "blog observability article title (zh)",
    ),
    CountSurface(
        "apps/web/locales/zh/translation.json",
        re.compile(rf"{_COUNT}个Prometheus指标，覆盖"),
        "prometheus_metrics",
        "blog observability article body (zh)",
    ),
    CountSurface(
        "docs/knowledge/34_self_diagnostics.md",
        re.compile(rf"{_COUNT} metrics are defined and"),
        "prometheus_metrics",
        "self-diagnostics knowledge mirror (coverage sentence)",
    ),
)


def _read(root: Path, relative: str) -> str:
    """Read a declared surface, preserving line endings verbatim.

    Args:
        root: Repository root.
        relative: Repository-relative POSIX path.

    Returns:
        The file content with its original newlines.

    Raises:
        FileNotFoundError: If the declared surface no longer exists — a
            renamed or deleted surface must fail loudly, never scan nothing.
    """
    path = root / relative
    if not path.is_file():
        raise FileNotFoundError(
            f"Declared release surface is missing: {relative}. Either restore it "
            "or update scripts/release/version_surfaces.py in the same change."
        )
    with path.open("r", encoding="utf-8", newline="") as handle:
        return handle.read()


def _write(root: Path, relative: str, text: str) -> None:
    """Write a surface back without translating line endings."""
    with (root / relative).open("w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def _line_of(text: str, index: int) -> int:
    """1-based line number of ``index`` in ``text``."""
    return text.count("\n", 0, index) + 1


def _require_semver(version: str) -> str:
    """Validate a dotted three-part numeric version.

    Args:
        version: Candidate version string.

    Returns:
        The validated version.

    Raises:
        ValueError: If it is not semver-like.
    """
    if not SEMVER_PATTERN.match(version):
        raise ValueError(f"Not a semver-like version: {version!r} (expected X.Y.Z)")
    return version


def canonical_version(root: Path) -> str:
    """Return the release version from the root ``package.json``.

    Args:
        root: Repository root.

    Returns:
        The canonical version.

    Raises:
        ValueError: If the declared version is not semver-like.
        FileNotFoundError: If the manifest is missing.
    """
    manifest = json.loads(_read(root, "package.json"))
    return _require_semver(str(manifest.get("version", "")))


def _guide_paths(root: Path) -> list[Path]:
    """Every markdown guide, sorted for deterministic output."""
    return sorted((root / GUIDES_DIR).glob("*.md"))


def discover_guide_stamps(root: Path) -> list[GuideStamp]:
    """Find every ``**Label**: LIA vX.Y.Z`` stamp under the guides directory.

    Discovery is deliberate: the tracked set is derived from the file stem, so
    a new stamped guide is *seen* even though no table lists it. Classification
    (and the failure on an unknown stem) happens in :func:`version_occurrences`.

    Args:
        root: Repository root.

    Returns:
        Every discovered stamp, tracked and exempt alike, sorted by path.
    """
    stamps: list[GuideStamp] = []
    for path in _guide_paths(root):
        relative = path.relative_to(root).as_posix()
        with path.open("r", encoding="utf-8", newline="") as handle:
            text = handle.read()
        stem = path.name.split(".", 1)[0]
        for match in _GUIDE_STAMP_RE.finditer(text):
            stamps.append(
                GuideStamp(
                    path=relative,
                    line=_line_of(text, match.start()),
                    version=match.group("version"),
                    stem=stem,
                    tracked=stem in STAMPED_GUIDE_STEMS,
                )
            )
    return stamps


def _classified_stamps(root: Path) -> list[GuideStamp]:
    """Discover stamps and reject any that nobody has classified.

    Raises:
        UnknownStampError: If a stamped guide is neither tracked nor exempt.
    """
    stamps = discover_guide_stamps(root)
    unknown = sorted(
        {
            stamp.stem
            for stamp in stamps
            if not stamp.tracked and stamp.stem not in EXEMPT_GUIDE_STEMS
        }
    )
    if unknown:
        raise UnknownStampError(
            "Stamped guide(s) with no declared policy: "
            + ", ".join(unknown)
            + ". Add the stem to STAMPED_GUIDE_STEMS (it follows the release) or "
            "to EXEMPT_GUIDE_STEMS with a written reason (it does not) in "
            "scripts/release/version_surfaces.py."
        )
    return stamps


def _fixed_occurrences(root: Path) -> list[Occurrence]:
    """Read every non-guide surface declared in :data:`FIXED_SURFACES`.

    Raises:
        SurfaceError: If a surface matches a different number of times than
            declared — a partial match would bump some occurrences only.
    """
    found: list[Occurrence] = []
    for surface in FIXED_SURFACES:
        text = _read(root, surface.path)
        matches = list(surface.pattern.finditer(text))
        if len(matches) != surface.expected:
            raise SurfaceError(
                f"{surface.label} ({surface.path}): expected {surface.expected} "
                f"version occurrence(s), found {len(matches)}. The file changed "
                "shape — update the pattern in version_surfaces.py."
            )
        found.extend(
            Occurrence(
                path=surface.path,
                line=_line_of(text, match.start()),
                version=match.group("version"),
                label=surface.label,
            )
            for match in matches
        )
    return found


def version_occurrences(root: Path) -> list[Occurrence]:
    """Every version token that must equal :func:`canonical_version`.

    Args:
        root: Repository root.

    Returns:
        Occurrences from the fixed surfaces and the tracked guide stamps.

    Raises:
        FileNotFoundError: If a declared surface is missing.
        UnknownStampError: If a stamped guide is unclassified.
        SurfaceError: If a surface matches an unexpected number of times.
    """
    found = _fixed_occurrences(root)
    found.extend(
        Occurrence(
            path=stamp.path,
            line=stamp.line,
            version=stamp.version,
            label=f"guide stamp ({stamp.path.rsplit('/', 1)[-1]})",
        )
        for stamp in _classified_stamps(root)
        if stamp.tracked
    )
    return found


def _prometheus_metric_count(root: Path) -> int:
    """How many Prometheus metrics the backend defines.

    Loaded from ``scripts/audit/measure_metric_coverage.py`` rather than
    reimplemented: that module owns the AST scan (a regex over the source
    over-counts — it reads ``ZoneInfo("UTC")`` as an ``Info`` metric), and the
    coverage ratchet already depends on it. Two scanners would have disagreed,
    which is precisely the failure this surface exists to close: seven public
    documents quoted five different metric counts (500+, 483, 473, 450+, 425)
    for one source, and every one of them read as a fact.

    The scanner is loaded from THIS repository, never from ``root``: it is
    code, not data. ``root`` supplies the sources being counted, which is what
    lets the function run against a synthetic fixture — the same split as
    ``MIN_EXPECTED_GUIDE_STAMPS``, whose anti-rot floor lives in the CI guard
    so this module stays pure.

    Args:
        root: Repository root holding the sources to scan.

    Returns:
        Number of distinct metric names defined under ``root/apps/api/src``.

    Raises:
        SurfaceError: If the scanner or the backend source tree is missing.
            An absent source tree is never counted as zero: every surface
            quoting a real number would read as drifted, and the repair would
            write zeros into six public documents.
    """
    scanner = _MODULE_ROOT / "scripts" / "audit" / "measure_metric_coverage.py"
    if not scanner.is_file():
        raise SurfaceError(f"Metric scanner not found at {scanner} — broken checkout?")

    src_dir = root / "apps" / "api" / "src"
    if not src_dir.is_dir():
        raise SurfaceError(f"Backend source tree not found at {src_dir} — wrong root?")

    spec = importlib.util.spec_from_file_location("_measure_metric_coverage", scanner)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise SurfaceError(f"Cannot load the metric scanner at {scanner}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return len(module.metrics_defined_in_code(src_dir))


def derived_counts(root: Path) -> dict[str, int]:
    """Recompute the counts quoted by public surfaces from their sources.

    Args:
        root: Repository root.

    Returns:
        ``adr_files`` (ADR markdown files), ``adr_latest`` (highest ADR number
        — ADR-008 has no file, so it runs one above the count),
        ``changelog_releases`` (``## [x]`` headings, excluding ``Unreleased``)
        and ``prometheus_metrics`` (metrics defined in the backend).

    Raises:
        SurfaceError: If a source directory or file is missing or empty.
    """
    adr_dir = root / "docs" / "architecture"
    adr_files = sorted(adr_dir.glob("ADR-*.md"))
    if not adr_files:
        raise SurfaceError(f"No ADR files found under {adr_dir} — wrong root?")
    numbers = [
        int(match.group(1))
        for match in (re.match(r"ADR-(\d+)", path.name) for path in adr_files)
        if match is not None
    ]

    changelog = _read(root, "CHANGELOG.md")
    headings = re.findall(r"^## \[([^\]]+)\]", changelog, re.MULTILINE)
    releases = [name for name in headings if name.strip().lower() != "unreleased"]
    if not releases:
        raise SurfaceError("No release headings found in CHANGELOG.md — wrong root?")

    return {
        "adr_files": len(adr_files),
        "adr_latest": max(numbers),
        "changelog_releases": len(releases),
        "prometheus_metrics": _prometheus_metric_count(root),
    }


def count_occurrences(root: Path) -> list[CountOccurrence]:
    """Every quoted count found in the declared count surfaces.

    Args:
        root: Repository root.

    Returns:
        One record per quoted count.

    Raises:
        SurfaceError: If a count surface matches an unexpected number of times.
        FileNotFoundError: If a count surface is missing.
    """
    found: list[CountOccurrence] = []
    for surface in COUNT_SURFACES:
        text = _read(root, surface.path)
        matches = list(surface.pattern.finditer(text))
        if len(matches) != surface.expected:
            raise SurfaceError(
                f"{surface.label} ({surface.path}): expected {surface.expected} "
                f"occurrence(s) of the {surface.source} count, found {len(matches)}."
            )
        found.extend(
            CountOccurrence(
                path=surface.path,
                line=_line_of(text, match.start()),
                value=int(match.group("count")),
                source=surface.source,
                label=surface.label,
            )
            for match in matches
        )
    return found


def read_last_updated(root: Path) -> str:
    """Return the landing timestamp currently declared in ``version.ts``.

    Args:
        root: Repository root.

    Returns:
        The ISO-like timestamp, e.g. ``2026-08-22T07:00:00``.

    Raises:
        SurfaceError: If the declaration cannot be found.
        FileNotFoundError: If ``version.ts`` is missing.
    """
    text = _read(root, LAST_UPDATED_PATH)
    match = _LAST_UPDATED_RE.search(text)
    if match is None:
        raise SurfaceError(
            f"No LAST_UPDATED declaration found in {LAST_UPDATED_PATH} — the file "
            "changed shape; update the pattern in version_surfaces.py."
        )
    return match.group("timestamp")


def set_last_updated(root: Path, timestamp: str) -> bool:
    """Write the landing timestamp shown on the hero.

    The value is always supplied by the caller, never read from the clock: a
    release timestamp is an editorial fact (when the release is *published*),
    and deriving it here would make the tool non-deterministic and untestable.

    Args:
        root: Repository root.
        timestamp: ``YYYY-MM-DDTHH:MM:SS``.

    Returns:
        ``True`` if the file changed, ``False`` when it already carried it.

    Raises:
        ValueError: If ``timestamp`` is not in the expected ISO-like format.
        SurfaceError: If the declaration cannot be found.
    """
    if not _LAST_UPDATED_VALUE_RE.match(timestamp):
        raise ValueError(
            f"Not an ISO-like timestamp: {timestamp!r} (expected YYYY-MM-DDTHH:MM:SS)"
        )
    text = _read(root, LAST_UPDATED_PATH)
    if _LAST_UPDATED_RE.search(text) is None:
        raise SurfaceError(
            f"No LAST_UPDATED declaration found in {LAST_UPDATED_PATH} — the file "
            "changed shape; update the pattern in version_surfaces.py."
        )
    updated = _replace_group(text, _LAST_UPDATED_RE, "timestamp", timestamp)
    if updated == text:
        return False
    _write(root, LAST_UPDATED_PATH, updated)
    return True


def _replace_group(text: str, pattern: re.Pattern[str], group: str, value: str) -> str:
    """Replace only ``group`` in every match, leaving all other bytes intact.

    Rewriting through the group's span (rather than re-emitting the whole match)
    is what makes the bump byte-preserving: CRLF, spacing, localized labels and
    surrounding prose are never re-rendered.
    """
    pieces: list[str] = []
    cursor = 0
    for match in pattern.finditer(text):
        start, end = match.span(group)
        pieces.append(text[cursor:start])
        pieces.append(value)
        cursor = end
    pieces.append(text[cursor:])
    return "".join(pieces)


def bump_version_surfaces(root: Path, version: str) -> list[str]:
    """Rewrite every tracked surface to ``version``.

    Validation runs to completion BEFORE the first write: an unclassified guide
    stamp or a missing surface aborts with nothing written, because a partial
    bump is harder to detect than no bump at all.

    Args:
        root: Repository root.
        version: Target version, semver-like.

    Returns:
        Repository-relative paths actually modified, sorted. Empty when every
        surface already carries the target version (the call is idempotent).

    Raises:
        ValueError: If ``version`` is not semver-like.
        FileNotFoundError: If a declared surface is missing.
        UnknownStampError: If a stamped guide is unclassified.
        SurfaceError: If a surface matches an unexpected number of times.
    """
    _require_semver(version)
    _fixed_occurrences(root)
    stamps = _classified_stamps(root)

    changed: set[str] = set()

    for surface in FIXED_SURFACES:
        text = _read(root, surface.path)
        updated = _replace_group(text, surface.pattern, "version", version)
        if updated != text:
            _write(root, surface.path, updated)
            changed.add(surface.path)

    for relative in sorted({stamp.path for stamp in stamps if stamp.tracked}):
        text = _read(root, relative)
        updated = _replace_group(text, _GUIDE_STAMP_RE, "version", version)
        if updated != text:
            _write(root, relative, updated)
            changed.add(relative)

    return sorted(changed)


def sync_derived_counts(root: Path) -> list[str]:
    """Align every quoted count with its recomputed source.

    Args:
        root: Repository root.

    Returns:
        Repository-relative paths actually modified, sorted. Empty when every
        quoted count already matches its source.

    Raises:
        SurfaceError: If a count surface or source cannot be read as declared.
    """
    counts = derived_counts(root)
    count_occurrences(root)  # validate every surface before writing anything

    changed: set[str] = set()
    for surface in COUNT_SURFACES:
        text = _read(root, surface.path)
        updated = _replace_group(
            text, surface.pattern, "count", str(counts[surface.source])
        )
        if updated != text:
            _write(root, surface.path, updated)
            changed.add(surface.path)
    return sorted(changed)
