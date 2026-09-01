"""Parse, strip and carry the per-turn tone annotation.

The tag travels IN BAND, appended after the answer:

    <lia_tone register="warm" intensity="0.6" accent="nod"/>

That is not a shortcut — it is the only shape that satisfies both halves of the
requirement. The signal has to be declared by the model that wrote the answer
(nothing else knows the register it chose) AND it has to land at the instant the
answer lands (the avatar reacts on completion, and a background pass loses that
race — production logs show the existing fire-and-forget appraisal missing it on
most turns). An in-band tag on the same generation costs no extra call and
arrives with the last token.

The pattern is deliberately identical to the psyche self-report tag, which has
carried this exact contract in production for months: fragments are stripped
from the SSE stream so nothing flashes on screen, and the full tag is removed
from the persisted content in the response node.

Three invariants:

- **Stripping is the same regex, wherever it runs.** Two independent strippers
  is how a tag ends up in a database row: the streaming filter and the content
  cleaner both use ``TONE_STREAMING_PATTERN`` / ``TONE_TAG_PATTERN`` from here.
- **A malformed tag is stripped anyway.** Returning the text untouched because
  the attributes did not parse would put raw markup in front of the user; the
  annotation is lost, the answer is not.
- **An unknown register yields NO annotation**, never a made-up one. A face
  nobody designed is worse than no reaction at all.
"""

from __future__ import annotations

import re
import time as _time
from dataclasses import dataclass
from typing import Any, Final

import structlog

from src.domains.agents.expressivity.vocabulary import (
    normalize_accent,
    normalize_intensity,
    normalize_register,
)

logger = structlog.get_logger(__name__)

# =============================================================================
# Tag patterns
# =============================================================================

#: The complete, well-formed tag. Mirrors ``PSYCHE_EVAL_TAG_PATTERN``.
TONE_TAG_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"<lia_tone\s+([^/]*?)\s*/>",
    re.DOTALL | re.IGNORECASE,
)

#: Attribute extraction inside the tag.
TONE_ATTR_PATTERN: Final[re.Pattern[str]] = re.compile(r'(\w+)\s*=\s*"([^"]*)"')

#: Fragment filter for streamed tokens: the tag arrives a few characters at a
#: time, so the streaming path must match a PARTIAL tag as well as a whole one.
TONE_STREAMING_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"<lia_tone[^>]*/?>?",
    re.IGNORECASE,
)

#: Cheap pre-test before running any regex on every streamed token.
TONE_TAG_MARKER: Final[str] = "<lia_tone"

# =============================================================================
# The annotation
# =============================================================================


@dataclass(frozen=True, slots=True)
class ToneAnnotation:
    """How THIS answer was said, as the model that wrote it declares.

    Attributes:
        register: One of ``TONE_REGISTERS`` — the speech act.
        intensity: Stage direction in [0, 1]; the renderer overplays it.
        accent: One of ``TONE_ACCENTS``; ``none`` most of the time.
    """

    register: str
    intensity: float
    accent: str

    def to_wire(self) -> dict[str, Any]:
        """Serialize for the SSE ``done`` metadata (frontend contract)."""
        return {
            "register": self.register,
            "intensity": self.intensity,
            "accent": self.accent,
        }


# =============================================================================
# Parsing
# =============================================================================

#: What an intensity becomes when the model omits it. Mid-range on purpose: a
#: register declared without a dial still deserves to be played.
DEFAULT_INTENSITY: Final[float] = 0.5


def parse_tone_annotation(content: str) -> tuple[ToneAnnotation | None, str]:
    """Extract the tone tag and return the content without it.

    Args:
        content: The model's raw final answer, tag included.

    Returns:
        ``(annotation, cleaned_content)``. The annotation is None when there is
        no tag or when its register is not in the vocabulary; the content is
        ALWAYS returned stripped of any tag that was present, because leaving
        markup in front of the user is the worse failure.
    """
    if TONE_TAG_MARKER not in content.lower():
        return None, content

    # The LAST tag is the declaration: the instruction says it comes after the
    # response, so anything earlier is the model QUOTING the marker — which a
    # self-documenting assistant does the moment a user asks about it. Every
    # occurrence is still stripped below; only the reading is disambiguated.
    matches = list(TONE_TAG_PATTERN.finditer(content))
    match = matches[-1] if matches else None
    if not match:
        # A marker without a well-formed tag: the model started one and did not
        # finish it. Sweep the fragment and carry on without an annotation.
        return None, TONE_STREAMING_PATTERN.sub("", content).strip()

    cleaned = TONE_TAG_PATTERN.sub("", content).strip()
    attributes = {
        key.lower(): value for key, value in TONE_ATTR_PATTERN.findall(match.group(1) or "")
    }
    register = normalize_register(attributes.get("register"))
    if register is None:
        return None, cleaned

    intensity = normalize_intensity(attributes.get("intensity"))
    return (
        ToneAnnotation(
            register=register,
            intensity=DEFAULT_INTENSITY if intensity is None else intensity,
            accent=normalize_accent(attributes.get("accent")),
        ),
        cleaned,
    )


def strip_tone_fragments(content: str) -> str:
    """Remove partial or complete tag text from ONE streamed token.

    Kept separate from :func:`parse_tone_annotation` because the streaming path
    has no use for the annotation — it runs on every token and must stay cheap.
    """
    return TONE_STREAMING_PATTERN.sub("", content)


# =============================================================================
# In-process per-run registry (written in the graph, popped by the SSE layer)
# =============================================================================
# Same shape and the same reasoning as ``store_psyche_summary``: the response
# node parses the tag deep inside the graph, and the ``done`` chunk is assembled
# in the API layer with no state in between.

_ANNOTATION_TTL_SECONDS: Final[int] = 300

_tone_annotations: dict[str, tuple[float, ToneAnnotation]] = {}


def store_tone_annotation(run_id: str, annotation: ToneAnnotation) -> None:
    """Hold the annotation until the ``done`` chunk is built."""
    _tone_annotations[run_id] = (_time.monotonic(), annotation)


def pop_tone_annotation(run_id: str) -> ToneAnnotation | None:
    """Take the annotation for a run, evicting anything stale first.

    A run that ends without its ``done`` chunk (an HITL interrupt, a dropped
    connection) leaves an entry behind; the TTL sweep is what keeps this from
    growing for the life of the process.
    """
    now = _time.monotonic()
    stale = [
        key for key, (at, _) in _tone_annotations.items() if now - at > _ANNOTATION_TTL_SECONDS
    ]
    for key in stale:
        del _tone_annotations[key]

    entry = _tone_annotations.pop(run_id, None)
    return entry[1] if entry is not None else None
