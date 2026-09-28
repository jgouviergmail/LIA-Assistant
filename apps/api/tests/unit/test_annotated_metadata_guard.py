"""An ``Annotated`` description is never hidden behind a union.

``language: Annotated[str, "…"] | None = None`` reads naturally and LOSES the
description: the union wraps the ``Annotated``, and LangChain reads the metadata
of an ``Annotated`` only at the top of a parameter's annotation — the schema the
model is bound to then carries ``anyOf`` and a default, and nothing that says
what the parameter is. One mechanical pass (ADR-323) silently stripped seven
tool parameters that way. Write ``Annotated[str | None, "…"]``; the same rule
holds for a Pydantic field and a FastAPI parameter, whose metadata also belongs
at the top of the annotation.

An alias does not hide it either: ``Lang = Annotated[str, "…"]`` then
``x: Lang | None``, an alias of that alias, an alias of the union itself
(``MaybeLang = Annotated[str, "…"] | None``), an alias defined in a
module-level block (``if TYPE_CHECKING:``, ``try:``), and any of them imported
from another module — relatively or not, re-exports included — or read through
the module that defines it (``types.Lang | None``) are resolved over the whole
of ``src``.
"""

from __future__ import annotations

import ast
from collections.abc import Mapping
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SRC = Path(__file__).resolve().parents[2] / "src"


#: What a module knows: its spellings of ``Annotated``, its aliases of one, and
#: its aliases of a union that hides one.
_Spelling = tuple[frozenset[str], frozenset[str], frozenset[str]]
_PLAIN: _Spelling = (frozenset({"Annotated"}), frozenset(), frozenset())
#: Per module: (aliases of an Annotated, aliases of a union hiding one).
_Exports = dict[str, tuple[frozenset[str], frozenset[str]]]


def _named(node: ast.expr, name: str) -> bool:
    return (isinstance(node, ast.Name) and node.id == name) or (
        isinstance(node, ast.Attribute) and node.attr == name
    )


def _reference(node: ast.expr) -> str | None:
    """``Lang`` for a name, ``types.Lang`` for an attribute chain — how aliases are held."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        owner = _reference(node.value)
        return f"{owner}.{node.attr}" if owner else None
    return None


def _is_annotated(node: ast.expr, spelling: _Spelling = _PLAIN) -> bool:
    names, aliases, _hiding = spelling
    if _reference(node) in aliases:
        return True
    if not isinstance(node, ast.Subscript):
        return False
    target = node.value
    return (isinstance(target, ast.Name) and target.id in names) or (
        isinstance(target, ast.Attribute) and target.attr == "Annotated"
    )


def _union_members(annotation: ast.expr) -> list[ast.expr] | None:
    """The members of a union annotation, flattened; None when it is not one.

    Reads ``A | B | C``, ``Optional[A]`` and ``Union[A, B]``, nested in one
    another at any depth (``Optional[Annotated[…] | int]``).
    """
    members: list[ast.expr]
    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        members = [annotation.left, annotation.right]
    elif isinstance(annotation, ast.Subscript) and _named(annotation.value, "Optional"):
        members = [annotation.slice]
    elif isinstance(annotation, ast.Subscript) and _named(annotation.value, "Union"):
        inner = annotation.slice
        members = list(inner.elts) if isinstance(inner, ast.Tuple) else [inner]
    else:
        return None
    return [flat for member in members for flat in (_union_members(member) or [member])]


def _hides_annotated(annotation: ast.expr | None, spelling: _Spelling = _PLAIN) -> bool:
    """A union holding an ``Annotated`` — or an alias of one — at any depth."""
    if annotation is None:
        return False
    hiding = spelling[2]
    if _reference(annotation) in hiding:
        return True
    members = _union_members(annotation)
    return members is not None and any(
        _is_annotated(member, spelling) or _reference(member) in hiding for member in members
    )


def _module_level(body: list[ast.stmt]) -> list[ast.stmt]:
    """Every module-level statement, those of ``if``/``try``/``with`` blocks included."""
    found: list[ast.stmt] = []
    for node in body:
        found.append(node)
        if isinstance(node, ast.If | ast.For | ast.While | ast.With | ast.AsyncWith):
            found.extend(_module_level(node.body))
            found.extend(_module_level(getattr(node, "orelse", [])))
        elif isinstance(node, ast.Try | ast.TryStar):
            for block in (node.body, node.orelse, node.finalbody):
                found.extend(_module_level(block))
            for handler in node.handlers:
                found.extend(_module_level(handler.body))
    return found


def _imported_module(node: ast.ImportFrom, module: str, package: bool) -> str | None:
    """The dotted module an ``ImportFrom`` reads, relative levels resolved."""
    if not node.level:
        return node.module
    parts = module.split(".") if package else module.split(".")[:-1]
    up = node.level - 1
    if up > len(parts):
        return None
    base = parts[: len(parts) - up]
    return ".".join([*base, node.module]) if node.module else ".".join(base)


def _alias_definitions(tree: ast.Module) -> list[tuple[str, ast.expr]]:
    """``(name, value)`` of every module-level assignment or ``type`` alias, in order."""
    found: list[tuple[str, ast.expr]] = []
    for node in _module_level(tree.body):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            first = node.targets[0]
            if isinstance(first, ast.Name):
                found.append((first.id, node.value))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.value is not None:
                found.append((node.target.id, node.value))
        elif isinstance(node, ast.TypeAlias) and isinstance(node.name, ast.Name):
            found.append((node.name.id, node.value))
    return found


class _Known:
    """What a module knows as an ``Annotated`` while its imports are read."""

    def __init__(self) -> None:
        self.names = {"Annotated"}
        self.annotated: set[str] = set()
        self.hiding: set[str] = set()

    def read_through(self, local: str, source: tuple[frozenset[str], frozenset[str]]) -> None:
        """``local.Lang`` for every alias the module named ``local`` exports."""
        self.annotated.update(f"{local}.{name}" for name in source[0])
        self.hiding.update(f"{local}.{name}" for name in source[1])

    def spelling(self) -> _Spelling:
        return frozenset(self.names), frozenset(self.annotated), frozenset(self.hiding)


def _read_import(node: ast.Import, module: str, known: _Exports, into: _Known) -> None:
    """``import src.a as types``: every alias ``src.a`` exports, read through ``types``."""
    for alias in node.names:
        if alias.name in known and alias.name != module:
            into.read_through(alias.asname or alias.name, known[alias.name])


def _read_import_from(
    node: ast.ImportFrom, module: str, package: bool, known: _Exports, into: _Known
) -> None:
    """``from … import …``: typing's own spelling, a submodule, or the aliases themselves."""
    imported = _imported_module(node, module, package)
    if imported is None:
        return
    if imported in {"typing", "typing_extensions"}:
        into.names.update(a.asname for a in node.names if a.name == "Annotated" and a.asname)
        return
    for alias in node.names:
        submodule = f"{imported}.{alias.name}"
        if submodule in known and submodule != module:  # from src import a
            into.read_through(alias.asname or alias.name, known[submodule])
    source = known.get(imported)
    if source is not None and imported != module:
        _read_aliases(node, source, into)


def _read_aliases(
    node: ast.ImportFrom, source: tuple[frozenset[str], frozenset[str]], into: _Known
) -> None:
    """``from src.a import Lang as L``: ``L`` is what ``Lang`` is in ``src.a``."""
    for alias in node.names:
        local = alias.asname or alias.name
        if alias.name in source[0]:
            into.annotated.add(local)
        if alias.name in source[1]:
            into.hiding.add(local)


def _spelling(
    tree: ast.Module,
    module: str = "",
    exports: _Exports | None = None,
    package: bool = False,
) -> _Spelling:
    """What ``tree`` knows as an ``Annotated``, in body order, imports resolved.

    Args:
        tree: The module.
        module: Its dotted path (``src.domains.x``), to resolve a relative import
            and to skip a self-reference.
        exports: What every OTHER module exports, when known.
        package: Whether the module is a package's ``__init__`` (a relative
            import then starts from the module itself).

    Returns:
        The module's spellings, aliases of an Annotated and aliases of a hiding union.
    """
    known = exports or {}
    spelled = _Known()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            _read_import(node, module, known, spelled)
        elif isinstance(node, ast.ImportFrom):
            _read_import_from(node, module, package, known, spelled)
    for target, value in _alias_definitions(tree):
        current = spelled.spelling()
        if _is_annotated(value, current):
            spelled.annotated.add(target)
        elif _hides_annotated(value, current):
            spelled.hiding.add(target)
    return spelled.spelling()


def _exports(trees: Mapping[str, ast.Module], packages: frozenset[str] = frozenset()) -> _Exports:
    """Every module's aliases, resolved across modules to a fixed point (re-exports)."""
    exports: _Exports = {module: (frozenset(), frozenset()) for module in trees}
    while True:
        changed = False
        for module, tree in trees.items():
            _names, annotated, hiding = _spelling(tree, module, exports, module in packages)
            if (annotated, hiding) != exports[module]:
                exports[module] = (annotated, hiding)
                changed = True
        if not changed:
            return exports


def _offenders(tree: ast.Module, label: str, spelling: _Spelling | None = None) -> list[str]:
    """Every parameter or field whose ``Annotated`` sits inside a union.

    A string annotation is not parsed: an ``Annotated`` written as text is invisible.
    """
    spelling = spelling if spelling is not None else _spelling(tree)
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            arguments = node.args
            every = [
                *arguments.posonlyargs,
                *arguments.args,
                *arguments.kwonlyargs,
                *(a for a in (arguments.vararg, arguments.kwarg) if a is not None),
            ]
            for arg in every:
                if _hides_annotated(arg.annotation, spelling):
                    found.append(f"{label}:{arg.lineno} {node.name}({arg.arg})")
        elif isinstance(node, ast.AnnAssign) and _hides_annotated(node.annotation, spelling):
            found.append(f"{label}:{node.lineno}")
    return found


def _dotted(path: Path) -> str:
    parts = list(path.relative_to(SRC.parent).with_suffix("").parts)
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _all_offenders(
    trees: Mapping[str, ast.Module], packages: frozenset[str] = frozenset()
) -> list[str]:
    exports = _exports(trees, packages)
    return [
        hit
        for module, tree in trees.items()
        for hit in _offenders(tree, module, _spelling(tree, module, exports, module in packages))
    ]


def _src_offenders() -> list[str]:
    """Every offender of ``src`` — the parsed trees live for this call only (kept
    for a worker's life, the 1 800 modules held about 440 MB)."""
    paths = sorted(SRC.rglob("*.py"))
    trees = {_dotted(path): ast.parse(path.read_text(encoding="utf-8")) for path in paths}
    packages = frozenset(_dotted(path) for path in paths if path.name == "__init__.py")
    return _all_offenders(trees, packages)


def test_no_annotated_metadata_is_wrapped_in_a_union() -> None:
    offenders = _src_offenders()

    assert offenders == [], (
        "An Annotated wrapped in a union loses its metadata — write "
        "Annotated[X | None, ...] instead:\n  " + "\n  ".join(offenders)
    )


@pytest.mark.parametrize(
    ("source", "caught"),
    [
        ('def f(x: Annotated[str, "d"] | None = None): ...', True),
        ('def f(x: None | typing.Annotated[str, "d"] = None): ...', True),
        ('def f(x: Annotated[str, "d"] | int | None = None): ...', True),
        ('def f(x: Optional[Annotated[str, "d"]] = None): ...', True),
        ('def f(x: typing.Union[Annotated[str, "d"], None] = None): ...', True),
        ('def f(*args: Annotated[str, "d"] | None): ...', True),
        ('def f(**kwargs: Annotated[str, "d"] | None): ...', True),
        ("def f(x: Optional[str] = None, y: Union[int, str] = 0): ...", False),
        ("class M:\n    x: Annotated[str, Field()] | None = None", True),
        ('def f(x: Annotated[str | None, "d"] = None): ...', False),
        ("def f(x: str | None = None): ...", False),
        # Shapes the guard claimed and missed (review of 2026-09-26).
        ('def f(x: Optional[Annotated[str, "d"] | int] = None): ...', True),
        ('def f(x: Union[Annotated[str, "d"] | int, None] = None): ...', True),
        ('def f(x: Optional[Union[Annotated[str, "d"], int]] = None): ...', True),
        ('Lang = Annotated[str, "d"]\ndef f(x: Lang | None = None): ...', True),
        ('type Lang = Annotated[str, "d"]\ndef f(x: Lang | None = None): ...', True),
        ('from typing import Annotated as A\ndef f(x: A[str, "d"] | None = None): ...', True),
        ('Lang = Annotated[str | None, "d"]\ndef f(x: Lang = None): ...', False),
        # Aliases the guard missed (review of 2026-09-26, round 4).
        ('MaybeLang = Annotated[str, "d"] | None\ndef f(x: MaybeLang = None): ...', True),
        ('Lang = Annotated[str, "d"]\nLang2 = Lang\ndef f(x: Lang2 | None = None): ...', True),
        ('Lang = Annotated[str, "d"]\nMaybe = Lang | None\ndef f(x: Maybe = None): ...', True),
        ('Maybe = Annotated[str, "d"] | None\nAgain = Maybe\ndef f(x: Again = None): ...', True),
    ],
)
def test_the_guard_reads_the_shape(source: str, caught: bool) -> None:
    assert bool(_offenders(ast.parse(source), "probe")) is caught


@pytest.mark.parametrize(
    ("modules", "caught"),
    [
        (
            {
                "src.a": 'Lang = Annotated[str, "d"]',
                "src.b": "from src.a import Lang as L\ndef f(x: L | None = None): ...",
            },
            True,
        ),
        (
            {
                "src.a": 'Maybe = Annotated[str, "d"] | None',
                "src.b": "from src.a import Maybe\ndef f(x: Maybe = None): ...",
            },
            True,
        ),
        (
            {
                "src.a": 'Lang = Annotated[str, "d"]',
                "src.b": "from src.a import Lang",
                "src.c": "from src.b import Lang\ndef f(x: Lang | None = None): ...",
            },
            True,
        ),
        (
            {
                "src.a": 'Lang = Annotated[str | None, "d"]',
                "src.b": "from src.a import Lang\ndef f(x: Lang = None): ...",
            },
            False,
        ),
    ],
    ids=["imported_alias", "imported_union_alias", "re_exported_alias", "sound_import"],
)
def test_the_guard_follows_an_alias_across_modules(modules: dict[str, str], caught: bool) -> None:
    trees = {module: ast.parse(source) for module, source in modules.items()}
    assert bool(_all_offenders(trees)) is caught


@pytest.mark.parametrize(
    ("modules", "packages"),
    [
        (
            {
                "src.a.types": 'Lang = Annotated[str, "d"]',
                "src.a.b": "from .types import Lang\ndef f(x: Lang | None = None): ...",
            },
            frozenset(),
        ),
        (
            {
                "src.a.types": 'Lang = Annotated[str, "d"]',
                "src.a": "from .types import Lang\ndef f(x: Lang | None = None): ...",
            },
            frozenset({"src.a"}),
        ),
        (
            {
                "src.a": 'Lang = Annotated[str, "d"]',
                "src.b": "from src import a\ndef f(x: a.Lang | None = None): ...",
            },
            frozenset(),
        ),
        (
            {
                "src.a": 'Lang = Annotated[str, "d"]',
                "src.b": "import src.a as types\ndef f(x: types.Lang | None = None): ...",
            },
            frozenset(),
        ),
        (
            {
                "src.a": 'if TYPE_CHECKING:\n    Lang = Annotated[str, "d"]',
                "src.b": "from src.a import Lang\ndef f(x: Lang | None = None): ...",
            },
            frozenset(),
        ),
        (
            {
                "src.a": 'Maybe = Annotated[str, "d"] | None',
                "src.b": "import src.a as types\ndef f(x: types.Maybe = None): ...",
            },
            frozenset(),
        ),
    ],
    ids=[
        "relative_import",
        "relative_import_in_a_package",
        "module_attribute",
        "aliased_module",
        "alias_in_a_block",
        "hiding_alias_read_through_a_module",
    ],
)
def test_the_guard_reads_the_shapes_the_fifth_review_found(
    modules: dict[str, str], packages: frozenset[str]
) -> None:
    """Round 5: a relative import, a module read through, an alias in a block."""
    trees = {module: ast.parse(source) for module, source in modules.items()}
    assert _all_offenders(trees, packages)
