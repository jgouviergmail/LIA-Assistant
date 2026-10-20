"""Legacy health payload adapter over the common Shortcuts parser."""

from pydantic import JsonValue

from src.domains.ingestion.parser import IngestionBodyError, parse_body
from src.domains.ingestion.registry import IngestionResource, policy_for


class HealthSamplesBodyParseError(ValueError):
    """Raised when the ingestion body cannot be interpreted as a sample batch."""


def parse_samples_body(raw_body: bytes) -> list[dict[str, JsonValue]]:
    """Retain historical health shapes, dictionary filtering and route byte limit."""
    try:
        parsed = parse_body(
            raw_body,
            max_bytes=None,
            legacy_fields=policy_for(IngestionResource.HEALTH).legacy_fields,
        )
    except IngestionBodyError as exc:
        raise HealthSamplesBodyParseError(str(exc)) from None
    return [item for item in parsed.items if isinstance(item, dict)]
