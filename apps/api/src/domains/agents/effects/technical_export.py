"""The technical register: what happened, with nobody named (ADR-263).

The readable register is a person's own record and leaves with their archive.
This one answers a different question — *is the execution chain behaving?* —
and is meant to be handed to a tool, an analyst or a model. So it is
**pseudonymised BY CONSTRUCTION** rather than by filtering:

- the row is built from an explicit ALLOWLIST of columns, so a column added
  tomorrow is absent until someone decides otherwise (a denylist would leak it
  the day it lands);
- ``user_id`` becomes an HMAC keyed by the server secret — stable enough to
  group one account's rows, useless outside this instance;
- ``label`` and ``result_payload`` never appear at all: they are exactly where
  a third party's name or words would be;
- ``provider_ref`` becomes a short fingerprint: correlating two rows must stay
  possible, retrieving the provider's object must not.

The cap is published in the header rather than applied in silence: an operator
who needs more narrows the period.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.core.config import settings

#: Columns that may appear in a technical row, and nothing else. Adding one is
#: a decision, taken here, with the PII guard's test to answer to.
EXPORTED_COLUMNS: tuple[str, ...] = (
    "id",
    "schema_version",
    "tool_name",
    "mutation_policy",
    "status",
    "source",
    "execution_mode",
    "approval_kind",
    "error_code",
    "args_digest",
    "draft_digest",
    "result_truncated",
    "claimed_at",
    "closed_at",
    "thread_id",
    "run_id",
    "idempotency_key",
    "approval_ref",
    "retry_of",
    # Non-identifying by construction: digests and a catalogue version. They
    # are what makes the file analysable — "the same call twice", "the
    # catalogue changed under the same tool".
    "catalogue_fingerprint",
    "result_digest",
)

#: Exported columns that name something rather than describe it: correlation
#: must survive, identity must not. A conversation id or a draft id is enough
#: to reconstruct someone's day once joined with anything else.
PSEUDONYMISED_COLUMNS: frozenset[str] = frozenset(
    {"id", "thread_id", "run_id", "idempotency_key", "approval_ref", "retry_of"}
)

#: Columns that must NEVER be exported, whatever a future edit intends. The
#: allowlist above already excludes them; this states WHY, and the guard reads
#: it, so removing a column from one list cannot silently add it to the export.
FORBIDDEN_COLUMNS: frozenset[str] = frozenset(
    {
        "user_id",  # replaced by a keyed pseudonym
        "label",  # names people
        "result_payload",  # quotes third parties
        "provider_ref",  # replaced by a fingerprint
        "claim_token",  # a capability, not data
        # The notary's bookkeeping (ADR-263 lot 5). Excluded for a reason that
        # is not privacy but REPRODUCIBILITY: they say when a background job
        # reached a row, so the same period exported twice would differ in a
        # column that says nothing about the execution. Whether a row is
        # sealed is answered by /effects/chain/verify, which is the surface
        # built for it.
        "notarised_at",
        "settled_notarised_at",
    }
)

#: Length of the pseudonyms. Long enough not to collide over a deployment,
#: short enough to read in a terminal.
PSEUDONYM_LENGTH = 16


@dataclass(frozen=True)
class TechnicalSpec:
    """What one register exports, and what it must never export.

    Two registers, one renderer: a second copy of the row builder would be a
    second place for a column to slip from "forbidden" to "exported" without
    anyone noticing.

    Attributes:
        slug: The register's identity in the file name and the header.
        model: Name of the row class, for the guard that checks every column is
            classified.
        module: Where that class lives. Declared rather than assumed: the
            inference log is ``token_usage_logs``, which predates the registers
            and lives in the chat domain — a resolver hard-coding one module
            would refuse the very spec that proves this contract generalises.
        exported: The ALLOWLIST — a column added tomorrow is absent until
            someone decides otherwise.
        pseudonymised: Exported columns that name rather than describe.
        forbidden: Columns that must never appear, with the reason stated in
            the constant that carries them.
        filters: Query filters this register actually HONOURS, beyond the
            period and the account list every register understands. Declared
            here rather than inferred at the route, because what a register can
            be asked is the same kind of contract as what it can show: a header
            that states a filter the query never applied makes an unfiltered
            file read as a filtered one (ADR-184 — whatever a layer enforces,
            its caller must be able to read).
    """

    slug: str
    model: str
    exported: tuple[str, ...]
    pseudonymised: frozenset[str]
    forbidden: frozenset[str]
    filters: frozenset[str] = frozenset()
    module: str = "src.domains.agents.effects.models"


#: Columns of the CONSULTATION register. Deliberately short, because the row
#: itself is: a consultation records which capability answered, never what was
#: asked, so there is no content column to exclude — only identifiers to
#: pseudonymise.
TREATMENT_EXPORTED_COLUMNS: tuple[str, ...] = (
    "id",
    "tool_name",
    "mutation_policy",
    "outcome",
    "source",
    "execution_mode",
    "duration_ms",
    "occurred_at",
    "thread_id",
    "run_id",
)

TREATMENT_PSEUDONYMISED_COLUMNS: frozenset[str] = frozenset({"id", "thread_id", "run_id"})

TREATMENT_FORBIDDEN_COLUMNS: frozenset[str] = frozenset(
    {
        "user_id",  # replaced by a keyed pseudonym
        "notarised_at",  # the notary's bookkeeping — see FORBIDDEN_COLUMNS
    }
)


def spec_model(spec: TechnicalSpec) -> Any:
    """The mapped class one contract describes.

    One resolver, shared by the completeness guard and any reader that needs
    the columns: two would be two places for a spec to point at a class nobody
    checks.

    Args:
        spec: The register's contract.

    Returns:
        The mapped class.
    """
    from importlib import import_module

    return getattr(import_module(spec.module), spec.model)


def pseudonymise(value: Any) -> str | None:
    """A stable, non-reversible handle for one identifier.

    Keyed with the server secret: two rows of the same account share a handle
    inside this deployment, and the handle means nothing outside it — an
    exported file cannot be joined back to a user by whoever receives it.

    Args:
        value: The identifier, or None.

    Returns:
        The handle, or None when there is nothing to name.
    """
    if value is None:
        return None
    digest = hmac.new(
        settings.secret_key.encode("utf-8"), str(value).encode("utf-8"), hashlib.sha256
    )
    return digest.hexdigest()[:PSEUDONYM_LENGTH]


def technical_row(effect: Any, spec: TechnicalSpec | None = None) -> dict[str, Any]:
    """One register row, stripped to what an analyst may see.

    Args:
        effect: An ``AgentEffect`` or ``AgentTreatment`` row.
        spec: Which register's contract to apply. Defaults to the action
            ledger, so every existing caller keeps its behaviour unchanged.

    Returns:
        The exportable mapping — allowlisted columns, pseudonymised
        identifiers, no content of any kind.
    """
    contract = spec or ACTIONS_SPEC
    row: dict[str, Any] = {}
    for column in contract.exported:
        value = getattr(effect, column, None)
        if column in contract.pseudonymised:
            # Checked FIRST: an identifier that happened to be a stored enum
            # would otherwise be exported in clear by the branch below.
            row[column] = pseudonymise(value)
        elif isinstance(value, datetime):
            row[column] = value.isoformat()
        elif value is not None and hasattr(value, "value"):  # a stored enum
            row[column] = value.value
        else:
            row[column] = value
    row["user"] = pseudonymise(getattr(effect, "user_id", None))
    if "provider_ref" in contract.forbidden:
        row["provider_fingerprint"] = pseudonymise(getattr(effect, "provider_ref", None))
    return row


#: Columns of the DECISION register (ADR-263, lot 6). The two message
#: references are pseudonymised rather than excluded: correlation must survive
#: — « the same conversation, twice » is exactly what a technical reader needs —
#: while identity must not, and a raw message id joined with anything else
#: reconstructs someone's day.
DECISION_EXPORTED_COLUMNS: tuple[str, ...] = (
    "id",
    "schema_version",
    "run_id",
    "thread_id",
    "source",
    "execution_mode",
    "route",
    "plan_step_count",
    "request_message_id",
    "response_message_id",
    "outcome",
    # Why the turn stopped short (ADR-263 lot 8). Exported, not forbidden: a
    # reader asking « did this answer come out whole? » is asking exactly this.
    "stop_reason",
    "segments",
    "started_at",
    "ended_at",
    "duration_ms",
)

DECISION_PSEUDONYMISED_COLUMNS: frozenset[str] = frozenset(
    {"id", "run_id", "thread_id", "request_message_id", "response_message_id"}
)

DECISION_FORBIDDEN_COLUMNS: frozenset[str] = frozenset(
    {
        "user_id",  # replaced by a keyed pseudonym
    }
)


#: Columns of the INFERENCE log (ADR-263, lot 7). Not a fourth register: it is
#: ``token_usage_logs``, which was already the per-call record, keyed by the
#: same ``run_id``. What lot 7 added is what was SENT — normalised, so one
#: concept does not wear three provider spellings.
#:
#: One honesty note this contract cannot express and the documentation must:
#: unlike the three registers, this table is ``BILLING_RETAINED`` and therefore
#: OUTLIVES the account it describes.
INFERENCE_EXPORTED_COLUMNS: tuple[str, ...] = (
    "id",
    "run_id",
    "node_name",
    "llm_type",
    "model_name",
    "provider",
    "temperature",
    "top_p",
    "max_output_tokens",
    "reasoning_level",
    "reasoning_budget_tokens",
    "params_digest",
    "prompt_tokens",
    "completion_tokens",
    "cached_tokens",
    "latency_ms",
    "status",
    "failure_kind",
    "created_at",
)

INFERENCE_PSEUDONYMISED_COLUMNS: frozenset[str] = frozenset({"id", "run_id"})

INFERENCE_FORBIDDEN_COLUMNS: frozenset[str] = frozenset(
    {
        "user_id",  # replaced by a keyed pseudonym
        # Money is not an inference parameter, and a file about HOW an answer
        # was produced is not the place to publish what it cost: the usage
        # export already answers that question, for its own audience.
        "cost_usd",
        "cost_eur",
        "usd_to_eur_rate",
        # Inherited from the base model and meaningless here: the log is
        # immutable, so it always equals ``created_at``. Exporting it would put
        # a second timestamp beside the real one for a reader to wonder about.
        "updated_at",
    }
)


#: The action ledger's contract — the original, unchanged.
ACTIONS_SPEC: TechnicalSpec = TechnicalSpec(
    slug="actions",
    model="AgentEffect",
    exported=EXPORTED_COLUMNS,
    pseudonymised=PSEUDONYMISED_COLUMNS,
    forbidden=FORBIDDEN_COLUMNS,
    filters=frozenset({"tool_name", "mutation_policy", "status", "source", "execution_mode"}),
)

#: The consultation register's contract.
TREATMENTS_SPEC: TechnicalSpec = TechnicalSpec(
    slug="consultations",
    model="AgentTreatment",
    exported=TREATMENT_EXPORTED_COLUMNS,
    pseudonymised=TREATMENT_PSEUDONYMISED_COLUMNS,
    forbidden=TREATMENT_FORBIDDEN_COLUMNS,
    # A consultation has no status, no policy and no approval — only the
    # capability it named.
    filters=frozenset({"tool_name"}),
)

#: The decision register's contract: one row per TURN, the spine the two others
#: hang off. It carries no content — a route, a count, timings and two
#: pseudonymised pointers.
DECISIONS_SPEC: TechnicalSpec = TechnicalSpec(
    slug="decisions",
    model="AgentDecision",
    exported=DECISION_EXPORTED_COLUMNS,
    pseudonymised=DECISION_PSEUDONYMISED_COLUMNS,
    forbidden=DECISION_FORBIDDEN_COLUMNS,
    # A turn names no capability: it is the SPINE the capabilities hang off.
    # Filtering it by tool name would answer a question about a different
    # register, so the header reports the request as ignored instead.
    filters=frozenset(),
)

#: Columns of the INTEGRITY register (ADR-263, lot 8). Everything it holds is
#: exportable: it carries a bounded classification and no content by
#: construction, which is what makes it safe to hand to a reader whole.
INTEGRITY_EXPORTED_COLUMNS: tuple[str, ...] = (
    "id",
    "kind",
    "run_id",
    "detail",
    "occurred_at",
)

INTEGRITY_PSEUDONYMISED_COLUMNS: frozenset[str] = frozenset({"id", "run_id"})

INTEGRITY_FORBIDDEN_COLUMNS: frozenset[str] = frozenset(
    {
        "user_id",  # replaced by a keyed pseudonym
        "updated_at",  # inherited and meaningless: the row is never updated
    }
)


#: The integrity register's contract.
INTEGRITY_SPEC: TechnicalSpec = TechnicalSpec(
    slug="integrity",
    model="AgentIntegrityEvent",
    exported=INTEGRITY_EXPORTED_COLUMNS,
    pseudonymised=INTEGRITY_PSEUDONYMISED_COLUMNS,
    forbidden=INTEGRITY_FORBIDDEN_COLUMNS,
    filters=frozenset(),
)


#: The inference log's contract.
INFERENCE_SPEC: TechnicalSpec = TechnicalSpec(
    slug="inference",
    model="TokenUsageLog",
    module="src.domains.chat.models",
    exported=INFERENCE_EXPORTED_COLUMNS,
    pseudonymised=INFERENCE_PSEUDONYMISED_COLUMNS,
    forbidden=INFERENCE_FORBIDDEN_COLUMNS,
    # A call names a slot and a model, never a capability: ``tool_name`` would
    # answer a question about a different register.
    filters=frozenset(),
)

#: Register name -> contract. The route reads this, so an unknown register is
#: a 422 from the framework rather than a branch nobody tested.
TECHNICAL_SPECS: dict[str, TechnicalSpec] = {
    ACTIONS_SPEC.slug: ACTIONS_SPEC,
    TREATMENTS_SPEC.slug: TREATMENTS_SPEC,
    DECISIONS_SPEC.slug: DECISIONS_SPEC,
    INFERENCE_SPEC.slug: INFERENCE_SPEC,
    INTEGRITY_SPEC.slug: INTEGRITY_SPEC,
}


#: Filter keys whose VALUES are identifiers. The header states what was asked
#: for, and a request naming accounts must be stated the way the rows are —
#: found by a test: an export promising "pseudonymised by construction" listed
#: the account ids in clear on its first line, undoing every row below it.
_IDENTIFYING_FILTERS: frozenset[str] = frozenset({"user_ids", "user_id"})


def _stated_filters(filters: dict[str, Any]) -> dict[str, Any]:
    """The filters, with identifiers replaced by their handles.

    Correlation survives — the same handle appears in the rows — while the
    file stops naming the accounts it covers. The operator who asked knows who
    they asked for; the file does not have to say.

    Args:
        filters: What the operator asked for.

    Returns:
        The same mapping, safe to write into the file.
    """
    stated: dict[str, Any] = {}
    for name, value in filters.items():
        if name not in _IDENTIFYING_FILTERS or value is None:
            stated[name] = value
        elif isinstance(value, list):
            stated[name] = [pseudonymise(one) for one in value]
        else:
            stated[name] = pseudonymise(value)
    return stated


def export_header(
    *,
    row_count: int,
    cap: int,
    filters: dict[str, Any],
    generated_at: datetime,
    spec: TechnicalSpec | None = None,
) -> dict[str, Any]:
    """The context line every technical export opens with.

    A file with no header is a file whose reader guesses: what was asked, what
    was refused, and whether the answer is complete.

    Args:
        row_count: Rows actually exported.
        cap: The ceiling that applied.
        filters: The filters the operator asked for. Identifiers among them are
            pseudonymised here, with the same key as the rows.
        generated_at: When the export was produced.
        spec: Which register the file holds. Defaults to the action ledger, so
            existing callers are unchanged — but a header that described the
            wrong register would tell a reader the file carries columns it does
            not have.

    Returns:
        The header mapping.
    """
    contract = spec or ACTIONS_SPEC
    columns = [*contract.exported, "user"]
    if "provider_ref" in contract.forbidden:
        columns.append("provider_fingerprint")
    return {
        "kind": f"lia.{contract.slug}.technical",
        "register": contract.slug,
        "generated_at": generated_at.isoformat(),
        "pseudonymised": True,
        "identifiers": "HMAC-SHA256 keyed by the instance secret, truncated",
        "excluded_columns": sorted(contract.forbidden),
        "columns": columns,
        "filters": _stated_filters(filters),
        "row_count": row_count,
        "row_cap": cap,
        "truncated": row_count >= cap,
    }


def render_jsonl(rows: list[dict[str, Any]], header: dict[str, Any]) -> str:
    """Render the export as JSON Lines, header first.

    Args:
        rows: The technical rows.
        header: The context header.

    Returns:
        The file content.
    """
    lines = [json.dumps(header, ensure_ascii=False, sort_keys=True)]
    lines.extend(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows)
    return "\n".join(lines) + "\n"
