"""Measure what an instance SearXNG answers LIA, before LIA relies on it (lot 18).

A MEASUREMENT, never a gate, and free: SearXNG is a metasearch engine the operator
runs; it asks public search engines on the host's own address. Whether that holds
from a home server — results for every language LIA speaks, dated news, a bounded
wait, no engine refusing a burst — is what decides if it can be the web search of
an account with no key of its own (today: Wikipedia alone).

Each query is asked the way LIA's client asks it (``format=json``, the person's
language, ``time_range`` for a recency, the ``news`` category for news), over a
corpus in the six languages of the site, in ROUNDS spaced like a person's turns,
then once as a BURST with no pause — the case a busy instance meets. Per query: the
status, the wait, the results, the engines that answered and those SearXNG reports
unresponsive (with their reason: a CAPTCHA, a timeout, « too many requests »).

Run against a SearXNG started from ``infrastructure/searxng/settings.yml``::

    python -m scripts.connectors.measure_searxng --url http://127.0.0.1:8888
    python -m scripts.connectors.measure_searxng --url http://searxng:8080 --rounds 1
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Final
from urllib.parse import urlparse

import httpx


@dataclass(frozen=True)
class Probe:
    """One query of the corpus.

    Attributes:
        key: Stable identifier.
        language: The language LIA would send (``zh-CN`` for Chinese, ADR-323).
        kind: ``fact``, ``news``, ``local``, ``product`` or ``technical``.
        query: The words searched.
        time_range: SearXNG's ``time_range`` for a recency, or None.
    """

    key: str
    language: str
    kind: str
    query: str
    time_range: str | None = None


CORPUS: Final[tuple[Probe, ...]] = (
    Probe("en-fact", "en", "fact", "boiling point of water at 2000 m altitude"),
    Probe("en-news", "en", "news", "central bank interest rate decision", "week"),
    Probe("en-local", "en", "local", "opening hours British Museum"),
    Probe("en-tech", "en", "technical", "python asyncio wait_for cancel timeout"),
    Probe("fr-fact", "fr", "fact", "capitale de l'Australie"),
    Probe("fr-news", "fr", "news", "grève SNCF", "week"),
    Probe("fr-local", "fr", "local", "horaires piscine municipale Lyon"),
    Probe("fr-product", "fr", "product", "prix lave-linge hublot 9 kg"),
    Probe("de-fact", "de", "fact", "Wie hoch ist die Zugspitze"),
    Probe("de-news", "de", "news", "Bundestag Abstimmung Haushalt", "week"),
    Probe("de-local", "de", "local", "Öffnungszeiten Bürgeramt München"),
    Probe("de-product", "de", "product", "Fahrradhelm Test Stiftung Warentest"),
    Probe("es-fact", "es", "fact", "cuántos habitantes tiene Madrid"),
    Probe("es-news", "es", "news", "elecciones resultados", "month"),
    Probe("es-local", "es", "local", "horario Museo del Prado"),
    Probe("es-tech", "es", "technical", "cómo instalar docker en ubuntu"),
    Probe("it-fact", "it", "fact", "altezza del Monte Bianco"),
    Probe("it-news", "it", "news", "maltempo allerta meteo", "week"),
    Probe("it-local", "it", "local", "orari Musei Vaticani"),
    Probe("it-product", "it", "product", "prezzo macchina caffè espresso"),
    Probe("zh-fact", "zh-CN", "fact", "长城有多长"),
    Probe("zh-news", "zh-CN", "news", "人工智能 最新 新闻", "week"),
    Probe("zh-local", "zh-CN", "local", "故宫 开放时间"),
    Probe("zh-tech", "zh-CN", "technical", "Python 异步 超时 处理"),
)

#: The pause between two queries of a round, like a person's turns (seconds).
ROUND_PAUSE_SECONDS: Final = 1.5
#: Queries asked back to back in the burst.
BURST_SIZE: Final = 12
#: What a result is worth reading as: three results is a search, fewer is a gap.
USEFUL_RESULTS_MIN: Final = 3
TOP_DOMAINS: Final = 5


@dataclass
class Outcome:
    """What one query got back.

    Attributes:
        key: The probe's key.
        phase: ``round-<n>`` or ``burst``.
        status: The HTTP status, 0 when no answer came.
        seconds: The wait.
        results: How many results.
        dated: How many results carry a publication date.
        engines: The engines that contributed a result.
        unresponsive: ``engine: reason`` for each engine SearXNG reports failed.
        domains: The distinct hosts of the first results.
        error: The transport failure's type, when nothing came back.
    """

    key: str
    phase: str
    status: int
    seconds: float
    results: int = 0
    dated: int = 0
    engines: list[str] = field(default_factory=list)
    unresponsive: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def useful(self) -> bool:
        """A search the person can be answered from."""
        return self.status == 200 and self.results >= USEFUL_RESULTS_MIN


def search_params(probe: Probe) -> dict[str, str]:
    """The query string LIA's client sends for this probe."""
    params = {"q": probe.query, "format": "json", "language": probe.language, "pageno": "1"}
    if probe.kind == "news":
        params["categories"] = "news"
    if probe.time_range:
        params["time_range"] = probe.time_range
    return params


def outcome_of(
    probe: Probe, phase: str, status: int, seconds: float, payload: dict[str, Any] | None
) -> Outcome:
    """Read one answer into an outcome (pure: the HTTP call is elsewhere)."""
    outcome = Outcome(key=probe.key, phase=phase, status=status, seconds=round(seconds, 3))
    if status != 200 or not isinstance(payload, dict):
        return outcome
    results = [item for item in payload.get("results") or [] if isinstance(item, dict)]
    outcome.results = len(results)
    outcome.dated = sum(1 for item in results if item.get("publishedDate"))
    outcome.engines = sorted(
        {engine for item in results for engine in item.get("engines") or [] if engine}
    )
    outcome.unresponsive = [
        f"{entry[0]}: {entry[1]}"
        for entry in payload.get("unresponsive_engines") or []
        if isinstance(entry, list | tuple) and len(entry) >= 2
    ]
    hosts: list[str] = []
    for item in results:
        host = urlparse(str(item.get("url") or "")).hostname
        if host and host not in hosts:
            hosts.append(host)
        if len(hosts) == TOP_DOMAINS:
            break
    outcome.domains = hosts
    return outcome


def tally(outcomes: list[Outcome]) -> dict[str, Any]:
    """Useful searches per language, per kind and per phase; waits; failing engines."""

    def share(rows: list[Outcome]) -> str:
        return f"{sum(row.useful for row in rows)}/{len(rows)}"

    by_language: dict[str, list[Outcome]] = {}
    by_kind: dict[str, list[Outcome]] = {}
    by_phase: dict[str, list[Outcome]] = {}
    probes = {probe.key: probe for probe in CORPUS}
    for row in outcomes:
        probe = probes[row.key]
        by_language.setdefault(probe.language, []).append(row)
        by_kind.setdefault(probe.kind, []).append(row)
        by_phase.setdefault(row.phase, []).append(row)
    waits = sorted(row.seconds for row in outcomes if row.status == 200)
    failing = Counter(entry for row in outcomes for entry in row.unresponsive)
    contributing = Counter(engine for row in outcomes for engine in row.engines)
    news = [row for row in outcomes if probes[row.key].kind == "news" and row.status == 200]
    return {
        "useful": share(outcomes),
        "by_language": {key: share(rows) for key, rows in sorted(by_language.items())},
        "by_kind": {key: share(rows) for key, rows in sorted(by_kind.items())},
        "by_phase": {key: share(rows) for key, rows in sorted(by_phase.items())},
        "wait_p50": round(statistics.median(waits), 2) if waits else None,
        "wait_p95": round(waits[max(0, round(0.95 * len(waits)) - 1)], 2) if waits else None,
        "wait_max": round(waits[-1], 2) if waits else None,
        "news_dated": f"{sum(row.dated > 0 for row in news)}/{len(news)}",
        "engines_contributing": dict(contributing.most_common()),
        "engines_unresponsive": dict(failing.most_common()),
        "transport_errors": dict(Counter(row.error for row in outcomes if row.error)),
    }


async def _ask(client: httpx.AsyncClient, url: str, probe: Probe, phase: str) -> Outcome:
    started = time.perf_counter()
    try:
        response = await client.get(f"{url.rstrip('/')}/search", params=search_params(probe))
    except httpx.HTTPError as exc:
        outcome = Outcome(probe.key, phase, 0, round(time.perf_counter() - started, 3))
        outcome.error = type(exc).__name__
        return outcome
    seconds = time.perf_counter() - started
    payload: dict[str, Any] | None = None
    if response.status_code == 200:
        try:
            payload = response.json()
        except ValueError:
            payload = None
    return outcome_of(probe, phase, response.status_code, seconds, payload)


async def run(url: str, rounds: int, timeout: float) -> list[Outcome]:
    """The rounds, then the burst, against one SearXNG."""
    outcomes: list[Outcome] = []
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        for number in range(1, rounds + 1):
            for probe in CORPUS:
                outcomes.append(await _ask(client, url, probe, f"round-{number}"))
                await asyncio.sleep(ROUND_PAUSE_SECONDS)
        burst = [CORPUS[index % len(CORPUS)] for index in range(BURST_SIZE)]
        outcomes.extend(
            await asyncio.gather(*(_ask(client, url, probe, "burst") for probe in burst))
        )
    return outcomes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--url", default="http://127.0.0.1:8888", help="the SearXNG to measure")
    parser.add_argument("--rounds", type=int, default=2, help="spaced passes over the corpus")
    parser.add_argument("--timeout", type=float, default=10.0, help="client wait, seconds")
    parser.add_argument("--out", type=Path, default=None, help="write every outcome as JSON")
    args = parser.parse_args(argv)

    outcomes = asyncio.run(run(args.url, args.rounds, args.timeout))
    summary = tally(outcomes)
    if args.out is not None:
        args.out.write_text(
            json.dumps(
                {"summary": summary, "outcomes": [asdict(row) for row in outcomes]},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    json.dump(summary, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
