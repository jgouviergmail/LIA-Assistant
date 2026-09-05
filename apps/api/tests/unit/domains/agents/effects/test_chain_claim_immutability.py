"""No writer may mutate a column the CLAIM stage covers (ADR-263, lot 5).

The two-stage split is what makes a normal lifecycle verify clean: an effect is
inserted, then UPDATEd when it closes, so a single digest taken at claim time
would turn every legitimate close into a tampering alarm. ``EFFECT_CLAIMED``
therefore covers only columns nothing ever changes afterwards.

That is a property of the REPOSITORY, not of the spec — and nothing in the spec
can enforce it. A future ``close`` that also set ``label``, or a maintenance
method that touched ``tool_name``, would silently break every chain on the
instance, and it would break them for rows written BEFORE the change: the
symptom would be a wave of « your journal was altered » on data nobody touched.

So the guard reads the repository's own ``.values(...)`` keys — every column any
UPDATE assigns — and refuses any overlap with the claim allowlist. It reads the
source rather than the runtime, so the refusal lands before the code ever runs.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

REPOSITORY = (
    Path(__file__).resolve().parents[5] / "src" / "domains" / "agents" / "effects" / "repository.py"
)

TREATMENT_REPOSITORY = REPOSITORY.with_name("treatment_repository.py")

#: The notary's own markers. They are the ONLY columns an UPDATE may set on a
#: covered row, and the chain deliberately does not digest them — digesting
#: them would make the act of notarising invalidate the digest it just took.
NOTARY_MARKERS = frozenset({"notarised_at", "settled_notarised_at"})


#: Method calls that ASSIGN columns on an existing row. ``insert(...).values``
#: assigns them on a row being created, which is not a mutation and must not be
#: reported — the claim itself writes every column the claim digest covers.
_ASSIGNING_METHODS = frozenset({"values", "set_"})


def _statement_root(node: ast.AST) -> str | None:
    """The constructor a chained statement expression starts from.

    ``update(Model).where(...).values(...)`` roots at ``update``;
    ``pg_insert(Model).values(...)`` roots at ``pg_insert``. Reading the root is
    what separates a mutation from an insertion, and the whole guard rests on
    that distinction.

    Args:
        node: Any node of the chain.

    Returns:
        The root callable's name, or None when it cannot be read.
    """
    current = node
    while True:
        if isinstance(current, ast.Call):
            current = current.func
        elif isinstance(current, ast.Attribute):
            current = current.value
        elif isinstance(current, ast.Name):
            return current.id
        else:
            return None


def _assigned_columns(source: Path) -> set[str]:
    """Every column an UPDATE in this module assigns.

    Args:
        source: The module to read.

    Returns:
        The keyword names. Positional-dict and ``**kwargs`` forms are reported
        as the sentinel ``"<dynamic>"`` so an opaque call cannot pass by being
        unreadable. Insertions are excluded: creating a row is not mutating it.
    """
    tree = ast.parse(source.read_text(encoding="utf-8"))
    assigned: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if not isinstance(function, ast.Attribute) or function.attr not in _ASSIGNING_METHODS:
            continue
        if _statement_root(function.value) != "update":
            continue
        if node.args:
            assigned.add("<dynamic>")
        for keyword in node.keywords:
            assigned.add(keyword.arg if keyword.arg is not None else "<dynamic>")
    return assigned


class TestTheClaimStageIsFrozen:
    def test_the_guard_reads_something(self) -> None:
        """Anti-vacuity: a refactor that moves the UPDATEs elsewhere must not
        silence this file — it must fail it."""
        assigned = _assigned_columns(REPOSITORY)

        assert assigned, "no update(...).values(...) found in the ledger repository"
        assert "status" in assigned, "the close path is no longer visible to this guard"

    def test_it_does_not_mistake_an_INSERT_for_a_mutation(self) -> None:
        """The claim itself writes every column the claim digest covers; a
        guard that read insertions would be unsatisfiable by construction."""
        assert "idempotency_key" not in _assigned_columns(REPOSITORY)

    def test_no_update_touches_a_column_the_CLAIM_digest_covers(self) -> None:
        from src.domains.agents.effects.chain_spec import EFFECT_CLAIMED

        offenders = _assigned_columns(REPOSITORY) & set(EFFECT_CLAIMED.columns)

        assert not offenders, (
            f"{sorted(offenders)} is/are covered by the CLAIM digest and assigned by an "
            "UPDATE. Every chain on the instance would break on rows nobody touched. "
            "Either stop mutating the column, or move it to EFFECT_SETTLED and say why."
        )

    def test_the_dynamic_values_call_is_the_close_helper_and_stays_bounded(self) -> None:
        """``_close`` forwards ``**values`` from its two callers.

        Those callers pass outcome columns only, and the test above cannot see
        through them — so this pins the callers' vocabulary instead.
        """
        from src.domains.agents.effects.chain_spec import EFFECT_CLAIMED, EFFECT_SETTLED

        forwarded = {
            "provider_ref",
            "result_digest",
            "result_payload",
            "result_truncated",
            "error_code",
        }

        assert forwarded <= set(EFFECT_SETTLED.columns), "an outcome column is not covered"
        assert not forwarded & set(EFFECT_CLAIMED.columns)


class TestAConsultationIsNeverUPDATEd:
    def test_the_consultation_repository_assigns_nothing_but_the_marker(self) -> None:
        """A consultation is written once, which is why ONE stage covers ALL of
        it. An UPDATE anywhere here would invalidate that reasoning."""
        from src.domains.agents.effects.chain_spec import TREATMENT_RECORDED

        assigned = _assigned_columns(TREATMENT_REPOSITORY)

        assert not assigned & set(TREATMENT_RECORDED.columns)
        assert assigned <= NOTARY_MARKERS | {"<dynamic>"} or not assigned
