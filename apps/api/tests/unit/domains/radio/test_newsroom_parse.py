"""Feeds and pages are wrong somewhere, each in its own way — the newsroom normalises it."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.domains.radio.constants import SOURCE_ADDRESS_MAX_CHARS, URL_MAX_BYTES
from src.domains.radio.newsroom.catalogue import CATALOGUE, CATALOGUE_URLS
from src.domains.radio.newsroom.discovery import (
    CONVENTIONAL_FEED_PATHS,
    advertised_feeds,
    candidate_feeds,
    describe_feed,
)
from src.domains.radio.newsroom.fulltext import ARTICLE_MAX_CHARS, decode_page, extract_article
from src.domains.radio.newsroom.parse import (
    SUMMARY_MAX_CHARS,
    canonical_url,
    fingerprint,
    parse_feed,
    plain_text,
)

pytestmark = pytest.mark.unit


def test_feed_comparison_is_not_eaten_as_part_of_the_following_html_tag() -> None:
    assert plain_text("Growth < 3 percent, <b>confirmed</b> today", 100) == (
        "Growth < 3 percent, confirmed today"
    )


FETCHED = datetime(2026, 9, 26, 8, 0, tzinfo=UTC)
FEED_URL = "https://news.example.org/rss.xml"

RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Example</title>
<item>
  <title>Parliament &amp; budget: <b>adopted</b></title>
  <link>/articles/budget?utm_source=rss&amp;at_medium=RSS&amp;page=2</link>
  <guid>budget-1</guid>
  <description>&lt;p&gt;The budget was &lt;i&gt;adopted&lt;/i&gt; by 312 votes.&lt;/p&gt;</description>
  <pubDate>Sat, 26 Sep 2026 06:30:00 GMT</pubDate>
</item>
<item>
  <title>Budget adopted</title>
  <link>https://news.example.org/articles/budget-copy</link>
  <guid>budget-1</guid>
</item>
<item>
  <title>A story from tomorrow</title>
  <link>https://news.example.org/articles/future</link>
  <pubDate>Sun, 27 Sep 2026 10:00:00 GMT</pubDate>
</item>
<item>
  <title>No date at all</title>
  <link>https://news.example.org/articles/undated</link>
</item>
<item><title></title><link>https://news.example.org/articles/untitled</link></item>
<item><title>Not a web link</title><link>mailto:desk@example.org</link></item>
</channel></rss>"""

ATOM = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>Atom example</title>
<entry><title>新闻标题：预算通过</title><link href="https://zh.example.org/a/1"/>
<id>tag:zh.example.org,2026:1</id><updated>2026-09-26T05:00:00Z</updated>
<summary>议会以三百一十二票通过预算。</summary></entry>
</feed>""".encode()

CONTENT_ONLY_ATOM = b"""<feed xmlns="http://www.w3.org/2005/Atom"><title>Blog</title>
<entry><title>Notes</title><link href="https://blog.example.org/n"/><id>n1</id>
<content type="html">&lt;p&gt;The whole post, in the feed.&lt;/p&gt;</content></entry></feed>"""


class TestParse:
    def test_an_rss_feed_is_normalised(self) -> None:
        items = parse_feed(RSS, feed_url=FEED_URL, fetched_at=FETCHED)
        assert [i.title for i in items] == [
            "Parliament & budget: adopted",
            "A story from tomorrow",
            "No date at all",
        ]
        first = items[0]
        assert first.url == "https://news.example.org/articles/budget?page=2"
        assert first.summary == "The budget was adopted by 312 votes."
        assert first.published_at == datetime(2026, 9, 26, 6, 30, tzinfo=UTC)

    def test_a_duplicate_guid_is_one_item(self) -> None:
        items = parse_feed(RSS, feed_url=FEED_URL, fetched_at=FETCHED)
        assert len({i.item_key for i in items}) == len(items)
        assert not any(i.url.endswith("budget-copy") for i in items)

    def test_a_date_from_the_future_or_missing_is_the_fetch_instant(self) -> None:
        by_title = {i.title: i for i in parse_feed(RSS, feed_url=FEED_URL, fetched_at=FETCHED)}
        assert by_title["A story from tomorrow"].published_at == FETCHED
        assert by_title["No date at all"].published_at == FETCHED

    def test_an_atom_feed_in_chinese(self) -> None:
        [item] = parse_feed(ATOM, feed_url="https://zh.example.org/atom", fetched_at=FETCHED)
        assert item.title == "新闻标题：预算通过"
        assert item.summary == "议会以三百一十二票通过预算。"
        assert item.fingerprint

    def test_an_entry_with_only_content_keeps_a_summary(self) -> None:
        [item] = parse_feed(
            CONTENT_ONLY_ATOM, feed_url="https://blog.example.org/atom", fetched_at=FETCHED
        )
        assert item.summary == "The whole post, in the feed."

    def test_something_that_is_not_a_feed_yields_nothing(self) -> None:
        html_page = b"<html><body>hello</body></html>"
        assert parse_feed(html_page, feed_url=FEED_URL, fetched_at=FETCHED) == []
        assert parse_feed(b"\x00\xff garbage", feed_url=FEED_URL, fetched_at=FETCHED) == []

    def test_a_body_naming_a_local_file_never_reads_it(self, tmp_path: Path) -> None:
        # Handed bytes, feedparser tries them as a PATH first: a hostile server
        # answering with a path on our disk must get that path parsed as text.
        local = tmp_path / "local.xml"
        local.write_bytes(RSS)
        body = str(local).encode()
        assert parse_feed(body, feed_url=FEED_URL, fetched_at=FETCHED) == []
        assert describe_feed(body) is None

    def test_the_key_is_stable_across_fetches(self) -> None:
        a = parse_feed(RSS, feed_url=FEED_URL, fetched_at=FETCHED)
        b = parse_feed(RSS, feed_url=FEED_URL, fetched_at=datetime(2026, 9, 27, tzinfo=UTC))
        assert [i.item_key for i in a] == [i.item_key for i in b]

    def test_a_large_feed_is_not_cut_after_its_first_entries(self) -> None:
        entries = "".join(
            f"<item><title>Story {n}</title><link>https://news.example.org/{n}</link></item>"
            for n in range(1_001)
        )
        body = f"<rss><channel><title>Large feed</title>{entries}</channel></rss>".encode()
        items = parse_feed(body, feed_url=FEED_URL, fetched_at=FETCHED)
        assert len(items) == 1_001
        assert items[-1].title == "Story 1000"


#: Characters PostgreSQL refuses in a text (NUL) or that no reader wants (the
#: other C0 and C1 controls) — built by code point: no escape in this file.
NUL, BELL, C1 = chr(0), chr(7), chr(0x85)


class TestControlCharacters:
    """A feed or a site is written by a stranger: one control character in one item
    must not become a row the database refuses — which would lose the whole feed."""

    def test_an_item_keeps_its_words_and_loses_its_control_characters(self) -> None:
        body = (
            f'<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>'
            f"<item><title>Budget{NUL}adopted{BELL}</title>"
            f"<link>https://news.example.org/a/1</link>"
            f"<description>By{BELL}312 votes</description></item></channel></rss>"
        ).encode()
        (item,) = parse_feed(body, feed_url=FEED_URL, fetched_at=FETCHED)
        assert (item.title, item.summary) == ("Budget adopted", "By 312 votes")
        assert item.fingerprint == "budget adopted"
        assert plain_text(f"a{C1}b{NUL}c", 10) == "a b c"

    def test_a_link_holding_a_control_character_is_no_link(self) -> None:
        assert canonical_url(f"https://news.example.org/a{NUL}b", FEED_URL) is None
        assert canonical_url(f"/a{BELL}b", FEED_URL) is None

    def test_a_site_describes_itself_without_them(self) -> None:
        body = (
            f'<?xml version="1.0"?><rss version="2.0"><channel><title>My{NUL}blog</title>'
            f"<language>fr{NUL}</language>"
            f"<item><title>t</title><link>https://b.example.org/1</link></item>"
            f"</channel></rss>"
        ).encode()
        described = describe_feed(body)
        assert described is not None
        assert (described.title, described.language) == ("My blog", None)


class TestHelpers:
    def test_plain_text_cuts_at_a_word_and_says_so(self) -> None:
        text = plain_text("<p>" + "mot " * 1000 + "</p>", SUMMARY_MAX_CHARS)
        assert len(text) <= SUMMARY_MAX_CHARS and text.endswith("…")
        assert "  " not in text

    def test_tracking_is_stripped_and_fragments_dropped(self) -> None:
        url = canonical_url("https://A.example.org/x?utm_medium=a&id=3&gclid=z#top", FEED_URL)
        assert url == "https://a.example.org/x?id=3"
        assert canonical_url("javascript:alert(1)", FEED_URL) is None

    def test_a_url_longer_than_the_newsroom_keeps_is_no_url(self) -> None:
        """Counted in BYTES: an indexed row holds bytes, and « é » is two of them."""
        base = "https://a.example.org/"
        fits = base + "x" * (URL_MAX_BYTES - len(base))
        assert canonical_url(fits, FEED_URL) == fits
        assert canonical_url(fits + "x", FEED_URL) is None
        half = base + "é" * ((URL_MAX_BYTES - len(base)) // 2 + 1)
        assert len(half) <= URL_MAX_BYTES and canonical_url(half, FEED_URL) is None
        assert SOURCE_ADDRESS_MAX_CHARS + len("https://") <= URL_MAX_BYTES

    def test_the_same_story_under_two_outlets_punctuation(self) -> None:
        assert fingerprint("Budget : l'Assemblée adopte le texte !") == fingerprint(
            "BUDGET — L'ASSEMBLEE ADOPTE LE TEXTE"
        )


ARTICLE = (
    "<html><head><title>x</title></head><body><nav>Menu Home About</nav>"
    "<article><h1>Budget adopted</h1>"
    + "".join(
        f"<p>Paragraph {n}: the parliament debated the budget at length. </p>" for n in range(20)
    )
    + "</article><footer>Cookies</footer></body></html>"
)
FRENCH = "<p>" + "L'élève façonne un cœur à Noël, en été comme en hiver. " * 20 + "</p>"


def page(body: str, head: str = "") -> str:
    return f"<html><head>{head}</head><body><article>{body}</article></body></html>"


class TestFullText:
    def test_the_article_is_kept_one_paragraph_per_line(self) -> None:
        text = extract_article(ARTICLE.encode())
        assert text is not None
        assert "Paragraph 0" in text and "Paragraph 19" in text
        assert "\n" in text and "<" not in text

    def test_scripts_and_styles_never_reach_the_text(self) -> None:
        body = FRENCH + "<script>var TRACKER = 1;</script><style>.ad{}</style>"
        text = extract_article(page(body).encode())
        assert text is not None and "TRACKER" not in text and ".ad{" not in text

    def test_a_consent_wall_is_not_an_article(self) -> None:
        assert extract_article(b"<html><body><p>Accept cookies</p></body></html>") is None
        assert extract_article(b"") is None

    def test_the_text_is_bounded(self) -> None:
        text = extract_article(page("<p>" + "word " * 20_000 + "</p>").encode())
        assert text is not None and len(text) <= ARTICLE_MAX_CHARS

    def test_a_latin_1_page_keeps_its_accents(self) -> None:
        body = FRENCH.replace("œ", "oe")  # œ is windows-1252, not ISO-8859-1
        legacy = page(body, '<meta charset="iso-8859-1">').encode("cp1252")
        text = extract_article(legacy)
        assert text is not None and "L'élève façonne" in text

    def test_a_gbk_page_keeps_its_ideographs(self) -> None:
        body = "<p>" + "议会以三百一十二票通过预算，镕。" * 40 + "</p>"  # 镕 is GBK, not GB2312
        text = extract_article(page(body, '<meta charset="gb2312">').encode("gb18030"))
        assert text is not None and "镕" in text

    def test_the_http_header_wins_over_the_page(self) -> None:
        mislabelled = page(FRENCH, '<meta charset="iso-8859-1">').encode("utf-8")
        assert "élève" in decode_page(mislabelled, "utf-8")
        assert "élève" not in decode_page(mislabelled)

    def test_an_unknown_label_falls_back(self) -> None:
        assert decode_page("é".encode(), "x-no-such-codec") == "é"


PAGE = b"""<html><head>
<link rel="alternate" type="application/rss+xml" href="/feed.xml">
<link rel="alternate" type="application/atom+xml" href="https://site.example.org/atom">
<link rel="alternate" type="application/rss+xml" href="/feed.xml">
<link rel="alternate" type="application/rss+xml" href="javascript:void(0)">
<link rel="stylesheet" type="text/css" href="/style.css">
</head><body>x</body></html>"""


class TestDiscovery:
    def test_a_page_advertises_its_feeds(self) -> None:
        assert advertised_feeds(PAGE, "https://site.example.org/news/") == [
            "https://site.example.org/feed.xml",
            "https://site.example.org/atom",
        ]

    def test_a_feed_is_recognised_and_described_and_a_page_is_not(self) -> None:
        described = describe_feed(RSS)
        assert described is not None and described.entries > 0 and described.title
        assert describe_feed(PAGE) is None

    def test_garbage_is_neither(self) -> None:
        assert advertised_feeds(b"", "https://site.example.org/") == []

    def test_a_site_advertising_nothing_is_tried_where_feeds_usually_live(self) -> None:
        silent = b"<html><head><title>x</title></head><body>x</body></html>"
        candidates = candidate_feeds(silent, "https://site.example.org/some/page")
        assert candidates[0] == "https://site.example.org/feed/"
        assert len(candidates) == len(CONVENTIONAL_FEED_PATHS)
        assert candidate_feeds(PAGE, "https://site.example.org/")[0].endswith("/feed.xml")


SOURCE_LANGUAGES = {"fr", "en", "de", "es", "it", "zh-CN", "pt"}
MEASURED_EXCLUSIONS = ("apnews.com", "efe.com", "swissinfo.ch", "nhk.or.jp", "thenewhumanitarian")


class TestCatalogue:
    def test_every_shipped_feed_is_https_unique_and_labelled(self) -> None:
        urls = [feed.url for feed in CATALOGUE]
        assert len(urls) == len(set(urls))
        assert all(url.startswith("https://") for url in urls)
        assert {feed.language for feed in CATALOGUE} <= SOURCE_LANGUAGES
        assert CATALOGUE_URLS == set(urls)  # what a listener unticks a base source by

    def test_the_measured_exclusions_stay_out(self) -> None:
        hosts = " ".join(feed.url for feed in CATALOGUE)
        assert not [excluded for excluded in MEASURED_EXCLUSIONS if excluded in hosts]
