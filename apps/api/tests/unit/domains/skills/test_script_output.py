"""Unit tests for SkillScriptOutput and parse_skill_stdout.

Covers:
- Plain text stdout → wrapped as {text}
- Valid JSON with text/frame/image → parsed correctly
- Invalid JSON → text fallback
- JSON without 'text' field → text fallback
- XOR validation (frame.html vs frame.url)
- Size validation (frame.html max bytes)
- HTTPS validation (frame.url, image.url)
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from src.domains.skills.script_output import (
    SkillFrame,
    SkillImage,
    SkillScriptOutput,
    parse_skill_stdout,
)


class TestSkillFrame:
    def test_html_only_valid(self) -> None:
        frame = SkillFrame(html="<p>hi</p>")
        assert frame.html == "<p>hi</p>"
        assert frame.url is None

    def test_url_only_valid(self) -> None:
        frame = SkillFrame(url="https://example.com")
        assert frame.url == "https://example.com"
        assert frame.html is None

    def test_rejects_both_html_and_url(self) -> None:
        with pytest.raises(ValidationError, match="mutually exclusive"):
            SkillFrame(html="<p>hi</p>", url="https://example.com")

    def test_rejects_neither_html_nor_url(self) -> None:
        with pytest.raises(ValidationError, match="must have either html or url"):
            SkillFrame()

    def test_rejects_http_url(self) -> None:
        with pytest.raises(ValidationError, match="must start with https"):
            SkillFrame(url="http://example.com")

    def test_rejects_javascript_url(self) -> None:
        with pytest.raises(ValidationError, match="must start with https"):
            SkillFrame(url="javascript:alert(1)")

    def test_html_size_rejected(self) -> None:
        huge = "x" * (300 * 1024)  # 300 KB > 200 KB cap
        with pytest.raises(ValidationError, match="exceeds max size"):
            SkillFrame(html=huge)

    def test_aspect_ratio_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            SkillFrame(html="<p>x</p>", aspect_ratio=0)
        with pytest.raises(ValidationError):
            SkillFrame(html="<p>x</p>", aspect_ratio=-1.5)


class TestSkillImage:
    def test_https_url_valid(self) -> None:
        img = SkillImage(url="https://example.com/img.png", alt="Example")
        assert img.url.startswith("https://")

    def test_data_uri_valid(self) -> None:
        img = SkillImage(url="data:image/png;base64,iVBOR...", alt="QR")
        assert img.url.startswith("data:")

    def test_rejects_http(self) -> None:
        with pytest.raises(ValidationError, match="data: URI or start with https"):
            SkillImage(url="http://example.com/img.png", alt="Example")

    def test_rejects_javascript(self) -> None:
        with pytest.raises(ValidationError, match="data: URI or start with https"):
            SkillImage(url="javascript:alert(1)", alt="x")

    def test_alt_required_non_empty(self) -> None:
        with pytest.raises(ValidationError):
            SkillImage(url="https://example.com/i.png", alt="")


class TestSkillScriptOutput:
    def test_text_only(self) -> None:
        out = SkillScriptOutput(text="Hello")
        assert out.text == "Hello"
        assert out.frame is None
        assert out.image is None

    def test_text_and_frame(self) -> None:
        out = SkillScriptOutput(
            text="Caption",
            frame=SkillFrame(url="https://example.com"),
        )
        assert out.frame is not None
        assert out.frame.url == "https://example.com"

    def test_text_and_image(self) -> None:
        out = SkillScriptOutput(
            text="Caption",
            image=SkillImage(url="data:image/png;base64,x", alt="x"),
        )
        assert out.image is not None

    def test_text_frame_and_image_combined(self) -> None:
        out = SkillScriptOutput(
            text="Both at once",
            frame=SkillFrame(html="<p>ok</p>"),
            image=SkillImage(url="data:image/png;base64,x", alt="x"),
        )
        assert out.frame is not None
        assert out.image is not None

    def test_text_required(self) -> None:
        with pytest.raises(ValidationError):
            SkillScriptOutput.model_validate({})


class TestParseSkillStdout:
    def test_plain_text_wrapped(self) -> None:
        out = parse_skill_stdout("Hello world")
        assert out.text == "Hello world"
        assert out.frame is None
        assert out.image is None

    def test_empty_stdout(self) -> None:
        out = parse_skill_stdout("")
        assert out.text == ""

    def test_whitespace_only(self) -> None:
        out = parse_skill_stdout("   \n\t  ")
        assert out.text == ""

    def test_valid_json_text_only(self) -> None:
        stdout = json.dumps({"text": "Caption"})
        out = parse_skill_stdout(stdout)
        assert out.text == "Caption"
        assert out.frame is None

    def test_valid_json_with_frame(self) -> None:
        stdout = json.dumps(
            {
                "text": "Map of Paris",
                "frame": {"url": "https://maps.google.com/maps?q=Paris&output=embed"},
            }
        )
        out = parse_skill_stdout(stdout)
        assert out.text == "Map of Paris"
        assert out.frame is not None
        assert out.frame.url is not None

    def test_valid_json_with_image(self) -> None:
        stdout = json.dumps(
            {
                "text": "QR code",
                "image": {"url": "data:image/png;base64,x", "alt": "QR"},
            }
        )
        out = parse_skill_stdout(stdout)
        assert out.image is not None
        assert out.image.alt == "QR"

    def test_invalid_json_fallback_to_text(self) -> None:
        """Malformed JSON should be treated as plain text, not raise."""
        out = parse_skill_stdout('{"text": "broken')
        assert out.text.startswith('{"text"')
        assert out.frame is None

    def test_json_without_text_field_fallback(self) -> None:
        """Valid JSON but missing 'text' key → treat as plain text."""
        stdout = json.dumps({"result": "ok"})
        out = parse_skill_stdout(stdout)
        # Fallback wraps the whole stdout as text (backward compat)
        assert "result" in out.text

    def test_json_array_fallback(self) -> None:
        """JSON arrays (not dicts) are wrapped as text."""
        stdout = json.dumps(["a", "b"])
        out = parse_skill_stdout(stdout)
        assert "a" in out.text

    def test_json_with_invalid_frame_degrades_gracefully(self) -> None:
        """Well-formed JSON with validation errors in frame should not raise."""
        stdout = json.dumps(
            {
                "text": "Caption",
                "frame": {"url": "http://not-https.com"},  # invalid scheme
            }
        )
        out = parse_skill_stdout(stdout)
        # Graceful degradation — text preserved
        assert out.text == "Caption" or out.text == stdout
