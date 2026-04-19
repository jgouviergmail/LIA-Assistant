"""Unit tests for build_skill_app_output.

Covers:
- RegistryItem construction (type, payload, meta)
- CSP injection for user skills only
- No CSP injection for system skills
- frame.url vs frame.html routing
- Image payload mapping
- UnifiedToolOutput.data_success wrapping
"""

from __future__ import annotations

from src.core.field_names import FIELD_REGISTRY_ID
from src.domains.agents.data_registry.models import RegistryItemType
from src.domains.skills.output_builder import (
    _AUTORESIZE_SCRIPT,
    _USER_SKILL_CSP_META,
    _inject_autoresize_script,
    _inject_csp_meta,
    build_skill_app_output,
)
from src.domains.skills.script_output import (
    SkillFrame,
    SkillImage,
    SkillScriptOutput,
)


def _sole_item(out):  # type: ignore[no-untyped-def]
    assert len(out.registry_updates) == 1
    return next(iter(out.registry_updates.values()))


class TestInjectCsp:
    def test_injects_after_head_tag(self) -> None:
        html = "<html><head><title>x</title></head><body>y</body></html>"
        result = _inject_csp_meta(html)
        assert _USER_SKILL_CSP_META in result
        # CSP inserted right after <head>
        head_idx = result.index("<head>") + len("<head>")
        assert result[head_idx:].startswith(_USER_SKILL_CSP_META)

    def test_creates_head_if_missing(self) -> None:
        html = "<html><body>y</body></html>"
        result = _inject_csp_meta(html)
        assert "<head>" in result
        assert _USER_SKILL_CSP_META in result

    def test_wraps_fragment(self) -> None:
        html = "<p>just a fragment</p>"
        result = _inject_csp_meta(html)
        assert "<!DOCTYPE html>" in result
        assert _USER_SKILL_CSP_META in result
        assert "<p>just a fragment</p>" in result


class TestBuildSkillAppOutput:
    def _system_output(self, output: SkillScriptOutput):
        return build_skill_app_output(output, "sys-skill", is_system_skill=True)

    def _user_output(self, output: SkillScriptOutput):
        return build_skill_app_output(output, "user-skill", is_system_skill=False)

    def test_success_flag(self) -> None:
        out = self._system_output(
            SkillScriptOutput(
                text="x",
                frame=SkillFrame(url="https://example.com"),
            )
        )
        assert out.success is True

    def test_registry_type_is_skill_app(self) -> None:
        out = self._system_output(
            SkillScriptOutput(
                text="x",
                frame=SkillFrame(url="https://example.com"),
            )
        )
        item = _sole_item(out)
        assert item.type == RegistryItemType.SKILL_APP

    def test_payload_has_registry_id(self) -> None:
        out = self._system_output(
            SkillScriptOutput(
                text="x",
                frame=SkillFrame(url="https://example.com"),
            )
        )
        item = _sole_item(out)
        assert FIELD_REGISTRY_ID in item.payload
        assert item.payload[FIELD_REGISTRY_ID] == item.id

    def test_frame_url_payload(self) -> None:
        out = self._system_output(
            SkillScriptOutput(
                text="Paris",
                frame=SkillFrame(url="https://maps.google.com/maps?q=Paris"),
            )
        )
        item = _sole_item(out)
        assert item.payload["frame_url"] == "https://maps.google.com/maps?q=Paris"
        assert item.payload["html_content"] is None

    def test_frame_html_system_skill_no_csp(self) -> None:
        html = "<html><head></head><body>hi</body></html>"
        out = self._system_output(
            SkillScriptOutput(
                text="x",
                frame=SkillFrame(html=html),
            )
        )
        item = _sole_item(out)
        content = item.payload["html_content"]
        assert isinstance(content, str)
        assert _USER_SKILL_CSP_META not in content
        # System skills skip CSP but still receive the auto-resize snippet so
        # the iframe can grow dynamically to the skill's rendered height.
        assert "ui/notifications/size-changed" in content
        assert "hi" in content

    def test_frame_html_user_skill_csp_injected(self) -> None:
        html = "<html><head></head><body>hi</body></html>"
        out = self._user_output(
            SkillScriptOutput(
                text="x",
                frame=SkillFrame(html=html),
            )
        )
        item = _sole_item(out)
        content = item.payload["html_content"]
        assert isinstance(content, str)
        assert _USER_SKILL_CSP_META in content
        assert "connect-src 'none'" in content
        # User skills also get the auto-resize snippet (CSP allows inline scripts)
        assert "ui/notifications/size-changed" in content

    def test_image_payload(self) -> None:
        out = self._system_output(
            SkillScriptOutput(
                text="QR",
                image=SkillImage(url="data:image/png;base64,x", alt="QR code"),
            )
        )
        item = _sole_item(out)
        assert item.payload["image_url"] == "data:image/png;base64,x"
        assert item.payload["image_alt"] == "QR code"

    def test_combined_frame_and_image(self) -> None:
        out = self._system_output(
            SkillScriptOutput(
                text="Report",
                frame=SkillFrame(html="<p>ok</p>"),
                image=SkillImage(url="data:image/png;base64,x", alt="Chart"),
            )
        )
        item = _sole_item(out)
        assert item.payload["html_content"] is not None
        assert item.payload["image_url"] is not None

    def test_text_summary_in_payload(self) -> None:
        out = self._system_output(
            SkillScriptOutput(
                text="Caption for accessibility",
                frame=SkillFrame(url="https://example.com"),
            )
        )
        item = _sole_item(out)
        assert item.payload["text_summary"] == "Caption for accessibility"

    def test_is_system_skill_flag(self) -> None:
        system_out = self._system_output(
            SkillScriptOutput(
                text="x",
                frame=SkillFrame(url="https://example.com"),
            )
        )
        user_out = self._user_output(
            SkillScriptOutput(
                text="x",
                frame=SkillFrame(url="https://example.com"),
            )
        )
        assert _sole_item(system_out).payload["is_system_skill"] is True
        assert _sole_item(user_out).payload["is_system_skill"] is False

    def test_message_is_the_text(self) -> None:
        out = self._system_output(
            SkillScriptOutput(
                text="This goes to the LLM",
                frame=SkillFrame(url="https://example.com"),
            )
        )
        assert out.message == "This goes to the LLM"

    def test_metadata_contains_skill_name(self) -> None:
        out = build_skill_app_output(
            SkillScriptOutput(text="x", frame=SkillFrame(url="https://example.com")),
            skill_name="my-skill",
            is_system_skill=True,
            execution_time_ms=42,
        )
        assert out.metadata["skill_name"] == "my-skill"
        assert out.metadata["execution_time_ms"] == 42
        assert out.metadata["has_frame"] is True
        assert out.metadata["has_image"] is False

    def test_structured_data_includes_skill_apps_key(self) -> None:
        out = self._system_output(
            SkillScriptOutput(
                text="x",
                frame=SkillFrame(url="https://example.com"),
            )
        )
        assert "skill_apps" in out.structured_data


class TestInjectAutoresizeScript:
    def test_injects_before_body_close(self) -> None:
        html = "<html><head></head><body><p>hi</p></body></html>"
        result = _inject_autoresize_script(html)
        assert _AUTORESIZE_SCRIPT in result
        # Snippet placed immediately before </body>
        assert result.index(_AUTORESIZE_SCRIPT) < result.lower().index("</body>")
        # Body content preserved
        assert "<p>hi</p>" in result

    def test_falls_back_to_before_html_close(self) -> None:
        html = "<html><p>no body tag</p></html>"
        result = _inject_autoresize_script(html)
        assert _AUTORESIZE_SCRIPT in result
        assert result.index(_AUTORESIZE_SCRIPT) < result.lower().index("</html>")

    def test_appends_when_no_closing_tags(self) -> None:
        html = "<p>bare fragment</p>"
        result = _inject_autoresize_script(html)
        assert result.startswith("<p>bare fragment</p>")
        assert result.endswith(_AUTORESIZE_SCRIPT)

    def test_snippet_emits_size_changed_message(self) -> None:
        # Contract: the snippet posts a JSON-RPC ``ui/notifications/size-changed``
        # message aligned with ``useSkillAppBridge``.
        assert "'ui/notifications/size-changed'" in _AUTORESIZE_SCRIPT
        assert "jsonrpc:'2.0'" in _AUTORESIZE_SCRIPT
        assert "parent.postMessage" in _AUTORESIZE_SCRIPT

    def test_snippet_debounces_sub_pixel_noise(self) -> None:
        # Guard rail: the snippet must avoid emitting on micro-variations
        # (otherwise ResizeObserver would flood the bridge).
        assert "Math.abs(h-lastH)<4" in _AUTORESIZE_SCRIPT

    def test_snippet_observes_body(self) -> None:
        # We observe body only — documentElement reports the iframe viewport,
        # not the content, leading to oversized frames.
        assert "ro.observe(document.body)" in _AUTORESIZE_SCRIPT

    def test_snippet_uses_bounding_client_rect_for_measurement(self) -> None:
        # Contract: measurement is based on body.getBoundingClientRect().bottom
        # (pattern from iframe-resizer) — avoids the scrollHeight/offsetHeight
        # traps that include the iframe viewport.
        assert "getBoundingClientRect" in _AUTORESIZE_SCRIPT
        assert "rect.bottom" in _AUTORESIZE_SCRIPT

    def test_snippet_resets_html_body_margin_padding(self) -> None:
        # Inline <style> resets html/body margin+padding so default browser
        # margins don't inflate the measurement.
        assert "margin:0!important" in _AUTORESIZE_SCRIPT
        assert "padding:0!important" in _AUTORESIZE_SCRIPT
