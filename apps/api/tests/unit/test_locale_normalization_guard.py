"""AST guard: no ad-hoc locale normalization outside the single chokepoint.

Backend canonical Chinese is ``zh-CN`` (``User.language``, ``SUPPORTED_LANGUAGES``,
every backend i18n table); the frontend spells it ``zh`` (URLs, locale files).
``src/core/i18n.py::normalize_language`` is the ONE place allowed to reconcile
the two — CLAUDE.md, *i18n & prompts*: "never do ad-hoc normalization
(``language[:2]``…): route every raw locale through the single chokepoint".

The failure this guards against is silent by construction. Both shortcuts —

    lang = locale.split("-")[0].lower()          # "zh"  -> "zh"
    lang = language[:2] if len(language) > 2 ...  # "zh"  -> "zh"

leave the raw frontend spelling in place, the i18n table lookup misses, and the
code falls back to its default language. A Chinese user then reads FRENCH day
names and ENGLISH placeholders while every test that only exercises ``zh-CN``
stays green.

Enforced as an AST scan rather than a grep so a renamed variable or a different
formatting cannot slip past.
"""

from __future__ import annotations

import ast
import re

import pytest

from tests._repo_paths import find_apps_api_root

pytestmark = pytest.mark.unit

SRC = find_apps_api_root() / "src"

# The chokepoint itself is where the reconciliation legitimately happens.
ALLOWLIST: frozenset[str] = frozenset({"src/core/i18n.py"})

# Boundaries that legitimately speak a DIFFERENT vocabulary than the backend
# canonical one. Each entry states why, and ``test_every_exemption_is_still_used``
# deletes it the moment the code stops needing it (shrink-only).
EXEMPTIONS: dict[str, str] = {
    "src/core/i18n_telephony.py": (
        "ElevenLabs speaks ISO-639-1: its tables are keyed on 'zh', not on the "
        "backend canonical 'zh-CN'. _iso() converts APP language -> ISO at that "
        "boundary, which is the opposite direction from normalize_language."
    ),
    "src/domains/agents/tools/web_fetch_tools.py": (
        "Reads the lang attribute of a FETCHED web page — document metadata, not "
        "a user locale; no backend i18n table is keyed with it."
    ),
}

# Variable names that designate a language / locale code.
_LOCALE_NAME_RE = re.compile(r"(?i)\b(lang|language|locale)s?\b")


def _is_locale_expression(node: ast.expr) -> bool:
    """True when the expression reads a variable that holds a locale code."""
    if isinstance(node, ast.Name):
        return bool(_LOCALE_NAME_RE.search(node.id))
    if isinstance(node, ast.Attribute):
        return bool(_LOCALE_NAME_RE.search(node.attr))
    return False


def _violations(tree: ast.AST) -> list[tuple[int, str]]:
    """Collect (line, pattern) for every ad-hoc normalization in a module."""
    found: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        # locale.split("-") / language.split("_")
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "split"
            and _is_locale_expression(node.func.value)
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value in ("-", "_")
        ):
            found.append((node.lineno, f'{ast.unparse(node.func.value)}.split("-")'))

        # language[:2]
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.slice, ast.Slice)
            and _is_locale_expression(node.value)
            and node.slice.lower is None
            and isinstance(node.slice.upper, ast.Constant)
            and node.slice.upper.value == 2
        ):
            found.append((node.lineno, f"{ast.unparse(node.value)}[:2]"))

    return found


def _scan(*, include_exempt: bool = False) -> dict[str, list[tuple[int, str]]]:
    offenders: dict[str, list[tuple[int, str]]] = {}
    for path in sorted(SRC.rglob("*.py")):
        relative = path.relative_to(SRC.parent).as_posix()
        if relative in ALLOWLIST:
            continue
        if not include_exempt and relative in EXEMPTIONS:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        if violations := _violations(tree):
            offenders[relative] = violations
    return offenders


class TestLocaleNormalizationGuard:
    """``normalize_language`` is the only door; the guard keeps it that way."""

    def test_no_ad_hoc_locale_normalization_in_src(self) -> None:
        offenders = _scan()

        assert not offenders, (
            "Ad-hoc locale normalization found — route the raw locale through "
            "src.core.i18n.normalize_language instead:\n"
            + "\n".join(
                f"  {path}:{line} — {pattern}"
                for path, violations in offenders.items()
                for line, pattern in violations
            )
        )

    def test_every_exemption_is_still_used(self) -> None:
        """Shrink-only: an exemption whose code no longer needs it must go."""
        still_violating = set(_scan(include_exempt=True))

        stale = sorted(set(EXEMPTIONS) - still_violating)
        assert not stale, (
            f"These files no longer normalize locales ad hoc: remove them from "
            f"EXEMPTIONS — {stale}"
        )

    def test_guard_detects_both_historical_shortcuts(self) -> None:
        """Oracle for the guard itself: it must flag the two shipped shapes."""
        module = ast.parse(
            'lang = locale.split("-")[0].lower()\n'
            'short = language[:2] if len(language) > 2 and language != "zh-CN" else language\n'
        )

        patterns = {pattern for _line, pattern in _violations(module)}

        assert 'locale.split("-")' in patterns
        assert "language[:2]" in patterns

    def test_guard_does_not_flag_unrelated_string_handling(self) -> None:
        module = ast.parse('name.split("-")\nvalue[:2]\nlocale.lower()\n')

        assert _violations(module) == []


class TestNormalizeLanguageContract:
    """The chokepoint's own contract, since every caller now depends on it."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("zh", "zh-CN"),
            ("zh-CN", "zh-CN"),
            ("zh_CN", "zh-CN"),
            ("ZH", "zh-CN"),
            ("zh-TW", "zh-CN"),
            ("fr-FR", "fr"),
            ("en_US", "en"),
            ("de", "de"),
            ("es-ES", "es"),
            ("it", "it"),
        ],
    )
    def test_every_spelling_resolves_to_the_backend_canonical_code(
        self, raw: str, expected: str
    ) -> None:
        from src.core.i18n import normalize_language

        assert normalize_language(raw) == expected

    def test_unsupported_locale_falls_back_to_the_configured_default(self) -> None:
        from src.core.config import settings
        from src.core.i18n import normalize_language

        assert normalize_language("pt-BR") == settings.default_language

    def test_empty_input_falls_back_to_the_configured_default(self) -> None:
        from src.core.config import settings
        from src.core.i18n import normalize_language

        assert normalize_language("") == settings.default_language
