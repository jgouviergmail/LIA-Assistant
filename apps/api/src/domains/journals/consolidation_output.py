"""Natural portrait claims with exact private evidence and bounded publication.

Code verifies structure and current source proofs; independent semantic review
decides whether the natural wording follows from them. Valid references alone
are never a semantic approval.
"""

import json
import re
from dataclasses import dataclass
from typing import Any, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from src.core.config import settings
from src.domains.journals.models import JournalEntry
from src.domains.journals.output_json import load_complete_json
from src.domains.journals.portrait_catalogue import (
    PORTRAIT_SUPPORT_QUOTE_MAX_CHARS,
    eligible_source_items,
    journal_item_id,
    resolve_source_item,
)
from src.domains.journals.portrait_diagnostics import PortraitValidationError
from src.domains.journals.schemas import JournalActionFields
from src.domains.shared.portrait_sources import PORTRAIT_SOURCE_KEYS
from src.infrastructure.llm.providers.token_counter import OpenAITokenCounter


class MaintenanceAction(JournalActionFields):
    """Merge is one explicit operation, never an update/delete approximation."""

    model_config = ConfigDict(extra="forbid")
    action: Literal["create", "update", "delete", "merge"]
    merge_source_ids: list[UUID] = Field(default_factory=list, max_length=20)
    support_ids: list[UUID] = Field(default_factory=list, max_length=20)


class PortraitSupport(BaseModel):
    """An exact complete authorized passage, retained privately as a proof."""

    model_config = ConfigDict(extra="forbid")
    source: str
    quote: str | None = Field(
        None,
        min_length=1,
        max_length=PORTRAIT_SUPPORT_QUOTE_MAX_CHARS,
        exclude_if=lambda value: value is None,
    )
    item_id: str | None = Field(
        None, min_length=1, max_length=100, exclude_if=lambda value: value is None
    )

    @model_validator(mode="after")
    def exactly_one_selector(self) -> Self:
        if (self.quote is None) == (self.item_id is None):
            raise ValueError("portrait support requires exactly one quote or item_id")
        return self

    @field_validator("source")
    @classmethod
    def canonical_source(cls, value: str) -> str:
        if value.startswith("journal:"):
            return f"journal:{UUID(value.removeprefix('journal:'))}"
        if value not in PORTRAIT_SOURCE_KEYS:
            raise ValueError("unknown portrait source")
        return value


_TECHNICAL_STYLE = re.compile(
    r"\b(?:WHEN|DO|BECAUSE)\b|```|</?[A-Za-z][^>]*>|"
    r"\b[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\b|"
    r"\b\d{4}-\d{2}-\d{2}\b|"
    r"\bpi_[0-9a-fA-F]{64}\b|\bportrait_item_id\b|"
    r"\b(?:ev|co|conf|uses|revision|char_count|injection_count)\s*[=:]|"
    r"\[(?:self_reflection|ideas_analyses|user_observations|learnings|memories|"
    r"interests|habits|relation_debriefs)(?:\]|[;: ])|"
    r"(?m:^\s*(?:[-*#>]\s|\d+[.)]\s))"
)


class PortraitClaim(BaseModel):
    """A self-contained natural paragraph; evidence is never its public text."""

    model_config = ConfigDict(extra="forbid")
    facet: Literal["context", "posture", "focus", "interaction", "uncertainty"]
    text: str = Field(min_length=1, max_length=2000)
    supports: list[PortraitSupport] = Field(min_length=1, max_length=8)
    in_brief: bool = False

    @field_validator("text")
    @classmethod
    def natural_text(cls, value: str) -> str:
        value = value.strip()
        if not value or _TECHNICAL_STYLE.search(value):
            raise ValueError("portrait requires natural prose without technical metadata")
        return value

    @model_validator(mode="after")
    def proofs_are_not_the_prose(self) -> Self:
        for support in self.supports:
            if support.quote is None:
                continue
            quote = support.quote.strip()
            if self.text in (quote, quote.removeprefix("- ").strip()):
                raise ValueError("exact proofs belong in metadata, not the portrait text")
        return self


class MaintenanceOutput(BaseModel):
    actions: list[MaintenanceAction] = Field(default_factory=list)
    portrait_claims: list[PortraitClaim] | None = Field(None, max_length=32)
    valid: bool = False
    error: str | None = None


class _MaintenancePayload(BaseModel):
    """Provider input has no authority over internal validation status."""

    model_config = ConfigDict(extra="forbid")
    actions: list[MaintenanceAction]
    portrait_claims: list[PortraitClaim] | None = Field(None, max_length=32)


_UPDATE_FIELDS = ("theme", "title", "content", "mood", "search_hints", "confidence", "level")


def _validate_create(action: MaintenanceAction) -> None:
    if action.entry_id is not None:
        raise ValueError("create cannot name an existing entry")
    if not (action.theme and action.title and action.content and action.content.strip()):
        raise ValueError("incomplete create")


def _validate_operation_fields(action: MaintenanceAction) -> None:
    if action.evidence_outcome is not None:
        raise ValueError("maintenance cannot invent a reaction event")
    if action.action == "create":
        _validate_create(action)
    elif action.entry_id is None:
        raise ValueError("missing entry_id")
    has_mutation = any(getattr(action, field) is not None for field in _UPDATE_FIELDS)
    if action.action == "update" and not has_mutation:
        raise ValueError("empty update")
    if action.action in ("delete", "merge") and (has_mutation or action.support_ids):
        raise ValueError("delete and merge cannot carry ignored mutation fields")
    if action.action == "merge" and not action.merge_source_ids:
        raise ValueError("merge requires source IDs")
    if action.action != "merge" and action.merge_source_ids:
        raise ValueError("only merge can name merge sources")


def _validate_action_ids(actions: list[MaintenanceAction]) -> None:
    seen: set[str] = set()
    for action in actions:
        _validate_operation_fields(action)
        ids = ([action.entry_id] if action.entry_id else []) + [
            str(identifier) for identifier in action.merge_source_ids
        ]
        if len(set(ids)) != len(ids) or seen.intersection(ids):
            raise ValueError("repeated UUID across maintenance operations")
        seen.update(ids)


def _validation_summary(exc: ValidationError) -> str:
    """Bounded schema diagnostics never include private provider input or context."""
    errors = exc.errors(include_input=False, include_context=False, include_url=False)[:8]
    safe = [{"loc": error["loc"], "type": error["type"], "msg": error["msg"]} for error in errors]
    return json.dumps(safe, ensure_ascii=False)[:4096]


def parse_maintenance_output(raw: str) -> MaintenanceOutput:
    """Reject malformed, ambiguous or incomplete output as a whole."""
    try:
        payload = load_complete_json(raw)
        if isinstance(payload, list):
            payload = {"actions": payload}  # legacy maintenance only
        if not isinstance(payload, dict) or not isinstance(payload.get("actions"), list):
            raise ValueError("actions must be explicitly supplied")
        output = _MaintenancePayload.model_validate(payload)
        _validate_action_ids(output.actions)
        return MaintenanceOutput(
            actions=output.actions, portrait_claims=output.portrait_claims, valid=True
        )
    except ValidationError as exc:
        return MaintenanceOutput(error=_validation_summary(exc))
    except (ValueError, TypeError) as exc:
        return MaintenanceOutput(error=str(exc))


def _journal_proof(support: PortraitSupport, journal: dict[str, JournalEntry]) -> dict[str, Any]:
    entry = journal.get(support.source.removeprefix("journal:"))
    quote = entry.content if entry is not None and support.item_id is not None else support.quote
    if (
        entry is None
        or entry.content != quote
        or (support.item_id is not None and support.item_id != journal_item_id(entry))
        or entry.level not in ("L1", "L2", "L3")
        or entry.confidence not in ("medium", "high")
        or entry.contradiction_count > 0
    ):
        raise ValueError("portrait passage is not a complete current operational rule")
    return {
        "source": support.source,
        "quote": quote,
        "revision": entry.revision,
        "theme": entry.theme,
        "level": entry.level,
        "confidence": entry.confidence,
        "evidence_count": entry.evidence_count,
        "contradiction_count": entry.contradiction_count,
    }


def _section_proof(support: PortraitSupport, sections: dict[str, str]) -> dict[str, Any]:
    lines = [
        item.quote
        for item in eligible_source_items(support.source, sections.get(support.source, ""))
    ]
    quote = support.quote
    if support.item_id is not None:
        quote = _resolve_source_reference(support, sections)
    assert quote is not None
    if quote not in lines or not quote.startswith("- ") or "…" in quote:
        raise PortraitValidationError(
            "portrait passage is not a complete authorized source item",
            {
                "phase": "source_proof",
                "source": support.source,
                "exact_item": quote in lines,
                "has_item_prefix": quote.startswith("- "),
                "contains_ellipsis": "…" in quote,
            },
        )
    return {"source": support.source, "quote": quote}


def _resolve_source_reference(support: PortraitSupport, sections: dict[str, str]) -> str:
    assert support.item_id is not None
    try:
        return resolve_source_item(
            support.source, support.item_id, sections.get(support.source, "")
        )
    except ValueError as exc:
        raise PortraitValidationError(
            "portrait reference is not a complete authorized source item",
            {
                "phase": "source_proof",
                "source": support.source,
                "selector_kind": "item_id",
                "unknown_reference": True,
            },
        ) from exc


@dataclass(frozen=True)
class SupportedPortraitClaim:
    claim: PortraitClaim
    evidence: list[dict[str, Any]]
    provisional: bool


def _supported_claim(
    claim: PortraitClaim, journal: dict[str, JournalEntry], sections: dict[str, str]
) -> SupportedPortraitClaim:
    seen: set[tuple[str, str]] = set()
    evidence: list[dict[str, Any]] = []
    for support_index, support in enumerate(claim.supports):
        try:
            proof = (
                _journal_proof(support, journal)
                if support.source.startswith("journal:")
                else _section_proof(support, sections)
            )
        except PortraitValidationError as exc:
            exc.details = {**exc.details, "support_index": support_index}
            raise
        identity = (proof["source"], proof["quote"])
        if identity in seen:
            raise ValueError("duplicate portrait support")
        seen.add(identity)
        if claim.text in (proof["quote"], proof["quote"].removeprefix("- ").strip()):
            raise ValueError("exact proofs belong in metadata, not the portrait text")
        evidence.append(proof)
    provisional = any(
        proof.get("level") in ("L2", "L3") and proof.get("confidence") != "high"
        for proof in evidence
    )
    if provisional and claim.facet != "uncertainty":
        raise ValueError("provisional syntheses require an uncertainty facet")
    canonical = claim.model_copy(
        update={
            "supports": [
                PortraitSupport(source=proof["source"], quote=proof["quote"]) for proof in evidence
            ]
        }
    )
    return SupportedPortraitClaim(canonical, evidence, provisional)


def validate_portrait_claims(
    claims: list[PortraitClaim], entries: list[JournalEntry], sections: dict[str, str]
) -> list[SupportedPortraitClaim]:
    """Validate complete current proofs, without claiming semantic entailment."""
    journal = {str(entry.id): entry for entry in entries}
    seen: set[str] = set()
    validated: list[SupportedPortraitClaim] = []
    for claim_index, claim in enumerate(claims):
        if claim.text in seen:
            raise ValueError("duplicate portrait paragraph")
        seen.add(claim.text)
        try:
            validated.append(_supported_claim(claim, journal, sections))
        except PortraitValidationError as exc:
            exc.details = {**exc.details, "claim_index": claim_index}
            raise
    return validated


def render_exact_evidence(
    claims: list[PortraitClaim], entries: list[JournalEntry], sections: dict[str, str]
) -> list[dict[str, Any]]:
    """Stable indexed evidence for independent review and its publication receipt."""
    return [
        {
            "index": index,
            "facet": supported.claim.facet,
            "text": supported.claim.text,
            "supports": supported.evidence,
            "provisional": supported.provisional,
        }
        for index, supported in enumerate(validate_portrait_claims(claims, entries, sections))
    ]


def _fits_budget(
    counter: OpenAITokenCounter, passages: list[str], text: str, max_tokens: int
) -> bool:
    return counter.count("\n\n".join([*passages, text]), "gpt-4o") <= max_tokens


def grounded_portraits(
    claims: list[PortraitClaim],
    entries: list[JournalEntry],
    sections: dict[str, str],
    *,
    published: list[PortraitClaim] | None = None,
) -> tuple[str | None, str | None]:
    """Validate all proofs, then pack whole natural paragraphs under both budgets.

    The proxy is the application's offline OpenAI token counter, not a claim
    about the supplier's billing tokenizer. Native consumers enforce their own
    whole rendered-frame budget as well.
    """
    full: list[str] = []
    brief: list[str] = []
    counter = OpenAITokenCounter()
    for supported in validate_portrait_claims(claims, entries, sections):
        claim, text = supported.claim, supported.claim.text
        if _fits_budget(counter, full, text, settings.journal_portrait_full_max_tokens):
            full.append(text)
            in_brief = claim.in_brief and _fits_budget(
                counter, brief, text, settings.journal_portrait_brief_max_tokens
            )
            if in_brief:
                brief.append(text)
            if published is not None:
                published.append(claim.model_copy(update={"in_brief": in_brief}))
    return "\n\n".join(full) or None, "\n\n".join(brief) or None
