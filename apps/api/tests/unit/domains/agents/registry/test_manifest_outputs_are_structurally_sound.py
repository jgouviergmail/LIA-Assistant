"""Every published output path must describe a reachable shape.

The two sibling suites answer "does this path resolve against a real payload?",
which needs a builder and therefore covers 27 tools out of 88. This one asks a
weaker question of ALL of them — one that needs no execution at all: is the
declaration internally coherent?

It exists because a manual read of ~2900 lines of manifests is not evidence.
Run mechanically over the whole catalogue the day it was written, it found a
real defect the other guards could not see: ``run_skill_script`` published
``skill_apps[].title`` without ever declaring ``skill_apps``, so a planner was
told about members of a collection whose existence was never stated — the same
class of gap ADR-194 closed for the weather and Hue manifests.
"""

from __future__ import annotations

import re

import pytest

from src.domains.agents.registry.catalogue import ToolManifest

pytestmark = pytest.mark.unit

#: The JSON-schema type names a manifest may declare.
_VALID_TYPES = frozenset({"string", "number", "integer", "boolean", "array", "object"})

#: ``a``, ``a[]``, ``a.b``, ``a[].b``, and ``matrix[][].x`` for the 2-D route matrix.
_PATH_SYNTAX = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(\[\])*(\.[A-Za-z_][A-Za-z0-9_]*(\[\])*)*")


def _declaration_problems(manifest: ToolManifest) -> list[str]:
    """Every structural defect in one manifest's outputs.

    Args:
        manifest: The manifest to inspect.

    Returns:
        Human-readable problems, empty when the declaration is coherent.
    """
    problems: list[str] = []
    outputs = manifest.outputs or []
    declared = {output.path: output for output in outputs}

    if len(declared) != len(outputs):
        problems.append("the same path is declared twice")

    for output in outputs:
        if output.type not in _VALID_TYPES:
            problems.append(f"{output.path}: unknown type {output.type!r}")
        if not (output.description or "").strip():
            problems.append(f"{output.path}: no description — the planner reads these")
        if not _PATH_SYNTAX.fullmatch(output.path):
            problems.append(f"{output.path!r}: not a valid output path")

        if "." not in output.path:
            continue

        # A member implies its container. The catalogue declares an array
        # WITHOUT brackets ("contacts") and addresses it WITH them
        # ("contacts[].name"), so both spellings are accepted here.
        raw_parent = output.path.rsplit(".", 1)[0]
        parent = next((c for c in (raw_parent, raw_parent.rstrip("[]")) if c in declared), None)
        if parent is None:
            problems.append(
                f"{output.path}: container {raw_parent!r} is never declared — the planner "
                f"cannot know the collection exists"
            )
            continue

        expected = "array" if raw_parent.endswith("[]") else "object"
        if declared[parent].type != expected:
            problems.append(
                f"{output.path}: container {parent!r} is declared "
                f"{declared[parent].type!r} but addressed as {expected!r}"
            )

    return problems


class TestEveryManifestOutputIsStructurallySound:
    def test_the_whole_catalogue_declares_coherent_outputs(
        self, manifests: dict[str, ToolManifest]
    ) -> None:
        offenders = {
            name: problems
            for name, manifest in manifests.items()
            if (problems := _declaration_problems(manifest))
        }

        assert not offenders, "manifests whose outputs contradict themselves:\n" + "\n".join(
            f"  {name}:\n" + "\n".join(f"    - {p}" for p in problems)
            for name, problems in sorted(offenders.items())
        )

    def test_the_catalogue_is_actually_being_inspected(
        self, manifests: dict[str, ToolManifest]
    ) -> None:
        """A guard that silently inspects nothing is the defect it guards against.

        Deliberately a floor against COLLAPSE, not a ratchet on the exact count:
        the catalogue size depends on which feature flags are on (81 tools /
        372 outputs under the test settings, 88 / 390 in the dev container), and
        pinning the exact number would fail for a reason that says nothing about
        correctness.
        """
        declared_outputs = sum(len(m.outputs or []) for m in manifests.values())

        assert len(manifests) >= 70, f"only {len(manifests)} tools loaded — catalogue collapsed"
        assert declared_outputs >= 300, f"only {declared_outputs} outputs inspected"
        assert "run_skill_script" in manifests, (
            "the manifest this guard was written against must be in scope, or the "
            "defect it found could come back unnoticed"
        )
