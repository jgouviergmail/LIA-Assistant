# ADR-221 : le réglage que l'exploitant voit est le réglage que le système applique

**Statut**: ✅ IMPLEMENTED (2026-08-16)
**Date**: 2026-08-16
**Origine**: contre-audit « Tokens fantômes » (F2)

## Contexte

Le champ `timeout_seconds` existait de bout en bout — dialogue
d'administration (libellé, infobulle, badge « modifié »), validation API
(`gt=0`), colonne `llm_config_overrides.timeout_seconds`, résolution
`LLMAgentConfig`, valeur déclarée pour les 57 emplacements — puis la chaîne
s'arrêtait : ni la factory ni l'adaptateur ne le lisaient, aucun client ne
recevait de timeout. Pendant ce temps, un second mécanisme fonctionnait sans
être visible : une quarantaine de sites enveloppent leur appel dans
`asyncio.wait_for` avec des durées lues dans les settings d'environnement.
Miroir exact de la doctrine ADR-184 : une valeur que le producteur peut
écrire mais que le système n'applique pas est un piège. S'y ajoutait
`router_llm_timeout_seconds`, défini depuis des années et lu nulle part — le
nœud routeur ne fait aucun appel LLM direct.

## Décision

### 1. Deux couches, deux rôles — et les deux sont vraies

Le `timeout_seconds` par emplacement devient la **borne transport par
tentative**, transmise au client de chaque provider (l'alias `timeout` est
accepté par les quatre SDK installés — vérifié : openai/deepseek
`request_timeout`, anthropic `default_request_timeout`, gemini `timeout` ;
le chemin Responses API le reçoit par paramètre explicite). Les barrières
`asyncio.wait_for` existantes restent la **borne d'expérience utilisateur**
au niveau des nœuds du graphe, inchangées — elles peuvent être plus serrées
(la barrière chat `response` reste à 60 s pendant que le client du même
emplacement, à 120 s, protège ses appelants SANS barrière : notification de
rappel, jobs de fond). Un `timeout` explicite dans le JSON `provider_config`
garde la priorité (échappatoire documentée).

### 2. Aucun défaut appliqué sans mesure préalable

Appliquer un timeout là où il n'y en avait pas peut couper des appels lents
qui aboutissaient. Plutôt qu'un déploiement en deux temps, les défauts ont
été confrontés à 30 jours de latences de production (p99 par nœud +
comptage des appels au-delà de 60 s) AVANT application. Six relèvements,
chacun commenté avec sa mesure dans `LLM_DEFAULTS` : `response` 60→120
(p99 47,4 s), `planner` 60→90 (44,7 s), `heartbeat_decision` 60→120
(59,7 s + 2 dépassements observés), `interest_content` 60→120 (~60 s + 1
dépassement), `open_loop_extraction` 45→90 (35,1 s),
`memory_reference_extraction` 30→45 (15,3 s). Les autres défauts dominent
leur p99 mesuré avec au moins ~2× de marge. Le test
`TestDefaultsHoldAgainstProduction` épingle chaque relèvement AVEC sa mesure.

### 3. Le réglage mort disparaît

`router_llm_timeout_seconds` et sa constante sont supprimés. Le champ visible
dans l'UI d'administration cesse d'être décoratif sans qu'une ligne de l'UI
ne change : c'est la couche d'application qui manquait.

## Conséquences

- L'administrateur qui règle un timeout règle réellement un timeout ; la
  clé de cache d'instances LLM intègre déjà `timeout_seconds` (model_dump),
  donc un changement d'override produit un client neuf.
- Les retries SDK (2 par défaut) peuvent porter l'attente cumulée d'une
  tentative au-delà du timeout unitaire — c'est le rôle assumé de la
  barrière externe, qui coupe l'expérience utilisateur comme avant.
- Tout futur emplacement déclare son timeout (test : aucun
  `timeout_seconds=None` dans `LLM_DEFAULTS`).

## Amendment 2026-10-28 — the per-attempt timeout no longer multiplies: a generation whose outcome is unknown is never relaunched

Measured (spec 2026-10-21 §0ter E2, local server): the clients LIA builds sent THREE requests after a
read timeout on the OpenAI wire and on Anthropic — the slot's timeout multiplied by three, and a
generation that may have run and been billed bought again twice — and Gemini six after a 500 or a
429. One declared policy now holds every family (`infrastructure/llm/providers/retry_policy.py`,
owner decision Q3 (a)): never after a timeout, nor after any transport failure once the request may
have been sent; at most `LLM_TRANSIENT_RETRY_MAX` relaunches after a 429, a 5xx or a connection that
never reached the provider; never a stream once its first byte arrived. The slot's timeout is
therefore the bound of the ONE attempt that may have run. Each family receives the policy through
its SDK's own seam (adopted clients on the OpenAI wire and Anthropic; on Gemini the attempts count
AND the httpx transport, whose failure after the send its predicate never retries — the aiohttp
branch re-sent once after a lost connection whatever the options said; Ollama has no loop),
measured per `ProviderType` by `test_retry_policy.py` against a real local server, asynchronous and
synchronous, timeout and lost connection. The billed generations LIA calls outside the chat factory
(an image, an OpenAI spoken answer) are adopted through `adopt_relaunch_policy`.

Retry happens at ONE layer: a caller's own loop — the structured-output door, the compaction —
asks `client_retries.caller_may_relaunch`, which leaves every call to a client owning its retries
(zero included: `LLM_TRANSIENT_RETRY_MAX=0` means no relaunch at all, never the door's three) and
sends again only a call that never reached the provider, on a client without a loop (Ollama),
within the same budget. The agents' model-retry middleware cannot see the model, so it relaunches
only a call that never left (`never_reached_the_server`) — it buys nothing twice. **Nor does a
caller answer a failed call with another request** — the planner's and the ReAct loop's buffered
call after a failed stream, the structured output's next door after the auto-tool door: each is a
second generation unless the first generated nothing, so `client_retries.may_send_in_another_form`
allows it only for a deterministic refusal, a failure off the wire (a capture defect), or a call
`caller_may_relaunch` allows (fresh review 2026-10-29: after a read timeout the SDK sent nothing
again, and these callers then sent the whole generation again). The operator's failover chain
(`FALLBACK_MODELS`) is entered only for a failure whose outcome is known — an error status, or a
request that never left — and never after a timeout or a connection lost once sent
(`fallback_policy.KnownOutcomeFallbackMiddleware`, `request_outcome.outcome_unknown`); it starts at
the first fallback, never at the primary again, whose client already spent its budget. **The chain
is not mounted today**: `create_agent_middleware_stack` adds it only when its caller passes the
agent's `primary_model`, and its one caller (`base_agent_builder`) never did, before or after this
amendment — whether to wire it or remove it is an owner decision, still open.

## Amendment 2026-10-29 — a connector request follows the same rule, and a create carries the provider's own idempotency

Measured on 2026-10-28 (spec §0ter E4) with the real `GoogleCalendarClient.create_event` against a
server that creates the event and then answers after the read timeout: the request loop of
`BaseOAuthClient` sent the POST three times and made **three events**, then reported a failure.
Microsoft's creates go through the same loop, and Apple's retry loop resent any failure, where caldav
mints a new uid on every save. Whether a request may have left is now decided once, for the model
clients and the connectors alike (`infrastructure/utils/request_outcome.py`, moved out of
`client_retries`); the Microsoft paging loop and Google's raw downloads ask the same policy (GET only
today, so nothing changes there).

- **A transport failure is retried only when the request cannot repeat an act**
  (`connectors/clients/retry_policy.may_resend`): its method is replay-safe (PATCH included — both
  providers apply it as a merge of the fields it names), its caller declares it replay-safe
  (`_make_request(..., idempotent=True)`: Google's `freeBusy`, Gmail's trash, untrash and label
  changes), or it never left. Every other POST is sent once after it may have been received — the
  mail sends already were (ADR-344). A read keeps its resends.
- **A create that must survive a lost answer carries the provider's own idempotency**, derived from
  the effect register's key (ADR-263, `provider_idempotency_id`): a Graph `transactionId` (Graph keeps
  one event, so the create may be resent), a CalDAV `uid` fixed before Apple's retry loop (the object
  URL derives from it, so a resend writes the same object; an Apple contact's uid is drawn once per
  call before its loop, not derived from the key — its resends write one contact), and a
  Google event `id`: the create is declared replay-safe and resent like the other two, because Google
  refuses an id it already holds, live or deleted, with a 409 — and the client then **reads the event
  back by `GET`**, as it does after any failure but a 4xx other than 409 — every attempt carried the
  act's own id, and resends spent on a 5xx or a 429 after a kept first attempt fail with no cause
  (third fresh review). Found, the create happened;
  « cancelled » is final (the act was undone); « not found » is read again, `CREATE_SETTLE_READS`
  times `backoff_seconds` apart, before the failure stands. A call outside any effect scope mints its
  own key, so its own resends stay safe.
- **Measured on a real Google calendar (2026-10-29, owner-authorised, probe event far in the future,
  no attendee, deleted after):** the derived id is accepted (one POST); the same act sent again gets a
  409 and is read back (no second event); a deleted act sent again gets a 409, reads « cancelled » and
  fails. A create whose answer was lost (read budget forced to 50 ms) first exposed a defect: the
  immediate read answered 404 while Google was still writing — the act was reported failed and the
  event was there three seconds later. With the create resent and the bounded read, the same scenario
  ends with three POSTs carrying one id, one event and a success. Graph and iCloud were not measured
  (no active account on dev).
- The confirmed draft hands the client its key (`calendar_draft_execution`, `current_scope()`); the
  same scenario now ends with one event and a success on the three providers
  (`test_calendar_create_idempotency.py`). The complexity of `_make_request` did not grow (29).

Not measured: a live Graph or CalDAV call (no active account on dev). Those two contracts are their
documented ones: Graph `transactionId`, CalDAV objects addressed by uid. Google's was measured (above).
