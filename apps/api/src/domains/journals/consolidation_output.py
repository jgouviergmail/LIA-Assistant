"""Natural portrait claims with exact private evidence, admitted claim by claim.

Code verifies what can be verified without a second model (ADR-343 § 6): every
support resolves in THIS snapshot, no duplicate, no claim resting on an entry
the batch changes, no technical metadata, figure, date, address or name taken
from the evidence in the prose, no paragraph that restates one cited item. A
claim that fails is DROPPED and logged, never fatal to the batch; a repairable
fault (a duplicate support, a support past the cap) is repaired (ADR-184).
"""

import json
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from src.domains.journals.models import JournalEntry
from src.domains.journals.output_json import load_complete_json
from src.domains.journals.portrait_catalogue import (
    PORTRAIT_SUPPORT_QUOTE_MAX_CHARS,
    CatalogueIndex,
    journal_item_id,
)
from src.domains.journals.portrait_diagnostics import PortraitValidationError
from src.domains.journals.schemas import JournalActionFields
from src.domains.shared.portrait_sources import PORTRAIT_SOURCE_KEYS
from src.infrastructure.observability.logging import get_logger

#: How many items one reading may cite. A cross-source analysis of a record of
#: sixty memories rests on many; eight forced one-item paraphrases (2026-10-12 b).
#: Past the cap the tail is CUT (a repair), never the batch refused.
PORTRAIT_CLAIM_SUPPORTS_MAX = 40

#: How many claims one compilation may propose; the tail is cut and counted.
PORTRAIT_CLAIMS_MAX = 32

#: A paragraph whose content words are mostly those of ONE cited item restates it.
PORTRAIT_RESTATEMENT_OVERLAP = 0.5

_WORD = re.compile(r"[^\W\d_]{4,}", re.UNICODE)
_ITEM_DECORATION = re.compile(r"^- (?:\[[^\]]*\]\s*)*|\s*\([^()]*\)\s*$")
_LABELS = re.compile(r"^- (?:\[[^\]]*\]\s*)*")
_TRAILING_PARENTHETICAL = re.compile(r"\(([^()]*)\)\s*$")

#: Function words of four letters or more in the six interface languages, left out of
#: every content-word comparison (the admission's and the measurement harness's).
PORTRAIT_STOP_WORDS: frozenset[str] = frozenset(
    "avec dans pour cette cela ceux elle elles leur leurs mais plus sans sont vers vous "
    "notre votre comme très tout tous toute toutes donc ainsi entre aussi encore chez "
    "quand lors chaque autre autres même mêmes être avoir fait faire "
    "this that with from have been were their which what when they them than then also "
    "into over only such some will would about after before "
    "aber auch dann dass dein deine dieser diese dieses durch eine einem einen einer eines "
    "nach nicht noch oder sein seine sich sind über unter wenn wird "
    "para pero como cada todo todos esta este esto ellos ellas sobre desde hasta cuando "
    "anche come dalla dalle dello della delle nella nelle però quando questa questo sono "
    "tutto tutti sopra sotto".split()
)


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


logger = get_logger(__name__)

_TECHNICAL_STYLE = re.compile(
    r"\d|@|://|"
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
    #: The seven analytical facets of the v1.45 contract (ADR-343, 2026-10-12 b).
    facet: Literal["posture", "focus", "context", "rhythm", "tension", "interaction", "uncertainty"]
    text: str = Field(min_length=1, max_length=2000)
    #: A reading cites EVERY item it rests on: the cap bounds abuse, never an analysis.
    supports: list[PortraitSupport] = Field(min_length=1, max_length=PORTRAIT_CLAIM_SUPPORTS_MAX)
    placement: Literal["full", "brief"] = "full"

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
    portrait_claims: list[PortraitClaim] | None = Field(None, max_length=PORTRAIT_CLAIMS_MAX)
    #: Claims the parser could not read (codes only), counted with the drops.
    rejected_claims: list[dict[str, Any]] = Field(default_factory=list)
    #: Actions the parser or the snapshot refused, by proposal index (codes or a
    #: fixed reason, never the text they carried).
    rejected_actions: list[dict[str, Any]] = Field(default_factory=list)
    valid: bool = False
    error: str | None = None


class _MaintenancePayload(BaseModel):
    """Provider input has no authority over internal validation status.

    The claims and the actions are read as raw objects: ONE unreadable item must
    not void the others (review 2026-10-12 b for the claims — a 41st support, a
    figure in a sentence, an unknown facet used to refuse the whole paid run;
    2026-10-13 for the actions — a support cited by its portrait id did).
    """

    model_config = ConfigDict(extra="forbid")
    actions: list[Any]
    portrait_claims: list[Any] | None = None


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


def _named_entries(action: MaintenanceAction) -> list[str]:
    """Every entry an action writes: its own, and a merge's absorbed sources."""
    return ([action.entry_id] if action.entry_id else []) + [
        str(identifier) for identifier in action.merge_source_ids
    ]


def _parse_actions(raw: list[Any]) -> tuple[list[MaintenanceAction], list[dict[str, Any]]]:
    """Read the actions one by one: an unreadable one is rejected and counted, never fatal.

    Two actions writing one entry have no order the service could trust, so every
    action naming a shared entry is rejected with it (the prompt's « single action
    per UUID »). A rejection carries the proposal index and the error codes or the
    rule's fixed reason — never the text the action carried.
    """
    readable: list[tuple[int, MaintenanceAction]] = []
    rejected: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        try:
            action = MaintenanceAction.model_validate(item)
            _validate_operation_fields(action)
        except ValidationError as exc:  # before ValueError: it is one
            codes = sorted({str(error["type"]) for error in exc.errors()})
            rejected.append(
                {"action_index": index, "reason": "unreadable maintenance action", "codes": codes}
            )
            continue
        except ValueError as exc:
            rejected.append({"action_index": index, "reason": str(exc)})
            continue
        readable.append((index, action))
    counts = Counter(entry for _, action in readable for entry in set(_named_entries(action)))
    kept: list[MaintenanceAction] = []
    for index, action in readable:
        named = _named_entries(action)
        if len(set(named)) != len(named):
            rejected.append({"action_index": index, "reason": "entry named twice by one action"})
        elif any(counts[entry] > 1 for entry in named):
            rejected.append(
                {"action_index": index, "reason": "entry named by several maintenance actions"}
            )
        else:
            kept.append(action)
    return kept, sorted(rejected, key=lambda item: int(item["action_index"]))


def _validation_summary(exc: ValidationError) -> str:
    """Bounded schema diagnostics never include private provider input or context."""
    errors = exc.errors(include_input=False, include_context=False, include_url=False)[:8]
    safe = [{"loc": error["loc"], "type": error["type"], "msg": error["msg"]} for error in errors]
    return json.dumps(safe, ensure_ascii=False)[:4096]


def parse_maintenance_output(raw: str) -> MaintenanceOutput:
    """Read the answer item by item; refuse it whole only when nothing of it can be used.

    Malformed or ambiguous JSON is refused whole. An unreadable claim or action is
    rejected alone (``rejected_claims``, ``rejected_actions``); an answer made of
    actions alone, every one of them rejected, is invalid — nothing of it can be
    used, and reporting it as a no-op would consume the work it left undone.
    """
    try:
        payload = load_complete_json(raw)
        if isinstance(payload, list):
            payload = {"actions": payload}  # legacy maintenance only
        if not isinstance(payload, dict) or not isinstance(payload.get("actions"), list):
            raise ValueError("actions must be explicitly supplied")
        output = _MaintenancePayload.model_validate(payload)
        actions, rejected_actions = _parse_actions(output.actions)
        claims, rejected = _parse_claims(output.portrait_claims)
        if rejected_actions and not actions and claims is None:
            raise ValueError("every maintenance action was unreadable")
        return MaintenanceOutput(
            actions=actions,
            portrait_claims=claims,
            rejected_claims=rejected,
            rejected_actions=rejected_actions,
            valid=True,
        )
    except ValidationError as exc:
        return MaintenanceOutput(error=_validation_summary(exc))
    except (ValueError, TypeError) as exc:
        return MaintenanceOutput(error=str(exc))


def _repair_claim(item: Any) -> Any:
    """Mechanical repairs before validation (ADR-184): duplicate supports, the cap."""
    if not isinstance(item, dict) or not isinstance(item.get("supports"), list):
        return item
    kept: list[Any] = []
    seen: set[str] = set()
    for support in item["supports"]:
        key = json.dumps(support, sort_keys=True, ensure_ascii=False, default=str)
        if key in seen:
            continue
        seen.add(key)
        kept.append(support)
    return {**item, "supports": kept[:PORTRAIT_CLAIM_SUPPORTS_MAX]}


def _parse_claims(
    raw: list[Any] | None,
) -> tuple[list[PortraitClaim] | None, list[dict[str, Any]]]:
    """Read the claims one by one: an unreadable one is rejected and counted, never fatal."""
    if raw is None:
        return None, []
    claims: list[PortraitClaim] = []
    rejected: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        if index >= PORTRAIT_CLAIMS_MAX:
            rejected.append({"claim_index": index, "reason": "beyond the claims cap"})
            continue
        try:
            claims.append(PortraitClaim.model_validate(_repair_claim(item)))
        except ValidationError as exc:
            codes = sorted({str(error["type"]) for error in exc.errors()})
            rejected.append(
                {"claim_index": index, "reason": "unreadable portrait claim", "codes": codes}
            )
    return claims, rejected


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


def _section_proof(support: PortraitSupport, index: CatalogueIndex) -> dict[str, Any]:
    lines = index.items(support.source)
    quote = support.quote
    if support.item_id is not None:
        quote = _resolve_source_reference(support, index)
    assert quote is not None
    if quote not in lines or not quote.startswith("- "):
        raise PortraitValidationError(
            "portrait passage is not a complete authorized source item",
            {
                "phase": "source_proof",
                "source": support.source,
                "exact_item": quote in lines,
                "has_item_prefix": quote.startswith("- "),
            },
        )
    return {"source": support.source, "quote": quote}


def _resolve_source_reference(support: PortraitSupport, index: CatalogueIndex) -> str:
    assert support.item_id is not None
    try:
        return index.resolve(support.source, support.item_id)
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
    claim: PortraitClaim, journal: dict[str, JournalEntry], index: CatalogueIndex
) -> SupportedPortraitClaim:
    seen: set[tuple[str, str]] = set()
    evidence: list[dict[str, Any]] = []
    for support_index, support in enumerate(claim.supports):
        try:
            proof = (
                _journal_proof(support, journal)
                if support.source.startswith("journal:")
                else _section_proof(support, index)
            )
        except PortraitValidationError as exc:
            exc.details = {**exc.details, "support_index": support_index}
            raise
        identity = (proof["source"], proof["quote"])
        if identity in seen:
            continue  # the same item cited twice is one support (a repair, ADR-184)
        seen.add(identity)
        if claim.text in (proof["quote"], proof["quote"].removeprefix("- ").strip()):
            raise ValueError("exact proofs belong in metadata, not the portrait text")
        evidence.append(proof)
    if _restates_one_item(claim.text, evidence):
        raise ValueError("portrait paragraph restates one cited item")
    if _names_from_evidence(claim.text, evidence):
        raise ValueError("portrait paragraph carries a name taken from the evidence")
    provisional = any(
        proof.get("level") in ("L2", "L3") and proof.get("confidence") != "high"
        for proof in evidence
    )
    # A provisional synthesis belongs to the uncertainty facet: the facet is
    # metadata, REPAIRED here (ADR-184) — the prompt asks for cautious words there,
    # and refusing the whole batch for a label lost three paid portraits of three
    # on the measured corpus (2026-10-12).
    canonical = claim.model_copy(
        update={
            "facet": "uncertainty" if provisional else claim.facet,
            "supports": [
                PortraitSupport(source=proof["source"], quote=proof["quote"]) for proof in evidence
            ],
        }
    )
    return SupportedPortraitClaim(canonical, evidence, provisional)


def validate_portrait_claims(
    claims: list[PortraitClaim],
    entries: list[JournalEntry],
    sections: dict[str, str],
    *,
    dropped: list[dict[str, Any]] | None = None,
) -> list[SupportedPortraitClaim]:
    """Validate complete current proofs, without claiming semantic entailment.

    A claim whose proof cannot be resolved in this snapshot — an unknown or
    ambiguous reference, a passage that is not a current operational rule, a
    duplicate paragraph, a paragraph restating one item or carrying a name from
    the evidence — is DROPPED and counted, never fatal to the batch: refusing the
    whole portrait for one reference the model got wrong lost every paid portrait
    on the measured corpus (2026-10-12). The maintenance actions keep their
    all-or-nothing contract.

    Args:
        claims: The claims the model returned, in its order.
        entries: The active journal entries of the snapshot.
        sections: The captured source sections.
        dropped: When given, receives ``{claim_index, reason}`` per dropped claim.

    Returns:
        The claims whose every proof resolved, in the model's order.
    """
    journal = {str(entry.id): entry for entry in entries}
    index = CatalogueIndex(sections)
    seen: set[str] = set()
    validated: list[SupportedPortraitClaim] = []
    for claim_index, claim in enumerate(claims):
        if claim.text in seen:
            _drop(dropped, claim_index, "duplicate portrait paragraph")
            continue
        try:
            validated.append(_supported_claim(claim, journal, index))
        except PortraitValidationError as exc:
            _drop(dropped, claim_index, str(exc), **exc.details)
            continue
        except ValueError as exc:
            _drop(dropped, claim_index, str(exc))
            continue
        # Only a RESOLVED paragraph bars a later identical one: a twin whose own
        # proofs resolve must not pay for a first copy whose proofs did not.
        seen.add(claim.text)
    return validated


def content_words(text: str) -> set[str]:
    """Words of four letters or more, lower-cased, function words left out.

    The ONE reading of « the words of a text » the admission and the measurement
    harness share, so a restatement is the same thing measured and enforced.
    """
    return {word.lower() for word in _WORD.findall(text) if word.lower() not in PORTRAIT_STOP_WORDS}


def item_words(quote: str) -> set[str]:
    """The content words of a rendered item, its labels and trailing parenthetical removed."""
    return content_words(_ITEM_DECORATION.sub("", quote))


def _restates_one_item(text: str, evidence: list[dict[str, Any]]) -> bool:
    """Whether the paragraph is mostly the words of ONE cited item (a paraphrase)."""
    words = content_words(text)
    if len(words) < 4:
        return False
    return any(
        len(words & item_words(str(proof["quote"]))) / len(words) >= PORTRAIT_RESTATEMENT_OVERLAP
        for proof in evidence
    )


def _names_from_evidence(text: str, evidence: list[dict[str, Any]]) -> set[str]:
    """The person names the cited items carry STRUCTURALLY that the prose repeats.

    A name is certain in two positions only: the head of a relationship debrief (the
    line opens on the person's name) and the counterparty of an open loop (after the
    direction, inside the trailing parenthetical). Nothing is guessed from capitals:
    every German noun is capitalised, so are the English weekdays, and a guard reading
    them as names would drop a legitimate reading on every turn. A name in a memory's
    free text is the prompt's rule — measured, seven readings of seven carried none
    (2026-10-12) — never the admission's.
    """
    names: set[str] = set()
    for proof in evidence:
        quote = _LABELS.sub("", str(proof["quote"]))
        if proof["source"] == "relation_debriefs":
            names.update(_name_tokens(quote.split(" (", 1)[0]))
        elif proof["source"] == "open_loops":
            tail = _TRAILING_PARENTHETICAL.search(quote)
            if tail is not None:
                names.update(_name_tokens(tail.group(1).split(";", 1)[0].partition(", ")[2]))
    return {name for name in names if re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", text)}


def _name_tokens(name: str) -> set[str]:
    """The capitalised words of a displayed name (« l'ébéniste » names nobody)."""
    tokens = (token.strip("\"'«».,;:()") for token in name.split())
    return {token for token in tokens if len(token) >= 2 and token[:1].isupper()}


def _drop(
    dropped: list[dict[str, Any]] | None, claim_index: int, reason: str, **details: Any
) -> None:
    if dropped is not None:
        dropped.append({"claim_index": claim_index, "reason": reason, **details})


def changed_entry_ids(output: MaintenanceOutput) -> set[str]:
    """Every entry the batch PROPOSES to touch (the settlement narrows it to what applied)."""
    changed = {action.entry_id for action in output.actions if action.entry_id}
    changed.update(
        str(identifier) for action in output.actions for identifier in action.merge_source_ids
    )
    return changed


def _unchanged_supports(
    changed: set[str], claims: list[PortraitClaim], dropped: list[dict[str, Any]]
) -> list[PortraitClaim]:
    """Keep the claims whose journal supports this batch leaves untouched; count the rest."""
    kept: list[PortraitClaim] = []
    for index, claim in enumerate(claims):
        if any(
            support.source.removeprefix("journal:") in changed
            for support in claim.supports
            if support.source.startswith("journal:")
        ):
            dropped.append(
                {
                    "claim_index": index,
                    "reason": "Portrait supports must survive maintenance unchanged",
                }
            )
            continue
        kept.append(claim)
    return kept


def admit_portrait_claims(
    output: MaintenanceOutput,
    entries: list[JournalEntry],
    sections: dict[str, str],
    *,
    changed: set[str] | None = None,
) -> list[PortraitClaim]:
    """The readings this snapshot can publish: proven, deduplicated, untouched by the batch.

    Every structurally valid claim is admitted; a claim the snapshot cannot prove, a
    duplicate, or one resting on an entry this batch changes is dropped and logged
    (codes only). No model judges the readings any more (ADR-343, 2026-10-12 b):
    measured, a semantic reviewer rejected 70 to 80 % of grounded analytical
    readings as « unsupported » whatever its instructions — a verifier demands a
    literal proof, an analysis has none by definition. What refuses invention is
    structural: a reading cites items of this snapshot or it is not published.

    Args:
        output: The parsed proposal (its unreadable claims already counted).
        entries: The snapshot's active entries.
        sections: The snapshot's source sections.
        changed: The entries this batch actually CHANGED — the settlement knows
            what applied; left unset, every proposed action counts (a zero-effect
            update would then drop the claims citing its entry for nothing).
    """
    claims = output.portrait_claims or []
    dropped: list[dict[str, Any]] = list(output.rejected_claims)
    resolved = [
        supported.claim
        for supported in validate_portrait_claims(claims, entries, sections, dropped=dropped)
    ]
    touched = changed_entry_ids(output) if changed is None else changed
    admitted = _unchanged_supports(touched, resolved, dropped)
    if dropped:
        logger.warning(
            "journal_portrait_claims_dropped",
            proposed=len(claims) + len(output.rejected_claims),
            dropped=len(dropped),
            reasons=sorted({str(item["reason"]) for item in dropped}),
        )
    return admitted


def grounded_portraits(
    claims: list[PortraitClaim],
    entries: list[JournalEntry],
    sections: dict[str, str],
    *,
    published: list[PortraitClaim] | None = None,
) -> tuple[str | None, str | None]:
    """Validate all proofs, then publish every proven claim whole, each format from its own.

    A ``full`` claim goes to the full portrait, a ``brief`` claim to the brief:
    the brief is a synthesis of its own, never a prefix of the full (2026-10-12).
    The budgets the settings hold are the TARGETS the prompt states to the
    model, never a clamp applied here: an admitted facet is never dropped for a
    token count — the synthesis is complete (owner rule 2026-10-12, ADR-292's
    « a stated budget, not a clamp »). Native consumers enforce their own whole
    rendered-frame budget where a frame has one.
    """
    full: list[str] = []
    brief: list[str] = []
    for supported in validate_portrait_claims(claims, entries, sections):
        claim = supported.claim
        (brief if claim.placement == "brief" else full).append(claim.text)
        if published is not None:
            published.append(claim)
    return "\n\n".join(full) or None, "\n\n".join(brief) or None
