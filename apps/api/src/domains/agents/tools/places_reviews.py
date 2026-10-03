"""One review projection for display, with bounded previews for the model."""

from collections.abc import Mapping

from src.domains.agents.display.values import rating_value


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def normalize_reviews(value: object) -> list[dict[str, object]]:
    """Preserve supplied attribution and full text; ignore unusable entries."""
    if not isinstance(value, list):
        return []
    entries = [_normalize(review) for review in value if isinstance(review, dict)]
    return sorted(entries, key=lambda entry: _text(entry["publish_time"]), reverse=True)


def _normalize(review: Mapping[str, object]) -> dict[str, object]:
    raw_text = review.get("text")
    text = _text(raw_text.get("text")) if isinstance(raw_text, dict) else _text(raw_text)
    author = review.get("authorAttribution")
    attribution = author if isinstance(author, dict) else {}
    original = review.get("originalText")
    return {
        "rating": rating_value(review.get("rating")),
        "text": text,
        "relative_time": _text(review.get("relativePublishTimeDescription")),
        "publish_time": _text(review.get("publishTime")),
        "author_name": _text(attribution.get("displayName")),
        "author_url": _text(attribution.get("uri")),
        "author_photo_url": _text(attribution.get("photoUri")),
        "source_url": _text(review.get("googleMapsUri")),
        "original_text": _text(original.get("text")) if isinstance(original, dict) else "",
        "report_url": _text(review.get("flagContentUri")),
        "visit_date": review.get("visitDate"),
    }
