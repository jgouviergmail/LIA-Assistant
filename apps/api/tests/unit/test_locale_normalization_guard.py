"""AST guard: no ad-hoc locale normalization outside the single chokepoint.

Backend canonical Chinese is ``zh-CN`` (``User.language``, ``SUPPORTED_LANGUAGES``,
every backend i18n table); the frontend spells it ``zh`` (URLs, locale files).
``src/core/i18n_types.py::canonical_language`` — read through
``core.i18n.normalize_language``, or directly where an unsupported code must be
told apart from a supported one (it answers None) — is the ONE place allowed to
reconcile the two
— CLAUDE.md, *i18n & prompts*: "never do ad-hoc normalization
(``language[:2]``…): route every raw locale through the single chokepoint".

The failure this guards against is silent by construction. Both shortcuts —

    lang = locale.split("-")[0].lower()          # "zh"  -> "zh"
    lang = language[:2] if len(language) > 2 ...  # "zh"  -> "zh"

leave the raw frontend spelling in place, the i18n table lookup misses, and the
code falls back to its default language. A Chinese user then reads FRENCH day
names and ENGLISH placeholders while every test that only exercises ``zh-CN``
stays green.

Enforced as an AST scan rather than a grep, so a different formatting cannot
slip past. A value is recognised as a locale by its NAME — any language name
(``tests/_language_names.py``: snake, camel or kebab case, ``_code``/``_hint``,
plural), a ``.get("<language name>", …)`` or a subscript by such a key
(``prefs.get("language", "")``, ``headers.get("accept-language")``) — read
THROUGH a text-method chain, ``str()`` and every operand of an ``or``
(``(language or "").split("-")``), cut by ``[:2]``/``[0:2]`` or split at a
separator given positionally or as ``sep=``, the ``rsplit``/``partition`` family
included — and a local holding such a value, bound by ``=``, an annotation or
``:=``, is read as one (``lang_lower = language.lower()`` then
``lang_lower.split("-")``). A comparison of a locale with the Chinese prefix
(``startswith("zh")``, ``== "zh"``, ``!= "zh"``) is the same reconciliation
written by hand. A locale held under an unrelated name, never assigned from
one (``code.split("-")``, a loop variable), is not read: nothing in the code
says it is one.
"""

from __future__ import annotations

import ast
from functools import cache

import pytest

from tests._ast_bindings import binding
from tests._language_names import is_language_name
from tests._repo_paths import find_apps_api_root

pytestmark = pytest.mark.unit

SRC = find_apps_api_root() / "src"

# The chokepoint itself is where the reconciliation legitimately happens;
# ``test_the_allowlist_is_still_used`` keeps the entry honest.
ALLOWLIST: frozenset[str] = frozenset({"src/core/i18n_types.py"})

# Boundaries that legitimately speak a DIFFERENT vocabulary than the backend
# canonical one, keyed by (file, the exact shape) with the number of sites it
# covers — a NEW cut in the same file is not exempt. Each entry states why, and
# ``test_every_exemption_is_still_used`` deletes it the moment the code stops
# needing it (shrink-only).
EXEMPTIONS: dict[tuple[str, str], tuple[int, str]] = {
    ("src/infrastructure/browser/pool.py", 'browser_locale.split("-")'): (
        1,
        "Builds the headless browser's Accept-Language header from the canonical "
        "display locale (get_locale_for_language) — a header for web servers, not "
        "the lookup key of any backend i18n table.",
    ),
    ("src/domains/agents/tools/web_fetch_tools.py", 'lang.split("-")'): (
        1,
        "Reads the lang attribute of a FETCHED web page — document metadata, not "
        "a user locale; no backend i18n table is keyed with it.",
    ),
}

#: Methods whose result is their receiver's text, reshaped: a cut applied after
#: them still cuts the locale (``language.lower().split("-")``).
_TEXT_METHODS = frozenset(
    {
        "lower",
        "upper",
        "casefold",
        "strip",
        "lstrip",
        "rstrip",
        "replace",
        "title",
        "capitalize",
        "swapcase",
    }
)

#: Methods that cut a code at its separator.
_SPLITTERS = frozenset({"split", "rsplit", "partition", "rpartition"})


def _key_names_a_language(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and is_language_name(node.value)
    )


def _method_receiver(node: ast.expr, methods: frozenset[str]) -> ast.expr | None:
    """``x`` of ``x.method(...)`` when ``method`` is one of ``methods``, else None."""
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in methods
    ):
        return node.func.value
    return None


def _single_argument_of(node: ast.expr, function: str) -> ast.expr | None:
    """``x`` of ``function(x)``, else None."""
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == function
        and len(node.args) == 1
    ):
        return node.args[0]
    return None


def _unwrap_text(node: ast.expr) -> ast.expr:
    """What a text-method chain, ``str()`` or the first piece of a split reads:
    ``language.lower()``, ``str(language)``, ``header.split(",")[0]``."""
    while True:
        inner = (
            _method_receiver(node, _TEXT_METHODS)
            or _single_argument_of(node, "str")
            or (
                _method_receiver(node.value, _SPLITTERS)
                if isinstance(node, ast.Subscript)
                else None
            )
        )
        if inner is None:
            return node
        node = inner


def _looked_up_key(node: ast.expr) -> ast.expr | None:
    """The key of ``getattr(x, key, …)`` or ``x.get(key, …)``, else None."""
    if not isinstance(node, ast.Call):
        return None
    if isinstance(node.func, ast.Name) and node.func.id == "getattr" and len(node.args) >= 2:
        return node.args[1]
    if isinstance(node.func, ast.Attribute) and node.func.attr == "get" and node.args:
        return node.args[0]
    return None


def _names_a_locale(node: ast.expr, aliases: frozenset[str]) -> bool:
    """The read under the text methods: a locale by its name, by the key it is
    looked up with, or a local ``aliases`` says was assigned one."""
    if isinstance(node, ast.BoolOp):  # (language or "")
        return any(_is_locale_expression(operand, aliases) for operand in node.values)
    if isinstance(node, ast.Name):
        return is_language_name(node.id) or node.id in aliases
    if isinstance(node, ast.Attribute):
        return is_language_name(node.attr)
    if isinstance(node, ast.Subscript):  # prefs["language"]
        return _key_names_a_language(node.slice)
    key = _looked_up_key(node)  # getattr(user, "language", "") / prefs.get("language")
    return key is not None and _key_names_a_language(key)


def _is_locale_expression(node: ast.expr, aliases: frozenset[str] = frozenset()) -> bool:
    """True when the expression reads a variable that holds a locale code —
    by its name, or as a local ``aliases`` says was assigned one."""
    return _names_a_locale(_unwrap_text(node), aliases)


def _separator(call: ast.Call) -> str | None:
    """The ``-``/``_`` a splitter cuts at, given positionally or as ``sep=``."""
    candidates = [*call.args[:1], *(kw.value for kw in call.keywords if kw.arg == "sep")]
    for candidate in candidates:
        if isinstance(candidate, ast.Constant) and candidate.value in ("-", "_"):
            return str(candidate.value)
    return None


def _is_two_letter_cut(index: ast.expr) -> bool:
    """``[:2]`` or ``[0:2]``."""
    return (
        isinstance(index, ast.Slice)
        and (
            index.lower is None
            or (isinstance(index.lower, ast.Constant) and index.lower.value == 0)
        )
        and isinstance(index.upper, ast.Constant)
        and index.upper.value == 2
    )


def _locale_aliases(tree: ast.AST) -> frozenset[str]:
    """The local names a module assigns a locale to, followed to a fixed point."""
    bindings = [found for node in ast.walk(tree) if (found := binding(node)) is not None]
    aliases: frozenset[str] = frozenset()
    while True:
        grown = aliases | {
            name for name, value in bindings if _is_locale_expression(value, aliases)
        }
        if grown == aliases:
            return aliases
        aliases = grown


def _shown(receiver: ast.expr) -> str:
    """A receiver as the pattern prints it: an ``or`` keeps its parentheses."""
    text = ast.unparse(receiver)
    return f"({text})" if isinstance(receiver, ast.BoolOp) else text


def _is_chinese_prefix(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.lower() == "zh"
    )


def _chinese_prefix_tests(node: ast.AST, aliases: frozenset[str]) -> list[tuple[int, str]]:
    """``locale.startswith("zh")`` and ``locale == "zh"``: Chinese reconciled by hand."""
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "startswith"
        and node.args
        and _is_chinese_prefix(node.args[0])
        and _is_locale_expression(node.func.value, aliases)
    ):
        return [(node.lineno, f'{_shown(node.func.value)}.startswith("zh")')]
    if isinstance(node, ast.Compare) and len(node.comparators) == 1:
        left, right = node.left, node.comparators[0]
        for locale, code in ((left, right), (right, left)):
            if _is_chinese_prefix(code) and _is_locale_expression(locale, aliases):
                return [(node.lineno, ast.unparse(node))]
    return []


def _split_site(node: ast.AST, aliases: frozenset[str]) -> tuple[int, str] | None:
    """``locale.split("-")`` / ``language.lower().rsplit("_")`` / ``lang.partition("-")``."""
    if not isinstance(node, ast.Call):
        return None
    receiver = _method_receiver(node, _SPLITTERS)
    if receiver is None or not _is_locale_expression(receiver, aliases):
        return None
    separator = _separator(node)
    if separator is None:
        return None
    assert isinstance(node.func, ast.Attribute)
    return node.lineno, f'{_shown(receiver)}.{node.func.attr}("{separator}")'


def _re_split_site(node: ast.AST, aliases: frozenset[str]) -> tuple[int, str] | None:
    """``re.split(r"[-_]", language)[0]``: the same cut through the re module."""
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "re"
        and node.func.attr == "split"
        and len(node.args) >= 2
        and _is_locale_expression(node.args[1], aliases)
    ):
        return node.lineno, f"re.split(…, {ast.unparse(node.args[1])})"
    return None


def _cut_site(node: ast.AST, aliases: frozenset[str]) -> tuple[int, str] | None:
    """``language[:2]`` / ``language_code.strip()[0:2]``."""
    if (
        isinstance(node, ast.Subscript)
        and _is_two_letter_cut(node.slice)
        and _is_locale_expression(node.value, aliases)
    ):
        return node.lineno, f"{_shown(node.value)}[:2]"
    return None


_SHAPES = (_split_site, _re_split_site, _cut_site)


def _violations(tree: ast.AST) -> list[tuple[int, str]]:
    """Collect (line, pattern) for every ad-hoc normalization in a module."""
    found: list[tuple[int, str]] = []
    aliases = _locale_aliases(tree)
    for node in ast.walk(tree):
        found.extend(_chinese_prefix_tests(node, aliases))
        found.extend(site for shape in _SHAPES if (site := shape(node, aliases)) is not None)
    return found


@cache
def _all_violations() -> dict[str, tuple[tuple[int, str], ...]]:
    """Every ad-hoc normalization of ``src``, per module, read once."""
    found: dict[str, tuple[tuple[int, str], ...]] = {}
    for path in sorted(SRC.rglob("*.py")):
        relative = path.relative_to(SRC.parent).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        if violations := _violations(tree):
            found[relative] = tuple(violations)
    return found


def _unexempted(relative: str, violations: tuple[tuple[int, str], ...]) -> list[tuple[int, str]]:
    """The violations of a module that no exemption covers, counts included."""
    left: list[tuple[int, str]] = []
    for pattern in dict.fromkeys(pattern for _line, pattern in violations):
        sites = [(line, found) for line, found in violations if found == pattern]
        covered = EXEMPTIONS.get((relative, pattern), (0, ""))[0]
        left.extend(sites[covered:])
    return left


def _scan(*, include_allowlisted: bool = False) -> dict[str, list[tuple[int, str]]]:
    offenders: dict[str, list[tuple[int, str]]] = {}
    for relative, violations in _all_violations().items():
        if relative in ALLOWLIST and not include_allowlisted:
            continue
        left = _unexempted(relative, violations)
        if left:
            offenders[relative] = left
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
        """Shrink-only: an exemption covers exactly the sites it names, no fewer."""
        live = {
            (relative, pattern): sum(1 for _line, found in violations if found == pattern)
            for relative, violations in _all_violations().items()
            for _line, pattern in violations
        }
        stale = sorted(
            f"{key}: covers {count}, found {live.get(key, 0)}"
            for key, (count, _reason) in EXEMPTIONS.items()
            if live.get(key, 0) < count
        )
        assert not stale, f"Exemptions covering sites that no longer exist — shrink them: {stale}"

    def test_the_allowlist_is_still_used(self) -> None:
        """The chokepoint is allowlisted because it DOES reconcile — or the entry goes."""
        reconciling = set(_scan(include_allowlisted=True))

        assert (
            ALLOWLIST <= reconciling
        ), f"These allowlisted files reconcile nothing any more: {sorted(ALLOWLIST - reconciling)}"

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
        module = ast.parse(
            'name.split("-")\nvalue[:2]\nlocale.lower()\nlanguage_model.split("-")\n'
        )

        assert _violations(module) == []

    @pytest.mark.parametrize(
        "source",
        ['user_language.split("-")', "user_lang[:2]", 'self.user_language.split("_")'],
    )
    def test_guard_reads_compound_names(self, source: str) -> None:
        """A word boundary never matched ``user_language``: compounds escaped."""
        assert _violations(ast.parse(source)), source

    @pytest.mark.parametrize(
        "source",
        [
            'language.lower().split("-")[0]',
            'user.language.strip().replace("_", "-").split("-")',
            'str(locale).split("_")',
            "language_code[:2]",
            "lang_code.lower()[0:2]",
            'locale.rsplit("-", 1)',
            'language.partition("-")[0]',
            'user_language.rpartition("_")',
            # Shapes the guard claimed and missed (review of 2026-09-26, round 5).
            'languageCode.split("-")',
            'language_hint.split("-")',
            '(language or "").split("-")[0]',
            'str(language or "")[:2]',
            'prefs.get("language", "").split("-")[0]',
            'request.headers.get("accept-language", "").split(",")[0].split("-")[0]',
            'user["language"][:2]',
            'language.split(sep="-")',
            'language.capitalize().split("-")',
            # Round 6: a language TAG, the re module, a getattr read.
            'language_tag.split("-")[0]',
            're.split(r"[-_]", language)[0]',
            'getattr(user, "language", "")[:2]',
            # Round 7: a local alias of a locale, and the Chinese prefix by hand —
            # the shape this lot deleted from i18n_hitl and i18n_v3.
            'lang_lower = language.lower()\nlang_lower.split("-")[0]',
            'lang_lower = language.lower()\nlang_lower.startswith("zh")',
            'language.startswith("zh")',
            'user_language == "zh"',
            '"ZH" == locale',
            # Round 8: an alias bound by an annotation or a walrus.
            'lang_lower: str = language.lower()\nlang_lower.split("-")[0]',
            'if (lang_lower := language.lower()):\n    lang_lower.split("-")[0]',
        ],
    )
    def test_guard_reads_through_chains_codes_and_every_cut(self, source: str) -> None:
        """The shapes the first version let through, each seen."""
        assert _violations(ast.parse(source)), source

    def test_an_or_receiver_keeps_its_parentheses(self) -> None:
        (pattern,) = [p for _line, p in _violations(ast.parse('(language or "en").split("-")'))]
        assert pattern == "(language or 'en').split(\"-\")"

    def test_a_comparison_is_shown_as_it_is_written(self) -> None:
        """It used to be printed ``== "zh"`` whatever its operator."""
        (pattern,) = [p for _line, p in _violations(ast.parse('user_language != "zh"'))]
        assert pattern == "user_language != 'zh'"

    def test_a_chain_on_an_unrelated_name_stays_unflagged(self) -> None:
        module = ast.parse(
            'text.lower().split("-")\nlanguage_model.strip().split("-")\nname[0:2]\n'
        )

        assert _violations(module) == []

    def test_an_exemption_covers_its_sites_and_no_new_one(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A second cut in an exempt file is not exempt — on a synthetic entry, so
        the oracle survives the shrink-only list reaching empty."""
        relative, pattern = "src/synthetic.py", 'lang.split("-")'
        monkeypatch.setitem(EXEMPTIONS, (relative, pattern), (1, "synthetic"))
        sites = ((1, pattern), (2, pattern))

        assert _unexempted(relative, sites) == [(2, pattern)]


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

    @pytest.mark.parametrize("raw", ["pt-BR", ""])
    def test_what_no_language_matches_reads_the_configured_default(self, raw: str) -> None:
        """Pinned off French, so a French literal fallback cannot pass."""
        from unittest.mock import patch

        from src.core.config import settings
        from src.core.i18n import normalize_language

        with patch.object(settings, "default_language", "it"):
            assert normalize_language(raw) == "it"

    def test_a_known_person_s_unsupported_code_never_reads_the_requester_s(self) -> None:
        """``normalize_language`` reads a GIVEN code: what it cannot read is the
        instance default — never the language the request declared (a person the
        requester is not), which is ``resolve_language``'s business alone."""
        from unittest.mock import patch

        from src.core.config import settings
        from src.core.i18n import language_scope, normalize_language

        with patch.object(settings, "default_language", "it"), language_scope("de"):
            assert normalize_language("pt-BR") == "it"
