"""A page the model wrote, made safe to show (ADR-370).

A model's HTML is not a skill's: nobody reviewed it, and it may have been written
after reading a third party's mail. So it runs under the strictest posture the
chat has, and each line below answers something measured on Chromium, Firefox and
WebKit against the application's real headers (2026-11-04; the map tiles and the
word on a hole, 2026-11-12):

- **Nothing leaves but the request for a map tile.** The skills' policy allows
  ``https:`` images, and an image URL is a way out for whatever the page holds.
  This one names the origins of the map tile sources the deployment allows
  (:mod:`src.core.map_tile_providers`), for images and for nothing else; with no
  source allowed it names no host at all.
- **A hole is said.** The policy blocks in silence: a frame, an image or a
  stylesheet it refuses leaves a blank where the page meant something. The
  runtime tells the host which directive refused, never the address: that is a
  word the page chose.
- **The policy comes first.** See :mod:`src.domains.shared.frame_policy`.
- **WebRTC is closed by hand.** A STUN packet left Chromium under this policy,
  ``webrtc 'block'`` included. The runtime runs before the page and takes the
  constructors away. ``frame-src 'none'`` is what stops a nested frame from
  handing back a fresh one: reading it throws, on all three engines.
- **Storage lives in memory.** An opaque origin makes ``localStorage`` throw, and
  a game's first line would kill the whole script.

The document is composed at the door, never stored composed for good: a reader
keeps the page's own bytes through ``source_offset``, so a policy changed here
reaches every page already archived (``message_widgets``).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from html.parser import HTMLParser
from typing import Final

from src.core.config import settings
from src.core.map_tile_providers import map_tile_providers
from src.domains.shared.frame_policy import with_leading_policy


def page_content_policy(tile_origins: Sequence[str] = ()) -> str:
    """What a page may reach: itself, and the tiles of a map.

    ``'unsafe-inline'`` is the page's own code, which is the point; the frame's
    sandbox gives it an opaque origin. A tile is an image, so ``img-src`` is the
    one directive that ever names a host.

    Args:
        tile_origins: Origins of the map tile sources allowed, empty for none.

    Returns:
        The policy, as the content of its ``<meta>``.
    """
    images = " ".join(("img-src data: blob:", *tile_origins))
    return (
        "default-src 'none'; "
        "script-src 'unsafe-inline'; "
        "style-src 'unsafe-inline'; "
        f"{images}; "
        "font-src data:; "
        "media-src data: blob:; "
        "connect-src 'none'; "
        "frame-src 'none'; "
        "child-src 'none'; "
        "worker-src 'none'; "
        "object-src 'none'; "
        "base-uri 'none'; "
        "form-action 'none'; "
        "manifest-src 'none'"
    )


#: Runs before the page. It tells the host three things, a height, a failure and
#: what the policy refused, and asks it for nothing: the skills' ``ui/open-link``
#: makes the HOST open a URL, which is exactly the exit the sandbox closes.
_FRAME_RUNTIME: Final = (
    "<script>(function(){"
    "['RTCPeerConnection','webkitRTCPeerConnection','RTCDataChannel',"
    "'RTCSessionDescription','RTCIceCandidate'].forEach(function(n){"
    "try{Object.defineProperty(window,n,{value:undefined,writable:false,configurable:false})}"
    "catch(e){}});"
    "function memory(){var m=new Map();return{"
    "get length(){return m.size},"
    "key:function(i){var k=Array.from(m.keys())[i];return k===undefined?null:k},"
    "getItem:function(k){k=String(k);return m.has(k)?m.get(k):null},"
    "setItem:function(k,v){m.set(String(k),String(v))},"
    "removeItem:function(k){m.delete(String(k))},"
    "clear:function(){m.clear()}}}"
    "['localStorage','sessionStorage'].forEach(function(n){"
    "try{Object.defineProperty(window,n,{value:memory(),configurable:false})}catch(e){}});"
    "function post(method,params){"
    "parent.postMessage({jsonrpc:'2.0',method:method,params:params},'*')}"
    "var last=0;"
    "function height(){var d=document.documentElement,b=document.body;"
    "return b?Math.ceil(Math.max(d.scrollHeight,b.scrollHeight,"
    "b.getBoundingClientRect().bottom)):0}"
    "function report(){var h=height();if(h>0&&Math.abs(h-last)>=4){last=h;"
    "post('ui/notifications/size-changed',{height:h})}}"
    "function schedule(){requestAnimationFrame(function(){requestAnimationFrame(report)})}"
    "document.addEventListener('DOMContentLoaded',function(){schedule();"
    "if(window.ResizeObserver){var o=new ResizeObserver(schedule);"
    "o.observe(document.documentElement);if(document.body)o.observe(document.body)}});"
    "addEventListener('load',schedule);addEventListener('resize',schedule);"
    "function fault(message){post('ui/notifications/error',"
    "{message:String(message).slice(0,300)})}"
    "addEventListener('error',function(e){fault(e.message)});"
    "addEventListener('unhandledrejection',function(e){fault(e.reason)});"
    "var told={};"
    "document.addEventListener('securitypolicyviolation',function(e){"
    "var d=String(e.effectiveDirective||'').slice(0,40);"
    "if(d&&!told[d]){told[d]=1;post('ui/notifications/blocked',{directive:d})}});"
    "})();</script>"
)

#: A whole answer wrapped in one Markdown fence, its language optional.
_WRAPPING_FENCE: Final = re.compile(r"\A\s*```[a-zA-Z]*[ \t]*\n(.*?)\n?```\s*\Z", re.DOTALL)

#: Elements that hold another document. The policy shows none of them.
_EMBEDDING_TAGS: Final = frozenset({"iframe", "frame", "frameset", "object", "embed"})


def _allowed_tile_origins() -> tuple[str, ...]:
    """Origins of the map tile sources this deployment allows, each once."""
    providers = map_tile_providers(settings.interactive_page_map_providers)
    return tuple(dict.fromkeys(provider.origin for provider in providers))


@lru_cache(maxsize=8)
def _prefixes(tile_origins: tuple[str, ...]) -> tuple[str, str]:
    """What opens a file and what opens a frame, under one policy.

    Args:
        tile_origins: Origins the policy names for images.

    Returns:
        The file's prefix, then the frame's (the same policy, plus the runtime).
    """
    meta = (
        '<meta http-equiv="Content-Security-Policy" '
        f'content="{page_content_policy(tile_origins)}">'
    )
    file_prefix = with_leading_policy(meta, "")
    return file_prefix, file_prefix + _FRAME_RUNTIME


@dataclass(frozen=True, slots=True)
class PageFrame:
    """What the iframe runs.

    Attributes:
        document: The policy, the runtime, then the page.
        source_offset: Where the page's own bytes start. ASCII precedes them, so
            the offset reads the same in Python and in the browser.
    """

    document: str
    source_offset: int


def clean_source(source: str) -> str:
    """What was written, in text every store can hold.

    A model's JSON can carry a NUL or half a surrogate pair. PostgreSQL refuses
    both in JSONB, so one such character would fail the whole message's archive,
    and half a pair does not even encode to UTF-8. A writer may also wrap its
    answer in a Markdown fence, which the page would show as text.

    Args:
        source: The page as received.

    Returns:
        The same page, those characters removed or replaced, out of its fence.
    """
    cleaned = source.encode("utf-8", "replace").decode("utf-8").replace("\x00", "")
    fenced = _WRAPPING_FENCE.match(cleaned)
    return fenced.group(1) if fenced else cleaned


def page_frame(source: str) -> PageFrame:
    """Compose the document an iframe runs.

    Args:
        source: The page as written.

    Returns:
        The frame document and where the page starts in it.
    """
    _, frame_prefix = _prefixes(_allowed_tile_origins())
    return PageFrame(document=frame_prefix + source, source_offset=len(frame_prefix))


def page_file(source: str) -> bytes:
    """Compose the ``.html`` file: the same policy, no runtime.

    Opened from a disk the page has no host to talk to and needs none of the
    frame's plumbing, and a page that was refused the network here is not handed
    it there.

    Args:
        source: The page as written.

    Returns:
        The file's bytes.
    """
    file_prefix, _ = _prefixes(_allowed_tile_origins())
    return (file_prefix + source).encode("utf-8")


def source_of(document: str, source_offset: int) -> str:
    """The page's own bytes in a frame document.

    Args:
        document: A frame document, possibly composed under an earlier policy.
        source_offset: Where the page starts in it.

    Returns:
        The page as written; the whole text when the offset cannot be read,
        since a second prefix is harmless and a lost page is not.
    """
    return document[source_offset:] if 0 <= source_offset <= len(document) else document


class PageRefusal(str, Enum):
    """Why a page is not shown. Each one would otherwise be a page that says nothing."""

    #: Nothing to show: no element at all.
    EMPTY = "empty"
    #: Over the budget published to the writer.
    TOO_LARGE = "too_large"
    #: A browser runs nothing of a script that never closes, and logs nothing.
    UNCLOSED_SCRIPT = "unclosed_script"
    #: The policy blocks it, so the page would load and do nothing.
    EXTERNAL_SCRIPT = "external_script"
    #: The policy shows no other document, so the page would load with a hole.
    EMBEDDED_DOCUMENT = "embedded_document"


class _PageReader(HTMLParser):
    """Reads what a page holds the way a browser tokenizes it, comments and strings included."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.saw_element = False
        self.open_script = False
        self.external_script = False
        self.embedded_document = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.saw_element = True
        self.embedded_document = self.embedded_document or tag in _EMBEDDING_TAGS
        if tag == "script":
            self.open_script = True
            self.external_script = self.external_script or any(name == "src" for name, _ in attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self.open_script = False


def refusal_of(source: str, *, max_bytes: int) -> PageRefusal | None:
    """Why a page cannot be shown, or ``None`` when it can.

    CPU-bound on a page of a few hundred kilobytes: a caller on the event loop
    runs it through ``asyncio.to_thread``.

    Args:
        source: The page as written.
        max_bytes: The budget, in UTF-8 bytes.

    Returns:
        The refusal, or ``None``.
    """
    if len(source.encode("utf-8")) > max_bytes:
        return PageRefusal.TOO_LARGE
    reader = _PageReader()
    reader.feed(source)
    reader.close()
    if not reader.saw_element:
        return PageRefusal.EMPTY
    if reader.open_script:
        return PageRefusal.UNCLOSED_SCRIPT
    if reader.external_script:
        return PageRefusal.EXTERNAL_SCRIPT
    return PageRefusal.EMBEDDED_DOCUMENT if reader.embedded_document else None
