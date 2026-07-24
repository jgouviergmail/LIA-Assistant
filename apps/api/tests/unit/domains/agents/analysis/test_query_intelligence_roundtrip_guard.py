"""Guard: the QueryIntelligence serialization pair can never drift apart.

``QueryIntelligence`` crosses every LangGraph checkpoint as a plain dict
(msgpack cannot carry the dataclass), so ``to_serializable_dict`` and
``reconstruct_query_intelligence`` form a pair. CLAUDE.md lists the failure as
a recurring, SILENT bug: "Adding a field on one side only […] fields lost after
every HITL checkpoint resume". The field simply reverts to its default after an
interrupt and nothing raises.

``test_round_trip_preserves_all_serialized_fields`` (sibling module) compares
the serialized dict before and after reconstruction — but it can only catch a
lost field if the FIXTURE gives that field a value distinguishable from its
default. Two fields already sat at their default there, which made the identity
assertion vacuous for them. This module closes both holes:

1. every key written by ``to_serializable_dict`` is read back by
   ``reconstruct_query_intelligence`` (static, so a field added on one side
   only fails immediately, even before anyone writes a value for it);
2. the round-trip fixture keeps a non-default value for every serialized field,
   so the identity assertion stays load-bearing.
"""

from __future__ import annotations

import ast

import pytest

from src.domains.agents.analysis.query_intelligence import QueryIntelligence
from tests._repo_paths import find_apps_api_root
from tests.unit.domains.agents.analysis.test_query_intelligence_helpers import (
    _make_full_query_intelligence,
)

pytestmark = pytest.mark.unit

API_ROOT = find_apps_api_root()
SERIALIZER = API_ROOT / "src/domains/agents/analysis/query_intelligence.py"
RECONSTRUCTOR = API_ROOT / "src/domains/agents/analysis/query_intelligence_helpers.py"

# Keys that are serialized but deliberately NOT read back from this dict.
# Each entry states why; ``test_every_exemption_is_still_needed`` removes it as
# soon as the asymmetry disappears.
RECONSTRUCTION_EXEMPTIONS: dict[str, str] = {
    "resolved_context": (
        "ResolvedContext is a complex object that cannot survive the dict; "
        "get_query_intelligence_from_state restores it from its own state key "
        "(STATE_KEY_RESOLVED_CONTEXT) right after reconstruction."
    ),
}


def _keys_written_by_serializer() -> set[str]:
    """String keys of the dict literal returned by ``to_serializable_dict``."""
    tree = ast.parse(SERIALIZER.read_text(encoding="utf-8"))
    keys: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name != "to_serializable_dict":
            continue
        for inner in ast.walk(node):
            if isinstance(inner, ast.Dict):
                keys.update(
                    key.value
                    for key in inner.keys
                    if isinstance(key, ast.Constant) and isinstance(key.value, str)
                )
    return keys


def _keys_read_by_reconstructor() -> set[str]:
    """String keys accessed (``data.get("x")`` / ``data["x"]``) when rebuilding."""
    tree = ast.parse(RECONSTRUCTOR.read_text(encoding="utf-8"))
    keys: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name != "reconstruct_query_intelligence":
            continue
        for inner in ast.walk(node):
            if (
                isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Attribute)
                and inner.func.attr == "get"
                and inner.args
                and isinstance(inner.args[0], ast.Constant)
                and isinstance(inner.args[0].value, str)
            ):
                keys.add(inner.args[0].value)
            if (
                isinstance(inner, ast.Subscript)
                and isinstance(inner.slice, ast.Constant)
                and isinstance(inner.slice.value, str)
            ):
                keys.add(inner.slice.value)
    return keys


def _minimal_intelligence() -> QueryIntelligence:
    """An instance where every OPTIONAL field keeps its declared default."""
    return QueryIntelligence(
        original_query="__minimal__",
        english_query="__minimal__",
        immediate_intent="__minimal__",
        immediate_confidence=0.0,
        user_goal=None,
        goal_reasoning="__minimal__",
    )


class TestSerializationPairSymmetry:
    """Both halves of the pair must know about exactly the same fields."""

    def test_serializer_writes_at_least_one_key(self) -> None:
        """Oracle for the AST extraction itself."""
        assert len(_keys_written_by_serializer()) > 10

    def test_every_serialized_key_is_read_back(self) -> None:
        written = _keys_written_by_serializer()
        read = _keys_read_by_reconstructor()

        missing = sorted(written - read - set(RECONSTRUCTION_EXEMPTIONS))
        assert not missing, (
            "These fields are written by to_serializable_dict but never read by "
            "reconstruct_query_intelligence — they silently reset to their default "
            f"after every checkpoint resume: {missing}"
        )

    def test_reconstructor_reads_no_unknown_key(self) -> None:
        written = _keys_written_by_serializer()
        read = _keys_read_by_reconstructor()

        unknown = sorted(read - written)
        assert not unknown, (
            "reconstruct_query_intelligence reads keys the serializer never "
            f"writes — they will always be absent: {unknown}"
        )

    def test_every_exemption_is_still_needed(self) -> None:
        """Shrink-only: an exemption that became symmetric must be deleted."""
        written = _keys_written_by_serializer()
        read = _keys_read_by_reconstructor()

        stale = sorted(
            key for key in RECONSTRUCTION_EXEMPTIONS if key in read or key not in written
        )
        assert not stale, f"These exemptions are obsolete, remove them: {stale}"


class TestRoundTripFixtureIsLoadBearing:
    """The identity assertion only bites on fields the fixture actually moves."""

    def test_fixture_gives_every_serialized_field_a_non_default_value(self) -> None:
        full = _make_full_query_intelligence().to_serializable_dict()
        minimal = _minimal_intelligence().to_serializable_dict()

        vacuous = sorted(
            key
            for key in full
            if key not in RECONSTRUCTION_EXEMPTIONS and full.get(key) == minimal.get(key)
        )
        assert not vacuous, (
            "The round-trip fixture leaves these fields at their default value, so "
            "the serialize -> reconstruct -> serialize identity would not notice "
            f"them being dropped: {vacuous}"
        )

    def test_fixture_covers_every_serialized_key(self) -> None:
        assert set(_make_full_query_intelligence().to_serializable_dict()) == (
            _keys_written_by_serializer()
        )
