# Rapport d'audit de la code base LIA

**Date** : 2026-07-03
**Périmètre** : 100 % du monorepo (`apps/api`, `apps/web`, `infrastructure/`, `docs/`, `scripts/`, CI/CD)
**Hors périmètre** : sécurité (exclue à la demande du commanditaire)
**Méthode** : audit inline systématique en 12 passes — inventaire structurel, lecture des fichiers clés, analyse AST (longueur de fonctions), greps de conformité aux patterns, contre-vérification de chaque constat chiffré.

---

## 1. Volumétrie et périmètre analysé

| Composant | Mesure vérifiée |
|---|---|
| Backend Python (`apps/api/src`) | 863 fichiers, ≈ 337 000 lignes, 5 957 fonctions |
| Frontend TypeScript (`apps/web/src`) | 438 fichiers, ≈ 85 000 lignes |
| Tests backend | 497 fichiers, 9 931 fonctions de test |
| Tests frontend | 13 fichiers, 103 cas |
| Migrations Alembic | 106, toutes avec `downgrade()` |
| Domaines DDD backend | 32 |
| Documentation | 288 fichiers markdown, 85 ADRs, 35 runbooks |
| Dashboards Grafana | 22 — 60 alertes Prometheus, 97 recording rules |
| Fichiers suivis par git | 2 869 (aucun artefact `__pycache__`/`egg-info`/`.pyc` committé) |

Le domaine `agents` concentre à lui seul **158 626 lignes (47 % du backend)** répartis sur 335 fichiers.

---

## 2. Synthèse des notes

Échelle : /10, calibrée sur les standards du marché pour un produit open-source destiné à la production (référentiels implicites : ISO 25010, DORA, pratiques SRE/12-factor).

| # | Périmètre | Note | Tendance |
|---|---|---|---|
| 1 | Infrastructure | **8,5** | Excellente pour une cible mono-nœud |
| 2 | Architecture | **8,0** | DDD rigoureux, un méga-domaine |
| 3 | Conception | **7,5** | Très bons fondamentaux, state god-object |
| 4 | Implémentation | **7,0** | Discipline élevée, god functions au cœur |
| 5 | Généricité | **8,0** | Abstractions connecteurs/LLM exemplaires |
| 6 | Évolutivité | **7,0** | Feature flags + registres, strates legacy |
| 7 | Maintenabilité | **6,0** | Point faible n°1 : complexité concentrée |
| 8 | Exploitabilité | **8,5** | Observabilité de niveau entreprise |
| 9 | Scalabilité | **6,0** | Multi-worker propre, horizontal absent (assumé) |
| 10 | Documentation | **9,0** | Rare à ce niveau, même en entreprise |
| 11 | Robustesse | **7,5** | Fail-fast + dégradation gracieuse |
| 12 | Fiabilité | **7,0** | Checkpointing solide, latence & flaky tests |
| 13 | Qualité | **7,5** | Outillage strict bout-en-bout |
| 14 | Optimisation | **7,5** | Nombreuses optimisations ciblées et documentées |
| 15 | Performances | **6,0** | TTFT prod 16-57 s — chantier connu, non démarré |
| 16 | Patterns & bonnes pratiques | **7,5** | Conformité élevée, écarts localisés |
| 17 | Tests unitaires | **6,0** | Volume massif mais couverture faible et quarantaine CI |
| 18 | Internationalisation (ajouté) | **8,5** | 6 langues, parité outillée et bloquante |
| 19 | Gestion de configuration (ajouté) | **8,0** | Settings par domaine, complétude vérifiée en CI |

### Note globale : **7,3 / 10**

Lecture : *codebase de qualité supérieure à la moyenne du marché open-source, avec une discipline d'ingénierie (observabilité, documentation, outillage qualité) digne d'une équipe entreprise — mais dont la dette de complexité est anormalement concentrée dans les 5-6 fichiers qui constituent le cœur exécutif du produit, et dont le filet de tests est trop lâche par rapport à la criticité de ce cœur.*

---

## 3. Constats détaillés par périmètre

### 3.1 Infrastructure — 8,5/10

**Forces (vérifiées)**
- `docker-compose.prod.yml` : limites CPU/mémoire calibrées sur mesures réelles (commentaires « actual usage ~7M »), healthchecks systématiques, `no-new-privileges`, dépendances `service_healthy`, API publiée en loopback-only derrière cloudflared (raisonnement documenté dans le fichier même).
- `Dockerfile.prod` API : multi-stage (builder / model-downloader / geoip-downloader / runtime), utilisateur non-root, healthcheck, résolution dynamique de la base GeoIP mensuelle (anti-404 daté).
- CI GitHub Actions : actions épinglées par SHA, concurrency groups, lint backend+frontend, MyPy, tests avec services PostgreSQL/Redis, build Docker des deux images, job « code-hygiene » original (parité i18n, heads Alembic multiples, complétude `.env.example`, appels Store synchrones).
- Release : build multi-arch (QEMU) + push GHCR avec tags semver.
- Secrets chiffrés SOPS (`.env.encrypted`, `.sops.yaml`), `generate-secrets.sh`.
- Entrypoint : migrations avant fork des workers, mode Prometheus multiprocess conditionné et non-fatal, seeds idempotents.

**Faiblesses**
- **[Majeur — effort S]** PostgreSQL publié sur `0.0.0.0:5432` en prod (« for external DB management »). Indépendamment de tout angle sécurité (hors périmètre), c'est une exposition opérationnelle inutile en régime nominal : à restreindre en loopback (`127.0.0.1:5432:5432`) et ouvrir ponctuellement au besoin.
- **[Modéré — effort M]** Image API très lourde : Chromium + Node 22 + Docker CLI + ffmpeg + modèle Whisper (~375 Mo) dans une seule image. Temps de build/deploy et surface de dépendances élevés ; le montage du socket Docker et du CLI Claude dans le conteneur API couple la fonction « DevOps remote » au runtime applicatif. Piste : image sidecar dédiée pour l'outillage DevOps.
- **[Mineur]** `pg_isready -h postgres -U postgres -d lia` codé en dur dans l'entrypoint alors que le reste utilise `${POSTGRES_*}` — fonctionne (pg_isready ne vérifie pas les credentials) mais incohérent.
- **[Mineur]** cAdvisor en `privileged: true` sans le commentaire de justification que les autres services ont.

### 3.2 Architecture — 8,0/10

**Forces**
- DDD réel et homogène : 27 domaines sur 32 exposent le quintuple `models/repository/service/router/schemas` ; les exceptions sont justifiées (briefing = lecture seule sans modèle, shared = schémas croisés).
- Agrégation des routers avec garde par feature flag systématique (`if getattr(settings, "x_enabled")`) et import paresseux — les sous-systèmes optionnels ne coûtent rien désactivés.
- Pattern alternatif documenté (BRIEFING_DOMAIN.md) pour les agrégations read-only hors LangGraph — signe d'une architecture pensée, pas subie.
- 85 ADRs indexés ; les décisions structurantes (ADR-063 invalidation cross-worker, ADR-070 modes d'exécution, ADR-092 HITL replay-safe) sont tracées et référencées dans le code.
- Multi-worker géré sérieusement : leader election pour le scheduler, invalidation de caches cross-worker via Redis pub/sub, Prometheus multiprocess.

**Faiblesses**
- **[Majeur — effort L]** Le domaine `agents` est un méga-domaine (47 % du backend, 335 fichiers) qui contient de facto plusieurs bounded contexts distincts (orchestration, streaming, HITL, drafts, registry de rendu, tools par fournisseur, sous-agents…). La cohésion interne existe (sous-dossiers), mais la frontière domaine est trop large : tout changement au cœur transite par ce domaine. Piste : promouvoir `streaming`, `hitl`, `tools` (ou `display/registry`) en domaines/paquets de premier niveau avec interfaces explicites.
- **[Modéré — effort M]** `Settings` composé par héritage multiple de 24 classes. Documenté (l'ordre MRO est commenté), mais fragile : une collision de nom de champ entre deux modules est silencieuse (le MRO tranche). Piste : composition par agrégation (`settings.agents.x`) ou test unitaire d'unicité des noms de champs entre modules.
- **[Modéré]** Strates architecturales successives visibles dans le nommage : « Phase 5 », « Phase 8 », « V3 », « LOT 4.3 », « OPTIMPLAN » coexistent dans les commentaires et noms de fichiers (`planner_node_v3.py`, `router_node_v3.py` sans v1/v2 restants). L'histoire est traçable mais le lecteur nouveau doit archéologiser. 51 fichiers du domaine agents portent encore des marqueurs legacy/deprecated.

### 3.3 Conception — 7,5/10

**Forces**
- `BaseRepository[ModelType]` (PEP 695) : CRUD générique, taxonomie d'erreurs DB pour les métriques (deadlock/timeout/constraint/serialization), soft-delete, pagination standardisée.
- 62 exception raisers centralisés typés `NoReturn` avec classification client/serveur pour les métriques — le contrat d'erreur API est un vrai sous-système conçu.
- Circuit breaker maison complet (états, half-open, métriques, décorateur et context manager).
- Migrations de schéma d'état LangGraph versionnées (`_schema_version` 0.0→1.3) avec fonctions de migration idempotentes — pratique rare et excellente pour un état checkpointé en base.
- Réducteur de messages avec mémoïsation des comptages de tokens par message-id (correctif de performance documenté in situ).

**Faiblesses**
- **[Majeur — effort L]** `MessagesState` est un god-object d'état : ~80 champs dans un seul TypedDict, dont une douzaine typés `Any`/`dict[str, Any]` (plans, résultats de validation), et **des champs de debug panel (`rag_injection_debug`, `memory_injection_debug`, `journal_injection_debug`…) persistés dans l'état checkpointé PostgreSQL**. Conséquences : perte de type-safety au cœur du système, checkpoints plus lourds, couplage entre l'UI de debug et la persistance. Pistes : (a) sous-structurer l'état en TypedDicts par sous-système, (b) typer les champs `Any` avec les vrais modèles Pydantic, (c) sortir le debug de l'état persisté (channel éphémère ou clé non checkpointée).
- **[Modéré — effort M]** Incohérence du pattern service : la règle maison (« constructor receives AsyncSession ») est appliquée dans `users`, mais `ConversationService` reçoit `db` en paramètre de chaque méthode. Les deux styles coexistent selon l'âge du code.
- **[Modéré]** Code neutralisé conservé : `_should_filter_hitl_message` documenté « DISABLED » mais toujours présent et appelé ; méthodes `get_messages_with_tokens`, `_v2`, `_auto` coexistantes dans le même service.

### 3.4 Implémentation — 7,0/10

**Forces**
- Typage : MyPy avec `disallow_untyped_defs`, `no_implicit_optional`, plugin Pydantic ; 2 749 sections `Args:`/`Returns:` de docstrings Google-style.
- Logging : structlog exclusif (les 8 usages de `logging.getLogger` sont légitimes — configuration des niveaux de bibliothèques tierces) ; zéro `print()` réel (les 7 occurrences sont dans des docstrings).
- Middleware pure-ASGI (refactor F28 documenté) : suppression du coût BaseHTTPMiddleware par requête, comportement SSE préservé, request-id propagé, enrichissement GeoIP hors chemins exclus.
- Zéro usage de `requests` (httpx async partout), 1 seul `time.sleep` (dans l'utilitaire de retry synchrone, à dessein).

**Faiblesses**
- **[Critique — effort XL]** Complexité de fonctions hors normes au cœur exécutif, mesurée par AST :
  - `response_node` : **2 210 lignes** (une fonction)
  - `_stream_with_new_services` : 1 689 lignes
  - `lifespan` : 1 091 lignes
  - `_handle_execution_plan` : 737 lignes ; `stream_sse_chunks` : 600 ; `planner_node_v3` : 593 ; `stream_chat` : 523 ; `build_graph` : 517…
  - **168 fonctions dépassent 150 lignes.** Ce sont précisément les chemins critiques (réponse, streaming, orchestration, HITL). Toute correction y est risquée, tout test unitaire y est difficile — c'est la racine commune des notes maintenabilité/tests. Piste : extraction incrémentale en fonctions pures testables (le découpage logique existe déjà sous forme de blocs commentés — le refactor est largement mécanique), en commençant par `response_node` et le lifespan (registre d'initialiseurs au lieu de 6 blocs copiés-collés « init cache + register invalidation »).
- **[Modéré]** 978 `except Exception` dans src/. L'échantillonnage montre une majorité de « log-and-degrade » assumés (observabilité, callbacks, locks — « metrics must never break the handler »), ce qui est défendable, mais 68 sont des `except Exception: pass` silencieux. Piste : bannir le pass nu (logger au minimum en debug + compteur Prometheus d'erreurs avalées).
- **[Modéré]** 183 `# type: ignore` et 86 `# noqa` — acceptable en volume relatif (0,05 %/ligne) mais à surveiller ; 69 `raise HTTPException` bruts subsistent (concentrés dans les clients connecteurs et 2-3 routers récents) en contradiction avec la règle maison des raisers centralisés.

### 3.5 Généricité — 8,0/10

**Forces**
- Abstraction connecteurs exemplaire : clients de base par type d'authentification (`base_oauth_client`, `base_api_key_client`, `base_google_client`, `base_microsoft_client`, `base_apple_client`), `protocols.py`, `registry.py`, `normalizers/` — l'ajout d'un provider est un chemin balisé (il existe même un `validate_new_connector.sh`).
- LLM factory multi-provider (OpenAI, Anthropic, Google, DeepSeek, Ollama) avec adapters, profils de capacités par modèle en cache, configuration par type d'usage (`LLM_TYPES_REGISTRY`).
- Système de tools uniformisé : `ToolResponse`/`ToolErrorModel`/`ToolErrorCode` avec validation d'exhaustivité de l'enum au boot (fail-fast).
- Prompts versionnés sur disque avec fallback, version pilotée par env var.

**Faiblesses**
- **[Mineur]** Les fichiers de tools par domaine dupliquent des structures d'orchestration très proches (les gros `*_tools.py` de 1 700-3 000 lignes partagent des séquences quasi identiques de validation/résolution/formatage). Les helpers existent (`runtime_helpers.py`, `mixins.py`) mais la factorisation est incomplète.

### 3.6 Évolutivité — 7,0/10

**Forces**
- Feature flags systématiques sur tous les sous-systèmes optionnels, du router à la config.
- Registre d'agents dynamique + catalogue de tools chargé par manifest ; ajout d'un agent = chemin documenté (GUIDE_AGENT_CREATION.md).
- Migrations d'état versionnées : les checkpoints d'anciennes versions survivent aux déploiements.

**Faiblesses**
- **[Majeur]** L'évolution du cœur passe par les god files (§3.4) : le coût marginal d'une évolution du pipeline de réponse ou du streaming est élevé et croissant.
- **[Modéré]** Purge legacy incomplète : suffixes `_v3` orphelins, 51 fichiers marqués legacy, méthodes versionnées coexistantes — chaque strate augmente la surface à comprendre avant de modifier.

### 3.7 Maintenabilité — 6,0/10

C'est la note plancher, conséquence directe des constats précédents :
- Les 10 plus gros fichiers du backend font 2 600-4 100 lignes ; `i18n_v3.py` (4 109), `constants.py` (3 876), `parallel_executor.py` (3 875), `config/agents.py` (3 500), `response_node.py` (3 383).
- `StreamingService` : 1 classe, 34 méthodes, 2 996 lignes.
- Frontend : 4 composants de settings entre 1 300 et 1 430 lignes.
- Le lifespan répète 6 fois le même motif init/register — 1 091 lignes là où un registre déclaratif en ferait ~200.

**Pistes priorisées (effort L→XL, gain élevé)**
1. Découper `response_node` en pipeline de fonctions pures (extraction des blocs commentés existants).
2. Registre déclaratif d'initialiseurs dans `main.py`.
3. Scinder `StreamingService` (émission SSE / debug metrics / cycle de vie).
4. Scinder `constants.py` et `config/agents.py` par sous-domaine.
5. Éclater les composants settings frontend en sous-composants par section.

À noter en positif : la densité de commentaires contextuels de très haute qualité (chaque contournement documente son pourquoi, souvent avec la date et le bug d'origine) atténue significativement le coût de lecture — sans elle, la note serait 4.

### 3.8 Exploitabilité — 8,5/10

**Forces**
- Observabilité de niveau entreprise : ~450 métriques Prometheus définies dans 23 modules dédiés, 22 dashboards Grafana thématiques (du pipeline agents au HITL en passant par la géographie utilisateurs), 60 alertes, 97 recording rules, traces Tempo corrélées logs/métriques, Langfuse pour le tracing LLM, filtre PII dans les logs.
- 35 runbooks (alertes, LangGraph, Redis, tunnel Cloudflare).
- CHANGELOG.md de 511 Ko tenu rigoureusement, versionnage semver discipliné, scripts d'administration et de diagnostic fournis (`scripts/admin`, `scripts/monitoring`, `test_oauth_health.py`).
- Endpoint `/config` pour l'auto-configuration des clients ; healthchecks à tous les étages.

**Faiblesses**
- **[Modéré]** Le monitoring lui-même vit sur le même nœud que l'application (Prometheus/Grafana/Loki sur le RPi5) : une panne du nœud emporte l'observabilité qui permettrait de la diagnostiquer. Piste : remote-write vers un Prometheus/Grafana Cloud gratuit en secours.
- **[Mineur]** Rétention traces/métriques 7 jours — court pour l'analyse de tendances (assumé vu le hardware).

### 3.9 Scalabilité — 6,0/10

**Forces**
- Le travail multi-worker est fait sérieusement : leader election du scheduler, invalidation cross-worker des 6 caches in-memory (ADR-063), métriques multiprocess agrégées, pool SQLAlchemy configuré (`pool_pre_ping`, timeout fail-fast, monitoring du pool avec seuils 503).
- PostgreSQL comme colonne vertébrale de l'état (checkpoints LangGraph, store) : le scale-out des workers API est théoriquement possible.

**Faiblesses**
- **[Majeur — assumé par design]** Architecture verticale mono-nœud (RPi5, 4 CPU/16 Go) : scheduler in-process (APScheduler), tâches de fond dans le process API (extraction mémoire, consolidation, embeddings E5 locaux), pas de file de travail externe. Le passage à N nœuds exigerait d'extraire le scheduler et les workers de fond. Ce n'est pas un défaut d'exécution — c'est un choix de cible — mais la note reflète la distance au scale-out.
- **[Modéré]** Modèle d'embeddings E5 chargé dans chaque worker API (×4) : RAM multipliée et démarrage ralenti (start_period 60 s). Piste : service d'embeddings dédié ou passage complet aux embeddings API.

### 3.10 Documentation — 9,0/10

288 fichiers, 85 ADRs indexés, 35 runbooks, guides de création (agents, tools, tests), INDEX maintenu, documentation fraîche (89 fichiers modifiés dans les 2 derniers mois), docstrings Google-style généralisées, commentaires de code contextuels datés. README/CONTRIBUTING/CHANGELOG de qualité professionnelle. C'est au-dessus des standards du marché, open-source comme entreprise.

**Faiblesses** : **[Mineur]** dérives ponctuelles doc/code — CLAUDE.md annonce 75 ADRs (85 réels) et érige en règle `check_resource_ownership()` alors que le code applique majoritairement le scoping par `user_id` au niveau repository (8 usages réels du helper). La règle documentée et la pratique réelle devraient être réalignées.

### 3.11 Robustesse — 7,5/10

**Forces**
- Fail-fast au boot : validation de la config LLM, de l'exhaustivité des `ToolErrorCode`, du registre d'affichage des drafts, de la matrice de capacités des modèles — les dérives de config cassent au démarrage, pas à la requête n.
- Dégradation gracieuse systématique et hiérarchisée : Redis indisponible → l'app démarre ; cache pricing KO → coût zéro (logué) ; multiproc metrics KO → mode single-process.
- HITL replay-safe (ADR-092) : les boucles d'édition de drafts checkpointent avant chaque interrupt — les resumes ne rejouent pas les mutations LLM. Bug latent des clés d'état non déclarées corrigé et documenté dans le code.
- Validation de séquence de messages OpenAI (suppression des ToolMessages orphelins) après troncature — classe d'erreurs API éliminée à la source.

**Faiblesses**
- **[Modéré]** 68 `except Exception: pass` totalement silencieux — chacun est une panne potentiellement invisible. Même dans les chemins « ne doit jamais casser le handler », un compteur d'erreurs avalées est nécessaire.
- **[Modéré]** Certaines dégradations gracieuses sont fonctionnellement trompeuses : pricing cache KO → coûts affichés à 0 € (l'utilisateur voit une donnée fausse plutôt qu'une absence de donnée).

### 3.12 Fiabilité — 7,0/10

**Forces** : checkpointing PostgreSQL de l'état conversationnel, migrations idempotentes exécutées avant le fork des workers, garde anti-multi-heads Alembic en CI, healthchecks avec `start_period` calibré, redémarrages `unless-stopped`.

**Faiblesses**
- **[Modéré]** Historique d'instabilité du tunnel Cloudflare en prod (documenté, correctifs appliqués 2026-03) — le point d'entrée public reste un SPOF hors du contrôle applicatif.
- **[Modéré]** 10 fichiers de tests quarantainés dans la CI (`--ignore=...` dans ci.yml) alors qu'ils tournent en local : la CI et le pre-commit ne valident pas le même ensemble. Un test quarantainé sans ticket est un test qui ne reviendra jamais. Piste : marqueur `flaky` explicite + issue par fichier, ou suppression assumée.

### 3.13 Qualité — 7,5/10

Ruff (E,W,F,I,B,C4,UP) + Black + MyPy quasi-strict + ESLint + tsc `--noEmit` + Prettier, appliqués aux trois niveaux (pre-commit, task ci, GitHub Actions). Conventional commits respectés (vérifié sur l'historique récent). Frontend TypeScript strict avec **2 occurrences de `: any` sur 85 000 lignes** — exceptionnel. Chat reducer FSM pur, immutable, défensif, avec commentaires de protection contre les races documentés.

**Faiblesses** : 52 % des `Field()` Pydantic sans `description` (628/1 206 en ont une) contre une règle maison à 100 % ; MyPy n'est pas en mode `strict = true` complet (`disallow_untyped_decorators = false`).

### 3.14 Optimisation — 7,5/10

**Forces (toutes vérifiées dans le code, avec leur justification écrite)**
- Mémoïsation des comptages tiktoken par message-id dans le réducteur (élimination d'un coût CPU synchrone répété sur l'event loop).
- Middleware pure-ASGI (F28) supprimant task-group + memory streams par requête.
- 6 caches applicatifs in-memory à invalidation cross-worker + caches Redis par section (briefing) avec TTL adaptés à la volatilité de chaque source.
- Architecture double mode pipeline/ReAct dont le mode par défaut est explicitement le plus économe (4-8× moins de tokens).
- Smart services (QueryAnalyzer, SmartPlanner) avec LRU et apprentissage de patterns pour réduire les appels LLM.

**Faiblesses** : les optimisations sont ponctuelles et réactives (chacune répond à un incident mesuré) ; il n'y a pas encore de budget de performance par endpoint ni de test de non-régression de latence automatisé (le plan « latency optimization » existe, non démarré).

### 3.15 Performances — 6,0/10

Le goulot est connu et mesuré par le projet lui-même : **TTFT en prod 16-57 s, p95 ~12-15 s par étage LLM** (query_analyzer, response, initiative). C'est intrinsèque à un pipeline multi-étages LLM sur une infra modeste, mais cela reste le principal point de douleur utilisateur. Le pré-chantier d'optimisation (3 lots) est spécifié mais non démarré. Les fondations non-LLM sont, elles, saines : pas d'I/O bloquante détectée sur l'event loop (2 301 fonctions async, offload `to_thread`/`run_in_executor` aux 20 endroits attendus), pool DB dimensionné, indexes présents (102 déclarations sur les modèles), eager loading utilisé (39 usages `selectinload`/`joinedload`).

**Pistes** : exécuter le plan de latence existant (streaming du raisonnement, parallélisation des étages indépendants, modèles plus rapides sur les étages non critiques) ; ajouter un benchmark de TTFT en CI nightly pour objectiver les régressions.

### 3.16 Respect des patterns et bonnes pratiques — 7,5/10

Conformité élevée aux règles que le projet s'est lui-même fixées (CLAUDE.md), vérifiée point par point : structlog exclusif ✔, ToolResponse/ToolErrorModel ✔ (validés au boot), prompts versionnés ✔, constantes centralisées ✔ (au point que `constants.py` en déborde), repositories génériques ✔, response_model déclarés (207) ✔, Depends d'auth systématiques (215) ✔.

**Écarts** : 69 `HTTPException` bruts ; règle `check_resource_ownership` documentée mais remplacée en pratique par le scoping `user_id` (équivalent fonctionnellement, divergent documentairement) ; pattern service incohérent entre domaines anciens et récents ; descriptions `Field()` à 52 %.

### 3.17 Tests unitaires — 6,0/10

**Forces**
- Volume : 9 931 fonctions de test backend, marqueurs disciplinés (`--strict-markers`), `asyncio_mode=auto`, tests dédiés aux migrations d'état, à la parité i18n, à la stabilité des types LangGraph, au PII filter — le ciblage des tests sur les invariants critiques est intelligent.
- Frontend : les 103 tests couvrent précisément les zones à plus haut risque (reducer FSM, handlers SSE, sanitization XSS, batching de tokens) — triage pertinent.
- Bonne pratique maison : interdiction des seuils en dur dans les tests (lecture depuis settings).

**Faiblesses**
- **[Majeur — effort L]** Seuil de couverture backend : **43 %** (gate CI et pyproject). Le standard marché pour un cœur critique est 70-80 %. Le cœur exécutif (response_node, streaming, orchestration) est précisément le moins couvrable en l'état à cause de sa forme monolithique — la dette de tests et la dette de complexité sont le même problème.
- **[Majeur]** 10 fichiers de tests exclus de la CI (`--ignore`) sans marqueur ni ticket — divergence CI/local (cf. §3.12).
- **[Modéré]** Frontend : 13 fichiers de tests pour 438 fichiers source ; aucun test de composant au-delà de 3, pas de tests E2E automatisés (Playwright présent comme outil mais pas de suite E2E applicative en CI).
- **[Mineur]** Organisation historique hétérogène : `tests/unit/` coexiste avec des dossiers top-level (`tests/agents`, `tests/core`, `tests/services`…) et des noms redondants (`test_conversation_service.py` / `test_conversations_service.py` / `test_conversation_service_v2.py`).

### 3.18 Internationalisation — 8,5/10 (périmètre ajouté)

6 langues avec parité de clés **bloquante** à trois niveaux (pre-commit, CI, doc du piège CLDR zh), i18n backend structurée en modules dédiés, locales frontend par namespace. Faiblesse : `i18n_v3.py` à 4 109 lignes (le suffixe `_v3` sans v1/v2 trahit encore l'archéologie) et chargement mémoire intégral.

### 3.19 Gestion de configuration — 8,0/10 (périmètre ajouté)

Settings Pydantic par domaine (25 modules), tout passe par l'environnement, `.env.example` de 111 Ko maintenu avec vérification de complétude en CI, feature flags homogènes, constantes centralisées. Faiblesses : héritage multiple 24 branches (§3.2), `constants.py` de 3 876 lignes devenu fourre-tout, mixité de pinning dans requirements.txt (54 `==`, 20 `>=`/`~=` — les non-épinglés créent un risque de dérive de build).

---

## 4. Plan de remédiation priorisé

| Priorité | Action | Criticité | Effort | Périmètres impactés |
|---|---|---|---|---|
| 1 | Découper `response_node` (2 210 l.) en pipeline de fonctions pures testables | Critique | XL (itératif) | Maintenabilité, tests, fiabilité |
| 2 | Découper `_stream_with_new_services` et `StreamingService` | Critique | L | Maintenabilité, tests |
| 3 | Sortir les tests quarantainés de la CI de leur zone grise (fix, marqueur `flaky`+ticket, ou suppression) | Majeur | S-M | Tests, fiabilité |
| 4 | Relever le gate de couverture par paliers (43→55→65→75 %) en ciblant d'abord le cœur refactoré | Majeur | L (continu) | Tests, qualité |
| 5 | Restreindre le port 5432 prod en loopback | Majeur | S | Infrastructure |
| 6 | Assainir `MessagesState` : typer les `Any`, sortir les champs debug de l'état checkpointé | Majeur | M | Conception, performances |
| 7 | Registre déclaratif d'initialiseurs dans le lifespan (1 091 → ~200 l.) | Modéré | M | Maintenabilité |
| 8 | Éliminer les 68 `except: pass` silencieux (log + compteur) | Modéré | S | Robustesse |
| 9 | Purge legacy : suffixes `_v3`, méthodes `_v2`/`_auto`, code « DISABLED » | Modéré | M | Évolutivité, maintenabilité |
| 10 | Exécuter le plan de latence (TTFT) + benchmark nightly | Modéré | L | Performances |
| 11 | Épingler les 20 dépendances non pinnées ; migrer les 69 HTTPException bruts | Modéré | S | Qualité, fiabilité |
| 12 | Test d'unicité des champs entre modules Settings (collision MRO silencieuse) | Modéré | S | Configuration |
| 13 | Compléter les descriptions `Field()` (628/1 206) ; réaligner CLAUDE.md sur la pratique réelle (ownership, 85 ADRs) | Mineur | S | Documentation, qualité |
| 14 | Sidecar DevOps (sortir Claude CLI/Docker CLI de l'image API) | Mineur | M | Infrastructure |

---

## 5. Conclusion

LIA est une codebase **atypiquement mature pour un projet individuel open-source** : l'observabilité, la documentation, l'outillage qualité et la discipline de configuration sont au niveau de ce qu'on trouve dans de bonnes équipes plateforme en entreprise, et plusieurs pratiques (migrations d'état versionnées, invalidation de caches cross-worker, fail-fast de config au boot, parité i18n bloquante) sont franchement au-dessus du standard.

La dette est réelle mais **remarquablement localisée** : elle se concentre dans la forme (pas le fond) du cœur exécutif du domaine agents — une poignée de fonctions et de classes monolithiques qui cumulent l'essentiel du risque de maintenance, du déficit de tests et de la friction d'évolution. C'est une bonne nouvelle : le problème est circonscrit, le découpage logique existe déjà sous forme de blocs commentés, et le refactoring est majoritairement mécanique. Les priorités 1-4 du plan ci-dessus traitent ~60 % de l'écart entre la note globale actuelle (7,3) et le potentiel réaliste de la base (8,5+).

*Sécurité exclue du périmètre à la demande du commanditaire ; les mentions d'exposition réseau (§3.1) sont traitées sous l'angle exploitation uniquement.*
