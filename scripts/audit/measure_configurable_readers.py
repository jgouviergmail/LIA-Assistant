#!/usr/bin/env python3
"""Find every read of the run context from the untyped ``configurable`` bag.

ADR-231 moved the run-scoped context (identity, preferences, live dependencies)
out of ``config["configurable"]`` into a frozen ``LiaRuntimeContext``. Both planes
coexist while the readers migrate: the bag stays populated and authoritative, so a
remaining reader is untyped rather than broken. This scan is what makes that
migration a ratchet instead of a hope — the CI guard
``apps/api/tests/unit/domains/agents/context/test_configurable_reader_ratchet.py``
fails on any reader that is not allowlisted, and on any allowlist entry whose file
has since been migrated.

Only run-scoped keys are scanned. LangGraph plumbing (``thread_id``,
``checkpoint_ns``, ``run_id``) and node-local values a caller writes for its own
callee (``node_name``, ``turn_id``, ``oauth_scopes``, ``resolved_person_names``,
``__parent_thread_id``) legitimately live in ``configurable`` and are not context.

Usage (from apps/api/):
    python ../../scripts/audit/measure_configurable_readers.py            # report
    python ../../scripts/audit/measure_configurable_readers.py --update   # shrink

``--update`` can only REMOVE allowlist entries whose file no longer reads the bag.
It never adds one: a new reader must be written against the typed context, not
allowlisted. Adding an entry by hand is an explicit, reviewable decision that
requires a written reason in the JSON.

Standard library only — no dependencies.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

#: Run-scoped keys the typed context owns. Reading one of these from the bag is
#: what the ratchet counts. Mirrors the fields of ``LiaRuntimeContext`` plus the
#: legacy spellings the chokepoint still writes (``langgraph_user_id``, the four
#: ``__``-prefixed private keys) — those disappear with the last wave.
CONTEXT_KEYS: frozenset[str] = frozenset(
    {
        "user_id",
        "langgraph_user_id",
        "user_language",
        "user_timezone",
        "user_display_mode",
        "user_execution_mode",
        "user_memory_enabled",
        "user_journals_enabled",
        "user_psyche_enabled",
        "user_display_name",
        "is_automated_source",
        "store",
        "__deps",
        "__browser_context",
        "__user_message",
        "__side_channel_queue",
    }
)

DEFAULT_SRC = Path("src")
DEFAULT_ALLOWLIST = Path("tests/unit/domains/agents/context/configurable_readers_allowlist.json")


def _reads_from_configurable(node: ast.expr) -> bool:
    """True when this expression is (or came from) a ``configurable`` mapping.

    Matched shapes, all of which occur in the codebase::

        config["configurable"].get("user_id")
        (config.get("configurable") or {}).get("user_id")
        configurable.get("user_id")          # local alias
        configurable["user_id"]

    The test is textual over the expression's dump rather than a structural match
    on each shape: the alias forms make a structural matcher long and brittle,
    while a false positive here is only ever a file that already deals with the
    bag — which is exactly what the ratchet wants to see.

    Args:
        node: The expression the read is performed on.

    Returns:
        Whether the expression denotes a ``configurable`` mapping.
    """
    return "configurable" in ast.dump(node).lower()


def _constant_aliases(src_dir: Path) -> dict[str, str]:
    """Module-level constants whose value IS a run-context key.

    ``configurable.get(FIELD_USER_ID)`` reads the bag exactly as
    ``configurable.get("user_id")`` does, but the key is a Name, not a literal —
    and a literal-only scanner reports zero readers while a real one stands
    (measured: ``infrastructure/llm/invoke_helpers.py`` read ``FIELD_USER_ID``
    through the whole migration without ever appearing in the count). Aliases are
    DISCOVERED, never listed, so declaring a new one cannot silently open the hole
    again.

    Args:
        src_dir: Root of the sources to scan.

    Returns:
        ``{constant name: key}`` for every ``UPPER_NAME = "<context key>"``.
    """
    aliases: dict[str, str] = {}
    for path in sorted(src_dir.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in tree.body:
            targets: list[ast.expr] = []
            if isinstance(node, ast.Assign):
                targets = list(node.targets)
            elif isinstance(node, ast.AnnAssign):
                targets = [node.target]
            value = getattr(node, "value", None)
            if not isinstance(value, ast.Constant) or value.value not in CONTEXT_KEYS:
                continue
            for target in targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    aliases[target.id] = value.value
    return aliases


def _key_of(node: ast.expr, aliases: dict[str, str]) -> str | None:
    """The context key an index expression denotes, literal or aliased."""
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else None
    if isinstance(node, ast.Name):
        return aliases.get(node.id)
    if isinstance(node, ast.Attribute):
        return aliases.get(node.attr)
    return None


def scan(src_dir: Path = DEFAULT_SRC) -> dict[str, list[str]]:
    """Map each file reading run-context keys from the bag to the keys it reads.

    Paths are keyed relative to ``src_dir``'s parent (``src/domains/...``) whether
    the caller passes a relative or an absolute root, so the allowlist written from
    the CLI and the one read by the CI guard are always the same strings.

    Args:
        src_dir: Root of the sources to scan.

    Returns:
        ``{posix path: sorted keys}``, empty when the migration is complete.
    """
    found: dict[str, set[str]] = {}
    base = src_dir.resolve().parent
    aliases = _constant_aliases(src_dir)

    for path in sorted(src_dir.rglob("*.py")):
        source = path.read_text(encoding="utf-8", errors="replace")
        if "configurable" not in source:
            continue
        try:
            tree = ast.parse(source)
        except SyntaxError:
            # A file that does not parse is the syntax gate's problem, not ours;
            # skipping keeps this scan usable mid-edit.
            continue

        for node in ast.walk(tree):
            key: str | None = None
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get"
                and node.args
                and _reads_from_configurable(node.func.value)
            ):
                key = _key_of(node.args[0], aliases)
            elif isinstance(node, ast.Subscript) and _reads_from_configurable(node.value):
                key = _key_of(node.slice, aliases)

            if isinstance(key, str) and key in CONTEXT_KEYS:
                rel = path.resolve().relative_to(base).as_posix()
                found.setdefault(rel, set()).add(key)

    return {path: sorted(keys) for path, keys in found.items()}


def count_scanned_files(src_dir: Path = DEFAULT_SRC) -> int:
    """Number of Python files the scan walks — anti-rot signal for the guard."""
    return sum(1 for _ in src_dir.rglob("*.py"))


def _update(allowlist_path: Path, found: dict[str, list[str]]) -> int:
    """Drop allowlist entries whose file no longer reads the bag.

    Args:
        allowlist_path: The ratchet JSON.
        found: Current scan result.

    Returns:
        Number of entries removed.
    """
    data = json.loads(allowlist_path.read_text(encoding="utf-8"))
    before = dict(data["files"])
    data["files"] = {path: reason for path, reason in before.items() if path in found}
    removed = len(before) - len(data["files"])

    if removed:
        allowlist_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", type=Path, default=DEFAULT_SRC)
    parser.add_argument("--allowlist", type=Path, default=DEFAULT_ALLOWLIST)
    parser.add_argument(
        "--update",
        action="store_true",
        help="remove allowlist entries whose file no longer reads the bag (never adds)",
    )
    args = parser.parse_args()

    found = scan(args.src)
    total = sum(len(keys) for keys in found.values())
    print(f"{len(found)} file(s) still read the run context from `configurable` ({total} reads)")
    for path, keys in sorted(found.items()):
        print(f"  {len(keys):2d}  {path}  {keys}")

    if args.update:
        removed = _update(args.allowlist, found)
        print(f"\nallowlist: {removed} entry(ies) removed" if removed else "\nallowlist unchanged")

    return 0


if __name__ == "__main__":
    sys.exit(main())
