# Une session vocale, deux carriers, deux modes : le téléphone personnel gagne le mode Live, le navigateur direct gagne le relais — et le pont de délégation devient un seam serveur

**Date** : 2026-09-20 · **Version** : 1 · **Statut** : ANALYSE systémique, en attente
d'arbitrage — zéro code métier · **ADR cible** : ADR-301 (amende ADR-290 lots 4, 7, 8 ; ADR-299
spec A3/A7 ; ADR-300 wave 4 ; ADR-263 ; ADR-272 amendement 2026-09-20 ; ADR-185) ·
**Sources externes lues** : ElevenLabs Agents — `create agent` (webhook tools : `execution_mode`,
`response_timeout_secs`, `pre_tool_speech`, `interruption_mode`), `post-call webhooks` (forme du
transcript : `tool_calls`, `tool_results`, `tool_latency_secs`), client events (troncature 64 KB
d'un résultat d'outil).

---

## 0. Décisions du propriétaire déjà prises (2026-09-20)

| # | Décision | Portée |
|---|---|---|
| D1 | Le mode Live téléphone **supprime** la synthèse + relais de fin d'appel ; sa fin est celle du Live navigateur (tours vocaux archivés, carte de clôture, décision, apprentissage). | téléphone |
| D2 | Le mode Live **direct** navigateur **gagne** la synthèse + relais de fin de session (celle du téléphone direct) — symétrie parfaite des deux politiques de fin. | navigateur |
| D3 | Un seul apprenant par mode : délégué → les tours vocaux ; direct → le tour relayé (les six extractions d'un tour parlé). | les deux |
| D4 | Réglage **propre au téléphone**, dans « Téléphonie · Mon identité » ; valeur par défaut **Live** (B). Le navigateur garde son choix par session dans le menu du casque. | réglage |
| D5 | Mode Live téléphone = **symétrie stricte** (A) : une seule fonction `send_to_lia`, aucun outil de lecture direct — « sinon on perd la traçabilité dans la discussion, ce qui est tout l'intérêt du Live ». | téléphone |
| D6 | Modèle : **B+** — contexte borné `domains/voice_sessions/` (objet de valeur + politiques), stockage par carrier (Redis pour le navigateur, `phone_calls` pour le téléphone), **le pont de délégation comme seam serveur unique**, le navigateur ne migrant qu'après preuve. | architecture |
| D7 | La mesure du webhook `async` ElevenLabs est le **lot 0**, en production sur le numéro vérifié du propriétaire (la téléphonie n'est pas complètement paramétrée sur Docker dev). | méthode |

---

## 1. Dépouillement du besoin

### 1.1 L'intention réelle

Le besoin brut : « un switch Live / Live direct dans Mon identité ; si Live, le téléphone agit
comme le Live OpenAI/Gemini/ElevenLabs, avec actions directes dans la discussion courante ;
symétrie parfaite pour tous les canaux ; factoriser live / live direct ». L'intention derrière :

1. **Traçabilité** — ce que la personne demande au téléphone doit apparaître, être exécuté et
   être confirmé (HITL) **dans sa conversation**, pendant l'appel, comme depuis le casque.
   Aujourd'hui l'appel personnel ne produit qu'un tour relayé après coup : l'action est différée,
   la conversation ne reflète pas l'échange, et LIA « ne fait rien pendant l'appel » (le prompt le
   dit : *« Nothing you say on this call performs an action by itself »*,
   `agents/prompts/v1/telephony_self_call_system_prompt.txt` § agent_identity).
2. **Un seul modèle mental** pour quatre situations (2 carriers × 2 modes), donc **un seul code**
   pour ce qui est commun — parce que l'étape suivante (HITL + mutables en direct) doit s'écrire
   une fois.
3. **Un réglage** que la personne comprend : au téléphone LIA appelle, la personne ne choisit
   pas au décroché — le choix se fait avant, dans les réglages.

### 1.2 Faits vérifiés dans le code (zéro extrapolation)

| Fait | Preuve |
|---|---|
| Le navigateur Live a deux modes choisis **par session** : `LiveSessionMode = "delegated" \| "direct"`, `POST /live/sessions {mode}`. | `live/schemas.py:25,368-377` ; menu `voice-toggle.tsx:195-216` (`startLive('delegated'/'direct')`) |
| Le mode délégué ne tient **aucun** outil : une fonction `send_to_lia` (`LIVE_DELEGATION_TOOL_NAME`), le mandat dit « anything … {delegate} ». | `core/constants.py:6322` ; `live_system_prompt.txt` ; `live/mandate.py:19,118` |
| Le pont navigateur est en TypeScript et tient les règles : plus récent gagne (stop du tour), attente bornée, réponse tardive poussée en texte, question HITL = résultat, aplatissement + borne en tokens, `superseded`/`timed_out`/`result_cut`/`empty_request`. | `apps/web/src/lib/live/delegation.ts:1-25, 160-280` ; `session-controller.ts:330-370` (`send = chat.sendMessage(request,{live_session_id, spoken_text})`, `stop`, `readAnswer`) |
| Un tour délégué est un `POST /chat/stream` ordinaire du navigateur, estampillé `live_session_id` + `spoken_text`. | `agents/api/router.py:722-723` ; `service.py:470-471` |
| La carte de clôture, les tours vocaux et l'apprentissage se retrouvent par la métadonnée `live_session_id` (`session_run_ids`, `session_voice_rows`, `count_voice_turns`). | `live/summary.py:76-160` |
| `LiveService.end` : agrégat des runs délégués + run de session, carte `render_summary_markdown(mode=…)`, décision `route="live_session"`, apprentissage **sauf** en direct ; `archive_turn` **refuse** une session directe (`raise_live_direct_not_archived`). | `live/service.py:617-756` |
| Le mode direct navigateur réutilise **déjà** le jeu d'outils du téléphone (`available_live_tools`, `VoiceToolHost.live_session`) et sa porte `POST /live/sessions/{id}/tools`. | `live/direct_mandate.py:1-50` ; `live/tool_door.py:60-100` ; `agents/telephony/live_tools.py:120-200` |
| Le téléphone personnel : `call_me_tool` → contexte riche (`build_owner_context`) → outils de lecture provisionnés par empreinte (`ensure_vendor_live_tools`) → `initiate_call(kind=SELF, live_tools=…)` ; les outils sont **attachés à l'AGENT** (le vendeur refuse `tool_ids` dans un override) puis détachés en fin d'appel. | `agents/tools/telephony_self_tools.py:122-190` ; `telephony/service.py:244-282,328-490` ; `agents/telephony/live_tools.py:560-660` |
| Le mandat SELF est rendu serveur (`str.format`, syntaxe vendeur neutralisée), avec blocs `no_context`/`live_tools`/`personality` ; table `MANDATES` bornée par un assert d'amorçage (ADR-085). | `telephony/mandates.py:70-278` |
| La porte de rappel : `POST /telephony/tools/{tool_name}` — flag `telephony_live_tools_enabled`, `call_id` du corps, appel SELF **vivant** + jeton dérivé du secret, outil offert, budget par appel (Redis `telephony_live_tool:` USER_RUNTIME), puis `run_live_tool`. | `agents/telephony/live_tools_router.py:100-200` ; `telephony/live_tools.py:252-326` ; `cache/key_families.py:125` |
| Le retour d'appel : `process_completed_call` → `process_owner_call` : synthèse **avant** la revendication `RELAYING`, détachement des outils, `run_relay`, `settle_owner_call`. | `telephony/return_synthesis.py:329-360` ; `telephony/owner_call.py:1-199` |
| Le relais pilote le **moteur de chat côté serveur** : `StreamRequest(spoken_by_person=True, origin=RunOrigin(kind="phone_call", hidden=False), execution_mode=celui de la personne)` → `stream_instruction` → `RunResult(outcome, text, interrupt)`. Dix `RelayOutcome`. | `infrastructure/scheduler/phone_relay_runner.py:80-200` ; `out_of_turn_run.py:142-240` |
| `stream_instruction` appelle `AgentService().stream_chat_response(...)` **sans** `original_run_id`, `live_session_id`, `spoken_text` : une résomption HITL n'est **pas** possible par ce moteur aujourd'hui (le relais s'en protège par `conversation_has_pending_hitl` → `PENDING_QUESTION`). | `out_of_turn_run.py:415-467,278-320` |
| Sur la porte HTTP, la résomption HITL est décidée par l'appelant : `check_pending_hitl_uncached` → `original_run_id` ; `is_hitl_resumption = original_run_id is not None`. | `agents/api/router.py:480-740` ; `service.py:634` |
| Les plafonds (compte + instance) sont **dans** `stream_chat_response` (« PRE-STREAM GATES »), donc tout tour délégué y passe ; le moteur hors tour lit le refus en `QUOTA_BLOCKED`. | `service.py:514-520` ; `out_of_turn_run.py:89-110` |
| Un tour `spoken_by_person` est **attendu** pour la porte d'effets (`is_automated_source=False` → scope.source « user » → un `confirm` INTERROMPT comme dans le chat, il n'est pas refusé). | `effects/gate.py:111-175` ; `out_of_turn_run.py:447-452` |
| `BACKGROUND_RUNS_ENABLED` est **false** dans `.env.example` et `.env.prod.example` (true sur dev) : le broker Redis / le réattachement `GET /runs/{stream_id}/stream` ne sont pas un acquis de production. | `core/config/background_runs.py:37` ; `.env.prod.example` |
| L'annulation d'un run (`request_cancel`) n'atteint que le **producteur détaché** (`background_runner.py:252`) ; un run consommé inline par `stream_instruction` ne la voit pas. | `run_stream_broker.py:550-575` |
| Colonnes d'identité téléphonique : mixin `PhoneIdentityColumns` (`phone_number_encrypted`, `phone_number_verified_at`, `phone_rich_context_enabled`, `phone_disabled_domains`). Réponse/mise à jour : `TelephonyIdentityResponse`, `TelephonyIdentityUpdateRequest` (au moins un switch). | `users/phone_identity_columns.py` ; `telephony/schemas.py:331-404` ; `telephony/identity.py:210-249` |
| Front : `TelephonyIdentitySection.tsx` (`RichContextSwitch`, `DomainsPanel`), hook `useTelephonyIdentity` sur `/telephony/identity` ; pattern de liste à glyphes `GlyphSelect` (`ExecutionModeField`). | `components/settings/TelephonyIdentitySection.tsx:278-330` ; `hooks/useTelephonyIdentity.ts:45-53` |
| Le bandeau direct promet « nothing said here is recorded by LIA » ; la carte de clôture directe dit « direct session, nothing recorded ». | `locales/en/translation.json` `live.direct_notice`, `live.summary.body_direct` ; `LiveBanner.tsx:220-227` |
| Le transcript vendeur post-appel porte par tour `role`, `message`, `tool_calls[{request_id, tool_name, params_as_json}]`, `tool_results[{result_value, tool_latency_secs, is_error}]`, `time_in_call_secs`. | doc ElevenLabs post-call webhooks (lue 2026-09-20) ; `telephony/payload.py:43-62` ne lit que `role`/`message` |
| Un webhook tool ElevenLabs déclare `execution_mode ∈ {immediate, post_tool_speech, async}`, `response_timeout_secs ∈ [5, 300]` (défaut 20), `pre_tool_speech ∈ {auto, force, off}`, `interruption_mode`. Notre `telephony_live_tool_timeout_seconds` est borné `le=60`. | doc ElevenLabs `agents/create` ; `core/config/telephony.py:247-256` |
| Tailles (SLOC logiques / plafond) : `live/service.py` **594/600**, `agents/telephony/live_tools.py` **593/600**, `agents/api/service.py` 1027/1037, `agents/api/router.py` 759/770, `out_of_turn_run.py` 292, `telephony/service.py` 395. | `scripts/audit/measure_sloc.py` (mesuré 2026-09-20) |
| Cycles : `live → telephony` (direct_mandate importe `self_call_context`) et `live → agents` existent ; `telephony ✗→ agents` est le cycle T2 évité par `infrastructure/scheduler/phone_relay_runner.py` ; le ratchet compte les paires bidirectionnelles de `src/domains/*`, imports locaux inclus. | `scripts/audit/measure_coupling.py:85-110` ; `.coupling-cycles-baseline.json` (24) |
| Coût : `elevenlabs_telephony` et `live` sont **USER** (la voix est sur la clé de la personne, jamais comptée) ; `llm` est **INSTANCE** (chaque tour délégué est compté, ADR-272). | `usage_limits/cost_bearers.py` |
| Dépense de la synthèse de relais : `telephony/self_call_relay.py` est sur la route `CALLER` → `telephony/synthesis_usage.py` (capture puis `track_proactive_tokens` sous `phone_call_<hex>`). | `infrastructure/llm/spend_roads.py` ; `self_call_relay.py:131-180` |

### 1.3 Non-dits explicités et hypothèses (chacune vérifiée)

| # | Non-dit | Réponse retenue | Fondement |
|---|---|---|---|
| H1 | « Actions directes dans la discussion courante » = un **tour de chat complet** par demande, dans la conversation active de la personne, avec HITL. | Oui — exactement ce que fait le navigateur (`send_to_lia` → `POST /chat/stream`) ; côté serveur la même chose par `stream_chat_response` avec `spoken_by_person=True`. | §1.2 lignes 4, 9-12 |
| H2 | La question HITL doit pouvoir être **répondue au téléphone**. | Oui : le résultat de la délégation est la question ; la réponse de la personne est une nouvelle délégation routée en **résomption** (`original_run_id` lu sur l'enregistrement HITL Redis). Le moteur hors tour ne le sait pas faire : **il faut l'y ajouter** (lot 2). | `router.py:480-740`, `out_of_turn_run.py:415-467` |
| H3 | Le vendeur peut attendre un tour de graphe (5-40 s). | Documenté : `response_timeout_secs` jusqu'à 300 s, `execution_mode: async` (« runs the tool in the background without blocking »). **À mesurer** (lot 0) : le résultat rejoint-il le LLM après que la voix a continué ? que fait-il à l'expiration ? deux délégations concurrentes ? | doc ElevenLabs |
| H4 | Le téléphone n'a **aucun canal de réponse tardive** (pas d'injection de texte dans un appel sortant en cours). | Vrai à notre connaissance (aucune API d'injection côté appel téléphonique) ; conséquence : la borne du pont téléphone = le timeout vendeur − marge, et au-delà la voix dit « la réponse sera dans la discussion » (ligne `timed_out`, déjà écrite). | `live_lines.txt` `timed_out` |
| H5 | Le mode Live téléphone garde le **cadre téléphonique** (vérification d'identité de qui décroche, sortie acoustique, `end_call`, confinement) — le navigateur n'en a pas besoin (la personne est authentifiée). | Oui : blocs `<who_you_are_talking_to>`, `<security_and_containment_protocols>`, `end_call` sont propres au carrier ; seuls les blocs « what LIA does » et « how a delegation behaves » sont partagés. | `telephony_self_call_system_prompt.txt`, `live_system_prompt.txt` |
| H6 | En Live téléphone, ni contexte riche (`<what_you_know>`), ni domaines (switches lot 8) : la voix délègue tout. | Symétrie avec le navigateur délégué (mandat sans données). Les deux réglages existants (`rich_context`, `disabled_domains`) ne s'appliquent qu'au **direct** : l'UI les montre sous ce mode. | D5 ; `live_system_prompt.txt` |
| H7 | La **personnalité** et l'**état intérieur** (psyché) restent dans le mandat Live téléphone. | Oui : lot 9 ADR-290 (personnalité) et ADR-300 (psyche block) — même producteurs. | `mandates.py:_self_prompt`, `live/mandate.py::MandateInputs.psyche_block` |
| H8 | Fin d'appel Live : quels tours archiver en `live_turn` ? | Les échanges **purement vocaux** : les tours du transcript vendeur **sans** `tool_calls` nommant `send_to_lia` (miroir de `turn.delegated` côté navigateur, `session-controller.ts:624`). Les tours délégués sont déjà dans le fil (le graphe les a archivés). | doc transcript ; `summary.py:session_run_ids` |
| H9 | La facture d'un appel Live = la somme des tours délégués + le run de l'appel. | Oui, comme la carte Live (`aggregate_usage([*run_ids, record.run_id])`) ; `GET /telephony/calls` lit aujourd'hui **une** ligne `phone_call_<hex>` : il doit lire l'agrégat de la clé de session. | `live/service.py:678`, `telephony/router.py:185-215` |
| H10 | Direct navigateur + relais : d'où vient le transcript ? | Le navigateur ne conserve rien (`archiveTurn` jette le tour en direct, `session-controller.ts:620-625`). Deux options : (a) le navigateur envoie le transcript à `end` ; (b) chaque tour est posté à `/turns` et **accumulé dans le record Redis** (non archivé), la synthèse le lisant à `end`. **(b) retenu** : robuste à une fermeture d'onglet (pas de `beforeunload` aujourd'hui — vérifié), borné (`LIVE_DIRECT_TRANSCRIPT_MAX_CHARS`), et symétrique du téléphone (le transcript est chez le carrier, pas dans l'archive). | `session-controller.ts`, `session_store.py` |
| H11 | Le relais navigateur peut-il tourner **dans** la requête `end` ? | Non : un tour de graphe dure 5-40 s et `end` est appelé au raccroché. Le relais est **planifié** (tâche détachée avec propriétaire, `infrastructure/async_utils.safe_fire_and_forget`), `end` répond `relay: "scheduled"`, la carte dit que la suite arrive dans le fil, et le fil se recharge (§3.6). | `owner_call.py` (le téléphone le fait dans le webhook, hors requête utilisateur) |
| H12 | Le relais direct navigateur, qui apprend ? | Le tour relayé (`spoken_by_person=True` → les six extractions) ; aucun `live_turn` n'existe en direct, donc **rien n'est appris deux fois** (D3). | `out_of_turn_run.py:447-452` |
| H13 | `TELEPHONY_LIVE_TOOLS_ENABLED=false` (défaut) rend le mode Live **impossible** (le vendeur ne peut pas rappeler l'API). | Vrai : la route n'existe pas sans le flag. Donc le réglage publie `live_available` + raison, l'UI grise « Live », et la numérotation **retombe en direct** (comptée). « L'UI se voit offrir ce que l'API accepte » (ADR-184). | `live_tools_router.py:120` |
| H14 | « Plus récent gagne » sur le téléphone : deux webhooks concurrents peuvent tomber sur **deux workers** (`WEB_CONCURRENCY=4` en prod). | Une annulation en mémoire ne suffit pas : signal Redis par appel (famille USER_RUNTIME déclarée), le pont en cours l'observe et s'annule ; le bail de conversation (`active_run_lease`) est libéré par l'ancien puis pris par le nouveau, attente bornée. | `run_stream_broker.py:444-512` ; ADR-271 (« un seul processus ») |
| H15 | Le mode par défaut **Live** change le comportement de tous les comptes existants dès la migration. | Assumé (D4-B) ; un compte dont l'instance n'a pas le flag reste en direct de fait (H13). | — |

### 1.4 Faux positifs et faux négatifs traqués

- **Faux positif évité** : « le moteur hors tour sait résumer une question HITL » — il **détecte** l'interruption (`_StreamReader`) mais ne sait pas **reprendre** (pas d'`original_run_id`). Sans le lot 2, la réponse « oui » de la personne au téléphone ouvrirait un **nouveau** tour sur un graphe interrompu.
- **Faux positif évité** : « le stop du chat (`POST /runs/active/cancel`) annule un tour serveur » — il ne touche que le producteur détaché ; le pont serveur consomme inline et doit s'annuler lui-même.
- **Faux positif évité** : « le navigateur tient le transcript d'une session directe » — il le jette tour par tour.
- **Faux négatif évité** : réécrire une projection vocale — `flatten_for_voice` existe en TS ; côté serveur, `markdown_to_plain_text` (lot 13 ADR-276) + `html_to_markdown` (ADR-291) + `filter_for_llm_context` existent : le Python compose l'existant, et un **corpus d'accord** (mêmes entrées, mêmes sorties en vitest et pytest) épingle les deux implémentations, comme les onze mails d'ADR-281.
- **Faux négatif évité** : la déclaration de fonction `send_to_lia` — `live/mandate.py` la décrit déjà (`tool_description`), `telephony/live_tools.webhook_tool_body` sait fabriquer un webhook tool ; il ne manque que le corps async et son empreinte.
- **Faux négatif évité** : la fermeture Live (carte, décision, apprentissage) existe dans `LiveService.end` ; elle est **extraite**, pas réécrite.

### 1.5 Arbitrages majeurs retenus (et pourquoi)

| Arbitrage | Retenu | Justification par les patterns en place |
|---|---|---|
| Où vit le commun | `domains/voice_sessions/` (objet de valeur, politiques, pont, relais, mandat partagé) ; **n'importe ni `agents`, ni `live`, ni `telephony`** au niveau module ; le moteur est atteint par `infrastructure/scheduler/out_of_turn_run` et les extracteurs d'apprentissage sont **offerts** par `agents` à l'amorçage. | Le modèle `domains/shared/portrait_sources.py` (« le registre est OFFERT, jamais cherché ») et le placement de `phone_relay_runner` (T2). Le ratchet de cycles refuserait `telephony ↔ agents`. |
| Le pont | **Serveur, en Python, pour le téléphone maintenant** ; le navigateur garde `delegation.ts` tant que `BACKGROUND_RUNS_ENABLED` n'est pas la norme (sinon le tour délégué cesse de s'afficher en flux dans le fil). Le chemin de migration est écrit (§3.4). | H14, H4, `.env.prod.example` ; ne pas régresser un pont **mesuré** (2026-09-18/19). |
| Consommation du tour côté serveur | Inline (le pont possède la tâche qui consomme le générateur), comme `stream_instruction` ; annulation = `task.cancel()` + signal Redis inter-workers. | `out_of_turn_run._one_attempt` ; ADR-117 (le tracker persiste même sur annulation). |
| Transcript direct navigateur | Accumulé dans le record Redis via `/turns` (non archivé), synthèse à `end`. | H10 |
| Relais direct navigateur | Planifié à `end`, hors requête ; notification SSE → rechargement du fil. | H11 |
| Où l'euro atterrit | Un tour délégué = son propre run (registres, compteur) ; l'appel/la session = la somme (`aggregate_usage`), affichée par la carte et par `GET /telephony/calls`. La synthèse de relais devient **ACCOUNTED** sous le run de la session (`out_of_turn_spend` + `TokenTrackingCallback`) pour les deux carriers. | ADR-272 amendé ; `billed_cost_eur` |
| Réglage | Colonne `users.phone_call_mode` (`live` \| `live_direct`, NOT NULL, `server_default='live'`), dans le mixin `PhoneIdentityColumns` ; exposé/modifié par l'API identité ; `call_mode_effective` + `live_available` publiés. | lot 8 ADR-290 (`phone_disabled_domains`) |
| Budget de délégations par appel | Réutilise le compteur et le réglage du budget d'outils (`telephony_live_tool_max_calls_per_call`), clé propre. | « un bond publié = un bond appliqué » (ADR-184) |
| Timeout vendeur du webhook `send_to_lia` | Nouveau réglage `telephony_delegation_timeout_seconds` (défaut 90, bornes 20..290 — le vendeur accepte 300) ; le pont attend `timeout − TELEPHONY_LIVE_TOOL_INNER_MARGIN_SECONDS`. | `telephony_live_tool_timeout_seconds` (même forme) |

### 1.6 Questions résiduelles (décision métier hors analyse technique)

1. **Lot 0 en production** : quand, et sur quel créneau (deux appels de ~2 min sur ton numéro,
   facturés sur ton compte ElevenLabs). Le script est prêt à écrire ; il ne touche ni l'agent ni
   les outils de production (agent et outil **temporaires**, supprimés à la fin).
2. **Le bandeau et la carte du direct navigateur** : le texte proposé — « Session directe : LIA lit
   pour toi en direct ; ce que tu lui demandes de faire est pris en charge à la fin de la session,
   dans la discussion » — remplace la promesse « rien n'est enregistré ». À valider.
3. **Notification à la fin d'un appel Live** : la personne a raccroché, les actions sont déjà dans
   le fil. Je propose **aucune** notification push (la carte de clôture suffit ; le direct garde
   ses pushs de relais). À confirmer.
4. **Libellés** du réglage : « Live » / « Live direct », avec les glyphes du menu du casque
   (`AudioLines` / `Radio`). À confirmer.

---

## 2. Cible fonctionnelle

### 2.1 La matrice

| | **Live** (délégué) | **Live direct** |
|---|---|---|
| Ce que la voix tient | `send_to_lia` seul | les lectures directes (`VoiceToolHost`), jamais une action |
| Pendant | chaque demande = un tour de chat (HITL, registres, quotas), visible dans le fil | lectures à la seconde, rien dans le fil |
| Fin | tours vocaux archivés `live_turn` · carte `live_session_summary` · décision · apprentissage sur les tours vocaux | synthèse « ce que la personne aurait tapé » · tour relayé (visible) · carte de clôture disant le sort du relais · le relais apprend |
| Navigateur | existe (ADR-299) | existe (ADR-300 w4) **+ relais** |
| Téléphone | **nouveau** (défaut) | existe (ADR-290) |

### 2.2 Ce que la personne voit

- **Réglages › Téléphonie · Mon identité** : sous le numéro et sa vérification, un `GlyphSelect`
  « Mode des appels » — *Live* (« LIA agit dans ta discussion pendant l'appel ») / *Live direct*
  (« LIA lit pour toi pendant l'appel et agit après ») ; sous *Live direct* seulement : le switch
  « Contexte riche » et le panneau des domaines (ils n'ont de sens qu'en direct — H6). Quand
  l'instance ne peut pas servir Live (H13), l'option est désactivée avec la raison, et le mode
  effectif est dit.
- **Pendant un appel Live** : les demandes apparaissent dans le fil comme des tours (estampillés
  `phone_call` + clé de session), avec leurs cartes, leurs confirmations HITL (la voix pose la
  question, la réponse parlée la règle), leur coût au compteur.
- **Fin d'un appel Live** : les échanges vocaux (hors demandes déléguées) en bulles `live_turn`,
  puis la carte de clôture (« Appel · N min · N demandes · N échanges vocaux · coût de LIA »).
- **Session directe navigateur** : bandeau reformulé (question 2) ; à la fin, la carte de clôture
  dit « LIA prend en charge ce que tu as demandé » / « rien à relayer » / « une question t'attend »
  (les dix `RelayOutcome` en six langues, déjà écrits pour le téléphone), puis le tour relayé
  apparaît dans le fil.
- **Liste des appels** : la facture d'un appel Live est l'agrégat de ses tours.

---

## 3. Architecture

### 3.1 Le contexte borné `domains/voice_sessions/` — tel que livré (lot 1, 2026-09-20)

Le découpage prévu (tout dans `voice_sessions`, extracteurs par port) a été **corrigé à la
livraison** contre le ratchet de cycles : la fermeture et le relais archivent, enregistrent une
décision et pilotent les extracteurs — tous dans `agents` — et `voice_sessions` doit rester
importable par `telephony` sans fermer T2. Le contexte borné ne garde donc que les **valeurs et
les requêtes** ; les **runners** vivent à côté des runners existants.

```
domains/voice_sessions/                 (importe core, chat, conversations, agents.utils.plain_text ;
  __init__.py                            jamais live, telephony, agents.api, agents.effects)
  session.py      VoiceSession(carrier, key, run_id, origin_id, mode, user_id, conversation_id, language, timezone)
                  .browser(...) / .phone(call_id, ...) ; origin_kind ; delegated
                  VoiceSessionMode = Literal["delegated", "direct"] ; as_voice_session_mode(str) (sans cast)
                  VoiceCarrier(Enum) ; PHONE_CALL_RUN_PREFIX ; phone_session_key(call_id) → "phone_call_<hex>"
                  (telephony/spend.py délègue ici — la vérité de la clé est dans ce module)
  transcript.py   VoiceTurn(role, text, offset_seconds, delegated) ; VoiceTranscript.from_rows / from_vendor_payload
                  (tool_calls → delegated : requête, appel, première restitution) ; voice_only() ;
                  voice_only_exchanges() (groupés comme le navigateur archive : un échange par tour de la personne) ;
                  lines() (vocabulaire du prompt de relais : `agent:` / `user:`)
  projection.py   char_token_cost / estimate_tokens / flatten_for_voice / bound_to_tokens — miroir de
                  delegation.ts, prouvé par UN corpus partagé (tests/unit/domains/voice_sessions/voice_projection_corpus.json,
                  lu par pytest ET vitest)
  summary.py      VoiceSessionOutcome, VoiceSessionUsage, render_summary_markdown, session_run_ids,
                  session_voice_rows, count_voice_turns, aggregate_usage (migré de live/summary.py, WHOLE_RECORD)
  mandate.py      DelegationBlockInputs, render_delegation_block (voice_delegation_block.txt, extrait de
                  live_system_prompt.txt qui se termine par {delegation_block}), delegation_tool_description,
                  delegation_request_schema, voice_lines, delegation_verb

infrastructure/scheduler/
  voice_session_closing.py  close_voice_session(db, session, memory_enabled, outcome, duration, extensions,
                            transcript?, started_at?) → ClosedSession ; archive_voice_turns (le téléphone) ;
                            schedule_voice_learning (primitives seulement) ; archive_row (LA porte, seam de test)
  voice_relay.py            RelayOutcome, transcript_of_payload / collected_of_payload / vendor_summary_of_payload,
                            project_transcript, synthesize_relay, VoiceRelayRequest, run_voice_relay
                            (golden byte-à-byte contre l'ancien self_call_relay)
  phone_relay_runner.py     ne garde que le téléphone : run_relay (construit VoiceSession.phone, appelle
                            run_voice_relay, compte, pousse), settle_owner_call, fallback_text
  voice_delegation.py       le pont serveur (lot 2, §3.4)
```

Supprimés : `live/learning.py`, `live/summary.py`, `telephony/self_call_relay.py`.
`live/schemas.py` ré-exporte `LiveSessionMode = VoiceSessionMode`, `LiveOutcome`, `LiveUsage`.
`live/service.py` : 594 → 547 SLOC. Cycles : 24 (inchangé).

### 3.2 Données

- `users.phone_call_mode` : `String(16)`, NOT NULL, `server_default 'live'`, vocabulaire
  `VoiceSessionMode` (« live » ⇔ `delegated`, « live_direct » ⇔ `direct` ; la colonne stocke le
  vocabulaire de l'objet de valeur — `delegated`/`direct` — et l'UI traduit). Migration Alembic
  unique (tête actuelle `b7d1e3f5a9c2`), `downgrade` inverse ; modèle déjà déclaré par le mixin
  (aucune entrée `import_all_models` à ajouter).
- Record Redis de session Live (navigateur) : champ `transcript: list[[role, text, at]]`, borné
  par `LIVE_DIRECT_TRANSCRIPT_MAX_CHARS` (coupe **la tête**, on garde la fin : la récapitulation
  de clôture est à la fin — décision explicite, contraire de `fit_lines` qui garde le début),
  même clé, même TTL — aucune nouvelle famille.
- Clé Redis `telephony_delegation:{call_id}` (USER_RUNTIME, déclarée dans `key_families.py` et
  `core/constants` — les deux gardes) : `current_request_id`, TTL = timeout de délégation + marge.
- `phone_calls` : aucune colonne. Un appel Live se ferme comme une vérification
  (`close_without_return`) **après** la politique de fermeture ; `notification_status` reste
  NULL (pas d'outbox), `summary` = résumé vendeur comme aujourd'hui, `outcome` dérivé (répondu /
  non répondu / échec) — les balayeurs `return`/`notification` ignorent une ligne sans outbox
  (à vérifier au lot 4 sur `reapers.py:54-142`, test dédié).
- Métadonnées d'archive (`archive_metadata.build_*`, jamais un dict inline — garde AST) : les
  tours délégués du téléphone portent `live_session_id = phone_call_<hex>` **et** l'estampille
  d'origine `phone_call` (les deux existent, `with_origin_stamp`) ; les `live_turn` du téléphone
  portent `live_session_id` + `type=live_turn` + `started_at` (dérivé de `time_in_call_secs`) ;
  la carte porte `mode` et un nouveau `carrier`.

### 3.3 Le mandat Live téléphone

Nouveau fichier `telephony_self_live_system_prompt.txt` (ajouté à `TelephonyPromptName` **et**
au `PromptName` miroir, avec ses producteurs — garde `test_prompt_placeholders_are_produced`) :
le cadre téléphonique de `telephony_self_call_system_prompt.txt` (identité, sortie acoustique,
temporalité, langue, personnalité, `end_call`, confinement, cas limites) **moins** `<what_you_know>`,
`<calendar_constraints>` et le bloc outils, **plus** les sections partagées rendues par
`voice_sessions.mandate` : « WHAT LIA DOES — AND ONLY LIA », « HOW A DELEGATION BEHAVES »
(`delegation_async` si la mesure du lot 0 confirme l'async, sinon `delegation_blocking`),
`tone_note_call`, les exemples. Le verbe : `delegate_by_call` avec `send_to_lia`. Le mandat dit
la borne : « si LIA n'a pas répondu à temps, dis que la réponse sera dans la discussion » (ligne
`timed_out`, existante). Nouveau `CallMandate` : `CallKind.SELF` garde **un** mandat, paramétré
par le mode (`prompt_name` devient une fonction du mode) — ou deux kinds ? **Un kind, deux
mandats** : `MANDATES[(CallKind.SELF, mode)]`, l'assert d'amorçage couvrant le produit
kind × mode ; `call_kind` en base ne change pas (un appel SELF reste SELF), le mode est lu sur
l'utilisateur au moment de la numérotation et **écrit dans `structured_data` de la ligne**
(`{"call_mode": …}`, nouveau dict) pour que le retour d'appel applique la politique de l'appel
tel qu'il a été passé, jamais celle du réglage courant.

### 3.4 Le pont de délégation serveur — tel que livré (lot 2, `infrastructure/scheduler/voice_delegation.py`)

```
delegate(DelegationRequest(session, request_id, request, spoken_text, wait_seconds), *, context: RunContext)
  -> DelegationResult(outcome, text, note)          # jamais une exception vers la voix
  1. requête vide → EMPTY, lines["empty_request"], aucun tour
  2. plus récent gagne : SET voice_delegation:newest:{session.key} = request_id (famille USER_RUNTIME,
     TTL = VOICE_DELEGATION_RUN_TIMEOUT_SECONDS) ; le pont qui tourne lit le marqueur toutes les
     250 ms (VOICE_DELEGATION_SUPERSEDE_POLL_SECONDS) et annule SON run → l'ancien webhook reçoit
     lines["superseded"] ; prouvé sur Redis réel avec deux tâches (test_voice_delegation_redis.py)
  3. résomption HITL : check_pending_hitl_uncached(conversation) → original_run_id = run_id, réutilisé
     comme run_id (l'accounting de la question et de la réponse sous un seul id, comme le routeur chat) ;
     une sonde aveugle lance un tour frais (le graphe relit de toute façon le checkpoint interrompu)
  4. StreamRequest(spoken_by_person=True, live_session_id=key, spoken_text, original_run_id,
     origin=None — un tour de chat ORDINAIRE, la barrière DEMANDE, les lignes sont visibles —,
     execution_mode/flags de la personne, max_attempts=1, timeout=VOICE_DELEGATION_RUN_TIMEOUT_SECONDS)
     sous le bail de conversation (active_run_lease, attente bornée VOICE_DELEGATION_LEASE_WAIT_SECONDS
     → BUSY, lines["busy"]) ; une reprise par le tour tapé de la personne (ActiveRunLockLost) → SUPERSEDED
  5. attente bornée à wait_seconds par asyncio.wait_for(shield(task)) : au-delà → TIMED_OUT,
     lines["timed_out"], la tâche CONTINUE (safe_fire_and_forget) et reste supervisée (la demande
     suivante l'annule encore)
  6. RunResult → SUCCESS : bound_to_tokens(flatten_for_voice(text)) + note de ton (tone_lines()[register],
     le registre lu sur le chunk `done` par le moteur) ; WAITING+interrupt → QUESTION, la question EST le
     résultat ; QUOTA_BLOCKED → lines["quota_blocked"] ; FAILED → lines["failed"]
```

Moteur (`out_of_turn_run.py`, 317 SLOC) : `StreamRequest` gagne `original_run_id`, `live_session_id`,
`spoken_text` (passés tels quels à `stream_chat_response`) ; `RunResult.register` lu sur `done`
(`metadata.expressivity.register`). Rien dans `agents/api/service.py`.

Les lignes `busy`, `quota_blocked`, `failed` rejoignent `live_lines.txt` et `BRIDGE_LINE_KEYS`
(`voice_sessions/mandate.py`, qui porte désormais `bridge_lines()` et `tone_lines()` ; `live/mandate.py`
les ré-exporte, `/live/config` les publie toutes).

Chemin de migration du navigateur (écrit, non exécuté) : `POST /live/sessions/{id}/delegate`
appelle le même pont ; le tour est **spawné** comme producteur détaché quand
`BACKGROUND_RUNS_ENABLED`, le navigateur se réattache par `GET /runs/{stream_id}/stream` pour
dessiner le flux et pousse la réponse tardive lui-même ; `delegation.ts` est supprimé **après**
preuve sur une session réelle. Pré-requis : le broker en production.

### 3.5 Le carrier téléphone — tel que livré (lot 4, 2026-09-20)

- **Données** : `users.phone_call_mode` (le CHOIX, défaut `delegated`) et `phone_calls.call_mode`
  (le mode que l'appel a RÉELLEMENT couru, écrit au dial, lu à la clôture ; `direct` pour tout
  appel antérieur et tout appel tiers) — une seule migration `c9e2a4b6d8f1`, replay F007 vert.
- **Provisionnement** : `telephony/delegation_tool.py` (dans `telephony`, pas `agents/telephony` :
  un outil fixe, aucun registre) — `delegation_tool_body` = `webhook_tool_body(asynchronous=True)`
  (`execution_mode: async`, `pre_tool_speech: force`, mesuré lot 0), nom/description/schéma
  partagés avec le navigateur (`voice_sessions/mandate`), URL = `callback.callback_base_url()`
  (`TELEPHONY_CALLBACK_BASE_URL` sinon `API_URL`), `response_timeout_secs` =
  `TELEPHONY_DELEGATION_TIMEOUT_SECONDS` (défaut 90, 20..290) ; empreinte dans les métadonnées du
  connecteur (`delegation_tool_id` / `delegation_tool_hash`), recréé à la dérive, refus vendeur →
  pas d'outil → l'appel part en DIRECT, honnêtement (`telephony_live_call_degraded_to_direct`).
- **Disponibilité** : `telephony/callback.py` — Live n'est offert que si l'hôte de rappel est
  PUBLIC (`is_public_host` : loopback, privé, link-local, `.local`, `host.docker.internal`…
  refusés) ; `PhoneIdentity.live_available` / `live_unavailable_reason` (`callback_not_public`) /
  `call_mode_effective` — l'UI dit ce qu'un appel courra, jamais le choix nu (ADR-184).
- **Dial** (`TelephonyService.initiate_call(call_mode, delegation_tool_id)`) :
  `mandate_for(SELF, mode="delegated")` → `LIVE_SELF_MANDATE` (aucun prefetch, aucun contexte),
  `_arm_agent_tools` attache l'UN (outils de lecture en direct, outil de délégation en Live),
  l'agent est détaché avant tout autre appel ; `telephony_self_tools._build_call_me_output` lit
  `identity.call_mode_effective`, n'ouvre AUCUNE source en Live.
- **Mandat Live** : `telephony_self_live_system_prompt.txt` — le cadre de l'appel direct (contrôle
  d'identité, sortie acoustique, `end_call`, sécurité) autour du bloc de délégation PARTAGÉ
  (`render_delegation_block(async_delegation=True)`), `_RENDERERS` = une table nom de prompt →
  moteur de rendu (plus de branche par kind).
- **Route** `POST /telephony/tools/send_to_lia` (déclarée AVANT `/{tool_name}`, aucun drapeau : le
  mode de la LIGNE est l'interrupteur) : même autorisation que les lookups (appel propriétaire
  actif + jeton dérivé), `refused_mode` sur un appel direct, `refused_request` hors
  `CHAT_MESSAGE_MAX_LENGTH` (constante nouvelle, lue aussi par le schéma du chat), budget par appel
  (le compteur des lookups, `budget_exhausted`), `request_id` frappé côté serveur (le corps vendeur
  n'en porte aucun), attente = timeout vendeur − `TELEPHONY_LIVE_TOOL_INNER_MARGIN_SECONDS`,
  réponse `{"result", "tone"?}` = la réponse de fonction du navigateur, verbatim.
- **Clôture** (`owner_call._close_live_owner_call`) : `mark_completed(notification_status=None)`
  (rien à livrer), outils rendus, `close_voice_session(session=VoiceSession.phone(delegated),
  transcript=transcript_of_payload(payload), started_at=call.initiated_at)` — les échanges
  vocaux archivés, la carte aux chiffres EXACTS, la décision `phone_call/answered`, l'apprentissage.
  **Forme réelle du transcript vendeur mesurée** (2026-09-20) : l'appel async est une entrée agent
  VIDE avec `tool_calls`, suivie d'une entrée vide `tool_results` (l'accusé), puis la conversation
  continue, puis une SECONDE paire à l'arrivée du résultat et la restitution ; un échange
  (tour de la personne → tour suivant de la personne) qui contient un appel est délégué EN ENTIER,
  comme le tampon du navigateur. Deux échanges à la même seconde gardent deux tampons distincts
  (le rang de l'échange en microsecondes).
- **Liste des appels** : `usage` d'un appel Live = SOMME de ses tours délégués et de son propre run,
  en DEUX lectures groupées pour la page (`session_run_ids_by_key`, prouvé sur PostgreSQL) ;
  `call_mode` sur le fil ; badge « Live » / « Live direct » sur la carte d'un appel avec la personne.
- **Métriques** : `telephony_delegations_total{outcome}`, `telephony_delegation_duration_seconds`,
  deux panneaux sur le tableau 24.
- **Preuves** (sans téléphone) : `task telephony:simulate:live` (le vendeur joué en HTTP contre
  l'API dev : tours réels, question HITL → résomption, webhook signé, livres) et
  `task telephony:probe:live -- --callback <tunnel>` (le moteur RÉEL du vendeur sur le mandat et
  l'outil de production, une conversation texte, le rappel via tunnel, la clôture sur le transcript
  du vendeur). Mesuré : contrôle d'identité, « Let me check your agenda for tomorrow. », délégation
  async (29 s de tour réel), petite conversation pendant l'attente, restitution exacte
  (l'anniversaire et le rappel créés par une simulation précédente), `end_call` ; livres exacts.
  Trouvé sur la route : la question HITL en attente d'une session précédente prend la première
  demande du nouvel appel pour sa réponse — la règle du chat (ADR-276 lot 7), identique au Live
  navigateur ; le rig la règle en refusant le brouillon.

### 3.6 Le carrier navigateur direct — tel que livré (lot 5, 2026-09-20)

- `/turns` en mode direct **accumule** dans le record (`LiveSessionStore.append_turns` : une LISTE
  Redis `live:session:{user}:turns` à côté du record, RPUSH, TTL du record, borne
  `LIVE_DIRECT_TRANSCRIPT_MAX_ROWS` = 400, jamais de lecture-modification-écriture qui perdrait
  une extension ou un tour), répond `{null, null}` ; `raise_live_direct_not_archived` est
  supprimé (erreur, phrase i18n, code frontend, `LIVE_ERROR_CODES`). Le contrôleur navigateur
  poste ses tours en direct comme en délégué (`archiveTurn`, plus de retour anticipé).
- `end` en direct : `close_voice_session(transcript=VoiceTranscript.from_rows(store.turns()))`
  → `_synthesize_direct` (la synthèse du relais, `owner_confirmed=True` par construction — la
  session est authentifiée —, comptée par `track_voice_synthesis_usage` sous le run id de la
  session, surface `live_session`) → `scheduled` | `empty` | `quota_blocked`
  (`UsageLimitExceededError`) | `failed` ; la carte est archivée avec ce sort
  (`live_session.relay`, `summary_body_direct` avec `{relay}`) et `end` répond
  `LiveEndResponse.relay`. Le tour relayé court dans une tâche que la clôture possède
  (`_settle_direct_relay` : `run_voice_relay` sur sa propre session DB, `live_direct_relay_total`,
  `_rewrite_card` — le contenu ET la métadonnée imbriquée réécrits par
  `ConversationRepository.rewrite_message`, la dépense RELUE via `aggregate_usage` puisque le tour
  a dépensé sous le run de la session après l'écriture de la carte —, puis un avis SSE
  `proactive_live_session` `{event: live_relay, relay}` sans archive ni push).
- Front : `LiveSessionSummaryCard` dessine `live.summary.relay.{fate}` sous une carte directe ;
  `handleProactiveNotification` (page chat) recharge le fil sur `metadata.event === 'live_relay'`
  (toast avec la phrase du serveur), `reloadConversation` extrait et partagé avec l'action
  planifiée ; `direct_notice` réécrit (six langues) ; mandat direct navigateur reformulé (une
  demande est NOTÉE et relayée à la fin, plus refusée).
- **Preuves** : rig HTTP contre l'API dev (session serveur frappée par la porte du store, `POST
  /live/sessions` direct avec un mint réel, 3 `/turns`, `/end`) — carte `scheduled`, puis le tour
  relayé RÉEL (« Rappelle-moi de prendre rendez-vous chez le dentiste jeudi 24 septembre 2026 à
  9h. » à la première personne, date absolue) et la réponse de LIA (le rappel posé, puis « ce
  rappel existe déjà » au second passage), la carte réécrite `answered` avec la dépense entière
  (0,0133 €), 0 ligne `live_turn`, avis SSE publié ; e2e Playwright `chat-live-session.spec.ts`
  (scénario direct : l'avis, le tour posté, la ligne du relais sur la carte) vert sur le bundle
  standalone. Trouvé et corrigé en route : `ConversationRepository.get_by_id` est celui de la
  CONVERSATION — la carte n'était jamais relue (`get_message` ajouté, test PostgreSQL) ; la
  carte réécrite gardait la dépense de la clôture (0,0004 €) alors que le tour avait coûté
  0,0133 € sous le même run (ADR-185 : relue au règlement).

### 3.7 Registres, coûts, quotas

- **Décisions** : chaque tour délégué est une décision (le graphe) ; l'appel/la session Live une
  décision de route `phone_call`/`live_session` (`out_of_turn_decision`), comme aujourd'hui pour
  la session.
- **Consultations** : celles des tours délégués sont du tour (porte d'outils) ; l'archivage des
  tours vocaux n'ouvre rien ; la synthèse de relais ne lit que le transcript (aucune ligne). Les
  surfaces `phone_call` et `live_session` restent (`consultation_surfaces.py:211,240`).
- **Effets** : la porte d'effets voit un tour **attendu** (H1) ; un `confirm` interrompt ; la
  réponse parlée le règle (H2). Les `agent_effects` sont ceux des tours.
- **Dépense** : `llm` INSTANCE — chaque tour délégué compte contre les deux plafonds dans
  `stream_chat_response` ; refus → `QUOTA_BLOCKED` → phrase de refus dite, rien dépensé. La
  synthèse de relais (direct, les deux carriers) est **ACCOUNTED** sous le run de la session
  (`LLM_SPEND_ROADS` : `domains/voice_sessions/relay.py: ACCOUNTED`, `telephony/self_call_relay.py`
  retiré). L'apprentissage (délégué) est ACCOUNTED sous le run de la session (existant,
  `learning.py:_learn`). Aucun euro du vendeur (voix, ASR, LLM ElevenLabs) n'est compté :
  `cost_bearers` inchangé.
- **Tokens** : vendeur (clé de la personne) — mandat Live téléphone ≈ 1,5-2 k tokens contre
  ≈ 2-5 k en direct (contexte riche + 55 descriptions d'outils) : Live est **moins** lourd côté
  vendeur. LIA (clé plateforme) — Live : N tours (le mode d'exécution de la personne s'applique,
  pipeline 4-8× moins cher que ReAct, ADR-070) + apprentissage ; direct : 1 synthèse structurée
  (slot `telephony_self_relay`) + 1 tour relayé + lectures. Un résultat de délégation est borné par
  `live_delegation_result_max_tokens` (publié, existant) et un résultat vendeur par 64 KB (doc).
- **Rate limits** : `call_me` garde son plafond horaire ; délégations par appel bornées par le
  budget (§1.5) ; le webhook n'est joignable que pour un appel SELF vivant avec le jeton.

### 3.8 Front, ergonomie, accessibilité

- `TelephonyIdentitySection.tsx` : un `GlyphSelect` « Mode des appels » (deux entrées, glyphes
  du menu du casque), nommé et décrit (`aria-describedby` sur l'aide), désactivé avec raison
  quand `live_available=false` ; `RichContextSwitch` + `DomainsPanel` rendus **sous** le mode
  direct seulement (avec une ligne expliquant que Live n'en a pas besoin) ; mobile-first (la
  liste pleine largeur, pas de tableau) ; ratchets a11y/react-hooks/complexité inchangés (la
  section reste sous ses seuils : un composant `CallModeField` dédié).
- `LiveBanner.tsx`, `LiveSessionSummaryCard.tsx` : nouvelles clés, le `carrier` sur la carte
  (« Appel » / « Session ») ; la carte téléphone est rendue par le **même** composant.
- i18n : parité stricte sur six locales (`lint:i18n`), zh avec `_one` dupliqué si pluriel.
- E2E : `chat-live-session.spec.ts` (Chromium, `page.routeWebSocket`) gagne un parcours direct
  (tours accumulés, `end` → `relay: scheduled`, carte) ; un parcours réglages (le select,
  l'indisponibilité) dans le spec des réglages.

---

## 4. Flux détaillés

### 4.1 Appel Live téléphone

```
call_me_tool(objective)
  ├─ identité vérifiée, mode = live, live_available ?  (sinon → direct, compté fallback)
  ├─ ensure_vendor_delegation_tool  (empreinte)          — échec → direct, compté
  ├─ initiate_call(kind=SELF, mode=live, live_tools=(delegation,))
  │    ├─ _arm_live_tools : attache send_to_lia SEUL (détache les lectures si présentes)
  │    ├─ build_override(SELF, live) : mandat Live téléphone
  │    ├─ ligne DIALING, structured_data={"call_mode":"delegated"}
  │    └─ dial (dynamic_variables : user_name, objective, current_datetime, call_id, personality)
  └─ « Je t'appelle. »
Pendant l'appel (vendeur → API) : POST /telephony/tools/send_to_lia {call_id, request}
  ├─ flag, corps, appel SELF vivant + jeton, budget
  ├─ VoiceDelegationBridge.handle(request_id=<vendor request id ou uuid>, request)
  │    ├─ supersede si un pont tourne (Redis + bail)
  │    ├─ pending HITL ? → original_run_id
  │    ├─ tour de chat (spoken_by_person, live_session_id=phone_call_<hex>, origin phone_call visible)
  │    └─ résultat : réponse bornée | question | timed_out | refus quota
  └─ {"result": …, "tone": …}   (≤ timeout − marge)
Fin d'appel (webhook post-appel) : process_owner_call
  ├─ détache l'outil
  ├─ call_mode = delegated → close_voice_session(phone, transcript vendeur)
  │    ├─ live_turn rows (tours sans send_to_lia), started_at dérivé
  │    ├─ carte (mode=delegated, carrier=phone, delegations = session_run_ids, usage agrégé)
  │    ├─ décision route phone_call
  │    └─ apprentissage (port) sur les tours vocaux
  └─ close_without_return(status, seconds, completed_at) ; compteurs
```

### 4.2 Session directe navigateur

```
POST /live/sessions {mode: direct} → record(mode=direct, transcript=[])
tour : POST /turns {user_text, assistant_text, started_at} → record.transcript += … (borné) ; 200 {ids: null}
lookups : POST /tools (inchangé)
POST /end {outcome, detail}
  ├─ close_voice_session(browser, transcript=record.transcript, mode=direct)
  │    ├─ synthesize_relay (out_of_turn_spend(session.run_id)) → relay | empty | quota | failed
  │    ├─ relais planifié (run_voice_relay, bail de conversation, spoken_by_person, live_session_id=session)
  │    ├─ carte (mode=direct, relay=<état connu>)
  │    └─ décision route live_session
  ├─ libère la place, métriques
  └─ LiveEndResponse{…, relay}
plus tard : le tour relayé se règle → SSE live_relay → le fil se recharge
```

---

## 5. Cas limites et dégradés (chacun un test)

| # | Scénario | Comportement attendu |
|---|---|---|
| E1 | Quelqu'un d'autre décroche (Live) | Le cadre téléphonique refuse (identité non confirmée → `end_call`), **aucune** délégation ne part ; si une partait quand même, la porte refuse-t-elle ? Non — l'appel est vivant. **Mitigation** : le mandat interdit toute délégation avant confirmation ; mesuré au lot 0 par un scénario « je ne suis pas X ». Résiduel accepté : la voix ne peut pas être forcée par le prompt seul — même surface d'attaque qu'aujourd'hui avec les lectures directes. |
| E2 | Délégation pendant qu'une autre tourne (correction) | La seconde supersede (Redis + bail) ; la première reçoit `superseded` ; une seule réponse dite. Test intégration Redis à deux tâches. |
| E3 | Deux workers | Idem, par le signal Redis (E2 exécuté sur deux processus dans le test d'intégration, comme le bail d'ADR-271). |
| E4 | Le tour dépasse le timeout vendeur | `timed_out` dit ; le tour continue et finit dans le fil ; aucune double réponse ; métrique. |
| E5 | Question HITL, puis réponse parlée | Résomption avec `original_run_id` ; l'action s'exécute ; la carte du fil montre le brouillon confirmé. Test avec le moteur factice + test du routage `check_pending_hitl_uncached`. |
| E6 | Question HITL, la personne raccroche sans répondre | La question reste en attente dans le fil (comme après une session Live) ; la fermeture n'y touche pas ; le prochain message chat la règle. |
| E7 | Quota compte/instance atteint | `QUOTA_BLOCKED` → phrase de refus (six langues) ; rien dépensé ; métrique `quota_blocked`. |
| E8 | Flag rappel off / connecteur sans secret / provisionnement vendeur en échec | Appel en **direct**, compté `fallback`, réglage affiché « effectif : direct ». |
| E9 | Webhook post-appel dupliqué | `mark_completed`/`close_without_return` conditionnels → la fermeture ne tourne qu'une fois (idempotence existante, test conservé). |
| E10 | Webhook post-appel jamais reçu | Balayeur `stale` ferme la ligne ; les tours délégués sont déjà dans le fil ; pas de carte (état documenté, comme un onglet fermé côté navigateur). |
| E11 | Transcript vendeur sans `tool_calls` (ancienne forme) | Tous les tours sont vocaux ; les tours délégués déjà archivés apparaissent alors deux fois (le vocal en doublon du tour). **Mitigation** : dédoublonnage par correspondance texte du `request` avec les tours délégués de la session (les `user` rows portant la clé) — test avec fixture sans `tool_calls`. |
| E12 | Transcript vide (appel raccroché à la première seconde) | Aucun `live_turn`, carte avec 0 échange, décision `interrupted`. |
| E13 | Résultat de délégation > 64 KB (vendeur) | Impossible : borné à `live_delegation_result_max_tokens` bien en deçà. Test de la borne. |
| E14 | Requête vide | `empty_request`, aucun tour, aucun budget consommé. |
| E15 | Appel direct avec `send_to_lia` attaché par erreur | La porte répond « not found » (mode enregistré direct). |
| E16 | Session directe navigateur fermée sans `end` | Rien n'est relayé (le record expire) — documenté ; identique à aujourd'hui pour la carte. |
| E17 | `end` direct, synthèse en échec / modèle injoignable | `relay: failed`, carte le dit, rien de perdu (le transcript n'est pas archivé — décision : on **n'invente pas** un tour). |
| E18 | `end` direct, transcript sans demande actionnable | `relay: empty` (RelayOutcome.EMPTY existant), pas de tour. |
| E19 | `end` direct pendant qu'un tour chat de la personne tourne | Le relais attend le bail (retries bornés, existants) puis BUSY → carte « à relayer plus tard »… **non** : BUSY = « la conversation était prise » → notification comme au téléphone (`relay_busy`), pas de tour. Test. |
| E20 | Transcript direct > `LIVE_DIRECT_TRANSCRIPT_MAX_CHARS` | La tête est coupée, la synthèse reçoit la fin, le compteur `truncated` monte. |
| E21 | Migration : comptes existants | `phone_call_mode='live'` par défaut ; leur prochain appel est Live si l'instance le peut (H13/H15). |
| E22 | Un tour délégué archivé sous la clé du téléphone, puis réinitialisation de la conversation | Les tours partent avec la conversation (comme le Live) ; la ligne `phone_calls` reste (durable) ; la liste des appels perd l'agrégat → `usage` absent, pas 0 (ADR-185 : un compte est exact ou n'existe pas). |

---

## 6. Impacts et risques

### 6.1 Cartographie

| Couche | Impact |
|---|---|
| **Back — nouveau** | `domains/voice_sessions/*` (7 modules) ; `agents/telephony/delegation_tool.py` ; route `/telephony/tools/send_to_lia` ; prompt `telephony_self_live_system_prompt.txt` ; réglages `telephony_delegation_timeout_seconds`, `LIVE_DIRECT_TRANSCRIPT_MAX_CHARS` ; migration `users.phone_call_mode` ; clé Redis `telephony_delegation` ; métriques ; port d'apprentissage installé à l'amorçage. |
| **Back — modifié** | `out_of_turn_run.StreamRequest` (+3 champs) ; `live/service.py` (fin de session extraite, `/turns` direct accumule) ; `live/schemas.py` (`LiveEndResponse.relay`, `LiveTurnRequest` inchangé) ; `telephony/mandates.py` (produit kind × mode) ; `telephony/service.py` (mode à la numérotation, armement) ; `telephony/owner_call.py` (politique par mode) ; `telephony/router.py` (agrégat) ; `telephony/identity.py`+`schemas.py` (mode, effectif, disponibilité) ; `telephony_self_tools.py` ; `live_tools_router.py` ; `i18n_live.py`/`i18n_telephony.py` ; `LLM_SPEND_ROADS` ; `key_families` ; `PromptName` miroirs. |
| **Back — supprimé/migré** | `telephony/self_call_relay.py` → `voice_sessions/relay.py` ; `live/learning.py`, `live/summary.py` → `voice_sessions` (ré-exports temporaires interdits : les imports sont réécrits) ; `raise_live_direct_not_archived`. |
| **Front** | `TelephonyIdentitySection.tsx` (+ `CallModeField`), `useTelephonyIdentity` (types), `session-controller.ts` (tours directs postés, `end` lit `relay`), `LiveBanner.tsx`, `LiveSessionSummaryCard.tsx`, gestionnaire SSE (`live_relay`), 6 locales, tests vitest, e2e. |
| **DB** | 1 migration (colonne + default), `db:migrate:replay-check`. |
| **LLM** | 1 prompt nouveau, 1 prompt direct navigateur modifié, blocs partagés extraits ; slot `telephony_self_relay` réutilisé pour les deux carriers ; `LLM_SPEND_ROADS` mis à jour (garde). |
| **Docs** | ADR-301 + index ; amendements ADR-290/299/300 ; `TELEPHONY.md`, `LIVE_MODE.md` ; `CLAUDE.md` (pointeur) + `AGENTS.md` ; guides how/why (section Live) ; FAQ/`docs/knowledge` si la téléphonie y est décrite ; CHANGELOG à la release ; les 4 `.env` démo + `.env*.example`. |

### 6.2 Matrice des risques

| Risque | Probabilité | Impact | Mitigation |
|---|---|---|---|
| R1 — L'`async` vendeur ne livre pas le résultat au LLM une fois la voix repartie | moyenne | fort (le mode dégrade en « c'est dans la discussion ») | **Lot 0 mesure avant tout code** ; le mandat a les deux blocs (`delegation_async`/`delegation_blocking`) ; le pont ne dépend pas du mode vendeur. |
| R2 — Timeout vendeur trop court pour un tour ReAct | moyenne | moyen | Réglage jusqu'à 290 s ; le mode d'exécution est celui de la personne (pipeline recommandé pour le téléphone — dit dans l'aide du réglage) ; `timed_out` honnête. |
| R3 — Régression du relais téléphone direct pendant la migration vers `voice_sessions.relay` | moyenne | fort | **Golden** : le prompt rendu et la `SelfCallRelay` produite, byte for byte, avant/après (le net d'ADR-269) ; les tests existants d'`owner_call`/`return_synthesis` conservés. |
| R4 — Régression de la fin de session Live navigateur (extraction vers `closing.py`) | moyenne | fort | Les tests de `test_service.py` (fin de session) rejoués sans modification d'assertion ; e2e `chat-live-session.spec.ts`. |
| R5 — Cycle d'import `telephony ↔ agents` via `voice_sessions` | forte si oublié | build rouge | Règle d'import écrite §3.1, port d'apprentissage, ratchet `lint:cycles` à chaque lot. |
| R6 — `live/service.py` / `live_tools.py` dépassent le plafond | certaine sans extraction | build rouge | Extraction imposée (§3.1, §3.5) ; `task ratchet:update` **abaisse** les plafonds après. |
| R7 — Deux implémentations de l'aplatissement vocal (TS/Python) divergent | moyenne | faible-moyen | Corpus d'accord partagé (`tests/…/voice_projection_corpus.json`, lu par vitest et pytest). |
| R8 — Résomption HITL hors tour ouvre un nouveau run sur un graphe interrompu | faible après lot 2 | fort | Test du routage + test d'intégration (Postgres/Redis) : question → réponse → action exécutée, un seul run. |
| R9 — Un tour délégué reste orphelin (worker tué) | faible | moyen | Le tracker persiste (ADR-117) ; la réparation de tour existante (ADR-248 inv. 4) ; la fermeture ne dépend pas de lui. |
| R10 — Double apprentissage (direct) | nulle par construction (D3) | — | Test : aucune `live_turn` en direct, un seul run d'extraction. |
| R11 — Le défaut Live surprend un compte existant | certaine | faible (produit) | Décision D4 ; la carte de clôture et le fil le rendent visible ; l'aide du réglage l'explique. |
| R12 — Coût LIA d'un appel Live bavard | moyenne | moyen | Budget de délégations par appel (publié), plafonds compte/instance à chaque tour, compteur affiché sur la carte et la liste des appels. |

---

## 7. Plan de test directeur

| Niveau | Cible | Scénarios |
|---|---|---|
| **TU back** | `voice_sessions/session.py` | clé de session par carrier ; vocabulaire fermé ; `phone_call_run_id` = clé téléphone. |
| | `transcript.py` | `from_vendor_payload` : tours, `delegated` par `tool_calls`, `started_at` dérivé, ancienne forme sans `tool_calls` (E11), vide (E12). |
| | `projection.py` | corpus d'accord TS/Python ; borne en tokens (coupe au mot, CJK). |
| | `delegation.py` (moteur factice) | vide (E14) ; succès aplati/borné ; question = résultat ; quota ; timeout (tour continue) ; échec ; supersede (E2) ; résomption `original_run_id` (E5) ; note de ton. |
| | `relay.py` | golden prompt + sortie (R3) ; entrée neutre depuis le vendeur et depuis le record ; garde de la tête coupée (E20). |
| | `closing.py` | politique délégué (rows, carte, décision, apprentissage via port) ; politique direct (synthèse, relais planifié, carte par état, aucune row) ; port vide → assert d'amorçage. |
| | `telephony/mandates.py` | produit kind × mode complet ; mandat Live : placeholders produits (garde), pas de `<what_you_know>`, blocs partagés présents, `send_to_lia` nommé. |
| | `delegation_tool.py` | corps vendeur (async/timeout/pre-speech), empreinte stable, échec → `()`. |
| | `live_tools_router.py` | `/send_to_lia` avant `/{tool_name}` ; mode direct → not found (E15) ; budget ; réponse sous timeout − marge. |
| | `owner_call.py` | Live → `close_voice_session` + `close_without_return`, pas de synthèse ; direct → inchangé ; webhook dupliqué (E9). |
| | `telephony/identity.py`, `router.py` | mode lu/écrit ; `live_available` selon flag/secret ; agrégat de `usage`. |
| | `live/service.py` | `/turns` direct accumule et borne ; `end` direct → `relay` ; `end` délégué inchangé (tests existants). |
| | gardes | `LLM_SPEND_ROADS`, `key_families`, prompts (placeholders, `PromptName` miroir), `user_data_readers`, `CONSULTATION_RECORDERS`, `test_no_hardcoded_timezone`, métriques (ratchet), file-size, cycles, i18n parité. |
| **Intégration back** (Postgres + Redis) | supersede à deux tâches et deux processus (E2/E3) ; résomption HITL bout en bout (E5) ; fermeture téléphone Live sur base réelle (rows, carte, décision, `close_without_return`, balayeurs indifférents) ; agrégat `GET /telephony/calls` ; migration `db:migrate:replay-check`. |
| **TU front** (vitest) | `CallModeField` (valeurs, désactivation avec raison, a11y : nom, description, clavier) ; `TelephonyIdentitySection` (sections conditionnelles) ; `session-controller` direct (tours postés, `end` → `relay`) ; carte de clôture par `carrier`/`relay` ; bandeau. |
| **E2E** (Playwright, API mockée) | session directe : tours → `end` → carte « prise en charge » → notification → fil rechargé ; réglages : choisir Live direct, voir le contexte/les domaines apparaître ; Live indisponible grisé. |
| **Runtime** | lot 0 (prod, vrai appel) ; lot 4 : un appel Live réel (question → réponse HITL → action → carte) ; lot 5 : session directe réelle sur dev (Gemini) → relais dans le fil. |

Simulations à écrire avant le code : fixtures de transcript vendeur (avec/sans `tool_calls`,
avec `tool_results` d'un `send_to_lia`), un moteur de chat factice à états (succès / question /
quota / lent / échec) réutilisé par tous les tests du pont, un record Redis factice pour le
transcript direct.

---

## 8. Plan d'actions séquencé

| Lot | Contenu | Sortie / preuve | Gardes & ratchets |
|---|---|---|---|
| **0 — Mesure vendeur** | `apps/api/scripts/telephony/probe_async_delegation.py` (forme de `scripts/live/probe.py` : aucun import `src`, clé en env, agent + outil **temporaires** supprimés à la fin, chiffres anonymes) ; `task telephony:probe`. Deux appels : (a) outil `async` vers un endpoint qui répond après 25 s (`httpstat.us/200?sleep=25000`, repli : route de sonde), (b) idem au-delà du `response_timeout_secs`. Lit ensuite la conversation vendeur : `tool_calls`, `tool_results.tool_latency_secs`, la voix a-t-elle parlé pendant l'attente, le résultat a-t-il été restitué, comportement à l'expiration, deux appels concurrents. | Un compte rendu chiffré dans la spec (§9 à créer) ; décide `delegation_async` vs `blocking` et le défaut du timeout. | — |
| **1 — Le contexte borné** | `voice_sessions/` : `session`, `transcript`, `projection` (+ corpus d'accord), `summary` et `learning` **migrés**, `relay` migré (golden), `closing` **extrait** de `LiveService.end` et branché sans changement de comportement ; port d'apprentissage installé à l'amorçage ; `LLM_SPEND_ROADS` à jour. | Tous les tests existants verts sans modification d'assertion ; `live/service.py` rétréci → `ratchet:update`. | cycles, spend roads, file-size, prompts. |
| **2 — Le moteur et le pont** | `StreamRequest` (+3) ; `VoiceDelegationBridge` (moteur factice) ; clé Redis déclarée ; intégration Redis à deux processus ; résomption HITL en intégration. | Suite du pont verte ; intégration verte. | key families, react reset guard (aucun état de graphe ajouté). |
| **3 — Le réglage** | Migration ; `identity` (mode, effectif, disponibilité) ; `TelephonyIdentity*` schémas ; front `CallModeField` + sections conditionnelles ; 6 locales ; `.env*` et 4 `.env` démo pour le nouveau réglage de timeout ; docs du réglage. | `db:migrate:replay-check` ; vitest ; e2e réglages. | i18n parité, hygiene (.env.example), capability wiring. |
| **4 — Téléphone Live** | `delegation_tool.py` ; mandat (`kind × mode`, prompt, lignes partagées) ; numérotation par mode ; route `/send_to_lia` ; fermeture Live dans `owner_call` ; agrégat des appels ; métriques + dashboard 24 ; **preuve prod** : un appel réel avec question HITL. | Appel mesuré (temps de réponse, HITL, carte, coût agrégé) consigné dans la spec. | prompts, metric ratchet, docs. |
| **5 — Navigateur direct + relais** | record transcript ; `/turns` direct ; `end` direct ; SSE `live_relay` + rechargement ; mandat direct reformulé ; bandeau/carte ; 6 locales ; e2e. **Preuve dev** : session Gemini directe réelle → tour relayé. | e2e vert ; preuve consignée. | i18n, a11y ratchet, complexité (`session-controller`). |
| **6 — Docs** | ADR-301, `ADR_INDEX`, amendements, `TELEPHONY.md`, `LIVE_MODE.md`, `CLAUDE.md` pointeur + `docs:sync-agents`, guides how/why, `docs/INDEX.md`, FAQ/knowledge si concernés. | `lint:docs:preview` vert. | doc facts. |
| **7 — Gates** | `task lint`, `test:backend:unit:fast`, `test:backend:integration` (ciblé), `test:frontend` + coverage, `test:e2e`, `ci:fast`. Ratchets abaissés (file-size, cycles si un cycle tombe). | Sorties collées dans le rapport final. | — |

Le lot 0 conditionne la ligne `delegation_*` du mandat et le défaut du timeout ; les lots 1-3
ne dépendent pas de lui et peuvent commencer avant son exécution (ils ne touchent pas au
vendeur). Le lot 4 attend le lot 0.

---

## 9. Grille d'auto-évaluation

| Critère | Verdict |
|---|---|
| Analyse complète, robuste, viable, sans flou bloquant | **Oui, sous une réserve nommée** : la forme exacte du bloc de délégation et le défaut du timeout dépendent de la mesure vendeur (lot 0) — le design accepte les deux issues (R1). Les quatre questions §1.6 sont métier, non techniques. |
| Hypothèses confrontées au code | Oui — §1.2 cite fichier:ligne pour chaque fait ; H1-H15 renvoient à ces preuves ; les faux positifs/négatifs traqués §1.4 sont ceux qui auraient bloqué (résomption HITL, annulation, transcript direct). |
| Tokens / coûts / registres / responsive cadrés | Oui — §3.7 (qui paie, où l'euro atterrit, bornes publiées, plafonds à chaque tour, routes de dépense déclarées), §3.2 (registres et estampilles), §3.8 (mobile-first, a11y, ratchets). |
| Plans d'actions et de tests prêts à démarrer | Oui — lots atomiques, chacun avec sa preuve et ses gardes ; les simulations à écrire d'abord sont nommées (§7) ; les contraintes de taille qui imposent l'extraction sont mesurées, pas supposées. |

---

## 10. Lot 0 — la mesure vendeur (2026-09-20, sans appel téléphonique)

**Rig** : `apps/api/scripts/telephony/probe_async_delegation.py` (aucun import `src`, clé en env,
agent + outils TEMPORAIRES supprimés à la fin) ; un serveur de délai local exposé par un quick tunnel
Cloudflare ; la clé du connecteur ElevenLabs **Live** de dev (celle du connecteur téléphonie de dev
est un *id* de clé, pas une clé — « API key ID used as API key » — ce qui est le sens de « la
téléphonie n'est pas complètement paramétrée sur dev »).

**Deux instruments, parce que le premier ment** : `simulate-conversation` MOQUE les outils
(`tool_results` = « Tool Called. », latence 0,0, aucune requête reçue par le serveur de délai) — il
ne montre que la forme du transcript et le comportement du LLM autour de l'appel. Le vrai moteur a
été atteint par une **conversation texte sur le WebSocket** (`conversation.text_only`), où le
webhook est réellement appelé, attendu et répondu.

| Question | Mesure |
|---|---|
| `execution_mode: async` + `pre_tool_speech: force` | Une phrase d'annonce, l'appel part, la voix **continue** (« is there anything else while we wait? ») et **le résultat est remis au LLM à l'arrivée du webhook** (t+9,0 s pour un délai de 8 s) puis restitué aussitôt. |
| Au-delà de `response_timeout_secs` (20 s ; réponse à 25 s) | À 20,9 s le vendeur remet un `tool_result` **`is_error=True`** et la voix improvise (« there was a technical issue ») ; la réponse tardive (25 s) est **perdue**. Conséquence : le pont serveur répond **avant** le timeout vendeur avec `timed_out` (borne = timeout − `TELEPHONY_LIVE_TOOL_INNER_MARGIN_SECONDS`), et le timeout vendeur est généreux (défaut 90 s, borné 20..290). |
| Deux demandes d'affilée | **Deux webhooks concurrents** (t+0 et t+2,9 s), les deux résultats remis et énoncés. « Plus récent gagne » se règle donc côté serveur : l'ancien webhook doit répondre `superseded` sans attendre son tour. |
| Forme du transcript (simulation, même moteur) | `tool_calls[{request_id, tool_name, params_as_json, type=webhook}]`, `tool_results[{tool_name, is_error, tool_latency_secs, result_value}]` — un échange délégué se reconnaît à `tool_name == send_to_lia`. |
| Trames texte observées | `agent_response` (réponse entière), `agent_chat_response_part` (deltas), `agent_tool_response{tool_name, tool_type, is_error}`, `ping`/`pong`. |

**Décisions dérivées** : bloc `delegation_async` dans le mandat Live téléphone ; réglage
`telephony_delegation_timeout_seconds` (défaut 90) ; le pont répond toujours avant l'expiration
vendeur ; `tool_error_handling_mode` reste `auto` (le pont ne renvoie jamais d'erreur HTTP à la
voix : un échec est une phrase).
