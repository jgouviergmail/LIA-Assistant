# ADR-382 — The instance searches the web for whoever has no key

**Status**: Accepted, 2026-11-13.
**Date**: 2026-11-13
**Amended**: 2026-11-13 — on by default and unfiltered (owner decision, see the amendment
at the end).

**Amends**:
[ADR-307](ADR-307-Keyless-Connectors-Belong-To-The-Instance.md) — a sixth keyless connector,
the instance's SearXNG, served only where the operator runs one (`search_not_deployed`).

## Context

LIA searches the web in four places: the chat's unified web search, the enrichment of an
answer with fresh results, the interest sweep, and the Tools' research assist. Each found
its page links through Brave, with the person's own key. A person with no Brave key (and no
Perplexity key) had Wikipedia and nothing else, on every one of those surfaces.

SearXNG is a metasearch engine an operator can run beside LIA: it asks public engines
(Google's programmable search, DuckDuckGo, Bing News, Brave's site…) on the server's own
address and merges what they return, with no key. Measured before any code
(`apps/api/scripts/connectors/measure_searxng.py`, `task connectors:searxng:measure`, free:
no paid API), on the image this decision pins, from a home connection like the production
host's — 24 queries in the six languages of the site, two spaced rounds and a burst of 12:

| What | Measured |
|---|---|
| Useful searches (3 results or more) | 58/60 — every language whole but Chinese news (6/8) |
| Wait | median 0.69 s, p95 1.61 s, max 3.0 s |
| Burst of 12 at once | 12/12 |
| Engines suspended or challenged | Brave's site (« too many requests ») within minutes, DuckDuckGo (CAPTCHA) — absorbed by the redundancy |
| News carrying a machine date | 0/15: the age and outlet travel as text (« Il y a 22 heures \| TF1 INFO ») |

## Decision

1. **A keyless connector the operator runs.** `ConnectorType.SEARXNG` joins the keyless
   types of ADR-307: no per-account row, the administrator's switch, and one more ceiling —
   `SEARXNG_URL` empty means the instance runs none (`REASON_SEARCH_NOT_DEPLOYED`). The
   `searxng` service ships in the compose files: always on in development, opt-in in
   production (the `searxng` profile), absent from the demonstrator. It is internal only:
   never published, its bot limiter and image proxy off (`infrastructure/searxng/settings.yml`),
   pinned by version and digest to the newest image at least two weeks old (SearXNG publishes
   several builds a day and no releases).

2. **The person's choice wins.** A person who configured Brave is searched with it,
   everywhere; the instance's search answers only for whoever has no Brave key, as Google
   Weather answers only for whoever configured no weather provider (ADR-307, decision 3). The
   Tools' research prefers the person's keys, then the instance, then Wikipedia.

3. **One door** (`connectors/instance_search.py`): `instance_search_available()` asks the
   keyless predicate in a session of its own, closed before anything is searched (ADR-304);
   `search_instance()` searches once and hands back plain links (`WebLink`: title, address,
   excerpt, and the engine's own line, written before the excerpt it dates). A failure RAISES,
   counted on the connector metrics every client shares (`connector_api_requests_total`,
   `connector_api_errors_total`, `connector_api_duration_seconds`, with the engines that could
   not answer as `engine_unresponsive`): each surface says it failed, none reads it as
   « nothing found » (ADR-303).

4. **Not an API-key client.** `SearXNGClient` authenticates nothing and its address is the
   operator's internal service, never a host a sandboxed run may be handed a key for (ADR-298
   derives those from the API-key clients). One shaper for the whole instance smooths the
   burst on one Redis key (`wait_for_slot`, ADR-254: a shaper, never a gate), one circuit
   breaker refuses a dead service at once, and a search is asked once — SearXNG already waited
   for its own slow engines.

5. **Every surface that searches the web reads it**, and the register files what ran:
   - the chat's unified search takes its links from it (`_search_links`), and a link search
     that failed is said in what the model reads;
   - the answer's enrichment searches it as `enrichment:searxng`, cached apart (a link one
     service found is never served as another's) and named for what it is in the prompt;
   - the interest sweep runs it as a source of its own — and every source now says, before it
     runs, whether it would ask its service (`applies`): a source that would ask nothing is
     skipped and files nothing, which also ends the « Brave consulted » filed for a person
     with no Brave key;
   - the Tools' research offers it as a provider (`searxng`).
   All three registers read it as the existing `web_search` domain.

## What this decision leaves, and says so

- **The radio** files an interest story by its publication date: SearXNG gives none (0/15),
  so the radio keeps its own-key rule.
- **The installer's wizard** does not offer the service: a self-hoster enables it by hand
  (profile, secret, URL — `docs/guides/GUIDE_SELF_HOSTING.md`). Offering it in the wizard
  means a question, a generated secret, a profile the installer stops by name and an image the
  release manifest locks: proposed, not done. *Done the same day: see the amendment.*
- **Engines throttle an address.** A busy instance will see more engines suspended; the
  operator reads `engine_unresponsive` and can raise or lower
  `CLIENT_RATE_LIMIT_SEARXNG_PER_SECOND`.

## Consequences

- A person with no search key gets web links on four surfaces where they had Wikipedia alone.
- One more container in production when the operator opts in: about 150 MB measured
  (limit 256 MB), and searches leave from the server's address to public engines.
- `ContentSourceStrategy.is_available` (synchronous, which could not ask anything) is replaced
  by `applies` (asynchronous, which does).

## References

- `apps/api/src/domains/connectors/clients/searxng_client.py`,
  `apps/api/src/domains/connectors/instance_search.py`, `apps/api/src/domains/connectors/keyless.py`
- `apps/api/src/domains/agents/tools/web_search_tools.py`,
  `apps/api/src/domains/agents/services/knowledge_enrichment_service.py`
- `apps/api/src/domains/interests/services/content_sources/searxng_source.py`,
  `apps/api/src/domains/tool_assists/selection_research.py`
- `infrastructure/searxng/settings.yml`, `docker-compose.dev.yml`, `docker-compose.prod.yml`,
  `scripts/release/build_self_host_bundle.py`, `scripts/deploy/prepare-prod.ps1`
- `apps/api/scripts/connectors/measure_searxng.py`, `apps/api/scripts/connectors/probe_instance_search.py`
- `docs/technical/WEB_SEARCH.md`

## Amendment 2026-11-13 — on by default, unfiltered (owner decision)

1. **On by default.** A person with no search key of their own should find web links on
   every installation, and a person with one sees no change: every surface asks the person's
   Brave key first. So:
   - the production template runs it (`COMPOSE_PROFILES=observability,searxng`,
     `SEARXNG_URL=http://searxng:8080`, a secret generated once with `openssl rand -hex 32`);
   - the installer asks `web_search` with **yes** as its default
     (`scripts/install/questions.py`): it starts the `searxng` profile, writes the URL and
     generates the secret, which it keeps across reconfigurations and while the search is
     off. Turning it off stops the container by name (`PROFILE_SERVICES`), and a prebuilt
     install pins its image (`searxng` joins `scripts/install/self_host_dependencies.json`,
     held equal to the production compose file by `test_self_host_compose_contract.py`). An
     installation recorded before the question keeps what it runs until it is asked again;
   - the Raspberry Pi deployment stages `infrastructure/searxng`
     (`scripts/deploy/prepare-prod.ps1`): `deploy-prod.Tests.ps1` read the omission off the
     compose file, which mounts `settings.yml` from there;
   - the demonstrator keeps none: its envelope starts no `searxng` service, its egress
     allowlist opens no public engine, and its search already runs on Brave.
2. **Unfiltered.** The owner wants the web as it is, from both providers. Brave filters
   « moderate » when its parameter is absent, so every Brave request sends `safesearch=off`
   (`BRAVE_SAFESEARCH_OFF`); every SearXNG request sends `safesearch=0`
   (`SEARXNG_SAFESEARCH_OFF`), whatever an operator's `settings.yml` holds. The clients'
   tests pin both.
3. **The engines it asks** are SearXNG's own defaults for the pinned image
   (`use_default_settings: true`, 81 of 261 engines enabled; LIA asks two categories). Web:
   Google (`google cse`), Brave's public site, DuckDuckGo, Wikipedia and Wikidata, plus
   engines that only answer conversions, definitions and translations. News: Brave News,
   DuckDuckGo News, Bing News, Google News, Reuters and Wikinews. Measured on 2026-11-13 over
   six searches: the web links came from Google, Brave and DuckDuckGo (Wikidata timed out);
   the news from Brave News, DuckDuckGo News, Bing News and Wikinews, Google News and Reuters
   refusing and being suspended. Moving the image is moving the engines: measure it again
   (`task connectors:searxng:measure`).
4. **Not measured**: whether its links are as relevant as the Brave API's. The person's Brave
   key keeps priority; a comparison bench is proposed, not run.
