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

from src.domains.interactive_pages.document import (
    PAGE_CONTENT_POLICY,
    PageRefusal,
    clean_source,
    page_file,
    page_frame,
    refusal_of,
    source_of,
)

pytestmark = pytest.mark.unit

MAX_BYTES = 10_000
PAGE = '<!doctype html><html lang="fr"><head><title>Jeu</title></head><body><p>x</p></body></html>'
POLICY_MARK = '<meta http-equiv="Content-Security-Policy"'


class TestTheBrowserJourney:
    def test_runs_the_prefix_this_module_composes(self) -> None:
        """A policy changed here must reach the engines: the spec reads this very file."""
        fixture = json.loads(
            Path(__file__).with_name("page_frame_prefix.json").read_text(encoding="utf-8")
        )
        assert fixture["prefix"] == page_frame("").document


class TestPolicy:
    def test_reaches_nothing_outside_the_page(self) -> None:
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
            assert directive in PAGE_CONTENT_POLICY

    def test_names_no_host_at_all(self) -> None:
        """A page written after reading a mail must not carry data out in an image URL."""
        assert "http" not in PAGE_CONTENT_POLICY
        assert "img-src data: blob:" in PAGE_CONTENT_POLICY
        assert "font-src data:" in PAGE_CONTENT_POLICY

    def test_never_allows_eval(self) -> None:
        assert "unsafe-eval" not in PAGE_CONTENT_POLICY


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

    def test_a_closing_tag_quoted_in_a_comment_closes_nothing(self) -> None:
        source = "<body><!-- </script> --><script>var a=1;</script></body>"
        assert refusal_of(source, max_bytes=MAX_BYTES) is None

    def test_a_tag_inside_a_script_string_is_no_element(self) -> None:
        source = '<body><script>var s="<script src=x>";</script></body>'
        assert refusal_of(source, max_bytes=MAX_BYTES) is None

    def test_accepts_a_fragment(self) -> None:
        assert refusal_of("<button>go</button>", max_bytes=MAX_BYTES) is None
