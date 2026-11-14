# Web search — who finds the links, and the instance's own search

LIA searches the web in four places. This document says which service answers each of
them, how the instance's keyless search (SearXNG) is run, and how to tell what it did.
The decision and its measurements: [ADR-382](../architecture/ADR-382-The-Instance-Searches-The-Web-For-Who-Has-No-Key.md);
the keyless frame it extends: [ADR-307](../architecture/ADR-307-Keyless-Connectors-Belong-To-The-Instance.md).

## Who answers

| Surface | The person's own key | Without it | Always |
|---|---|---|---|
| Chat — unified web search (`web_search_tools.unified_web_search_tool`) | Perplexity (synthesis), Brave (links) | the instance's SearXNG (links) | Wikipedia |
| Enrichment of an answer (`knowledge_enrichment_service`) | Brave | SearXNG (`enrichment:searxng`) | — |
| Interest sweep (`interests/services/content_sources`) | Brave, Perplexity | SearXNG (source `searxng`) | the reflection |
| Tools — research a selection (`tool_assists/selection_research`) | Brave, then Perplexity | SearXNG | Wikipedia |
| Radio — interest stories (`radio/interest_search`) | Brave, then Perplexity | — (a story is filed by its date; SearXNG gives none) | — |

The person's own key always wins: the instance answers only for whoever configured none,
as Google Weather answers only for whoever configured no weather provider (ADR-307).

In the chat's unified search, a link service that failed — the person's Brave as much as
the instance's SearXNG — is said in what the model reads (« did not answer this time »),
never shown as « no links »: the tool reads Brave's raising door (`search_or_raise`), and
nobody answers in the place of a Brave that failed. The two other sources follow the same
rule: a Perplexity or a Wikipedia that was asked and failed is named in its own line, never
read as « no key » or « no article », and the tool's `sources_failed` lists every source
that did not answer. Such an answer is not kept in the search cache, so the same question
asked again is the retry. The text the model reads is rendered in one place
(`agents/tools/web_search_output.render_summary`), each provider's words wrapped as
external content.

Every search is **unfiltered**, the owner's decision (ADR-382 amendment): Brave filters
« moderate » when its parameter is absent, so each Brave request sends `safesearch=off`
(`BRAVE_SAFESEARCH_OFF`), and each SearXNG request sends `safesearch=0`
(`SEARXNG_SAFESEARCH_OFF`) whatever the instance's `settings.yml` holds.

## The door

Every surface asks the instance's search through `apps/api/src/domains/connectors/instance_search.py`:

- `instance_search_available()` — the keyless predicate (`connectors/keyless.py`): the
  administrator's switch and `SEARXNG_URL`. Read in a session of its own, closed before
  any search (ADR-304).
- `search_instance(query, *, user_id, language, count, recency=None, news=False)` — one
  search, plain `WebLink`s (`title`, `url`, `snippet`, `note`). `note` is the engine's own
  line: a news item's age and outlet, which SearXNG gives as text, never as a date;
  `WebLink.excerpt` writes it before the words it dates.
- A failure **raises**: a refused request (`httpx.HTTPStatusError`), an unreachable or slow
  service (`httpx.RequestError`), an open breaker (`ExternalServiceError`). Each surface says
  it failed — the chat tells the model the link search did not answer, the interest sweep and
  the Tools file it failed — and none reads it as « nothing found » (ADR-303).

`SearXNGClient` (`connectors/clients/searxng_client.py`) is not an API-key client: it
authenticates nothing, and its address is never a host a sandboxed run may be handed a key
for (ADR-298). It sends `format=json`, the person's language verbatim (SearXNG reads the
backend's `zh-CN`), `safesearch=0`, `time_range` for a recency and `categories=news` for
news, and cuts an overlong query at a word boundary (`SEARXNG_QUERY_MAX_CHARS`).

## The engines it asks

SearXNG's own defaults for the pinned image (`use_default_settings: true`: 81 of its 261
engines enabled), of which LIA asks two categories:

| Category | Engines |
|---|---|
| `general` (every search) | Google (`google cse`), Brave's public site (not its API, never a person's key), DuckDuckGo, Wikipedia, Wikidata — plus engines that only answer conversions, definitions and translations |
| `news` (a recent question: today, this week) | Brave News, DuckDuckGo News, Bing News, Google News, Reuters, Wikinews |

Measured on 2026-11-13 over six searches: the web links came from Google, Brave and
DuckDuckGo (Wikidata timed out); the news from Brave News, DuckDuckGo News, Bing News and
Wikinews, while Google News refused (« access denied ») and Reuters failed, both then
suspended by SearXNG. Engines refusing an address is ordinary: SearXNG merges what the
others return, and a link several engines found ranks higher. Moving the image moves the
engines: measure again (`task connectors:searxng:measure`).

## Running it

The `searxng` service ships in the compose files, configured by
`infrastructure/searxng/settings.yml` (mounted read-only): JSON enabled, bot limiter and
image proxy off — the service is internal only, never published. The file travels with
every road to production: the self-host bundle carries it
(`scripts/release/build_self_host_bundle.py`), and the Raspberry Pi deployment stages
`infrastructure/searxng` (`scripts/deploy/prepare-prod.ps1`; `deploy-prod.Tests.ps1`
refuses any directory a shipped compose file mounts and the staging list forgets).

| Where | How |
|---|---|
| Development | always on (`docker-compose.dev.yml`); `.env` sets `SEARXNG_URL=http://searxng:8080` |
| Production | on by default: the template's `COMPOSE_PROFILES=observability,searxng` and `SEARXNG_URL=http://searxng:8080`, with a secret generated once (`openssl rand -hex 32`); to refuse it, drop the profile and empty the URL |
| Installer | asked (`web_search`), **yes** by default: the `searxng` profile, the URL and a generated secret, kept across reconfigurations; answering no later stops the container ([GUIDE_SELF_HOSTING.md](../guides/GUIDE_SELF_HOSTING.md)) |
| Demonstrator | not offered: its envelope starts no `searxng` service, its egress allowlist opens no public engine, and its search runs on Brave |

SearXNG refuses to start on its default secret: with the profile on and no
`SEARXNG_SECRET`, the container exits, loudly. Measured footprint about 150 MB (limit
256 MB). The image is pinned by version and digest to the newest build at least two weeks
old when it was measured — SearXNG publishes several builds a day and no releases.

| Setting | Default | Meaning |
|---|---|---|
| `SEARXNG_URL` | empty | The service's address on the internal network; empty means the instance runs none |
| `HTTP_TIMEOUT_SEARXNG` | `8.0` | One metasearch (seconds); keep it above SearXNG's own `outgoing.max_request_timeout` (6 s) |
| `CLIENT_RATE_LIMIT_SEARXNG_PER_SECOND` | `3.0` | Searches per second for the WHOLE instance: one shaper on one Redis key (ADR-254), which smooths a burst and never refuses |

The administrator can switch the service off for every account in the connectors
administration, like any keyless service.

## Watching it

The connector metrics every client shares carry `connector_type="searxng"` (dashboard
10): `connector_api_requests_total{operation="search", status}` (`success`, `error`,
`timeout`), `connector_api_duration_seconds`, and `connector_api_errors_total{error_type}`
— `refused`, `unreachable`, `timeout`, `circuit_open`, `malformed` (an answer that is not
SearXNG's JSON), and `engine_unresponsive`, counted
once per engine SearXNG reports it could not ask (a CAPTCHA, « too many requests », a
timeout). A rising `engine_unresponsive` means the public engines are throttling the
server's address: lower `CLIENT_RATE_LIMIT_SEARXNG_PER_SECOND`.

The consultation register files each search under the `web_search` domain:
`enrichment:searxng` in a turn, `interest:searxng` for the sweep, `tool_assist:searxng`
for the Tools.

## Measuring it

```bash
task connectors:searxng:measure                                   # against the dev service
cd apps/api && python -m scripts.connectors.measure_searxng --url http://127.0.0.1:8888
docker exec lia-api-dev python -m scripts.connectors.probe_instance_search  # the door, end to end
```

The bench asks 24 queries in the six languages of the site (facts, news, places, products,
technical questions), in two spaced rounds then one burst, and prints the useful searches
per language, kind and phase, the waits, and the engines that answered or failed. It costs
nothing: no paid API is called.
