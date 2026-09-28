"""What each of a listener's sources holds for them — the settings' view (ADR-324 decision 38).

Every base source of the catalogue, in its order, and every site the listener
added, each with what it published within the window a programme airs from and
how many of those stories the listener never heard. A story was heard when the
aired ledger holds its key or its fingerprint (another outlet's article of the
same story shares it): the counter says « never heard », exactly — an article
the station would leave out for telling the same event (decision 34) was not
heard, strictly.

The totals are what the station can air: the stories of the base sources the
listener ticked and of the sites they did not pause. An unticked source and a
paused site still say what they hold, on their own row, so ticking one back is
an informed choice. Pure: the stories, the ledger's sets and the sources are
inputs (the service reads them).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Collection, Sequence
from uuid import UUID

from src.domains.radio.newsroom.catalogue import CatalogueFeed
from src.domains.radio.repository import RadioSource, SourceStory
from src.domains.radio.schemas import (
    RadioBaseSourceResponse,
    RadioCustomSourceResponse,
    RadioSourcesResponse,
)


def _heard(story: SourceStory, keys: frozenset[str], fingerprints: frozenset[str]) -> bool:
    return story.key in keys or bool(story.fingerprint and story.fingerprint in fingerprints)


def sources_overview(
    *,
    catalogue: Sequence[CatalogueFeed],
    failing_base: Collection[str],
    own: Sequence[RadioSource],
    stories: Sequence[SourceStory],
    heard_keys: frozenset[str],
    heard_stories: frozenset[str],
    disabled_feeds: Collection[str],
    window_hours: int,
) -> RadioSourcesResponse:
    """Every source, what it holds, and what the station can air from them.

    Args:
        catalogue: The base sources, in the order the settings show them.
        failing_base: The base sources whose last readings failed (by address).
        own: The listener's sites.
        stories: What every source published within the window.
        heard_keys: The story keys the listener's ledger holds.
        heard_stories: The story fingerprints it holds.
        disabled_feeds: The base sources the listener unticked (by address).
        window_hours: The window the stories were counted over.

    Returns:
        The view.
    """
    base_count: Counter[str] = Counter()
    base_unheard: Counter[str] = Counter()
    own_count: Counter[UUID] = Counter()
    own_unheard: Counter[UUID] = Counter()
    for story in stories:
        fresh = not _heard(story, heard_keys, heard_stories)
        if story.own:
            own_count[story.feed_id] += 1
            own_unheard[story.feed_id] += int(fresh)
        else:
            base_count[story.feed_url] += 1
            base_unheard[story.feed_url] += int(fresh)
    base = [
        RadioBaseSourceResponse(
            url=feed.url,
            name=feed.outlet,
            language=feed.language,
            heard=feed.url not in disabled_feeds,
            failing=feed.url in failing_base,
            stories=base_count[feed.url],
            unheard=base_unheard[feed.url],
        )
        for feed in catalogue
    ]
    sites = [
        RadioCustomSourceResponse(
            id=site.id,
            feed_url=site.feed_url,
            title=site.title,
            language=site.language,
            paused=site.paused,
            failing=site.failing,
            stories=own_count[site.id],
            unheard=own_unheard[site.id],
        )
        for site in own
    ]
    ticked = [source for source in base if source.heard]
    running = [site for site in sites if not site.paused]
    return RadioSourcesResponse(
        base=base,
        own=sites,
        stories=sum(s.stories for s in ticked) + sum(s.stories for s in running),
        unheard=sum(s.unheard for s in ticked) + sum(s.unheard for s in running),
        window_hours=window_hours,
    )


__all__ = ["sources_overview"]
