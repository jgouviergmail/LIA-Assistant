# Grafana Dashboards (LIA)

**Document de reference technique - Observabilite Production avec Grafana**

> **Version 4.0** | 2026-03-09 | 18 dashboards, 312+ panels

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

Les **18 dashboards Grafana** fournissent une observabilite complete pour :

1. **Monitoring production** : Sante applicative, SLOs, performance HTTP, ressources infrastructure
2. **Agent debugging** : Pipeline d'orchestration LangGraph, router, planner, outils, HITL
3. **Cost tracking** : Tokens LLM, couts EUR, suivi par utilisateur
4. **Securite et OAuth** : Connecteurs Google, MCP, flux OAuth
5. **Incident response** : Logs + traces correles, recherche par run_id/user_id
6. **Analytics utilisateur** : Engagement, geolocalisation, patterns d'utilisation

### Chiffres cles

| Indicateur | Valeur |
|------------|--------|
| Dashboards | 18 |
| Panels total | 312+ |
| Recording rules | 70+ |
| Schema version | 38 (Grafana 11.3) |
| graphTooltip | 1 (shared crosshair) sur tous les dashboards |
| Navigation | Tag `lia` sur tous les dashboards |

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
| Prometheus | `prometheus` | Metriques + recording rules | Tous (01-18) |
| Loki | `loki` | Logs structures | 05, 06, 17 |
| Tempo | `tempo` | Traces distribuees | 06 |

### Fichiers de configuration

| Fichier | Contenu |
|---------|---------|
| `infrastructure/observability/prometheus/prometheus.yml` | Configuration scrape Prometheus |
| `infrastructure/observability/prometheus/recording_rules.yml` | 70+ recording rules |
| `infrastructure/observability/grafana/dashboards/*.json` | 18 fichiers JSON de dashboards |
| `infrastructure/observability/grafana/provisioning/` | Provisioning datasources et dashboards |

---

## Catalogue des Dashboards

| # | Dashboard | UID | Tags | Panels | Domaine |
|---|-----------|-----|------|--------|---------|
| 01 | Application Overview | `01-app-overview` | lia, overview, health | 23 | Sante globale, performance requetes, pipeline agent, infra, resume couts LLM |
| 02 | SLO Tracking | `02-slo-tracking` | lia, slo, reliability | 17 | SLOs API, SLOs agents, SLOs providers LLM, SLOs DB et business |
| 03 | Infrastructure & Resources | `03-infra-resources` | lia, infra, docker, raspberry-pi | 24 | Systeme hote (RPi), ressources conteneurs, PostgreSQL, Redis |
| 04 | HTTP & API Performance | `04-http-api` | lia, http, api, latency | 17 | Trafic, latence, erreurs, rate limiting |
| 05 | LLM Tokens & Cost | `05-llm-tokens-cost` | lia, llm, tokens, cost | 33 | Headlines couts, ventilation, consommation tokens, efficacite, suivi par utilisateur (Loki), performance API LLM, metriques cumulees |
| 06 | Logs, Traces & Correlations | `06-logs-traces` | lia, logs, traces, debug | 17 | Logs, traces, correlation metrique-log, vue correlee, jobs background, recherche |
| 07 | Agent Orchestration Pipeline | `07-agents-pipeline` | lia, agents, langgraph, orchestration | 32 | Router, planner et orchestrateur, execution nodes agent, execution outils, contexte et etat, SSE streaming |
| 08 | HITL Human-in-the-Loop | `08-hitl` | lia, hitl, approval | 24 | Vue d'ensemble HITL, qualite classification, comportement utilisateur, editions et rejets, reprise |
| 09 | Conversations & Users | `09-conversations-users` | lia, conversations, users, engagement | 26 | Activite utilisateurs, cycle de vie conversations, analyse abandon, succes et qualite agents |
| 10 | OAuth, Connectors & MCP | `10-oauth-connectors-mcp` | lia, oauth, connectors, mcp | 28 | Flux OAuth, performance OAuth, sante connecteurs, APIs Google, serveurs MCP |
| 11 | Voice & WebSocket | `11-voice-websocket` | lia, voice, tts, stt, websocket | 24 | TTS, streaming audio, STT, WebSocket |
| 12 | Channels / Telegram | `12-channels` | lia, channels, telegram | 13 | Flux messages, bindings et securite, fonctionnalites canal |
| 13 | Proactive & Heartbeat | `13-proactive-heartbeat` | lia, proactive, heartbeat | 13 | Vue d'ensemble taches, notifications et couts, eligibilite et feedback |
| 14 | Data Registry & Checkpoints | `14-registry-checkpoints` | lia, registry, checkpoints | 19 | Data registry, moteur de requetes, checkpoints LangGraph, recherche hybride |
| 15 | LangGraph Framework Deep Dive | `15-langgraph-deep` | lia, langgraph, framework | 21 | Execution graphe, gestion d'etat, integration Langfuse |
| 16 | Recording Rules & Alerts Health | `16-meta-health` | lia, meta, operational | 10 | Sante des recording rules, sante des alertes, validation et securite |
| 17 | User Analytics & Geo | `17-user-analytics-geo` | lia, users, analytics, geo | 27 | Vue geographique (Geomap), engagement utilisateur, patterns d'activite, usage outils et agents, qualite et cout conversations, logs geo detailles |
| 18 | RAG Spaces / Knowledge Documents | `18-rag-spaces` | lia, rag, spaces, knowledge | 21 | Vue d'ensemble RAG, pipeline de traitement documents, performance retrieval, couts embedding, reindexation |

---

## Details par Dashboard

### 01 - Application Overview (23 panels)

Dashboard d'accueil. Fournit une vue synthetique de la sante de l'application : taux de requetes, erreurs, latence p95, etat du pipeline agent (router, planner, outils), resume infra (CPU, memoire, DB, Redis) et resume des couts LLM du jour. Point d'entree pour identifier rapidement un probleme avant d'aller dans un dashboard specialise.

### 02 - SLO Tracking (17 panels)

Suivi des Service Level Objectives sur 4 axes : API (disponibilite, latence), agents (taux de succes, duree pipeline), providers LLM (taux d'erreur, latence par provider), et business (DB pool, Redis, taux abandon conversations). Chaque SLO affiche le budget d'erreur restant sur la periode.

### 03 - Infrastructure & Resources (24 panels)

Metriques systeme orientees Raspberry Pi (ARM64) : charge CPU hote, memoire, espace disque (node_exporter), metriques conteneurs Docker (cAdvisor), pool de connexions PostgreSQL, taille et memoire Redis. Essentiel pour le capacity planning sur hardware contraint.

### 04 - HTTP & API Performance (17 panels)

Trafic HTTP detaille : requetes/s par endpoint, distribution latence (p50/p95/p99), taux d'erreur par code HTTP, metriques de rate limiting. Complement du dashboard 01 pour le diagnostic precis des problemes de performance API.

### 05 - LLM Tokens & Cost (33 panels)

Dashboard le plus riche en panels. Headlines de couts (jour, mois, projection), ventilation par modele et par node, consommation tokens (prompt, completion, cached), metriques d'efficacite (cout par requete, tokens par seconde). Section Loki pour le suivi par utilisateur. Performance des appels API LLM (latence, erreurs par provider). Metriques de cout cumulees sur la duree de vie.

**Datasources** : Prometheus + Loki (pour les logs de suivi utilisateur).

### 06 - Logs, Traces & Correlations (17 panels)

Observabilite unifiee. Volume de logs par niveau, recherche par `run_id` ou `user_id`, vue traces distribuees via Tempo, correlation metrique-vers-log et trace-vers-log. Section jobs background (scheduler). Aides a la recherche (templates LogQL et TraceQL).

**Datasources** : Prometheus + Loki + Tempo.

### 07 - Agent Orchestration Pipeline (32 panels)

Coeur du monitoring agent. Sections pour chaque etape du pipeline : router (decisions, confiance, latence), planner (plans crees, retries, validation, succes), orchestrateur (vagues d'execution, parallellisme), execution des nodes agent (duree, statut, erreurs), execution des outils (taux succes, latence par outil), contexte et etat (taille state, checkpoints), SSE streaming (TTFT, tokens/s, erreurs).

### 08 - HITL Human-in-the-Loop (24 panels)

Monitoring des 6 types HITL : Plan Approval, Clarification, Draft Critique, Destructive Confirm, FOR_EACH Confirm, Modifier Review. Qualite de classification (taux d'approbation, confiance), comportement utilisateur (temps de reponse, timeouts), analyse des editions de parametres et des rejets, metriques de reprise apres interruption HITL.

### 09 - Conversations & Users (26 panels)

Activite utilisateurs (sessions actives, repartition horaire), cycle de vie des conversations (creation, duree, longueur en messages), analyse de l'abandon (ou et quand les utilisateurs quittent), succes des agents par domaine et indicateurs de qualite.

### 10 - OAuth, Connectors & MCP (28 panels)

Flux OAuth complet (initiations, callbacks, succes/echec, types d'erreurs), performance OAuth (latence d'echange de tokens, rafraichissement), sante des connecteurs Google (contacts, calendar, drive, gmail, tasks), metriques des serveurs MCP (admin et per-user : connexions, appels d'outils, erreurs).

### 11 - Voice & WebSocket (24 panels)

TTS : latence par provider (Edge, OpenAI, Gemini), taille audio, erreurs. Streaming audio : debit, qualite. STT : transcriptions via Sherpa-onnx Whisper (duree, precision). WebSocket : connexions actives, tickets d'authentification, latence.

### 12 - Channels / Telegram (13 panels)

Flux de messages Telegram (entrants/sortants, types), bindings utilisateur-canal (OTP, etat), securite (rate limiting, tentatives invalides), fonctionnalites canal (voix, HITL clavier, formatage).

### 13 - Proactive & Heartbeat (13 panels)

Taches proactives (selections, generations, envois), notifications heartbeat (volume, cout LLM de la decision + redaction), eligibilite (fenetres horaires, quotas, cooldowns, dedup), feedback utilisateur.

### 14 - Data Registry & Checkpoints (19 panels)

Data registry (items par type, taille, operations CRUD), moteur de requetes (latence, filtres), checkpoints LangGraph (duree sauvegarde, taille payload, frequence), recherche hybride (BM25 + semantic E5, scores, latence).

### 15 - LangGraph Framework Deep Dive (21 panels)

Metriques bas niveau LangGraph : execution de graphe (duree totale, nombre de noeuds traverses), gestion d'etat (taille, serialisation), integration Langfuse (traces LLM, cout par trace, latence par span).

### 16 - Recording Rules & Alerts Health (10 panels)

Dashboard meta/operationnel. Sante des 70+ recording rules Prometheus (evaluation, erreurs, duree), sante des alertes (firing, pending, erreurs d'evaluation), validation de la configuration et securite de la stack d'observabilite.

### 17 - User Analytics & Geo (27 panels)

Vue geographique via Geomap (DB-IP Lite City, compteur `http_requests_by_country_total`). Engagement utilisateur (sessions, frequence, retention). Patterns d'activite (heures, jours). Usage par outil et par agent. Qualite et cout des conversations. Logs geo detailles via Loki.

**Datasources** : Prometheus + Loki (pour les logs geo).

---

### 18 - RAG Spaces / Knowledge Documents (21 panels)

Vue d'ensemble des espaces de connaissances RAG : espaces actifs, documents traites, taux de succes, requetes de retrieval, tokens embedding. Pipeline de traitement documents (rate, duree percentiles, distribution chunks, tailles uploads). Performance retrieval (rate, latence percentiles, chunks retournes, raisons de skip). Couts embedding (tokens par operation, distribution statuts documents). Section reindexation (historique runs, succes/echecs).

**Datasources** : Prometheus.

---

## Variables et Datasources

### Variables de template

Tous les dashboards declarent au minimum :

| Variable | Type | Description | Dashboards |
|----------|------|-------------|------------|
| `$datasource` | Datasource (Prometheus) | Source de metriques principale | Tous (01-18) |
| `$datasource_loki` | Datasource (Loki) | Source de logs | 05, 06, 17 |
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

Les 70+ recording rules sont definies dans `infrastructure/observability/prometheus/recording_rules.yml`. Elles pre-calculent les requetes couteuses (taux, percentiles, aggregations) pour accelerer le rendu des dashboards. Le dashboard 16 (Meta Health) surveille la sante de ces rules.

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

**Dashboards** : `infrastructure/observability/grafana/dashboards/*.json` (17 fichiers)

**Metriques** :
- `apps/api/src/infrastructure/observability/metrics_agents.py`
- `apps/api/src/infrastructure/observability/metrics_langgraph.py`
- `apps/api/src/infrastructure/observability/metrics_database.py`
- `apps/api/src/infrastructure/observability/middleware.py`

**Recording rules** : `infrastructure/observability/prometheus/recording_rules.yml`

### References externes

- [Prometheus Best Practices](https://prometheus.io/docs/practices/)
- [PromQL](https://prometheus.io/docs/prometheus/latest/querying/basics/)
- [Grafana Dashboard Best Practices](https://grafana.com/docs/grafana/latest/dashboards/build-dashboards/best-practices/)
- [Grafana Provisioning](https://grafana.com/docs/grafana/latest/administration/provisioning/)
- [LogQL (Loki)](https://grafana.com/docs/loki/latest/query/)
- [TraceQL (Tempo)](https://grafana.com/docs/tempo/latest/traceql/)

---

**Version** : 4.0
**Date** : 2026-03-09
**Auteur** : Equipe LIA
**Statut** : Production (18 dashboards, 312+ panels)
