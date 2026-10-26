"""Qualify authorized, already-selected items before their first publication."""

from collections.abc import Mapping, Sequence
from typing import Literal
from uuid import UUID, uuid4

from pydantic import JsonValue, TypeAdapter, ValidationError

from src.core.constants import JEV_CLASSIFICATION_MAX_ITEMS
from src.core.content_classification import ContentClassification, EvidenceScope
from src.core.content_source import content_source_binding as source_binding
from src.core.context import current_tracker
from src.domains.agents.data_registry.models import RegistryItem, RegistryItemType
from src.domains.agents.services.qualification.contracts import (
    ClassificationObservation,
)
from src.domains.agents.services.qualification.service import qualify_observations
from src.domains.agents.tools.output import UnifiedToolOutput
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)
_JSON: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)
_EMAIL_FIELDS = (
    "from",
    "to",
    "subject",
    "date",
    "internalDate",
    "snippet",
    "body",
    "digest",
    "gist",
    "key_points",
    "actions",
    "summary",
    "body_part",
    "body_parts",
    # The unified vocabulary's name (ADR-287); ``replyTo`` matched no provider,
    # so a reply-to differing from the sender never reached the judgment.
    "reply_to",
)
_EVENT_FIELDS = (
    "summary",
    "description",
    "start",
    "end",
    "location",
    "attendees",
    "organizer",
)
# Calendar entries the provider itself types; ``default`` says nothing.
_UNTYPED_EVENT = "default"
_KINDS: tuple[tuple[RegistryItemType, Literal["email", "event"]], ...] = (
    (RegistryItemType.EMAIL, "email"),
    (RegistryItemType.EVENT, "event"),
)


def _scope(payload: Mapping[str, object], kind: Literal["email", "event"]) -> EvidenceScope:
    if kind == "event":
        return "event"
    if payload.get("body"):
        return "partial_body" if payload.get("body_parts", 1) != 1 else "body"
    if payload.get("gist") or payload.get("digest") or payload.get("summary"):
        return "summary"
    return "snippet" if payload.get("snippet") else "metadata"


def _provider_facts(
    payload: Mapping[str, object], kind: Literal["email", "event"]
) -> dict[str, JsonValue]:
    """What the provider already asserted and the source fields alone hide.

    Measured on a production-shaped corpus (2026-10-25): without its labels a
    message the provider filed under promotions read as spam, and an
    appointment's own type (a birthday, a focus block) was never seen.
    """
    facts: dict[str, JsonValue] = {}
    if kind == "email":
        labels = payload.get("labelIds")
        if isinstance(labels, list) and labels:
            facts["labels"] = [str(label) for label in labels]
        return facts
    event_type = payload.get("eventType")
    if isinstance(event_type, str) and event_type and event_type != _UNTYPED_EVENT:
        facts["event_type"] = event_type
    if payload.get("hangoutLink") or payload.get("conferenceData"):
        facts["video_call"] = True
    if payload.get("recurringEventId") or payload.get("recurrence"):
        facts["recurring"] = True
    return facts


def observation(
    identity: str,
    payload: Mapping[str, object],
    *,
    kind: Literal["email", "event"],
    container: str = "",
) -> ClassificationObservation | None:
    evidence: dict[str, JsonValue] = {}
    try:
        for field in _EMAIL_FIELDS if kind == "email" else _EVENT_FIELDS:
            if field in payload:
                evidence[field] = _JSON.validate_python(payload[field])
        evidence.update(_provider_facts(payload, kind))
        return ClassificationObservation(
            identity=identity,
            kind=kind,
            item_id=str(payload.get("id") or identity),
            container_id=str(payload.get("calendar_id") or container),
            occurrence=str(payload.get("originalStartTime") or ""),
            revision=str(payload.get("etag") or payload.get("updated") or ""),
            evidence_scope=_scope(payload, kind),
            evidence=evidence,
        )
    except ValidationError:
        return None


async def classify_selected(
    *,
    records: Sequence[Mapping[str, object]],
    kind: Literal["email", "event"],
    user_id: UUID,
    provider: str,
    binding: str,
    timezone: str,
    container: str = "",
) -> dict[str, ContentClassification]:
    values = [
        value
        for index, payload in enumerate(records[:JEV_CLASSIFICATION_MAX_ITEMS])
        if (value := observation(str(index), payload, kind=kind, container=container))
    ]
    return await _qualify(
        values, user_id=user_id, provider=provider, binding=binding, timezone=timezone
    )


async def _qualify(
    values: list[ClassificationObservation],
    *,
    user_id: UUID,
    provider: str,
    binding: str,
    timezone: str,
) -> dict[str, ContentClassification]:
    if not binding or not provider or not values:
        return {}
    tracker = current_tracker.get()
    run_id = tracker.run_id if tracker is not None and tracker.user_id == user_id else str(uuid4())
    try:
        return await qualify_observations(
            user_id=user_id,
            provider=provider,
            source_scope=binding,
            observations=values,
            run_id=run_id,
            timezone=timezone,
        )
    except Exception as exc:
        # Optional labels cannot turn a successful authorized read into a failed tool.
        logger.warning("content_classification_publication_failed", error_type=type(exc).__name__)
        return {}


async def qualify_tool_output(
    output: UnifiedToolOutput,
    *,
    client: object,
    provider: str,
    user_id: UUID,
    timezone: str,
) -> UnifiedToolOutput:
    for item_type, kind in _KINDS:
        items = [item for item in output.registry_updates.values() if item.type == item_type]
        for item in items:
            item.payload = {
                key: value for key, value in item.payload.items() if key != "classification"
            }
        values = [
            value
            for item in items[:JEV_CLASSIFICATION_MAX_ITEMS]
            if (value := observation(item.id, item.payload, kind=kind))
        ]
        annotations = await _qualify(
            values,
            user_id=user_id,
            provider=provider,
            binding=source_binding(client),
            timezone=timezone,
        )
        for item in items:
            if annotation := annotations.get(item.id):
                item.payload = {
                    **item.payload,
                    "classification": annotation.model_dump(mode="json"),
                }
        _publish_structured(output, items)
    return output


def _publish_structured(output: UnifiedToolOutput, items: Sequence[RegistryItem]) -> None:
    # Registry and structured_data are independent Pydantic copies: bind by the
    # native id, never by list position or the provider's raw MIME tree.
    annotations = {
        item.payload["id"]: item.payload.get("classification")
        for item in items
        if isinstance(item.payload.get("id"), str)
    }
    for key in ("emails", "events", "items"):
        records = output.structured_data.get(key)
        if not isinstance(records, list):
            continue
        for record in records:
            if (
                isinstance(record, dict)
                and isinstance(record.get("id"), str)
                and record["id"] in annotations
            ):
                record.pop("classification", None)
                if annotation := annotations[record["id"]]:
                    record["classification"] = annotation
