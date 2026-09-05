"""What the tamper-evident chain covers, column by column (ADR-263, lot 5).

An allowlist that forgets a column leaves a place where a value can be edited
without the chain noticing — exactly what the chain exists to prevent. So the
rule is the opposite of a denylist: every column of every covered model is
either **digested** or **excluded on purpose**, and a column added tomorrow
fails the build until someone decides which it is
(``tests/.../test_chain_spec.py``).

Two stages for an action, one for a consultation, because a ledger row is
MUTATED and a consultation row never is. Measured on the repository: four
writers touch ``agent_effects`` — ``claim`` (insert), ``close`` (update),
``refuse`` (insert) and ``abandon_stale`` (update). A single digest taken at
claim time would turn every legitimate close into a tampering alarm; splitting
the coverage in two is what makes a normal lifecycle verify clean.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from src.domains.agents.effects.chain_digest import row_digest

#: The ONLY columns the chain does not digest: the two the notary itself
#: writes. Digesting them would make the act of notarising invalidate the
#: digest it just took. Every other exception would be a hole someone has to
#: remember, so there are none.
NOT_DIGESTED: Final[frozenset[str]] = frozenset({"notarised_at", "settled_notarised_at"})


@dataclass(frozen=True)
class ChainSubject:
    """One stage of coverage for one register.

    Attributes:
        kind: ``<subject>.<stage>``, written into every entry's hash — renaming
            one would invalidate the chains that carry it.
        model: The mapped class name, read by the completeness guard.
        marker: The column the notary sets once this stage is chained.
        columns: The digested allowlist for this stage.
    """

    kind: str
    model: str
    marker: str
    columns: tuple[str, ...]


#: An action, at the moment it was DECIDED. Only columns that never change
#: afterwards: a close must not read as an alteration.
EFFECT_CLAIMED: Final[ChainSubject] = ChainSubject(
    kind="effect.claimed",
    model="AgentEffect",
    marker="notarised_at",
    columns=(
        "id",
        "user_id",
        "thread_id",
        "run_id",
        "source",
        "execution_mode",
        "tool_name",
        "mutation_policy",
        "idempotency_key",
        "args_digest",
        "label",
        "approval_kind",
        "approval_ref",
        "draft_digest",
        "claim_token",
        "claimed_at",
        "schema_version",
        "catalogue_fingerprint",
    ),
)

#: The same action, at the moment its OUTCOME was recorded. ``result_payload``
#: is digested as stored (encrypted): the chain notices any change to it,
#: without ever holding what it says.
EFFECT_SETTLED: Final[ChainSubject] = ChainSubject(
    kind="effect.settled",
    model="AgentEffect",
    marker="settled_notarised_at",
    columns=(
        "status",
        "closed_at",
        "provider_ref",
        "result_payload",
        "result_digest",
        "result_truncated",
        "error_code",
        "retry_of",
    ),
)

#: A consultation is written once and never mutated, so one stage covers it —
#: and it covers ALL of it.
TREATMENT_RECORDED: Final[ChainSubject] = ChainSubject(
    kind="treatment.recorded",
    model="AgentTreatment",
    marker="notarised_at",
    columns=(
        "id",
        "user_id",
        "thread_id",
        "run_id",
        "source",
        "execution_mode",
        "tool_name",
        "mutation_policy",
        "outcome",
        "duration_ms",
        "occurred_at",
    ),
)

#: Every stage, in the order a reader meets them.
CHAIN_SUBJECTS: Final[tuple[ChainSubject, ...]] = (
    EFFECT_CLAIMED,
    EFFECT_SETTLED,
    TREATMENT_RECORDED,
)

#: The chain's first entry for an account. It says, in the clear, that nothing
#: before it is covered — the honest alternative to a silence that would let a
#: reader assume the whole history was notarised.
GENESIS_KIND: Final[str] = "chain.genesis"


def subjects_for(model: str) -> tuple[ChainSubject, ...]:
    """The stages covering one mapped class.

    Args:
        model: The class name, e.g. ``AgentEffect``.

    Returns:
        Its stages, in coverage order.
    """
    return tuple(subject for subject in CHAIN_SUBJECTS if subject.model == model)


def digest_of(row: Any, subject: ChainSubject) -> str:
    """Digest one row's covered columns.

    Lives beside the allowlist rather than beside the caller, so there is ONE
    place where a spec becomes a digest — the write path and the verification
    path cannot drift into two readings of the same declaration.

    Args:
        row: The mapped row.
        subject: The stage whose allowlist applies.

    Returns:
        The digest, over an EXPLICIT column list — never ``__dict__``, which
        would silently start covering a column nobody classified.
    """
    return row_digest({column: getattr(row, column) for column in subject.columns})
