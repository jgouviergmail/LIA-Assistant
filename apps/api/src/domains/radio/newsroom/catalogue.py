"""The feeds an instance offers out of the box — each one MEASURED live, 2026-09-26.

The owner listed twenty outlets. Each was probed (feed discovery, robots.txt
for our user agent, freshness of the newest item, length of the summaries,
extraction of two full articles); what follows is what answered. Kept out, and
why, so nobody re-adds them by hand without re-measuring:

- AP News and EFE: every URL answers 403 to a declared crawler;
- Swissinfo: no feed advertised on any language edition;
- NHK World: the only feed found is Japanese and six weeks stale;
- The New Humanitarian: newest item three months old, articles answer 403;
- Global Voices in German and Simplified Chinese: newest items from 2025.

``full_text`` records whether the article pages yield a usable text
(France 24's extraction returns ~100 characters of chrome; Al Jazeera's
robots.txt forbids its article pages to us). robots.txt is re-read at fetch
time anyway — this flag only saves the attempt that is known to fail.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class CatalogueFeed:
    """One shipped feed — a base source every listener hears unless they untick it.

    Attributes:
        outlet: The outlet's display name.
        url: The feed URL (what a listener unticks it by).
        language: The feed's language (backend-canonical code): every one airs,
            translated into the listener's.
        full_text: Whether article pages yield a usable text.
    """

    outlet: str
    url: str
    language: str
    full_text: bool = True


CATALOGUE: Final[tuple[CatalogueFeed, ...]] = (
    CatalogueFeed("BBC News", "https://feeds.bbci.co.uk/news/world/rss.xml", "en"),
    CatalogueFeed("BBC Mundo", "https://feeds.bbci.co.uk/mundo/rss.xml", "es"),
    CatalogueFeed("BBC Afrique", "https://feeds.bbci.co.uk/afrique/rss.xml", "fr"),
    CatalogueFeed("BBC 中文", "https://feeds.bbci.co.uk/zhongwen/simp/rss.xml", "zh-CN"),
    CatalogueFeed("BBC News Brasil", "https://feeds.bbci.co.uk/portuguese/rss.xml", "pt"),
    CatalogueFeed("DW", "https://rss.dw.com/xml/rss-en-all", "en"),
    CatalogueFeed("DW", "https://rss.dw.com/xml/rss-de-all", "de"),
    CatalogueFeed("DW 中文", "https://rss.dw.com/xml/rss-chi-all", "zh-CN"),
    CatalogueFeed("France 24", "https://www.france24.com/fr/rss", "fr", full_text=False),
    CatalogueFeed("France 24", "https://www.france24.com/en/rss", "en", full_text=False),
    CatalogueFeed("France 24", "https://www.france24.com/es/rss", "es", full_text=False),
    CatalogueFeed("NPR", "https://feeds.npr.org/1001/rss.xml", "en"),
    CatalogueFeed("NPR World", "https://feeds.npr.org/1004/rss.xml", "en"),
    CatalogueFeed("ABC News (Australia)", "https://www.abc.net.au/news/feed/51120/rss.xml", "en"),
    CatalogueFeed("The Guardian", "https://www.theguardian.com/world/rss", "en"),
    CatalogueFeed("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml", "en", full_text=False),
    CatalogueFeed("Meduza", "https://meduza.io/rss/en/all", "en"),
    CatalogueFeed("The Kyiv Independent", "https://kyivindependent.com/news-archive/rss/", "en"),
    CatalogueFeed(
        "Agência Brasil", "https://agenciabrasil.ebc.com.br/rss/ultimasnoticias/feed.xml", "pt"
    ),
    CatalogueFeed(
        "ProPublica",
        "https://www.propublica.org/feeds/propublica/main",
        "en",
    ),
    CatalogueFeed("OCCRP", "https://www.occrp.org/en/feed", "en"),
    CatalogueFeed("Bellingcat", "https://www.bellingcat.com/feed/", "en"),
    CatalogueFeed("Agência Pública", "https://apublica.org/feed/", "pt"),
    CatalogueFeed("Global Voices", "https://globalvoices.org/feed/", "en"),
    CatalogueFeed("Global Voices", "https://fr.globalvoices.org/feed/", "fr"),
    CatalogueFeed("Global Voices", "https://es.globalvoices.org/feed/", "es"),
    CatalogueFeed("Global Voices", "https://it.globalvoices.org/feed/", "it"),
)

#: The base sources' addresses — what a listener may untick (enforced by the preferences).
CATALOGUE_URLS: Final[frozenset[str]] = frozenset(feed.url for feed in CATALOGUE)


__all__ = ["CATALOGUE", "CATALOGUE_URLS", "CatalogueFeed"]
