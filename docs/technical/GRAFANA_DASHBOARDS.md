# Grafana Dashboards (LIA)

**Document de reference technique - Observabilite Production avec Grafana**

> **Version 4.5** | 2026-07-29 | 26 dashboards, 637 panels

---

## Table des matieres

1. [Vue d'ensemble](#vue-densemble)
2. [Stack Observabilite](#stack-observabilite)
3. [Catalogue des Dashboards](#catalogue-des-dashboards)
4. [Details par Dashboard](#details-par-dashboard)
5. [Variables et Datasources](#variables-et-datasources)
6. [Troubleshooting](#troubleshooting)
7. [Maintenance](#maintenance)
8. [Ressources](#ressources)

---

## Vue d'ensemble

### Objectifs

Les **26 dashboards Grafana** fournissent une observabilite complete pour :

1. **Monitoring production** : Sante applicative, SLOs, performance HTTP, ressources infrastructure
2. **Agent debugging** : Pipeline d'orchestration LangGraph, router, planner, outils, HITL
3. **Cost tracking** : Tokens LLM, couts EUR, suivi par utilisateur
4. **Securite et OAuth** : Connecteurs Google, MCP, flux OAuth
5. **Incident response** : Logs + traces correles, recherche par run_id/user_id
6. **Analytics utilisateur** : Engagement, geolocalisation, patterns d'utilisation
7. **Vue produit** : Valeur utilisateur (North Star E1/E2), activation, retention, cout par resultat utile (dashboard 26, ADR-178)

### Chiffres cles

| Indicateur | Valeur |
|------------|--------|
| Dashboards | 26 |
| Panels total | 637 |
| Recording rules | 86 |
| Schema version | 38 (Grafana 11.3) |
| graphTooltip | 1 (shared crosshair) sur tous les dashboards |
| Navigation | Tag `lia` sur tous les dashboards |
| Couverture metriques | Mesuree, jamais estimee : `python scripts/audit/measure_metric_coverage.py` (dashboard, recording rule ou alerte comptent comme couverture). Le reste est un **ratchet shrink-only** — `apps/api/tests/unit/metric_coverage_baseline.json`, garde `test_metric_coverage_ratchet_guard.py` : une metrique qui n'atteint aucun panel doit y figurer explicitement, et en sort des qu'elle est cablee (`task ratchet:metrics`). |

---

## Stack Observabilite

### Architecture

```
FastAPI /metrics (port 9091 HTTP) --> Prometheus --> Grafana
Structlog JSON --> Promtail --> Loki --> Grafana
OpenTelemetry OTLP --> Tempo --> Grafana
```

**Sources de metriques** :

| Source | Port | Role |
|--------|------|------|
| FastAPI `/metrics` | 9091 (HTTP dedie) | Metriques applicatives (agents, LLM, HITL, etc.) |
| cAdvisor | 8080 | Metriques conteneurs Docker (CPU/memoire/reseau) |
| postgres_exporter | 9187 | Metriques PostgreSQL (pool, requetes) |
| redis_exporter | 9121 | Metriques Redis (memoire, commandes) |
| node_exporter | 9100 | Metriques systeme hote (disque, CPU, RAM) |

> **Important** : Prometheus scrape le port 9091 (HTTP-only), pas le port 8000 (HTTPS principal de l'API). Cela evite les problemes de certificats SSL lors du scraping.

**Datasources Grafana** :

| Datasource | UID | Type | Dashboards |
|------------|-----|------|------------|
| Prometheus | `prometheus` | Metriques + recording rules | Tous (01-26) |
| Loki | `loki` | Logs structures | 05, 06, 07, 17 |
| Tempo | `tempo` | Traces distribuees | 06 |

### Retention et fenetre interrogeable

| Source | Retention | Ou c'est configure |
|--------|-----------|--------------------|
| Loki (logs) | **168 h (7 jours)** | `infrastructure/observability/loki/loki-config.yml` (`limits_config.retention_period`, `compactor.retention_enabled`, `table_manager.retention_period`) |
| Prometheus (metriques) | **15 j** ou **2 Go**, la premiere limite atteinte | `--storage.tsdb.retention.time` / `.size` (cf. `infrastructure/observability/prometheus/prometheus.yml` et `alerts-core.yml`) |

> **PIEGE — un zero hors retention ne veut pas dire « aucun evenement ».** Une
> requete Loki portant sur une fenetre plus ancienne que 7 jours renvoie
> `status: success` avec **zero serie** : strictement indistinguable d'une
> periode sans incident. Vecu le 2026-08-29 : une requete sur une fenetre
> vieille de 5 semaines a renvoye 0 partout, y compris sur une periode ou 40
> timeouts avaient ete mesures — d'ou une conclusion erronee « Loki est en
> panne » (il etait sain). **Toujours inclure une periode de controle dont on
> sait qu'elle contient des evenements** ; si elle rend 0 elle aussi, c'est la
> requete ou la fenetre qui est en cause, pas la production.
>
> Ordre de grandeur mesure le 2026-08-29 : 7 jours de logs = **26,5 Mo** sur le
> volume `lia_loki_data` (161 Go libres sur l'hote). Allonger la retention est
> donc gratuit en disque — mais c'est une decision de **conservation de donnees
> personnelles** (les logs portent des identifiants et des contenus), pas un
> simple reglage technique : elle se tranche avec le proprietaire, pas en
> passant.

### Fichiers de configuration

| Fichier | Contenu |
|---------|---------|
| `infrastructure/observability/prometheus/prometheus.yml` | Configuration scrape Prometheus |
| `infrastructure/observability/prometheus/recording_rules.yml` | 86 recording rules |
| `infrastructure/observability/grafana/dashboards/*.json` | 26 fichiers JSON de dashboards |
| `infrastructure/observability/grafana/provisioning/` | Provisioning datasources et dashboards |

---

## Catalogue des Dashboards

| # | Dashboard | UID | Tags | Panels | Domaine |
|---|-----------|-----|------|--------|---------|
| 01 | Application Overview | `01-app-overview` | lia, overview, health | 24 | Sante globale, performance requetes, pipeline agent, infra, resume couts LLM |
| 02 | SLO Tracking | `02-slo-tracking` | lia, slo, reliability | 17 | SLOs API, SLOs agents, SLOs providers LLM, SLOs DB et business |
| 03 | Infrastructure & Resources | `03-infra-resources` | lia, infra, docker, raspberry-pi | 24 | Systeme hote (RPi), ressources conteneurs, PostgreSQL, Redis |
| 04 | HTTP & API Performance | `04-http-api` | lia, http, api, latency | 17 | Trafic, latence, erreurs, rate limiting |
| 05 | LLM Tokens & Cost | `05-llm-tokens-cost` | lia, llm, tokens, cost | 52 | Headlines couts, ventilation, consommation tokens, efficacite, suivi par utilisateur (Loki), performance API LLM, cache LLM et economies, pricing, metriques cumulees, embeddings (issues, regulateur, refus fournisseur par raison) |
| 06 | Logs, Traces & Correlations | `06-logs-traces` | lia, logs, traces, debug | 17 | Logs, traces, correlation metrique-log, vue correlee, jobs background, recherche |
| 07 | Agent Orchestration Pipeline | `07-agents-pipeline` | lia, agents, langgraph, orchestration | 61 | Router, planner et orchestrateur, execution nodes agent, execution outils, contexte et etat, SSE streaming, background runs (ADR-117), couche semantique (ADR-120/121) |
| 08 | HITL Human-in-the-Loop | `08-hitl` | lia, hitl, approval | 27 | Vue d'ensemble HITL, qualite classification, comportement utilisateur, editions et rejets, reprise |
| 09 | Conversations & Users | `09-conversations-users` | lia, conversations, users, engagement | 37 | Activite utilisateurs, cycle de vie conversations, analyse abandon, succes et qualite agents, attachments, inscriptions, purge du reset par famille de cles (ADR-260) |
| 10 | OAuth, Connectors & MCP | `10-oauth-connectors-mcp` | lia, oauth, connectors, mcp | 39 | Flux OAuth, performance OAuth, sante connecteurs, APIs Google, serveurs MCP, formes de requetes contacts/email |
| 11 | Voice & WebSocket | `11-voice-websocket` | lia, voice, tts, stt, websocket | 24 | TTS, streaming audio, STT, WebSocket |
| 12 | Channels / Telegram | `12-channels` | lia, channels, telegram | 13 | Flux messages, bindings et securite, fonctionnalites canal |
| 13 | Proactive & Heartbeat | `13-proactive-heartbeat` | lia, proactive, heartbeat | 26 | Vue d'ensemble taches, notifications et couts, eligibilite et feedback, presence en lecture et reveils push (ADR-214/261) |
| 14 | Data Registry & Checkpoints | `14-registry-checkpoints` | lia, registry, checkpoints | 26 | Data registry, moteur de requetes, checkpoints LangGraph, recherche hybride, sante repository |
| 15 | LangGraph Framework Deep Dive | `15-langgraph-deep` | lia, langgraph, framework | 36 | Execution graphe, gestion d'etat, latence par etage (TTFT), integration Langfuse (repliee, requiert LANGFUSE_ENABLED) |
| 16 | Recording Rules & Alerts Health | `16-meta-health` | lia, meta, operational | 33 | Sante des recording rules, sante des alertes, validation et securite, integrite du registre d'outils, auto-diagnostic (verdicts, incidents, duree du tick, cout LLM, sources de preuves lues) |
| 17 | User Analytics & Geo | `17-user-analytics-geo` | lia, users, analytics, geo | 27 | Vue geographique (Geomap), engagement utilisateur, patterns d'activite, usage outils et agents, qualite et cout conversations, logs geo detailles |
| 18 | RAG Spaces / Knowledge Documents | `18-rag-spaces` | lia, rag, spaces, knowledge | 35 | Vue d'ensemble RAG, pipeline de traitement documents, performance retrieval, couts embedding, reindexation, recuperation de jobs, reindexation Drive ciblee et source libelle Gmail (ADR-261/262) |
| 19 | Sub-agents & Skills | `19-subagents-skills` | lia, subagents, skills | 10 | Executions de sous-agents ReAct (spawns, duree, tokens, erreurs), skills |
| 20 | ReAct Agent & Browser | `20-react-browser` | lia, react, browser | 17 | Boucle ReAct (iterations, outils, HITL tool-level), sessions navigateur, snapshots |
| 21 | Health Metrics | `21-health-metrics` | lia, health-metrics | 10 | Ingestion des echantillons sante (auth, validation, doublons), variations detectees |
| 22 | Compaction | `22-compaction` | lia, compaction | 13 | Sante compaction (executions, fallbacks truncation, writer unavailable), timeouts, volume et economies de tokens |
| 23 | Journals & User Model | `23-journals-user-model` | lia, journals, user-model | 16 | Extraction, actions sur entrees, consolidation par niveaux, portrait utilisateur |
| 24 | Telephony | `24-telephony` | lia, telephony, calls | 9 | Appels sortants par statut, duree, reapers de recuperation (T1), webhooks ignores |
| 25 | Today Briefing | `25-briefing` | lia, briefing | 8 | Duree de build par etat de cache, statuts par section, invocations LLM, refresh |
| 26 | Product Value, Activation & Retention | `26-product-value` | lia, product, value, growth, outcomes | 42 | Cockpit produit (ADR-178) : North Star E1/E2, funnel d'activation, qualite agentique, retention, couts EUR, qualite des donnees — v0 avec panels LIVE/PRE-WIRED/TEXT |

---

## Lecture par tiers (audience)

Le catalogue ci-dessus est ordonne par numero ; celui-ci l'est par **qui ouvre
quoi**. Les deux vues portent sur les memes 26 dashboards — elles vivent dans ce
document, et non dans un second fichier, parce que la version enveloppe qui les
separait a derive quatre fois du catalogue qu'elle resumait (elle annoncait
encore 25 dashboards apres l'ajout du 26).

| Tier | Audience | Dashboards | Objectif |
|------|----------|------------|----------|
| 1 — Vue d'ensemble | Tous | 01, 02 | Sante globale, SLOs, budget d'erreurs |
| 2 — Plateforme | Ops / Dev | 03, 04, 05, 06 | Infra, HTTP, couts LLM, logs/traces |
| 3 — Fonctionnalites | Feature Dev | 07-13, 18-25 | Agents, HITL, conversations, OAuth/MCP, voix, canaux, proactif, RAG, sub-agents, ReAct/browser, sante, compaction, journaux, telephonie, briefing |
| 4 — Avance | SRE | 14, 15, 16 | Registry/checkpoints, LangGraph deep (latence par etage TTFT), sante des recording rules et du registre d'outils |
| 5 — Analytics / Produit | Product | 17, 26 | Engagement et geolocalisation ; cockpit produit ADR-178 (North Star, activation, retention) |

Points d'entree recommandes : **01 - Application Overview** en cas d'incident
(puis navigation par le tag `lia`), **02 - SLO Tracking** pour le suivi de
fiabilite, **05 - LLM Tokens & Cost** pour les couts.

---

## Details par Dashboard

### 01 - Application Overview (24 panels)

Dashboard d'accueil. Fournit une vue synthetique de la sante de l'application : taux de requetes, erreurs, latence p95, etat du pipeline agent (router, planner, outils), resume infra (CPU, memoire, DB, Redis) et resume des couts LLM du jour. Point d'entree pour identifier rapidement un probleme avant d'aller dans un dashboard specialise.

### 02 - SLO Tracking (17 panels)

Suivi des Service Level Objectives sur 4 axes : API (disponibilite, latence), agents (taux de succes, duree pipeline), providers LLM (taux d'erreur, latence par provider), et business (DB pool, Redis, taux abandon conversations). Chaque SLO affiche le budget d'erreur restant sur la periode.

### 03 - Infrastructure & Resources (24 panels)

Metriques systeme orientees Raspberry Pi (ARM64) : charge CPU hote, memoire, espace disque (node_exporter), metriques conteneurs Docker (cAdvisor), pool de connexions PostgreSQL, taille et memoire Redis. Essentiel pour le capacity planning sur hardware contraint.

### 04 - HTTP & API Performance (17 panels)

Trafic HTTP detaille : requetes/s par endpoint, distribution latence (p50/p95/p99), taux d'erreur par code HTTP, metriques de rate limiting. Complement du dashboard 01 pour le diagnostic precis des problemes de performance API.

> **Labels `endpoint` bornes (v1.21.1)** : les labels des metriques HTTP (`http_requests_total`, `http_request_duration_seconds`) utilisent desormais le **template de route** matche (`/api/v1/journals/{entry_id}`) et non plus le chemin brut avec UUID ; les requetes non routees (404, scans de bots) sont regroupees sous `unmatched`, et la gauge `http_requests_in_progress` (pre-routing) applique un repli qui remplace les segments UUID/hex/numeriques par `{id}`. Cardinalite bornee par construction. **Toute requete Grafana qui filtrait sur des chemins exacts contenant des identifiants doit etre adaptee aux templates.**

### 05 - LLM Tokens & Cost (48 panels)

Dashboard le plus riche en panels avec le 07. Headlines de couts (jour, mois, projection), ventilation par modele et par node, consommation tokens (prompt, completion, cached), metriques d'efficacite (cout par requete, tokens par seconde). Section Loki pour le suivi par utilisateur. Performance des appels API LLM (latence, erreurs par provider). Cache LLM (hits/misses, erreurs, migrations de format) et economies estimees (`llm_cache_cost_saved_total`), fallbacks du cache pricing. Metriques de cout cumulees sur la duree de vie. La section compaction historique a ete deplacee vers le dashboard 22.

**Datasources** : Prometheus + Loki (pour les logs de suivi utilisateur).

### 06 - Logs, Traces & Correlations (17 panels)

Observabilite unifiee. Volume de logs par niveau, recherche par `run_id` ou `user_id`, vue traces distribuees via Tempo, correlation metrique-vers-log et trace-vers-log. Section jobs background (scheduler). Aides a la recherche (templates LogQL et TraceQL).

**Datasources** : Prometheus + Loki + Tempo.

### 07 - Agent Orchestration Pipeline (61 panels)

Coeur du monitoring agent. Sections pour chaque etape du pipeline : router (decisions, confiance, latence), planner (plans crees, retries, validation, succes), orchestrateur (vagues d'execution, parallellisme), execution des nodes agent (duree, statut, erreurs), execution des outils (taux succes, latence par outil), contexte et etat (taille state, checkpoints), SSE streaming (TTFT, tokens/s, erreurs). Deux sections repliees completent le perimetre : background runs ADR-117 (producteurs detaches, statuts terminaux, resolution de contexte) et couche semantique ADR-120/121 (blocages du garde de parametres, expansion par evidence, fuites de termes semantiques detectees/autocorrigees, clarifications du validateur).

### 08 - HITL Human-in-the-Loop (27 panels)

Monitoring des 6 types HITL : Plan Approval, Clarification, Draft Critique, Destructive Confirm, FOR_EACH Confirm, Modifier Review. Qualite de classification (taux d'approbation, confiance), comportement utilisateur (temps de reponse, timeouts), analyse des editions de parametres et des rejets, metriques de reprise apres interruption HITL.

### 09 - Conversations & Users (35 panels)

Activite utilisateurs (sessions actives, repartition horaire), cycle de vie des conversations (creation, duree, longueur en messages), analyse de l'abandon (ou et quand les utilisateurs quittent), succes des agents par domaine et indicateurs de qualite. Section repliee : attachments en profondeur (duree upload par content_type, suppressions cleanup) et inscriptions par provider/statut.

### 10 - OAuth, Connectors & MCP (39 panels)

Flux OAuth complet (initiations, callbacks, succes/echec, types d'erreurs), performance OAuth (latence d'echange de tokens, rafraichissement), sante des connecteurs Google (contacts, calendar, drive, gmail, tasks), metriques des serveurs MCP (admin et per-user : connexions, appels d'outils, erreurs). Sections repliees : OAuth en profondeur (erreurs de callback, durees initiate/activation, cycle de vie des verrous de refresh, verification par cle API) et formes de requetes contacts/email (types de requetes, resultats par requete).

### 11 - Voice & WebSocket (24 panels)

TTS : latence par provider (Edge, OpenAI, Gemini), taille audio, erreurs. Streaming audio : debit, qualite. STT : transcriptions via Sherpa-onnx Whisper (duree, precision). WebSocket : connexions actives, tickets d'authentification, latence.

### 12 - Channels / Telegram (13 panels)

Flux de messages Telegram (entrants/sortants, types), bindings utilisateur-canal (OTP, etat), securite (rate limiting, tentatives invalides), fonctionnalites canal (voix, HITL clavier, formatage).

### 13 - Proactive & Heartbeat (20 panels)

Taches proactives (selections, generations, envois), notifications heartbeat (volume, cout LLM de la decision + redaction), eligibilite (fenetres horaires, quotas, cooldowns, dedup), feedback utilisateur.

### 14 - Data Registry & Checkpoints (26 panels)

Data registry (items par type, taille, operations CRUD), moteur de requetes (latence, filtres), checkpoints LangGraph (duree sauvegarde et chargement, taille payload, frequence), recherche hybride (BM25 + semantic OpenAI embeddings, scores, latence). Section repliee : sante du repository de conversations (erreurs par version, cache de resolution d'id).

### 15 - LangGraph Framework Deep Dive (36 panels)

Metriques bas niveau LangGraph : execution de graphe (duree totale, nombre de noeuds traverses), gestion d'etat (taille, serialisation), latence par etage du tour de chat (`langgraph_stage_duration_seconds`, l'instrument du chantier TTFT — voir LATENCY_PLAN), erreurs de graphe, appels d'outils par subgraph, garde double-appel du reasoning streaming. La section Langfuse est repliee et marquee : elle reste vide tant que `LANGFUSE_ENABLED=false`.

### 16 - Recording Rules & Alerts Health (27 panels)

Dashboard meta/operationnel. Sante des 86 recording rules Prometheus (evaluation, erreurs, duree), validation de la configuration et securite de la stack d'observabilite, integrite du registre d'outils (`tool_module_import_failures_total` : toute valeur > 0 signifie qu'une famille entiere d'outils manque silencieusement du registre). (L'alerting Prometheus est reactive depuis ADR-119 — le noyau de 14 alertes actives se consulte dans Prometheus `/alerts` et Alertmanager, voir README_ALERTING.md.)

### 17 - User Analytics & Geo (27 panels)

Vue geographique via Geomap (DB-IP Lite City, compteur `http_requests_by_country_total`). Engagement utilisateur (sessions, frequence, retention). Patterns d'activite (heures, jours). Usage par outil et par agent. Qualite et cout des conversations. Logs geo detailles via Loki.

**Datasources** : Prometheus + Loki (pour les logs geo).

---

### 18 - RAG Spaces / Knowledge Documents (30 panels)

Vue d'ensemble des espaces de connaissances RAG : espaces actifs, documents traites, taux de succes, requetes de retrieval, tokens embedding. Pipeline de traitement documents (rate, duree percentiles, distribution chunks, tailles uploads). Performance retrieval (rate, latence percentiles, chunks retournes, raisons de skip). Couts embedding (tokens par operation, distribution statuts documents). Section reindexation (historique runs, succes/echecs). Section repliee : recuperation de jobs par le reaper (`rag_jobs_recovered_total`).

**Datasources** : Prometheus.

### 19 - Sub-agents & Skills (10 panels)

Executions de sous-agents ReAct via `ReactSubAgentRunner` (ADR-083) : spawns par agent et mode, duree (p50/p95/p99), tokens entrants/sortants, sous-agents actifs, erreurs par type. Vision de la delegation de taches aux agents parametres.

### 20 - ReAct Agent & Browser (17 panels)

Mode d'execution ReAct : iterations par tour, appels d'outils, interruptions HITL tool-level, erreurs. Sessions navigateur headless (actions, navigation, memoire, tokens des snapshots).

### 21 - Health Metrics (10 panels)

Ingestion des echantillons sante (Apple Health) : volume par type, echecs d'authentification, rejets de validation, variations significatives detectees. Section repliee : doublons de batch ignores a l'ingestion.

### 22 - Compaction (13 panels)

Compaction de contexte v2. Ligne de sante en tete : compactions 24h, fallbacks truncation (rouge si > 0), erreurs, writer unavailable (rouge si > 0). Strategie mix, duree end-to-end et par chunk, timeouts par chunk et globaux, raisons de skip, tokens economises vs tokens consommes par la compaction.

### 23 - Journals & User Model (16 panels)

Feature journaux : extraction (volume, duree, erreurs), actions sur les entrees par action/theme/source, signaux d'evidence, consolidation (distribution par niveau, promotions/demotions, dedup), age des entrees jamais injectees, portrait utilisateur (age, feedback, duree de compilation, injections dans les prompts).

### 24 - Telephony (9 panels)

Appels sortants agentiques : appels par statut terminal, duree des appels (plafonnee par TELEPHONY_MAX_CALL_DURATION_SECONDS), reapers de recuperation T1 (notifications et syntheses de retour re-dispatchees apres crash), webhooks post-appel ignores par le filtre HMAC/foreign.

### 25 - Today Briefing (8 panels)

Page d'accueil Today Briefing (BRIEFING_DOMAIN) : duree de build par etat de cache (cold = LLM-bound, warm = quasi instantane), statuts de build par section (agenda, mails, meteo...), volume par section, invocations LLM (greeting / synthese) par issue, refreshes utilisateur.

### 26 - Product Value, Activation & Retention (42 panels)

Cockpit produit (ADR-178, spec `docs/superpowers/specs/2026-07-29-product-dashboard-program.md`). Repond a « combien d'utilisateurs obtiennent un resultat utile, a quel cout, reviennent-ils ? » sans dupliquer les dashboards techniques (liens de drill-down). 11 rows : scorecard executive (12 stats), North Star E1/E2, funnel d'activation, qualite agentique, HITL et brouillons, engagement/retention, connecteurs, routines/proactivite, recherche/mobile/performance percue, couts EUR, qualite des donnees. Trois etats de panel : **LIVE Prometheus** (series existantes : succes technique E3, feedback negatif, HITL, DAU/WAU avec caveat conversationnel, connecteurs, proactivite, TTFT, couts EUR DB-backed), **PRE-WIRED** (requetes posees sur les series `product_*` du pipeline outcomes — compteur + gauges DB-backed alimentees par le rollup horaire, `PRODUCT_ANALYTICS_ENABLED`), **LIVE PostgreSQL** (panels 3/5/18/27/31/32 : mediane de profondeur, first-pass proxy, signup->premiere valeur (ACT-03), cohortes hebdomadaires et sante des routines en SQL exact sur les vues en lecture seule). La North Star n'est jamais calculee depuis les compteurs Prometheus (etats E1/E2 mutables) : les gauges transportent des agregats SQL exacts.

La telemetrie client (Phase 4) alimente les familles `product_client_events_total` (funnel anonyme borne : landing, inscription, demo, PWA), `product_search_total` (recherche des reglages) et `product_web_vital_seconds`/`_ratio` (LCP/CLS) via `POST /api/v1/product/events` — endpoint a auth optionnelle, rate-limite par IP, schema borne par enums, emetteur frontend inerte sans `NEXT_PUBLIC_PRODUCT_TELEMETRY`.

**Datasources** : Prometheus + `postgres-product-readonly` (role `grafana_product_reader`, SELECT sur les 7 vues produit uniquement, `statement_timeout` 10s — cree par `task db:create-grafana-reader`). Alertes produit : `alerts-product.yml` prepare mais NON monte (baseline 4 semaines requise, ADR-119).

---

## Variables et Datasources

### Variables de template

Tous les dashboards declarent au minimum :

| Variable | Type | Description | Dashboards |
|----------|------|-------------|------------|
| `$datasource` | Datasource (Prometheus) | Source de metriques principale | Tous (01-26) |
| `$datasource_loki` | Datasource (Loki) | Source de logs | 05, 06, 07, 17 |
| `$datasource_tempo` | Datasource (Tempo) | Source de traces | 06 |

Des variables supplementaires sont definies par dashboard selon le besoin (filtres endpoint, node_name, model, user_id, etc.).

### UIDs des datasources

Les fichiers JSON des dashboards referencent les datasources par UID :

```json
{
  "datasource": {
    "type": "prometheus",
    "uid": "prometheus"
  }
}
```

UIDs attendus : `prometheus`, `loki`, `tempo`. Ils doivent correspondre aux UIDs configures dans le provisioning Grafana.

---

## Troubleshooting

### Probleme 1 : Panel affiche "NO DATA"

**Etape 1 - Verifier que la metrique existe** :
```bash
curl http://localhost:9091/metrics | grep <nom_metrique>
```

> Note : le endpoint metrics est sur le port 9091 (HTTP), pas 8000 (HTTPS).

**Etape 2 - Verifier le scraping Prometheus** :

Ouvrir `http://localhost:9090/targets`. Tous les targets doivent etre `UP` avec un dernier scrape recent (< 30s).

**Etape 3 - Tester la requete dans Prometheus** :

Ouvrir `http://localhost:9090/graph` et executer la requete PromQL du panel. Si aucun resultat, la metrique n'est pas generee cote application.

**Etape 4 - Verifier les labels** :

Les causes frequentes de "NO DATA" avec une metrique qui existe :
- Label inexistant dans la requete (ex: `{currency="USD"}` alors que la metrique utilise `{currency="EUR"}`)
- Metrique renommee sans mise a jour du dashboard
- `sum by (label)` sur un label qui n'existe pas

Inspecter les labels reels :
```bash
curl http://localhost:9091/metrics | grep <nom_metrique> | head -5
```

### Probleme 2 : "Data source not found"

Verifier que les datasources sont provisionnes avec les bons UIDs (`prometheus`, `loki`, `tempo`). Dans les parametres du dashboard, verifier que les variables `$datasource`, `$datasource_loki`, `$datasource_tempo` sont correctement definies et pointent vers les bons types.

### Probleme 3 : Panels cAdvisor sans donnees

Verifier que le conteneur cAdvisor est en cours d'execution et que le filtre de nom de conteneur correspond. Les dashboards utilisent le pattern `lia.*` pour matcher les conteneurs du projet :
```promql
container_cpu_usage_seconds_total{name=~"lia.*"}
```

Verifier les noms reels des conteneurs :
```bash
docker ps --format "{{.Names}}"
```

### Probleme 4 : Panels Loki sans donnees (dashboards 05, 06, 17)

Verifier que :
1. Promtail est en cours d'execution et collecte les logs de l'API
2. La datasource Loki est accessible dans Grafana (`http://localhost:3001` > Configuration > Data Sources)
3. Le job label correspond : `{job="lia-api"}`

### Probleme 5 : Panels Tempo sans donnees (dashboard 06)

Verifier que :
1. L'export OTLP est configure dans l'API (variable d'environnement `OTEL_EXPORTER_OTLP_ENDPOINT`)
2. Tempo est en cours d'execution et accessible
3. La datasource Tempo est configuree dans Grafana avec l'UID `tempo`

### Probleme 6 : Geomap sans donnees (dashboard 17)

Le panel Geomap utilise le compteur `http_requests_by_country_total` alimente par la base DB-IP Lite City. Verifier que :
1. La base GeoIP est presente et accessible par l'API
2. Le middleware de geolocalisation est actif
3. Des requetes HTTP ont ete effectuees (la metrique se remplit avec le trafic reel)

---

## Maintenance

### Emplacement des fichiers

Les dashboards sont provisionnes depuis les fichiers JSON :
```
infrastructure/observability/grafana/dashboards/
  01-app-overview.json
  02-slo-tracking.json
  03-infra-resources.json
  04-http-api.json
  05-llm-tokens-cost.json
  06-logs-traces.json
  07-agents-pipeline.json
  08-hitl.json
  09-conversations-users.json
  10-oauth-connectors-mcp.json
  11-voice-websocket.json
  12-channels.json
  13-proactive-heartbeat.json
  14-registry-checkpoints.json
  15-langgraph-deep.json
  16-meta-health.json
  17-user-analytics-geo.json
  18-rag-spaces.json
  19-subagents-skills.json
  20-react-browser.json
  21-health-metrics.json
  22-compaction.json
  23-journals-user-model.json
  24-telephony.json
  25-briefing.json
  26-product-value.json
```

### Ajouter un panel

1. **Definir la metrique** dans `apps/api/src/infrastructure/observability/metrics_*.py`
2. **Instrumenter** dans le code applicatif
3. **Tester** via `curl http://localhost:9091/metrics | grep <metrique>`
4. **Ajouter le panel** dans le JSON du dashboard concerne (ou via l'UI Grafana puis export JSON)
5. **Redemarrer Grafana** pour recharger : `task restart` ou `docker compose restart grafana`
6. **Mettre a jour cette documentation** si le panel modifie le perimetre du dashboard

### Ajouter un dashboard

1. Creer le fichier JSON dans `infrastructure/observability/grafana/dashboards/`
2. Nommer le fichier : `<numero>-<slug>.json` (ex: `18-new-domain.json`)
3. Respecter les conventions :
   - `schemaVersion: 38`
   - Tag `lia` obligatoire + tags specifiques
   - Variable `$datasource` (Prometheus) obligatoire
   - `graphTooltip: 1` (shared crosshair)
   - UID unique au format `<numero>-<slug>`
4. Ajouter le dashboard dans le tableau catalogue de cette documentation

### Conventions de rendu des panels (audit 2026-07)

Trois conventions garantissent des panels lisibles sur une instance a faible trafic :

1. **`noValue` nuance** : les panels stat de compteurs d'evenements rares (erreurs, violations, timeouts, recoveries...) declarent `noValue: "0"` — l'absence de serie pour un counter signifie reellement zero evenement. Les ratios dont le denominateur peut etre vide declarent `noValue: "n/a"` (un 0 affirmerait un 0 % jamais calcule). Les metriques de debit coeur (http_requests, llm_api_calls, tokens...) ne declarent JAMAIS de noValue : leur absence doit rester visible, c'est le signal d'une panne d'instrumentation.
2. **Fenetres adaptees a la cadence** : les `histogram_quantile` sur des familles a evenements rares (rag, voice, compaction, oauth, hitl for-each, subagents, browser...) utilisent une fenetre `[1h]` ; `user_daily_conversations_total` (observe ~1x/jour) utilise `increase(...[1d])`. Les requetes Loki utilisent `[$__auto]`, jamais une fenetre fixe.
3. **Descriptions systematiques** : chaque panel porte une description issue du help string Prometheus de sa metrique (ou du commentaire de sa recording rule), avec la mention « Empty panel = zero events in the window (healthy) » sur les timeseries d'evenements rares.

### Conventions de nommage des metriques

Suivre les bonnes pratiques Prometheus :

| Type | Suffixe | Exemple |
|------|---------|---------|
| Counter | `_total` | `http_requests_total` |
| Gauge | aucun | `db_connection_pool_size` |
| Histogram | `_seconds`, `_bytes` | `http_request_duration_seconds` |

**Labels** :
- Noms significatifs : `model`, `node_name`, `status`, `endpoint`
- Eviter la haute cardinalite (pas de `user_id` brut, utiliser `user_id_hash` si necessaire)
- Maximum ~10 labels par metrique

### Recording rules

Les 86 recording rules sont definies dans `infrastructure/observability/prometheus/recording_rules.yml`. Elles pre-calculent les requetes couteuses (taux, percentiles, aggregations) pour accelerer le rendu des dashboards. Le dashboard 16 (Meta Health) surveille la sante de ces rules.

Convention : les rules de taux d'erreur dont le numerateur peut ne matcher aucune serie (aucun 5xx, aucune erreur DB...) utilisent `or vector(0)` (ou `or <selecteur vivant> * 0` pour preserver les labels) afin de rendre 0 au lieu d'un resultat vide.

### Versionning et rollback

Les dashboards sont versionnes dans git. Pour annuler une modification :
```bash
git checkout HEAD -- infrastructure/observability/grafana/dashboards/<fichier>.json
docker compose restart grafana
```

---

## Ressources

### Documentation interne

- `docs/technical/OBSERVABILITY_AGENTS.md` : 110+ metriques Prometheus detaillees
- `docs/technical/METRICS_REFERENCE.md` : Catalogue complet de toutes les metriques
- `docs/technical/LANGFUSE.md` : Observabilite LLM complementaire (Langfuse UI)

### Code source

**Dashboards** : `infrastructure/observability/grafana/dashboards/*.json` (26 fichiers)

**Metriques** :
- `apps/api/src/infrastructure/observability/metrics_agents.py`
- `apps/api/src/infrastructure/observability/metrics_langgraph.py`
- `apps/api/src/infrastructure/observability/metrics_database.py`
- `apps/api/src/core/middleware.py`

**Recording rules** : `infrastructure/observability/prometheus/recording_rules.yml`

### References externes

- [Prometheus Best Practices](https://prometheus.io/docs/practices/)
- [PromQL](https://prometheus.io/docs/prometheus/latest/querying/basics/)
- [Grafana Dashboard Best Practices](https://grafana.com/docs/grafana/latest/dashboards/build-dashboards/best-practices/)
- [Grafana Provisioning](https://grafana.com/docs/grafana/latest/administration/provisioning/)
- [LogQL (Loki)](https://grafana.com/docs/loki/latest/query/)
- [TraceQL (Tempo)](https://grafana.com/docs/tempo/latest/traceql/)

---

**Version** : 4.5
**Date** : 2026-07-29
**Auteur** : Equipe LIA
**Statut** : Production (26 dashboards, 637 panels)
