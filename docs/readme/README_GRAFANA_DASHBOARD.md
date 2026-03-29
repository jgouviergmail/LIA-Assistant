# Grafana Dashboards - LIA

**Derniere mise a jour** : 2026-03-09
**Version** : 4.0
**Total Dashboards** : 18
**Total Panels** : 388
**Compatibilite** : Grafana 11.3, schemaVersion 38

---

## Table des Matieres

1. [Vue d'Ensemble](#vue-densemble)
2. [Catalogue des Dashboards](#catalogue-des-dashboards)
3. [Datasources](#datasources)
4. [Variables de Template](#variables-de-template)
5. [Stack Technique](#stack-technique)
6. [Troubleshooting](#troubleshooting)
7. [Maintenance](#maintenance)

---

## 1. Vue d'Ensemble

### Statistiques globales

| Metrique | Valeur |
|----------|--------|
| Dashboards | 17 |
| Panels totaux | 388 |
| Recording rules | 70+ |
| Datasources | 3 (Prometheus, Loki, Tempo) |
| Schema version | 38 |
| Navigation | Tag `lia` sur tous les dashboards |
| Tooltip partage | `graphTooltip: 1` (crosshair synchronise) |

### Architecture en Tiers

Les 18 dashboards sont organises en 5 tiers selon l'audience cible :

| Tier | Audience | Dashboards | Objectif |
|------|----------|------------|----------|
| 1 - Vue d'ensemble | Tous | 01, 02 | Sante globale, SLOs, budget d'erreurs |
| 2 - Plateforme | Ops / Dev | 03, 04, 05, 06 | Infra, HTTP, couts LLM, logs/traces |
| 3 - Fonctionnalites | Feature Dev | 07, 08, 09, 10, 11, 12, 13 | Agents, HITL, conversations, OAuth/MCP, voix, canaux, proactif |
| 4 - Avance | SRE | 14, 15, 16 | Registry, LangGraph deep, sante des regles |
| 5 - Analytics | Product | 17 | Engagement utilisateurs, geolocalisation |

---

## 2. Catalogue des Dashboards

### Tier 1 - Vue d'ensemble

#### 01 - Application Overview (23 panels)

Vue synthetique de la sante de l'application. Premiere page a consulter en cas d'incident.

**Metriques cles** : disponibilite API, budget d'erreurs, taux de requetes, latence P95, DAU/WAU, resume des couts.

Point d'entree principal vers les autres dashboards via les liens du tag `lia`.

#### 02 - SLO Tracking (17 panels)

Suivi des objectifs de niveau de service (SLOs) avec burn rate et fenetres glissantes.

**Metriques cles** : conformite SLO, burn rate (alerting windows), objectifs de latence par endpoint, disponibilite par provider LLM.

---

### Tier 2 - Plateforme

#### 03 - Infrastructure & Resources (24 panels)

Supervision de l'infrastructure sous-jacente : conteneurs Docker, bases de donnees, cache.

**Metriques cles** : CPU/memoire/disque/reseau par conteneur, pool de connexions PostgreSQL, statistiques Redis (memoire, commandes, keyspace), sante des conteneurs.

#### 04 - HTTP & API Performance (17 panels)

Performance detaillee de la couche HTTP FastAPI.

**Metriques cles** : taux de requetes (par route, methode), distribution des codes de statut, heatmap de latence, taux d'erreurs 4xx/5xx, rate limiting (compteurs Redis, rejets).

#### 05 - LLM Tokens & Cost (33 panels)

Dashboard le plus dense, dedie au suivi fin de la consommation LLM et des couts associes.

**Metriques cles** : cout USD (aujourd'hui / semaine / cumul), tokens par modele et par noeud LangGraph, ratio d'efficacite (tokens utiles vs total), suivi par utilisateur via Loki. Les 70+ recording rules pre-calculent les metriques de cout pour eviter les requetes PromQL couteuses.

#### 06 - Logs, Traces & Correlations (17 panels)

Observabilite avancee combinant les trois piliers (metriques, logs, traces).

**Metriques cles** : volume de logs (par niveau, par service), logs d'erreurs recents, traces distribuees (Tempo), correlation metrique-vers-log, suivi des jobs planifies (APScheduler).

---

### Tier 3 - Fonctionnalites

#### 07 - Agent Orchestration Pipeline (32 panels)

Vue complete du pipeline d'orchestration LangGraph, du routage a la reponse finale.

**Metriques cles** : decisions du routeur (distribution par domaine), performances du planner, execution par noeud (duree, taux de succes), utilisation des outils (top tools, echecs), contexte (taille, enrichissement), streaming SSE (latence premier token, debit).

#### 08 - HITL Human-in-the-Loop (24 panels)

Suivi du systeme d'approbation humaine a 6 types (Plan Approval, Clarification, Draft Critique, Destructive Confirm, FOR_EACH Confirm, Modifier Review).

**Metriques cles** : interruptions declenchees, taux d'approbation, qualite de classification, temps de reponse utilisateur, taux de reprise apres approbation.

#### 09 - Conversations & Users (26 panels)

Metriques metier sur l'engagement des utilisateurs et le cycle de vie des conversations.

**Metriques cles** : DAU/WAU, cycle de vie des conversations (creation, duree, messages), taux d'abandon, succes par agent, cout par conversation.

#### 10 - OAuth, Connectors & MCP (28 panels)

Sante des connexions externes : OAuth Google, connecteurs, serveurs MCP (admin + per-user).

**Metriques cles** : flux OAuth (initiations, completions, erreurs), validation PKCE, sante des connecteurs Google (Calendar, Gmail, Drive, Tasks), sante des serveurs MCP (temps de connexion, decouverte d'outils, erreurs).

#### 11 - Voice & WebSocket (24 panels)

Pipeline vocal complet : TTS (Edge/OpenAI/Gemini), STT (Sherpa-onnx Whisper), WebSocket.

**Metriques cles** : requetes TTS et latence par provider, streaming audio (debit, duree), transcription STT (precision, latence), connexions WebSocket (actives, ticket auth, erreurs).

#### 12 - Channels / Telegram (13 panels)

Canal Telegram : messages, authentification OTP, HITL via clavier inline.

**Metriques cles** : flux de messages (entrants/sortants, webhook), bindings OTP (creations, validations, expirations), interactions HITL via canal, transcriptions vocales Telegram.

#### 13 - Proactive & Heartbeat (13 panels)

Notifications proactives autonomes : interets et heartbeat.

**Metriques cles** : traitement des taches proactives (cycles, duree), notifications envoyees (par type, par canal), eligibilite (fenetres horaires, quotas, cooldowns), feedback utilisateur.

---

### Tier 4 - Avance

#### 14 - Data Registry & Checkpoints (19 panels)

Couche de donnees interne : registre de resultats, moteur de requetes, checkpoints LangGraph.

**Metriques cles** : executions d'outils (compteur, duree, resultats), moteur de requetes (recherche hybride BM25 + OpenAI embeddings), sauvegarde/chargement de checkpoints (latence, taille), recherche hybride dans le store.

#### 15 - LangGraph Framework Deep (21 panels)

Instrumentation bas niveau du framework LangGraph.

**Metriques cles** : duree des graphes et sous-graphes, taille de l'etat (serialisation), integration Langfuse (traces, spans, metriques).

#### 16 - Recording Rules & Alerts Health (10 panels)

Meta-dashboard : sante du systeme d'observabilite lui-meme.

**Metriques cles** : evaluation des recording rules (duree, erreurs), alertes actives (firing, pending), erreurs de validation des regles, metriques de securite.

---

### Tier 5 - Analytics

#### 17 - User Analytics & Geo (27 panels)

Analytique produit avec geolocalisation IP (DB-IP Lite).

**Metriques cles** : carte geographique des utilisateurs (geomap Grafana), engagement par utilisateur (sessions, duree), patterns d'activite (heatmap jour/heure), utilisation des outils par utilisateur, cout par utilisateur.

---

## 3. Datasources

Trois datasources sont configurees dans Grafana :

| Datasource | UID | Type | Usage |
|------------|-----|------|-------|
| Prometheus | `prometheus` | Metriques | Metriques applicatives, recording rules, alertes |
| Loki | `loki` | Logs | Logs structures (JSON), correlation, suivi par utilisateur |
| Tempo | `tempo` | Traces | Traces distribuees, spans, correlation avec metriques/logs |

**Note** : Prometheus scrape les metriques sur le port **9091** (HTTP-only, serveur de metriques dedie), distinct du port HTTPS 8000 utilise par l'API FastAPI. Cette separation permet un scraping sans TLS pour Prometheus tout en maintenant HTTPS sur l'API.

---

## 4. Variables de Template

### Variable commune a tous les dashboards

| Variable | Description | Valeur par defaut |
|----------|-------------|-------------------|
| `$datasource` | Selecteur de datasource Prometheus | `prometheus` |

### Variables specifiques par dashboard

| Variable | Dashboards | Description |
|----------|------------|-------------|
| `$interval` | 01, 03, 04, 05, 07 | Intervalle d'agrgation (auto, 1m, 5m, 15m, 1h) |
| `$provider` | 05, 10 | Filtrage par provider LLM (openai, anthropic, gemini, etc.) |
| `$model` | 05 | Filtrage par modele LLM |
| `$node` | 07, 15 | Noeud LangGraph (router, planner, orchestrator, etc.) |
| `$agent` | 07, 09 | Agent de domaine (email, calendar, weather, etc.) |
| `$user_id` | 09, 17 | Filtrage par utilisateur |
| `$status_code` | 04 | Code de statut HTTP |
| `$hitl_type` | 08 | Type d'interruption HITL |
| `$channel` | 12 | Canal de messagerie (telegram) |
| `$job` | 06, 16 | Job APScheduler |
| `$severity` | 06 | Niveau de log (DEBUG, INFO, WARNING, ERROR, CRITICAL) |

---

## 5. Stack Technique

### Architecture d'observabilite

```
Application (FastAPI)
  |
  +-- prometheus_client (port 9091)  --> Prometheus (scrape /metrics)
  |                                        |
  |                                        +--> Recording Rules (70+)
  |                                        +--> Alerting Rules
  |                                        +--> Grafana (dashboards 01-17)
  |
  +-- structlog (JSON)               --> Loki (via Promtail)
  |                                        |
  |                                        +--> Grafana (LogQL queries)
  |
  +-- OpenTelemetry traces           --> Tempo
                                           |
                                           +--> Grafana (trace viewer)
```

### Composants

| Composant | Role | Configuration |
|-----------|------|---------------|
| **Prometheus** | Collecte et stockage des metriques | Scrape interval 15s, retention 15j, port cible 9091 |
| **Loki** | Agrgation des logs | Labels: service, level, user_id |
| **Tempo** | Stockage des traces distribuees | Integration OpenTelemetry |
| **Promtail** | Agent de collecte de logs | Pipeline JSON, extraction de labels |
| **Grafana 11.3** | Visualisation et alerting | 18 dashboards, schemaVersion 38 |

### Recording Rules

Les 70+ recording rules pre-calculent les metriques frequemment utilisees pour optimiser les performances des dashboards. Elles sont definies dans la configuration Prometheus et couvrent :

- Taux de requetes agreges (par route, par methode)
- Couts LLM pre-calcules (par modele, par noeud, par utilisateur)
- SLOs et burn rates
- Statistiques d'agents (succes, duree moyenne)
- Metriques d'engagement utilisateur

---

## 6. Troubleshooting

### "NO DATA" sur un panel

1. **Verifier que le service cible tourne** : `task status` pour voir l'etat des conteneurs
2. **Verifier le scraping Prometheus** : acceder a `http://localhost:9090/targets` et confirmer que la cible est `UP`
3. **Verifier le port 9091** : `curl http://localhost:9091/metrics` doit retourner les metriques en format texte
4. **Verifier la recording rule** : dans Prometheus UI (`/rules`), verifier que la rule n'a pas d'erreur d'evaluation
5. **Verifier l'intervalle** : certains panels utilisent des fonctions `rate()` ou `increase()` qui necessitent un historique minimum (2x l'intervalle de scrape)

### Problemes de datasource

| Symptome | Cause probable | Solution |
|----------|---------------|----------|
| "Datasource not found" | UID incorrect dans le JSON | Verifier que les UIDs sont `prometheus`, `loki`, `tempo` |
| "Bad Gateway" sur Loki | Loki pas demarre | `task logs:api` puis verifier Loki dans docker-compose |
| Traces manquantes dans Tempo | OpenTelemetry non configure | Verifier `OTEL_EXPORTER_OTLP_ENDPOINT` dans `.env` |
| Metriques a 0 | Feature flag desactive | Verifier les flags (`CHANNELS_ENABLED`, `HEARTBEAT_ENABLED`, etc.) |

### Scraping

- Prometheus scrape le port **9091** (HTTP), pas le port 8000 (HTTPS)
- Si les metriques n'apparaissent pas apres un deploiement, verifier que `prometheus_client` est bien initialise dans le lifespan de l'application
- Les metriques custom (histogrammes, compteurs) ne produisent des donnees qu'apres la premiere occurrence de l'evenement mesure

---

## 7. Maintenance

### Ajouter un panel

1. Editer le fichier JSON du dashboard dans `infrastructure/observability/grafana/dashboards/`
2. Respecter les conventions :
   - `schemaVersion: 38`
   - `graphTooltip: 1` (crosshair partage)
   - Tag `lia` dans la liste des tags
   - Datasource via variable `$datasource` (sauf Loki/Tempo qui utilisent leur UID directement)
   - `id: null` pour les nouveaux panels (Grafana attribue l'ID automatiquement)
3. Privilegier les recording rules pour les requetes complexes ou frequentes
4. Tester dans Grafana UI (Explore) avant d'integrer dans le JSON

### Conventions des fichiers JSON

| Convention | Regle |
|------------|-------|
| Nommage | `XX-nom-du-dashboard.json` (XX = numero a 2 chiffres) |
| Emplacement | `infrastructure/observability/grafana/dashboards/` |
| UID du dashboard | Stable et unique, ne jamais changer apres creation |
| Version | Incrementer `version` dans le JSON a chaque modification |
| Lignes | Panels organises en `rows` logiques avec des titres de section |

### Procedure de redemarrage

```bash
# Redemarrer uniquement Grafana (conserve les donnees Prometheus/Loki)
docker compose -f docker-compose.dev.yml restart grafana

# Recharger les dashboards sans redemarrage (provisioning)
docker compose -f docker-compose.dev.yml exec grafana grafana-cli admin reload-dashboards

# Redemarrer toute la stack d'observabilite
task restart
```

### Ajouter un nouveau dashboard

1. Creer le fichier `XX-nom-du-dashboard.json` dans `infrastructure/observability/grafana/dashboards/`
2. Utiliser un dashboard existant comme template (copier la structure de base)
3. Ajouter le tag `lia` et configurer `graphTooltip: 1`
4. Mettre a jour ce document (`README_GRAFANA_DASHBOARD.md`) avec la description et les metriques cles
5. Si des recording rules sont necessaires, les ajouter dans la configuration Prometheus

---

*Document genere pour LIA v4.0 - 18 dashboards, 409 panels, 3 datasources.*
