"""Prove the instance's web search door end to end on a running stack (lot 18).

Asks the keyless predicate whether the instance runs a search, then searches once
through ``connectors/instance_search`` — the door every surface uses — and prints
facts only: availability, the number of links, their hosts. Run in the API
container::

    python -m scripts.connectors.probe_instance_search
"""

from __future__ import annotations

import asyncio
import json
import sys
from urllib.parse import urlparse

from src.infrastructure.database.registry import import_all_models

import_all_models()

from src.domains.connectors.instance_search import (  # noqa: E402
    instance_search_available,
    search_instance,
)


async def _probe() -> dict[str, object]:
    available = await instance_search_available()
    if not available:
        return {"available": False}
    web = await search_instance("capitale de l'Australie", user_id=None, language="fr", count=5)
    news = await search_instance(
        "intelligence artificielle", user_id=None, language="fr", count=5, recency="week", news=True
    )
    return {
        "available": True,
        "web_links": len(web),
        "web_hosts": [urlparse(link.url).hostname for link in web],
        "news_links": len(news),
        "news_with_engine_line": sum(1 for link in news if link.note),
    }


def main() -> int:
    json.dump(asyncio.run(_probe()), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
