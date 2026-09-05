"""Every manifest DECLARED IN SOURCE carries its policy — whatever the flags say.

The runtime guard (``assert_mutation_policy_completeness``) can only see the
manifests the catalogue actually loaded, and the catalogue is built behind nine
feature flags. Measured 2026-09-04, twice over:

- ``place_phone_call_tool`` — a call to a third party — was invisible to the
  first inventory because ``telephony_enabled`` was off;
- four peer manifests, including ``send_peer_message_tool``, were invisible to
  the "all flags on" test because its flag list carried a PHANTOM name
  (``peer_connections_enabled``, which does not exist — the real one is
  ``peers_enabled``). The runtime guard would then have refused the boot on any
  deployment with peers enabled: the very defect it exists to prevent, pointing
  the other way.

A hand-maintained flag list is a list someone must remember to update. This
guard reads the SOURCE instead: it needs no settings, no registry and no flags,
so a manifest cannot hide behind a switch. It also covers manifests that are
declared but deliberately never registered (the browser sub-tools), which the
runtime guard can never reach.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from src.domains.agents.registry.catalogue import (
    MUTATION_POLICIES,
    POLICIES_REQUIRING_REASON,
    POLICY_EXEMPT_CATEGORIES,
    infer_tool_category,
)
from tests._repo_paths import repo_root_or_skip

pytestmark = [pytest.mark.unit]

#: Manifest declarations live in these two shapes across the domains.
_MANIFEST_FILE_GLOBS = ("*catalogue_manifests.py", "*_manifest.py")


def _declared_manifests() -> list[tuple[str, str, str | None, str | None, str]]:
    """Read every ``ToolManifest(...)`` declaration out of the source tree.

    Returns:
        One ``(file, name, declared_category, policy, reason_expr)`` per
        declaration; ``policy`` is None when the keyword is absent, and
        ``reason_expr`` is the raw expression (a constant or a REASON_* name).
    """
    root = repo_root_or_skip() / "apps" / "api" / "src" / "domains"
    files: set[pathlib.Path] = set()
    for pattern in _MANIFEST_FILE_GLOBS:
        files.update(root.rglob(pattern))

    found: list[tuple[str, str, str | None, str | None, str]] = []
    for path in sorted(files):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            called = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if called != "ToolManifest":
                continue
            keywords = {kw.arg: kw.value for kw in node.keywords if kw.arg}
            name_node = keywords.get("name")
            if not isinstance(name_node, ast.Constant):
                continue  # a computed name (MCP builders) — not a source declaration
            category_node = keywords.get("tool_category")
            category = category_node.value if isinstance(category_node, ast.Constant) else None
            policy_node = keywords.get("mutation_policy")
            policy = policy_node.value if isinstance(policy_node, ast.Constant) else None
            reason_node = keywords.get("mutation_policy_reason")
            reason = "" if reason_node is None else ast.unparse(reason_node)
            found.append((str(path), str(name_node.value), category, policy, reason))
    return found


@pytest.fixture(scope="module")
def declarations() -> list[tuple[str, str, str | None, str | None, str]]:
    """Every manifest declared in the source tree."""
    found = _declared_manifests()
    # Anti-vacuity: a broken parse or a moved directory must fail loudly rather
    # than make this guard pass over an empty list.
    assert len(found) >= 110, f"only {len(found)} manifests parsed — the guard is blind"
    return found


class TestEveryDeclaredManifestSaysWhatItOwes:
    def test_no_acting_manifest_is_silent(
        self, declarations: list[tuple[str, str, str | None, str | None, str]]
    ) -> None:
        silent = [
            (name, category, path)
            for path, name, category, policy, _ in declarations
            if policy is None
            and (category or infer_tool_category(name)) not in POLICY_EXEMPT_CATEGORIES
        ]
        assert not silent, (
            "These manifests declare no mutation_policy and are not `search` "
            f"(the only exempt category): {silent}. A manifest gated behind a "
            "feature flag still refuses the boot on a deployment that enables it."
        )

    def test_every_policy_is_part_of_the_vocabulary(
        self, declarations: list[tuple[str, str, str | None, str | None, str]]
    ) -> None:
        unknown = [
            (name, policy)
            for _, name, _, policy, _ in declarations
            if policy is not None and policy not in MUTATION_POLICIES
        ]
        assert not unknown, unknown

    def test_every_exemption_carries_a_reason(
        self, declarations: list[tuple[str, str, str | None, str | None, str]]
    ) -> None:
        """Read from the SOURCE: a reason removed by hand fails here too."""
        missing = [
            (name, policy)
            for _, name, _, policy, reason in declarations
            if policy in POLICIES_REQUIRING_REASON and not reason.strip()
        ]
        assert not missing, missing

    def test_a_search_manifest_never_claims_to_act(
        self, declarations: list[tuple[str, str, str | None, str | None, str]]
    ) -> None:
        contradictions = [
            (name, policy)
            for _, name, category, policy, _ in declarations
            if (category or infer_tool_category(name)) in POLICY_EXEMPT_CATEGORIES
            and policy is not None
            and policy != "read"
        ]
        assert not contradictions, contradictions


class TestTheFlagsThisGuardMakesIrrelevant:
    """The phantom that made the runtime guard blind, pinned so it cannot return."""

    def test_the_peer_flag_is_the_real_one(self) -> None:
        from src.core.config import settings

        assert hasattr(settings, "peers_enabled")
        assert not hasattr(settings, "peer_connections_enabled"), (
            "A flag that does not exist silently disables the branch that sets it, "
            "and every manifest behind it escapes the runtime guard."
        )

    def test_the_peer_manifests_are_declared(
        self, declarations: list[tuple[str, str, str | None, str | None, str]]
    ) -> None:
        by_name = {name: policy for _, name, _, policy, _ in declarations}
        assert by_name.get("send_peer_message_tool") == "draft"
        for reader in (
            "list_peer_connections_tool",
            "get_peer_availability_tool",
            "get_peer_tasks_tool",
        ):
            assert by_name.get(reader) == "read", reader

    def test_the_unregistered_browser_subtools_are_declared_too(
        self, declarations: list[tuple[str, str, str | None, str | None, str]]
    ) -> None:
        """Declared in source, never registered — the runtime guard cannot see them."""
        by_name = {name: policy for _, name, _, policy, _ in declarations}
        assert by_name.get("browser_snapshot_tool") == "read"
        for actor in ("browser_click_tool", "browser_fill_tool", "browser_press_key_tool"):
            assert by_name.get(actor) == "reversible", actor
