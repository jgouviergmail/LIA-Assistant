"""A page the model wrote, made safe to show (ADR-370).

What the browser does with these documents was measured on Chromium, Firefox and
WebKit against the application's real headers: the spec of that measure lives in
``apps/web/e2e/smoke/chat-page-app.spec.ts``. These tests pin what the backend
owes that measure: the policy comes FIRST, whatever the page says.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.core.config import settings as app_settings
from src.core.constants import INTERACTIVE_PAGE_MAP_PROVIDERS_DEFAULT
from src.core.map_tile_providers import MAP_TILE_PROVIDERS
from src.domains.interactive_pages.document import (
    PageRefusal,
    clean_source,
    page_content_policy,
    page_file,
    page_frame,
    refusal_of,
    source_of,
)

pytestmark = pytest.mark.unit

MAX_BYTES = 10_000
PAGE = '<!doctype html><html lang="fr"><head><title>Jeu</title></head><body><p>x</p></body></html>'
POLICY_MARK = '<meta http-equiv="Content-Security-Policy"'
TILES = "https://tiles.example"


def _directive(policy: str, name: str) -> str:
    """One directive of a policy, its name included."""
    (found,) = [part.strip() for part in policy.split(";") if part.strip().startswith(f"{name} ")]
    return found


class TestTheBrowserJourney:
    def test_runs_the_prefix_this_module_composes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A policy changed here must reach the engines: the spec reads this very file.

        The file is the prefix of a deployment with the default map sources, whatever
        the workstation's own environment allows.
        """
        monkeypatch.setattr(
            app_settings,
            "interactive_page_map_providers",
            list(INTERACTIVE_PAGE_MAP_PROVIDERS_DEFAULT),
        )
        fixture = json.loads(
            Path(__file__).with_name("page_frame_prefix.json").read_text(encoding="utf-8")
        )
        assert fixture["prefix"] == page_frame("").document


class TestPolicy:
    @pytest.mark.parametrize("origins", [(), (TILES,)], ids=["no-map-source", "a-map-source"])
    def test_reaches_nothing_outside_the_page(self, origins: tuple[str, ...]) -> None:
        policy = page_content_policy(origins)
        for directive in (
            "default-src 'none'",
            "connect-src 'none'",
            "frame-src 'none'",
            "child-src 'none'",
            "worker-src 'none'",
            "object-src 'none'",
            "base-uri 'none'",
            "form-action 'none'",
            "manifest-src 'none'",
        ):
            assert directive in policy

    def test_names_no_host_at_all_when_no_map_source_is_allowed(self) -> None:
        """A page written after reading a mail must not carry data out in an image URL."""
        policy = page_content_policy(())
        assert "http" not in policy
        assert _directive(policy, "img-src") == "img-src data: blob:"
        assert "font-src data:" in policy

    def test_a_map_source_is_named_for_images_and_for_nothing_else(self) -> None:
        """Tiles are images: no script, frame, font or request gains a host with them."""
        policy = page_content_policy((TILES, "https://other.example"))
        assert _directive(policy, "img-src") == (
            f"img-src data: blob: {TILES} https://other.example"
        )
        assert policy.count("http") == 2

    @pytest.mark.parametrize("origins", [(), (TILES,)], ids=["no-map-source", "a-map-source"])
    def test_never_allows_eval(self, origins: tuple[str, ...]) -> None:
        assert "unsafe-eval" not in page_content_policy(origins)


class TestTheSourcesOfADeployment:
    def test_the_frame_names_the_origins_of_the_allowed_sources(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        first, second = list(MAP_TILE_PROVIDERS)[:2]
        monkeypatch.setattr(app_settings, "interactive_page_map_providers", [first, second])
        frame = page_frame(PAGE)
        prefix = frame.document[: frame.source_offset]
        assert MAP_TILE_PROVIDERS[first].origin in prefix
        assert MAP_TILE_PROVIDERS[second].origin in prefix

    def test_a_deployment_that_allows_none_names_no_host(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(app_settings, "interactive_page_map_providers", [])
        frame = page_frame(PAGE)
        assert "://" not in frame.document[: frame.source_offset]
        assert b"://" not in page_file(PAGE)[: -len(PAGE.encode())]

    def test_the_file_is_held_to_the_frame_s_policy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A page refused the network here is not handed it there, and the reverse."""
        (first,) = list(MAP_TILE_PROVIDERS)[:1]
        monkeypatch.setattr(app_settings, "interactive_page_map_providers", [first])
        frame = page_frame(PAGE)
        policy_end = frame.document.index("<script>")
        assert page_file(PAGE).decode().startswith(frame.document[:policy_end])

    def test_an_archived_page_follows_the_sources_allowed_today(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Composed at the door: a source withdrawn reaches every page already kept."""
        (first,) = list(MAP_TILE_PROVIDERS)[:1]
        monkeypatch.setattr(app_settings, "interactive_page_map_providers", [first])
        archived = page_frame(PAGE)
        monkeypatch.setattr(app_settings, "interactive_page_map_providers", [])
        today = page_frame(source_of(archived.document, archived.source_offset))
        assert MAP_TILE_PROVIDERS[first].origin not in today.document


class TestFrame:
    def test_the_policy_opens_the_document(self) -> None:
        document = page_frame(PAGE).document
        assert document.startswith(f'<!DOCTYPE html><meta charset="utf-8">{POLICY_MARK}')

    @pytest.mark.parametrize(
        "hostile",
        [
            "<!-- <head> --><!doctype html><html><head></head><body><script>x()</script>",
            "<script>x()</script><html><head></head></html>",
            '<!doctype html><html><body><script>var s="<head>";x()</script></body></html>',
            "﻿<script>x()</script>",
        ],
        ids=["head-in-a-comment", "script-before-head", "head-in-a-string", "byte-order-mark"],
    )
    def test_no_page_runs_before_the_policy(self, hostile: str) -> None:
        """The bypasses measured on the regex injection of ``output_builder``."""
        frame = page_frame(hostile)
        assert frame.document.index(POLICY_MARK) < frame.source_offset
        assert frame.document[frame.source_offset :] == hostile

    def test_the_runtime_runs_before_the_page(self) -> None:
        frame = page_frame(PAGE)
        prefix = frame.document[: frame.source_offset]
        assert prefix.index(POLICY_MARK) < prefix.index("<script>")
        assert prefix.endswith("</script>")

    def test_the_runtime_closes_webrtc(self) -> None:
        """A STUN packet left Chromium under this policy, ``webrtc 'block'`` included."""
        prefix = page_frame(PAGE).document[: page_frame(PAGE).source_offset]
        for name in ("RTCPeerConnection", "webkitRTCPeerConnection", "RTCDataChannel"):
            assert name in prefix

    def test_the_runtime_keeps_storage_in_memory(self) -> None:
        """An opaque origin makes ``localStorage`` throw, which would kill a game's first line."""
        prefix = page_frame(PAGE).document[: page_frame(PAGE).source_offset]
        assert "localStorage" in prefix
        assert "sessionStorage" in prefix

    def test_the_runtime_asks_the_host_for_nothing_it_can_abuse(self) -> None:
        prefix = page_frame(PAGE).document[: page_frame(PAGE).source_offset]
        assert "ui/notifications/size-changed" in prefix
        assert "ui/notifications/error" in prefix
        assert "ui/open" not in prefix
        assert "ui/initialize" not in prefix

    def test_the_runtime_tells_what_the_policy_blocked_and_never_where(self) -> None:
        """A hole in a page is said: the host hears the directive, not a URL the page chose."""
        prefix = page_frame(PAGE).document[: page_frame(PAGE).source_offset]
        assert "securitypolicyviolation" in prefix
        assert "ui/notifications/blocked" in prefix
        assert "effectiveDirective" in prefix
        assert "blockedURI" not in prefix


class TestFile:
    def test_carries_the_policy_and_no_runtime(self) -> None:
        data = page_file(PAGE)
        assert data.startswith(b'<!DOCTYPE html><meta charset="utf-8">')
        assert POLICY_MARK.encode() in data[:400]
        assert b"<script>" not in data
        assert data.endswith(PAGE.encode())

    def test_is_utf_8(self) -> None:
        assert "🎃".encode() in page_file("<p>🎃</p>")


class TestCleanSource:
    def test_leaves_a_page_alone(self) -> None:
        assert clean_source("<p>🎃 é\n</p>") == "<p>🎃 é\n</p>"

    def test_removes_what_jsonb_refuses(self) -> None:
        """PostgreSQL rejects a NUL in JSONB: the whole message would fail to archive."""
        assert clean_source("<p>a\x00b</p>") == "<p>ab</p>"

    @pytest.mark.parametrize(
        "wrapped",
        ["```html\n<p>x</p>\n```", "  ```\n<p>x</p>\n```\n", "```HTML\n<p>x</p>```"],
    )
    def test_takes_a_page_out_of_its_markdown_fence(self, wrapped: str) -> None:
        """A writer may wrap its answer: the fence would show as text on the page."""
        assert clean_source(wrapped) == "<p>x</p>"

    def test_leaves_a_fence_inside_a_page(self) -> None:
        page = "<pre>```js\na\n```</pre>"
        assert clean_source(page) == page

    def test_replaces_a_lone_surrogate(self) -> None:
        """A model's JSON can carry half a pair; it encodes to nothing and JSONB refuses it."""
        cleaned = clean_source("<p>\ud83d</p>")
        assert cleaned.encode("utf-8") == b"<p>?</p>"


class TestSourceOf:
    def test_the_offset_counts_the_same_in_python_and_in_the_browser(self) -> None:
        """Only ASCII comes before the page: code points and UTF-16 units agree there."""
        frame = page_frame("<p>🎃</p>")
        assert frame.document[: frame.source_offset].isascii()

    def test_gives_the_page_back_exactly(self) -> None:
        source = "<p>🎃 é\n</p>"
        frame = page_frame(source)
        assert source_of(frame.document, frame.source_offset) == source

    @pytest.mark.parametrize("offset", [-1, 10**9])
    def test_reads_a_damaged_offset_as_a_whole_document(self, offset: int) -> None:
        assert source_of("<p>x</p>", offset) == "<p>x</p>"


class TestRefusalOf:
    def test_accepts_a_page(self) -> None:
        assert refusal_of(PAGE, max_bytes=MAX_BYTES) is None

    @pytest.mark.parametrize("source", ["", "   \n", "no markup at all"])
    def test_refuses_what_holds_no_element(self, source: str) -> None:
        assert refusal_of(source, max_bytes=MAX_BYTES) is PageRefusal.EMPTY

    def test_refuses_a_page_over_its_budget(self) -> None:
        source = f"<p>{'é' * 6_000}</p>"
        assert refusal_of(source, max_bytes=MAX_BYTES) is PageRefusal.TOO_LARGE

    def test_refuses_a_script_that_never_closes(self) -> None:
        """A browser runs nothing of it: the page would stay blank, in silence."""
        source = "<html><body><button>go</button><script>var a=1;"
        assert refusal_of(source, max_bytes=MAX_BYTES) is PageRefusal.UNCLOSED_SCRIPT

    @pytest.mark.parametrize(
        "tag",
        [
            '<script src="https://cdn.example/lib.js"></script>',
            "<SCRIPT SRC=//cdn.example/lib.js></SCRIPT>",
            '<script src="data:text/javascript,1"></script>',
        ],
    )
    def test_refuses_a_script_the_policy_would_block(self, tag: str) -> None:
        source = f"<html><head>{tag}</head><body><p>x</p></body></html>"
        assert refusal_of(source, max_bytes=MAX_BYTES) is PageRefusal.EXTERNAL_SCRIPT

    @pytest.mark.parametrize(
        "tag",
        [
            '<iframe src="https://maps.example/maps?q=x&output=embed"></iframe>',
            '<IFRAME SRCDOC="<p>x</p>"></IFRAME>',
            "<iframe></iframe>",
            '<embed src="https://media.example/clip.swf">',
            '<object data="https://media.example/doc.pdf"></object>',
            '<frameset><frame src="https://other.example/"></frameset>',
        ],
        ids=["iframe-src", "iframe-srcdoc", "iframe-bare", "embed", "object", "frameset"],
    )
    def test_refuses_a_document_embedded_in_the_page(self, tag: str) -> None:
        """The policy shows none: the page would load with a hole, in silence."""
        source = f"<html><body><p>x</p>{tag}</body></html>"
        assert refusal_of(source, max_bytes=MAX_BYTES) is PageRefusal.EMBEDDED_DOCUMENT

    @pytest.mark.parametrize(
        "source",
        [
            '<body><script>var s="<iframe src=x></iframe>";</script></body>',
            "<body><!-- <iframe src=x></iframe> --><p>x</p></body>",
            "<body><svg><foreignObject><p>x</p></foreignObject></svg></body>",
            '<body><img alt="" src="https://tiles.example/1/2/3.png"></body>',
        ],
        ids=["in-a-script-string", "in-a-comment", "svg-foreign-object", "an-image"],
    )
    def test_what_only_looks_like_an_embedded_document_is_none(self, source: str) -> None:
        assert refusal_of(source, max_bytes=MAX_BYTES) is None

    def test_a_closing_tag_quoted_in_a_comment_closes_nothing(self) -> None:
        source = "<body><!-- </script> --><script>var a=1;</script></body>"
        assert refusal_of(source, max_bytes=MAX_BYTES) is None

    def test_a_tag_inside_a_script_string_is_no_element(self) -> None:
        source = '<body><script>var s="<script src=x>";</script></body>'
        assert refusal_of(source, max_bytes=MAX_BYTES) is None

    def test_accepts_a_fragment(self) -> None:
        assert refusal_of("<button>go</button>", max_bytes=MAX_BYTES) is None
