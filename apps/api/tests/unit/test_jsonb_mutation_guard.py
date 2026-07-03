"""Systemic guard: no in-place mutation of JSONB ORM columns anywhere in src/.

SQLAlchemy does not detect in-place mutations of JSONB columns (``obj.meta["k"] = v``,
``obj.meta.update(...)``, ``obj.emotions.extend(...)``): the UPDATE is silently
skipped and the write is lost. ``flag_modified`` / ``MutableDict`` are intentionally
absent from this codebase — the convention is to always build a NEW container and
reassign it::

    obj.meta = {**(obj.meta or {}), **updates}
    obj.items = [*(obj.items or []), *new_items]

This test enforces the convention statically:

1. It collects every JSONB-typed attribute name from all ``src/**/models.py``
   files by parsing their ASTs (any ``mapped_column(...)`` whose arguments
   reference ``JSONB``).
2. It scans every production file for AST nodes that mutate an attribute with
   one of those names in place (subscript assignment, augmented assignment,
   ``del``, or a call to a known mutator method such as ``update``/``append``).

If a non-ORM object legitimately shares an attribute name with a JSONB column
and must be mutated in place, add the offending ``(file, lineno)`` to
``ALLOWED_VIOLATIONS`` with a justification comment — do not weaken the scan.

Context: 2026-07 full-codebase audit, wave 2 (B5).
"""

import ast
from pathlib import Path

import pytest

SRC_DIR = Path(__file__).parents[2] / "src"

# Methods that mutate a dict or list in place.
MUTATOR_METHODS = {
    "update",
    "setdefault",
    "append",
    "extend",
    "insert",
    "remove",
    "pop",
    "popitem",
    "clear",
    "sort",
    "reverse",
}

# Known-legitimate in-place mutations of NON-ORM objects that happen to share
# an attribute name with a JSONB column. Format: ("relative/posix/path.py", lineno).
ALLOWED_VIOLATIONS: set[tuple[str, int]] = set()


def _subtree_references_jsonb(node: ast.AST) -> bool:
    """Return True if any node in the subtree references the JSONB type."""
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and child.id == "JSONB":
            return True
        if isinstance(child, ast.Attribute) and child.attr == "JSONB":
            return True
    return False


def _collect_jsonb_column_names() -> dict[str, list[str]]:
    """Collect JSONB attribute names per model file from src/**/models.py.

    Returns:
        Mapping of model file path (posix, relative to src/) to the list of
        JSONB-typed attribute names it declares.
    """
    columns: dict[str, list[str]] = {}
    for model_file in sorted(SRC_DIR.rglob("models.py")):
        tree = ast.parse(model_file.read_text(encoding="utf-8"), filename=str(model_file))
        names: list[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.AnnAssign) or not isinstance(node.target, ast.Name):
                continue
            value = node.value
            if (
                isinstance(value, ast.Call)
                and isinstance(value.func, ast.Name)
                and value.func.id == "mapped_column"
                and _subtree_references_jsonb(value)
            ):
                names.append(node.target.id)
        if names:
            columns[model_file.relative_to(SRC_DIR).as_posix()] = names
    return columns


def _iter_inplace_mutations(tree: ast.AST, jsonb_names: set[str]):
    """Yield (lineno, description) for every in-place mutation of a JSONB attribute."""
    for node in ast.walk(tree):
        # obj.attr[key] = value  /  obj.attr[key] += value
        if isinstance(node, (ast.Assign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if (
                    isinstance(target, ast.Subscript)
                    and isinstance(target.value, ast.Attribute)
                    and target.value.attr in jsonb_names
                ):
                    yield node.lineno, f"subscript assignment on .{target.value.attr}[...]"
                # obj.attr += [...]  (augmented assignment on the attribute itself)
                if (
                    isinstance(node, ast.AugAssign)
                    and isinstance(target, ast.Attribute)
                    and target.attr in jsonb_names
                ):
                    yield node.lineno, f"augmented assignment on .{target.attr}"
        # del obj.attr[key]
        elif isinstance(node, ast.Delete):
            for target in node.targets:
                if (
                    isinstance(target, ast.Subscript)
                    and isinstance(target.value, ast.Attribute)
                    and target.value.attr in jsonb_names
                ):
                    yield node.lineno, f"del on .{target.value.attr}[...]"
        # obj.attr.update(...) / .append(...) / .extend(...) / ...
        elif isinstance(node, ast.Call):
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr in MUTATOR_METHODS
                and isinstance(func.value, ast.Attribute)
                and func.value.attr in jsonb_names
            ):
                yield node.lineno, f".{func.value.attr}.{func.attr}(...) mutator call"


class TestJSONBColumnDiscovery:
    """Sanity checks on the JSONB column discovery itself."""

    def test_discovery_finds_known_jsonb_columns(self):
        """The scan must find well-known JSONB columns (guards against scan rot)."""
        columns = _collect_jsonb_column_names()
        all_names = {name for names in columns.values() for name in names}
        expected_sentinels = {
            "connector_metadata",  # connectors/models.py
            "message_metadata",  # conversations/models.py
            "active_emotions",  # psyche/models.py
            "last_appraisal",  # psyche/models.py
        }
        missing = expected_sentinels - all_names
        assert not missing, (
            f"JSONB column discovery no longer finds {sorted(missing)} — "
            "the AST scan in this guard is broken, fix it before trusting the guard."
        )


class TestNoInPlaceJSONBMutation:
    """CI guard: any in-place mutation of a JSONB column fails the build."""

    def test_no_inplace_mutation_of_jsonb_columns(self):
        """Scan all production code for in-place mutations of JSONB attributes."""
        columns = _collect_jsonb_column_names()
        jsonb_names = {name for names in columns.values() for name in names}
        assert jsonb_names, "No JSONB columns discovered — scan is broken."

        violations: list[str] = []
        for py_file in sorted(SRC_DIR.rglob("*.py")):
            rel_path = py_file.relative_to(SRC_DIR).as_posix()
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            for lineno, description in _iter_inplace_mutations(tree, jsonb_names):
                if (rel_path, lineno) in ALLOWED_VIOLATIONS:
                    continue
                violations.append(f"src/{rel_path}:{lineno}: {description}")

        if violations:
            pytest.fail(
                "In-place mutation of JSONB ORM columns detected — SQLAlchemy silently "
                "skips the UPDATE and the write is lost.\n"
                "Build a NEW dict/list and reassign instead: "
                "obj.meta = {**(obj.meta or {}), **updates}\n\n"
                + "\n".join(f"  - {v}" for v in violations)
            )
