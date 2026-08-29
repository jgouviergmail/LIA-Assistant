"""Systemic guard: the run context is read from the typed context, never from the bag.

ADR-231 replaced an untyped ``config["configurable"]`` bag — 17 keys written at a
single chokepoint, read across the codebase, four of them private and unpublished
— with a frozen ``LiaRuntimeContext``. The foundation shipped in v1.30.12; the
readers migrate behind this ratchet.

The migration is now COMPLETE — the allowlist is empty and the chokepoint writes
LangGraph plumbing only — so any hit is a regression, not remaining debt. The
ratchet stays because nothing else stops a new reader appearing, exactly as the
annotation guard stops it for tool signatures. Measured: between v1.30.12 and
v1.37.0 the parameterized annotations grew 145 → 170 (the guard steering new code)
while the bag readers stayed frozen at 43 files (nothing steering them).

A key spelled through a CONSTANT is a read like any other: ``configurable.get(
FIELD_USER_ID)`` survived a whole migration wave invisible to a literal-only scan,
including one reader in ``infrastructure/`` — see ``test_a_constant_key_is_not_a
_hiding_place``.

Mechanism (allowlist: ``configurable_readers_allowlist.json``):

1. Any read of a migrated key from a ``configurable`` mapping — ``.get("k")`` or
   ``["k"]`` — is a violation unless its file is allowlisted.
2. The allowlist is SHRINK-ONLY: an entry whose file no longer reads the bag FAILS
   the guard, so a migration wave cannot be claimed without the entry being
   removed in the same change.
3. Keys that legitimately stay in ``configurable`` are not scanned: ``thread_id``,
   ``run_id``, ``checkpoint_ns`` and friends are LangGraph plumbing, and
   ``node_name``/``turn_id``/``oauth_scopes``/``resolved_person_names``/
   ``__parent_thread_id`` are node-local values a nested call writes for its own
   callee — neither is run-scoped context.

The scan lives in ``scripts/audit/measure_configurable_readers.py`` (single
implementation, shared with the shrink-only updater), mirroring the file-size
ratchet's split between measurement and enforcement.

Context: ADR-231, task 11.
"""

import ast
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

from tests._repo_paths import repo_root_or_skip

REPO_ROOT = repo_root_or_skip()
SRC_DIR = Path(__file__).parents[5] / "src"
ALLOWLIST_PATH = Path(__file__).parent / "configurable_readers_allowlist.json"
SCANNER_PATH = REPO_ROOT / "scripts" / "audit" / "measure_configurable_readers.py"

# Anti-rot: the scan must keep seeing the codebase. A silent path or layout change
# dropping below this means the guard scans nothing and passes vacuously.
MIN_EXPECTED_FILES = 500


def _load_scanner() -> ModuleType:
    """Load the canonical reader scan shared with the shrink-only updater.

    The guard imports ``scripts/audit/measure_configurable_readers.py`` instead of
    duplicating the AST walk: the violations it enforces are the ones the updater
    removes, by construction. Fails loudly on a partial checkout — pre-commit
    (host) and CI (runner) always have the full repository.

    Returns:
        The loaded scanner module.
    """
    assert SCANNER_PATH.is_file(), (
        f"measure_configurable_readers.py not found at {SCANNER_PATH} — this guard "
        "needs the full repository checkout (scripts/audit/)."
    )
    spec = importlib.util.spec_from_file_location("measure_configurable_readers", SCANNER_PATH)
    assert spec is not None and spec.loader is not None, f"cannot load {SCANNER_PATH}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_scanner = _load_scanner()


def _allowlist() -> dict[str, str]:
    """The allowlisted files, mapped to their written reason."""
    return json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))["files"]


@pytest.mark.unit
def test_scan_still_sees_the_codebase() -> None:
    """A guard that silently scans nothing is worse than no guard."""
    scanned = _scanner.count_scanned_files(SRC_DIR)

    assert scanned >= MIN_EXPECTED_FILES, (
        f"only {scanned} source files scanned (expected >= {MIN_EXPECTED_FILES}) — "
        "the layout changed and this guard is now checking almost nothing."
    )


@pytest.mark.unit
def test_no_unallowlisted_reader_of_the_run_context() -> None:
    """A NEW reader of the bag is the drift this ratchet exists to stop."""
    allowed = _allowlist()
    found = _scanner.scan(SRC_DIR)
    new = {path: sorted(keys) for path, keys in found.items() if path not in allowed}

    assert not new, (
        'New reader(s) of the run context via `config["configurable"]`. Read the '
        "typed context instead — `tool_runtime_context(runtime)` in a tool, "
        "`runtime_context_if_running()` elsewhere inside a run (ADR-231).\n"
        + json.dumps(new, indent=2)
    )


@pytest.mark.unit
def test_allowlist_has_no_stale_entry() -> None:
    """Shrink-only: a migrated file must leave the allowlist in the same change.

    Without this, a wave could be declared landed while its entry lingered, and
    the ratchet would quietly stop measuring anything.
    """
    allowed = _allowlist()
    found = _scanner.scan(SRC_DIR)
    stale = sorted(set(allowed) - set(found))

    assert not stale, (
        "These files no longer read the run context from `configurable` — remove "
        "them from the allowlist (`python ../../scripts/audit/"
        f"measure_configurable_readers.py --update`):\n{json.dumps(stale, indent=2)}"
    )


@pytest.mark.unit
def test_every_allowlist_entry_carries_a_reason() -> None:
    """An allowlist without reasons rots into a list nobody dares to shrink."""
    empty = sorted(path for path, reason in _allowlist().items() if not reason.strip())

    assert not empty, f"allowlist entries with no written reason: {empty}"


@pytest.mark.unit
def test_a_constant_key_is_not_a_hiding_place() -> None:
    """``configurable.get(FIELD_USER_ID)`` is a read, and must be counted as one.

    A literal-only scanner reported "0 readers" while eight files, one of them in
    ``infrastructure/``, read the bag through a constant alias. The scanner now
    DISCOVERS the aliases (any module-level ``UPPER = "<context key>"``), so
    declaring a new one cannot reopen the hole; this test pins the resolution
    itself, on a synthetic file, so it cannot regress silently once the codebase
    has no reader left to catch it.
    """
    import tempfile

    NL = chr(10)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "src"
        root.mkdir()
        (root / "field_names.py").write_text('FIELD_USER_ID = "user_id"' + NL, encoding="utf-8")
        (root / "reader.py").write_text(
            NL.join(
                (
                    "from src.field_names import FIELD_USER_ID",
                    "def f(config):",
                    "    return config.get('configurable', {}).get(FIELD_USER_ID)",
                )
            ),
            encoding="utf-8",
        )
        found = _scanner.scan(root)

    assert found == {"src/reader.py": ["user_id"]}, found


@pytest.mark.unit
def test_the_chokepoint_bag_carries_plumbing_only() -> None:
    """The writer must stay empty, or the readers grow back.

    Emptying the readers is only half of ADR-231: while the chokepoint kept
    writing the 17 run-scoped values, both planes stayed authoritative and the
    untyped one always wins by being the easier to reach. This asserts the single
    construction site of the graph's ``RunnableConfig`` declares no context key.
    """
    service = SRC_DIR / "domains" / "agents" / "services" / "orchestration" / "service.py"
    tree = ast.parse(service.read_text(encoding="utf-8"))

    written: set[str] = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "RunnableConfig"):
            continue
        for keyword in node.keywords:
            if keyword.arg == "configurable" and isinstance(keyword.value, ast.Dict):
                written |= {
                    key.value
                    for key in keyword.value.keys
                    if isinstance(key, ast.Constant) and isinstance(key.value, str)
                }

    assert written, "no RunnableConfig(configurable=...) found — did the chokepoint move?"
    assert not (written & _scanner.CONTEXT_KEYS), (
        "The graph chokepoint writes run-scoped context into `configurable` again. "
        "It belongs on LiaRuntimeContext (ADR-231); the bag is LangGraph plumbing "
        f"only: {sorted(written & _scanner.CONTEXT_KEYS)}"
    )
