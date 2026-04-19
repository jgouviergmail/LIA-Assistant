"""Skill script output contract — rich output support for skills.

Defines the JSON contract that skill scripts can emit on stdout to return
text, interactive frames, and/or images in the chat response.

The contract is tolerant: scripts that emit plain text (not JSON) continue
to work unchanged — the parser wraps the text in ``SkillScriptOutput(text=...)``.

Rendering semantics:
    - ``text`` is always required and used for voice/LLM/accessibility
    - ``frame`` and ``image`` are independent and combinable
    - Rendered sequentially in the chat: text → image → frame
    - Multiple frames or images per invocation are NOT supported in v1
      (use a single HTML frame with a grid instead)

Security:
    - CSP injection is handled downstream in ``output_builder`` for user skills
    - HTML size is capped at ``SKILLS_FRAME_MAX_HTML_BYTES``
    - ``frame.html`` XOR ``frame.url`` (a frame has one mode only)
"""

from __future__ import annotations

import json

import structlog
from pydantic import BaseModel, Field, field_validator, model_validator

from src.core.constants import SKILLS_FRAME_MAX_HTML_BYTES

logger = structlog.get_logger(__name__)


class SkillFrame(BaseModel):
    """Interactive iframe output — either inline HTML or external URL.

    Attributes:
        html: Inline HTML content (rendered via iframe ``srcDoc``). Mutually
            exclusive with ``url``. Size capped at ``SKILLS_FRAME_MAX_HTML_BYTES``.
        url: External URL (rendered via iframe ``src``). Must be https://.
            Mutually exclusive with ``html``.
        title: Display title shown in the frame header badge.
        aspect_ratio: Width/height ratio for responsive rendering. Default 4:3.
    """

    html: str | None = Field(
        default=None,
        description="Inline HTML (srcDoc) — mutually exclusive with url",
    )
    url: str | None = Field(
        default=None,
        description="External URL (src) — mutually exclusive with html",
    )
    title: str | None = Field(
        default=None,
        description="Frame header badge title",
    )
    aspect_ratio: float = Field(
        default=1.333,
        gt=0.0,
        description="Width/height ratio (default 4:3 = 1.333)",
    )

    @field_validator("url")
    @classmethod
    def _url_must_be_https(cls, v: str | None) -> str | None:
        """External frame URLs must be https:// (no http, javascript:, data:)."""
        if v is None:
            return v
        if not v.startswith("https://"):
            raise ValueError("frame.url must start with https://")
        return v

    @field_validator("html")
    @classmethod
    def _html_size_within_limit(cls, v: str | None) -> str | None:
        """Enforce HTML size cap to prevent context bloat."""
        if v is None:
            return v
        if len(v.encode("utf-8")) > SKILLS_FRAME_MAX_HTML_BYTES:
            raise ValueError(f"frame.html exceeds max size ({SKILLS_FRAME_MAX_HTML_BYTES} bytes)")
        return v

    @model_validator(mode="after")
    def _html_xor_url(self) -> SkillFrame:
        """A frame has exactly one source: html OR url, not both, not neither."""
        if self.html is None and self.url is None:
            raise ValueError("frame must have either html or url")
        if self.html is not None and self.url is not None:
            raise ValueError("frame.html and frame.url are mutually exclusive")
        return self


class SkillImage(BaseModel):
    """Image output — data URI or https URL, always with alt text.

    Attributes:
        url: Image URL (``data:`` URI or ``https://``).
        alt: Alt text (required for accessibility and voice fallback).
    """

    url: str = Field(
        ...,
        description="Image URL (data: URI or https://)",
    )
    alt: str = Field(
        ...,
        min_length=1,
        description="Alt text — required for accessibility and voice",
    )

    @field_validator("url")
    @classmethod
    def _url_must_be_safe(cls, v: str) -> str:
        """Only data: and https:// allowed — reject http, javascript:, file:, etc."""
        if not (v.startswith("data:") or v.startswith("https://")):
            raise ValueError("image.url must be a data: URI or start with https://")
        return v


class SkillScriptOutput(BaseModel):
    """Standardized output contract for skill scripts.

    The skill script writes this structure as JSON on stdout. The app parses
    and routes based on which fields are present. Text is always required
    (used for voice, LLM context, accessibility). Frame and image are
    independent optional channels that can coexist.

    Attributes:
        text: Always required — caption, summary, or full textual response.
        frame: Optional interactive iframe (HTML inline or external URL).
        image: Optional image artifact.
        error: Optional error message for graceful failures.
    """

    text: str = Field(
        ...,
        description="Textual response — required for voice, LLM, and accessibility",
    )
    frame: SkillFrame | None = Field(
        default=None,
        description="Optional interactive frame (iframe)",
    )
    image: SkillImage | None = Field(
        default=None,
        description="Optional image artifact",
    )
    error: str | None = Field(
        default=None,
        description="Optional error message for graceful failures",
    )


def parse_skill_stdout(stdout: str) -> SkillScriptOutput:
    """Parse skill script stdout into a ``SkillScriptOutput``.

    Parsing strategy (tolerant, backward compatible):
        1. Try ``json.loads(stdout.strip())`` → if valid dict with ``text`` key,
           validate as ``SkillScriptOutput``
        2. Fallback: treat the whole stdout as plain text →
           ``SkillScriptOutput(text=stdout)``

    This ensures existing skills that emit plain text continue to work
    unchanged. New skills opt into rich outputs by emitting JSON.

    Convention: scripts should emit ONLY the JSON payload on stdout. Logs,
    debug prints, and progress indicators must go to stderr. Mixed stdout
    (text + JSON) will fail validation and fall back to text-only mode.

    Args:
        stdout: Raw stdout captured from the skill script subprocess.

    Returns:
        ``SkillScriptOutput`` — always returns a valid instance, never raises
        on parse errors (falls back to text). If validation fails on a
        well-formed JSON (e.g., html exceeds size), returns text-only with
        the error captured in ``error`` field.
    """
    stripped = stdout.strip()
    if not stripped:
        return SkillScriptOutput(text="")

    # Attempt JSON parse
    try:
        data = json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        # Not JSON — wrap as plain text (backward compat)
        return SkillScriptOutput(text=stdout)

    # JSON must be a dict with 'text' field to be considered rich output
    if not isinstance(data, dict) or "text" not in data:
        return SkillScriptOutput(text=stdout)

    # Attempt full rich-output validation
    try:
        return SkillScriptOutput.model_validate(data)
    except Exception as exc:  # pragma: no cover — defensive
        # Validation failed (bad frame/image) — degrade gracefully to text with error.
        # Log the full traceback so operators can trace malformed skill output.
        logger.exception(
            "skill_script_output_validation_failed",
            has_frame="frame" in data,
            has_image="image" in data,
            stdout_preview=stdout[:200],
        )
        return SkillScriptOutput(
            text=data.get("text", "") or stdout,
            error=f"Invalid rich output: {exc}",
        )
