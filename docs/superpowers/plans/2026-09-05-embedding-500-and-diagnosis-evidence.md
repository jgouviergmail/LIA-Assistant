# Embedding 500 INTERNAL + dossier de preuves du diagnostic — plan d'implémentation

> **Exécution : INLINE, dans cette session, tâche par tâche (règle projet : aucun sous-agent).**
> Aucune action git n'est faite par l'assistant : chaque « point de contrôle » est un moment
> où l'utilisateur peut relire et commiter. Les cases (`- [ ]`) servent au suivi.

**Objectif :** (1) rendre au tour de chat son contexte RAG, perdu à 100 % depuis au moins le
2026-09-01 parce que le SDK Gemini vide toute requête d'embedding dont l'entrée est une
SOUS-CLASSE de `str` ; (2) faire que le diagnostic automatique d'un incident nomme la cause au
lieu de « preuves insuffisantes », en lui remettant les preuves qui existaient déjà (ventilation
Prometheus, extrait Loki borné, version et âge du processus, runbook) ; (3) livrer réellement les
runbooks en production, où aucun n'a jamais atteint le diagnosticien.

**Architecture :** deux verrous structurels et un dossier de preuves déclaratif. Le verrou
principal est au SEUL entonnoir des embeddings Gemini (`GeminiRetrievalEmbeddings`), qui coerce
chaque entrée en `str` exact ; le point d'extraction du dernier message utilisateur fait de même
(ceinture et bretelles). Le dossier de preuves est une **recette par clé de corrélation**
(`EVIDENCE_RECIPES`, assert de complétude au boot, doctrine ADR-085) collectée **au moment du
diagnostic**, pas à celui du contrôle, en **échec ouvert** : une source indisponible retire une
preuve, jamais le diagnostic (doctrine ADR-247 : « la lecture de télémétrie ne lève jamais »).
Ce que le modèle a vu est stocké avec le diagnostic et rendu à l'administrateur.

**Stack :** FastAPI, structlog, prometheus_client, langchain-core 1.5.6 (`TextAccessor`),
langchain-google-genai 4.3.4, google-genai 2.10.0, Next.js 16 + react-i18next, Pester 5.

**Spécification :** ce plan est sa propre spécification ; la section « Faits établis » ci-dessous
tient lieu de dossier de preuves. Documents de doctrine à respecter :
`docs/architecture/ADR-247-Self-Diagnostics-And-Answer-Resilience.md`,
`docs/architecture/ADR-254-Embedding-Convergence-And-Shock-Absorbers.md` (§ « Insufficient
evidence, à chaque fois »), `docs/technical/DIAGNOSTICS_DOMAIN.md`.

## Faits établis (2026-09-05, production, chaque ligne mesurée)

| # | Fait | Preuve |
|---|---|---|
| F1 | Depuis 03:45 UTC, **5 tours sur 5** ont perdu leur contexte RAG (`rag_injection_failed`), messages de 84 à 405 caractères. | `agent_decisions` × `conversation_messages` ; logs `lia-api-prod` |
| F2 | Sur chaque tour : embedding mémoire OK à T, embedding RAG du **même texte** en `500 INTERNAL` à T+0,3 s, puis à T+1,3 s (réessai). | chronologie Loki 09-03, 09-04, 09-05 |
| F3 | Loki 7 j : 35 échecs `429` (1-2 sept., incident quota connu ADR-254), **23 échecs `500 INTERNAL`** (1, 3, 4, 5 sept.), tous `embed_query`, tous sur `rag_injection_failed` / `system_rag_injection_failed`. | `loki7d.py`, `loki_ops.py` |
| F4 | Le texte exact des 5 messages, ré-embarqué depuis un processus neuf par le client RAG de l'application : **5/5 OK**. Textes de 64 000 caractères : OK. Chaîne vide : `400`, pas `500`. | `repro5.py`, `repro.py` |
| F5 | `HumanMessage.text` renvoie un `TextAccessor`, **sous-classe de `str`** (langchain-core 1.5.6). Passé à `aembed_query` : `500 INTERNAL`. Un `class S(str)` nu : idem. Un `str` pur : OK. | `repro6.py` |
| F6 | Corps HTTP capturé (aiohttp) : `str` pur → `{"content":{"parts":[{"text":"…"}],…}}` ; sous-classe → `{"content":{},…}`. Le texte est perdu **à la validation pydantic du modèle de paramètres du SDK**, avant tout transformateur : `_EmbedContentParametersPrivate(contents=S("hi")).contents == Content()`. Cause exacte : `types.Content` a `from_attributes=True`, donc `Content.model_validate(S("hi"))` rend `Content()` (attributs absents → tout `None`) alors que `Content.model_validate("hi")` lève ; et dans l'union du champ `contents`, `Content` est déclaré AVANT `str`, donc l'union « smart » le retient pour une sous-classe. Identique sur google-genai 1.67.0 et 2.10.0 avec pydantic 2.13.4 : présent **au moins depuis le 8 juillet 2026** (premier lock). `t_content(S)` seul est correct — ce n'est pas le transformateur. | `repro8.py`, `union.py` (hors ligne, deux versions) |
| F7 | Le chemin mémoire réussit parce qu'il TRANCHE (`message[:N]` rend un `str` pur, `user_message_embedding.py:271`) ; le chemin RAG passe l'objet brut (`response_context.py:98` → `retrieval.py:217` → `embedding.py:190`). | code |
| F8 | `aembed_documents([S("…")])` : OK (chemin dictionnaires). Chat LangChain avec `TextAccessor` : OK. `generate_content(contents=S(…))` direct : `400 empty input` — aucun appelant direct du SDK dans `src/`. **Périmètre exact : `embed_query`/`aembed_query`.** | `repro11.py`, `repro12.py`, grep |
| F9 | Les 4 diagnostics stockés (3 × `EmbeddingOperationsFailing`, 1 × `SSELatencyP95High`) concluent tous « insuffisance de preuves ». Le dossier remis au modèle : `{check_id, value, detail:"", status, unit, warn, crit}`. | table `incidents` |
| F10 | `had_runbook = false` sur **tous** les diagnostics : `prepare-prod.ps1` ne copie que `docs/knowledge`, jamais `docs/runbooks` ; le montage compose `./docs/runbooks:/app/docs/runbooks:ro` pointe sur un répertoire vide créé par Docker. | `ls /app/docs/runbooks` (vide, root), `prepare-prod.ps1:317-328` |
| F11 | Le contrôle `embedding_failure_rate` a dit vrai : 25 % = 2 échecs / 8 opérations sur 30 min, et l'échec était déterministe (100 % des requêtes RAG). L'alerte Prometheus (≥ 3 échecs / 30 min) n'a pas tiré : 2 < 3. | Prometheus instant + range |
| F12 | Un test (`test_recent_platform_errors_are_quoted_as_DATA`) décrit une clé `recent_errors` que **rien** ne produit dans `src/`. | grep |
| F13 | Aucun autre appelant ne passe un `msg.text` brut à un embedding : `memory_injection.py:462`, `journals/context_builder.py:193`, `reminder_notification.py:346` tranchent ; le sélecteur d'outils embarque `intelligence.english_query` (sortie LLM, `str` pur). | grep des 28 appelants |

**Ce que le plan ne fait PAS, et pourquoi :** pas de plancher d'échantillons sur
`embedding_failure_rate` — l'incident du jour est un vrai positif que ce plancher aurait retardé ;
le dénominateur devient VISIBLE (ventilation dans le dossier) au lieu d'être un seuil de plus.
Pas de reclassification du `500` en permanent : le code ne peut pas distinguer un `500` de
contenu vide d'un `500` fournisseur ; le correctif retire la cause.

## Contraintes globales

- Python 3.14, MyPy strict, Black 100, Ruff ; docstrings Google ; commentaires et docs en anglais.
- Aucune chaîne utilisateur en dur côté backend ; le front ajoute ses clés dans les **6** locales.
- Aucune valeur numérique en prose dans un prompt : les bornes viennent des constantes/settings.
- Tout registre keyé par clé de domaine porte un assert de complétude au boot (ADR-085).
- Toute nouvelle métrique est câblée dans un tableau Grafana (ratchet `test_metric_coverage_ratchet_guard.py`).
- Aucun fichier logique ne dépasse 600 SLOC ; `diagnosis.py` (372 l.) et `checks.py` (381 l.) ont de la marge, mais la collecte va dans un **nouveau** module.
- La lecture de télémétrie ne lève jamais ; Loki est borné par le constructeur LogQL (`DIAGNOSTICS_LOKI_MAX_LINES`, `DIAGNOSTICS_LOKI_MAX_RANGE_HOURS`).
- Aucune donnée personnelle dans un dossier de preuves : champs en liste blanche + `sanitize_string`.
- `AGENTS.md` est généré (`task docs:sync-agents`).
- Docker Desktop local répond `500` sur l'API moteur (constaté 2026-09-05) : la preuve d'exécution se fera sur le conteneur dev si l'utilisateur le relance, sinon en production après déploiement (section « Preuve d'exécution »).

---

## Lot A — Correctif de la cause racine (RAG)

### Tâche A1 : l'entonnoir Gemini coerce chaque entrée en `str` exact

**Fichiers :**
- Modifier : `apps/api/src/infrastructure/llm/gemini_embeddings.py` (`embed_documents`, `embed_query`, `aembed_documents`, `aembed_query`, ~l. 190-258)
- Test : `apps/api/tests/unit/infrastructure/llm/test_gemini_embeddings.py`

**Interfaces :** signatures inchangées. Produit : garantie « ce qui atteint `self._client` est `type(x) is str` ».

- [ ] **Étape 1 : test rouge**

```python
class TestInputsReachTheSdkAsExactStr:
    """google-genai 2.10.0 drops the text of a `str` SUBCLASS before the request is built
    (measured 2026-09-05 in production: `"content": {}` on the wire, `500 INTERNAL` back).
    `HumanMessage.text` is one such subclass (`TextAccessor`), so the funnel is the one place
    that must normalise, whatever the caller passes."""

    class _Sub(str):
        pass

    @pytest.fixture
    def wrapper(self) -> GeminiRetrievalEmbeddings:
        wrapper = GeminiRetrievalEmbeddings.__new__(GeminiRetrievalEmbeddings)
        wrapper.model_name = "gemini-embedding-001"
        wrapper.output_dimensionality = 1536
        wrapper._client = MagicMock()
        wrapper._client.aembed_query = AsyncMock(return_value=[0.0])
        wrapper._client.aembed_documents = AsyncMock(return_value=[[0.0]])
        wrapper._client.embed_query = MagicMock(return_value=[0.0])
        wrapper._client.embed_documents = MagicMock(return_value=[[0.0]])
        return wrapper

    @pytest.mark.parametrize("text", [HumanMessage(content="bonjour").text, _Sub("bonjour")])
    async def test_aembed_query_hands_the_sdk_an_exact_str(self, wrapper, text, monkeypatch):
        monkeypatch.setattr("src.infrastructure.llm.gemini_embeddings.wait_for_slot", AsyncMock(return_value=SlotOutcome.ACQUIRED))
        monkeypatch.setattr("src.infrastructure.llm.embedding_context.persist_embedding_tokens", AsyncMock())
        await wrapper.aembed_query(text)
        sent = wrapper._client.aembed_query.await_args.args[0]
        assert type(sent) is str and sent == "bonjour"

    async def test_aembed_documents_hands_the_sdk_exact_strs(self, wrapper, monkeypatch): ...  # même forme, liste mixte
    def test_embed_query_sync_twin_normalises_too(self, wrapper): ...
    def test_embed_documents_sync_twin_normalises_too(self, wrapper): ...
```

(Vérifier dans le fichier existant le nom réel importé pour `SlotOutcome` — `src.infrastructure.rate_limiting.slot_waiter` — et le mock déjà utilisé par `test_gemini_embeddings_resilience.py` pour `wait_for_slot` ; réutiliser sa fixture si elle existe.)

- [ ] **Étape 2 :** `cd apps/api && .venv/Scripts/pytest tests/unit/infrastructure/llm/test_gemini_embeddings.py -k ExactStr -v` → **ROUGE** (`type(sent) is str` faux pour `TextAccessor`).

- [ ] **Étape 3 : implémentation minimale**

```python
def _exact_str(text: str) -> str:
    """The SDK loses the text of a ``str`` SUBCLASS: its request model validates
    ``contents`` through a pydantic union where ``Content`` (``from_attributes=True``)
    precedes ``str``, and a subclass instance is accepted as an attribute-less object —
    an EMPTY ``Content`` (measured 2026-09-05: ``"content": {}`` on the wire and
    ``500 INTERNAL`` back, on every RAG query of every turn; identical on google-genai
    1.67.0 and 2.10.0 under pydantic 2.13.4). ``HumanMessage.text`` IS such a subclass
    (``TextAccessor``). Normalising here, at the single funnel, means no caller can
    reintroduce the defect by forgetting to slice."""
    return text if type(text) is str else str(text)
```

Appliquer dans les quatre méthodes : `texts = [_exact_str(t) for t in texts]` / `text = _exact_str(text)` AVANT de construire la lambda (la lambda capture la variable normalisée) et avant `texts=[text]` de l'estimation de tokens.

- [ ] **Étape 4 :** relancer le test → VERT ; puis toute la classe de fichiers `tests/unit/infrastructure/llm/test_gemini_embeddings*.py` → VERT.
- [ ] **Étape 5 : point de contrôle** (relecture utilisateur).

### Tâche A2 : le point d'extraction du dernier message rend un `str` pur

**Fichiers :**
- Modifier : `apps/api/src/domains/agents/services/response_context.py:98` (`return str(msg.text)`), `apps/api/src/domains/agents/nodes/response_node.py:2964` (`last_user_message = str(msg.text)`)
- Test : `apps/api/tests/unit/domains/agents/services/test_response_context.py`

- [ ] **Étape 1 : test rouge**

```python
class TestExtractLastUserMessageIsAPlainStr:
    """`HumanMessage.text` is a `TextAccessor` (a `str` subclass). Whatever this function
    returns fans out to five consumers; one of them (the RAG query) handed it to a SDK that
    drops subclasses on the wire (2026-09-05). The chokepoint returns the exact type."""

    def test_str_content_is_returned_as_exact_str(self) -> None:
        state = {"messages": [HumanMessage(content="où en est le rapport ?")]}
        result = extract_last_user_message(state)
        assert type(result) is str and result == "où en est le rapport ?"

    def test_block_content_is_flattened_to_exact_str(self) -> None:
        state = {"messages": [HumanMessage(content=[{"type": "text", "text": "a"}, {"type": "text", "text": "b"}])]}
        result = extract_last_user_message(state)
        assert type(result) is str and result == "ab"
```

- [ ] **Étape 2 :** rouge (`TextAccessor`). **Étape 3 :** `str(...)` aux deux sites, avec un commentaire d'une ligne renvoyant à A1. **Étape 4 :** vert ; lancer aussi `tests/unit/domains/agents/services/test_response_context.py` et `tests/unit/domains/agents/utils/test_message_windowing.py`.
- [ ] **Étape 5 : point de contrôle.**

### Tâche A3 : la NATURE de l'échec fournisseur devient une métrique

**Pourquoi :** aujourd'hui `embedding_api_calls_total{status="error"}` dit qu'une tentative a échoué, jamais si c'est un `429`, un `500` ou une clé invalide ; la seule trace est une ligne de log. Le dossier de preuves (Lot C) doit pouvoir dire « 8 × `http_500` » sans Loki.

**Fichiers :**
- Modifier : `apps/api/src/infrastructure/llm/tracked_embeddings.py` (déclaration), `apps/api/src/infrastructure/llm/gemini_embeddings.py:_attempt` (incrément dans l'`except`)
- Modifier : `infrastructure/observability/grafana/dashboards/05-llm-tokens-cost.json` (panneau « Embedding Provider Errors by reason » à côté du panneau id 131, `gridPos {h:8, w:12, x:12, y:133}` si libre — vérifier les collisions avec `python scripts/audit/validate_observability.py` ou le script existant de validation des dashboards)
- Test : `apps/api/tests/unit/infrastructure/llm/test_gemini_embeddings_resilience.py`, ratchet `apps/api/tests/unit/test_metric_coverage_ratchet_guard.py`

Métrique :

```python
embedding_provider_errors_total = Counter(
    "embedding_provider_errors_total",
    "Embedding attempts refused by the provider, by classified reason "
    "(http_<code>, message:<marker>, or permanent) — the kind a rate cannot tell",
    ["model", "reason"],
)
```

Incrément : `reason = embedding_retry_reason(e) or "permanent"` (import depuis `embedding_errors.py`, qui expose déjà cette fonction). Cardinalité bornée : codes de `EMBEDDING_RETRYABLE_STATUS_CODES`, marqueurs `_TRANSIENT_TEXT_MARKERS`, noms de classe `TimeoutError`/`ConnectionError`, `permanent`.

- [ ] Test rouge : un `_attempt` dont la factory lève une exception avec `.code = 500` incrémente `embedding_provider_errors_total{reason="http_500"}` ; une `ValueError("bad key")` incrémente `reason="permanent"`.
- [ ] Implémentation ; panneau Grafana avec `sum by (reason) (increase(embedding_provider_errors_total[$__range])) or vector(0)` et `"noValue": "0"` ; `task ratchet:metrics` ne doit rien avoir à retirer (métrique câblée dès sa naissance) ; `pytest tests/unit/test_metric_coverage_ratchet_guard.py` vert.
- [ ] Point de contrôle.

---

## Lot B — Les runbooks atteignent la production

### Tâche B1 : `prepare-prod.ps1` stage `docs/runbooks`

**Fichiers :**
- Modifier : `scripts/deploy/prepare-prod.ps1` (après le bloc « [8/9] knowledge », l. 317-328) — même forme, copie récursive de `docs\runbooks\*` (les `.md` de premier niveau ET `alerts\`), compte des fichiers `alerts\*.md`, avertissement jaune si absent.
- Test : `scripts/deploy/deploy-prod.Tests.ps1` (le harnais hermétique fabrique déjà un projet factice avec `docs/knowledge` ; ajouter `docs/runbooks/alerts/ServiceDown.md` au projet factice et un `It "stages the alert runbooks into PROD/docs/runbooks/alerts"` dans le `Describe` du bundle, l. ~550).

- [ ] Test rouge (Pester) → `task test:deploy` rouge sur ce seul `It`.
- [ ] Implémentation ; `task test:deploy` vert.
- [ ] Point de contrôle.

### Tâche B2 : un répertoire de runbooks vide se voit

**Fichiers :**
- Modifier : `apps/api/src/domains/diagnostics/diagnosis.py` (nouvelle fonction `count_runbooks() -> int`, lecture `Path(settings.diagnostics_runbooks_dir).glob("*.md")`, jamais d'exception), `apps/api/src/infrastructure/startup/registries.py` (après les asserts diagnostics : `logger.warning("diagnostics_runbooks_missing", path=…)` quand le drapeau est actif et le compte vaut 0), `apps/api/src/domains/diagnostics/service.py:build_overview` (clé `runbooks_available: int`).
- Front : `apps/web/src/hooks/useDiagnostics.ts` (`runbooks_available: number` sur `DiagnosticsOverview`), `apps/web/src/components/settings/AdminDiagnosticsSection.tsx` (une ligne discrète quand `=== 0` : clé `settings.admin.diagnostics.runbooksMissing`), 6 locales.
- Tests : `test_diagnosis.py::TestRunbookLoader` (compte sur `tmp_path` ; répertoire absent → 0 sans lever), `test_service_overview_units.py` (clé présente), `AdminDiagnosticsSection.test.tsx` (`it('states that no runbook is mounted when the API counts zero')`).

- [ ] Rouge → implémentation → vert ; `task lint:i18n` vert.
- [ ] Point de contrôle.

---

## Lot C — Le dossier de preuves du diagnosticien

### Tâche C1 : les requêtes de ventilation entrent au catalogue

**Fichiers :** `apps/api/src/domains/diagnostics/query_catalogue.py` ; test `test_query_catalogue.py`.

Quatre entrées, toutes avec `params=(_WINDOW,)`, `unit="count"` :

| `query_id` | template |
|---|---|
| `embedding_outcomes_by_result` | `sum by (outcome) (increase(embedding_call_outcomes_total[{window_minutes}m]))` |
| `embedding_calls_by_status` | `sum by (status) (increase(embedding_api_calls_total[{window_minutes}m]))` |
| `embedding_shaper_by_outcome` | `sum by (outcome) (increase(embedding_shaper_outcomes_total[{window_minutes}m]))` |
| `embedding_errors_by_reason` | `sum by (reason) (increase(embedding_provider_errors_total[{window_minutes}m]))` |

Ajouter `"outcome"`, `"status"`, `"reason"` à `_NON_METRIC_TOKENS` si l'assert de boot les prend pour des métriques (le test `test_declared_metric_missing_from_template_is_refused` dira lequel). Pas de `or vector(0)` : ce sont des ventilations, une série absente signifie « zéro de ce libellé », ce que le collecteur (C3) écrit explicitement.

- [ ] Rouge : `TestRendering` paramétré sur les 4 ids (`render_query(id, window_minutes=30)` contient `[30m]`) ; `TestLiaMetricsResolveToProducers` couvre l'existence des métriques.
- [ ] Vert. Point de contrôle.

### Tâche C2 : le registre des recettes de preuves (déclaratif, assert au boot)

**Fichiers :**
- Créer : `apps/api/src/domains/diagnostics/evidence_recipes.py`
- Modifier : `apps/api/src/infrastructure/startup/registries.py` (l. 115-123 : appeler `assert_evidence_recipes_completeness()` dans le même `try`)
- Test : `apps/api/tests/unit/domains/diagnostics/test_evidence_recipes.py`

```python
@dataclass(frozen=True)
class EvidenceRecipe:
    """What to fetch for one incident before the diagnostician reads it.

    Keyed by CORRELATION key (the alertname a check mirrors, else the check id),
    so an alert-sourced and a self-check-sourced incident share one recipe.
    """
    correlation_key: str
    prom_queries: tuple[str, ...]          # catalogue ids, rendered with window_minutes
    log_events: tuple[str, ...]            # structlog event names (api service)
    log_levels: tuple[str, ...] = ("error", "warning")
    window_minutes: int = 30
    reason_for_none: str = ""              # non-empty ONLY when both tuples are empty

EVIDENCE_RECIPES: dict[str, EvidenceRecipe] = {r.correlation_key: r for r in (
    EvidenceRecipe("EmbeddingOperationsFailing",
        prom_queries=("embedding_outcomes_by_result", "embedding_calls_by_status",
                      "embedding_shaper_by_outcome", "embedding_errors_by_reason"),
        log_events=("gemini_embedding_failed", "rag_injection_failed",
                    "system_rag_injection_failed", "max_retries_exceeded")),
    EvidenceRecipe("LLMAPIFailureRateHigh", prom_queries=("llm_errors_by_kind",), log_events=("llm_api_call_failed",)),   # vérifié : observability/callbacks.py:294
    EvidenceRecipe("HighErrorRate", prom_queries=("http_request_rate",), log_events=("request_failed", "internal_server_error", "unhandled_exception")),  # vérifiés par grep dans src/
    EvidenceRecipe("SSELatencyP95High", prom_queries=("api_latency_p95", "llm_errors_by_kind"), log_events=()),
    EvidenceRecipe("api_latency_p95", prom_queries=("api_latency_p95",), log_events=()),
    EvidenceRecipe("DiskSpaceCritical", prom_queries=("disk_usage_percent",), log_events=()),
    EvidenceRecipe("HighMemoryUsage", prom_queries=("memory_usage_percent",), log_events=()),
    EvidenceRecipe("DatabaseDown", prom_queries=("dependency_up",), log_events=()),
    EvidenceRecipe("RedisDown", prom_queries=("dependency_up",), log_events=()),
    EvidenceRecipe("circuit_breakers", prom_queries=("llm_errors_by_kind",), log_events=()),
    EvidenceRecipe("scheduler_tick", prom_queries=("background_job_errors",), log_events=()),
    EvidenceRecipe("platform_egress", prom_queries=(), log_events=(),
        reason_for_none="the probe's own detail already names the unreachable target"),
)}
```

Les alertes cœur SANS contrôle miroir (`ServiceDown`, `ContainerRestartLoop`, `BackupFailed`, ledger…) reçoivent chacune une recette, au minimum `dependency_up`/`background_job_errors` ou un `reason_for_none` écrit : le test C2-1 lit `alerts-core.yml.template` et exige une entrée par `alertname`.

```python
def assert_evidence_recipes_completeness() -> None:
    """Every check's correlation key has a recipe; every recipe names real queries.
    Raises: AssertionError."""
```

- [ ] Tests rouges : (1) chaque `PromCheck.alertname or check_id` et chaque `InProcessCheck` key ∈ `EVIDENCE_RECIPES` ; chaque alertname de `alerts-core.yml.template` (parsé en YAML dans le test) ∈ `EVIDENCE_RECIPES` ; (2) chaque `prom_queries` id ∈ `QUERY_CATALOGUE` ; (3) chaque `log_events` nom apparaît comme littéral `"<nom>"` dans `apps/api/src` (rglob + recherche de chaîne — un nom inventé serait une recette morte) ; (4) recette vide sans `reason_for_none` refusée ; (5) `test_failfast_validations_wire_the_evidence_recipes_assert` (même forme que `TestBootWiring`).
- [ ] Vert. Point de contrôle.

### Tâche C3 : le collecteur, borné, en échec ouvert, sans PII

**Fichiers :**
- Créer : `apps/api/src/domains/diagnostics/context_collector.py`
- Créer : `apps/api/src/core/process_info.py` (`PROCESS_STARTED_AT: datetime = datetime.now(UTC)`, importé en tête de `apps/api/src/main.py`)
- Constantes : `apps/api/src/core/constants.py` → `DIAGNOSTICS_CONTEXT_LOG_LINES = 50` (lignes lues), `DIAGNOSTICS_CONTEXT_LOG_SAMPLES = 5`, `DIAGNOSTICS_CONTEXT_TOP_COUNTS = 10`, `DIAGNOSTICS_CONTEXT_FIELD_MAX_CHARS = 160`, `DIAGNOSTICS_CONTEXT_MAX_SERIES = 12`
- Métrique : `diagnostics_context_sources_total{source, status}` dans `metrics_diagnostics.py` + panneau dans `16-meta-health.json`
- Test : `apps/api/tests/unit/domains/diagnostics/test_context_collector.py`

```python
async def collect_diagnosis_context(
    incident: Incident,
    *,
    prom_client: PrometheusClient,
    loki_client: LokiClient,
) -> dict[str, object]:
    """The evidence a diagnostician can reason from, fetched AT DIAGNOSIS time.

    Fail-open by construction: every source degrades to ``{"status": "unavailable"}``
    and the runtime block is always present. Never raises.

    Returns:
        {"runtime": {...}, "metrics": [...], "logs": {...}, "recipe": key|None}
    """
```

Forme produite (JSON-sérialisable, ≤ ~4 Ko) :

```python
{
  "recipe": "EmbeddingOperationsFailing",
  "runtime": {"version": settings.app_version, "commit": settings.git_commit_sha[:12],
              "build_date": settings.build_date, "uptime_seconds": int, "window_minutes": 30},
  "metrics": [{"query_id": "embedding_outcomes_by_result", "title": "…", "status": "ok",
               "series": [{"labels": {"outcome": "failed"}, "value": 2.03}, …]}, …],
  "logs": {"status": "ok", "lines_read": 12,
           "counts": [{"event": "gemini_embedding_failed", "level": "error",
                       "head": "Error embedding content: 500 INTERNAL. {'error': {'code': 500…", "count": 8}, …],
           "samples": [{"ts": "…", "event": "…", "level": "…", "operation": "…", "error": "…"}, …]},
}
```

Règles : champs de log en **liste blanche** (`event`, `level`, `logger`, `operation`, `error`, `last_error`, `error_type`, `reason`, `attempt`, `max_retries`, `status_code`, `run_id`), chaque valeur tronquée à `DIAGNOSTICS_CONTEXT_FIELD_MAX_CHARS` puis passée dans `sanitize_string` (`pii_filter.py:483`, qui pseudonymise les e-mails et masque les secrets d'URL) ; `head` = 80 premiers caractères du champ `error`/`last_error` normalisés. Une requête Loki par recette : `build_log_query(DiagService.API, level="", minutes=window)` puis filtrage **côté client** sur `event ∈ log_events` et `level ∈ log_levels` (un `event=~` côté Loki n'est pas offert par le constructeur contraint, et on ne l'élargit pas) ; si `log_events` est vide → `logs: {"status": "skipped"}`. Séries Prometheus plafonnées à `DIAGNOSTICS_CONTEXT_MAX_SERIES` avec `truncated: true`.

- [ ] Tests rouges : Prometheus et Loki factices (`instant_query`/`query_range` sur `MagicMock` async) ; (1) recette connue → les 4 requêtes rendues avec la fenêtre de la recette ; (2) Loki `unavailable` → `logs.status == "unavailable"` et les métriques présentes ; (3) clé sans recette → seul `runtime`, `recipe: None` ; (4) une ligne dont `error` contient `alice@example.com` et `?token=abc` sort pseudonymisée/masquée ; (5) 60 lignes lues → 10 `counts`, 5 `samples`, `lines_read == 60` ; (6) un champ hors liste blanche (`content`, `user_email`) n'apparaît jamais ; (7) `metrics` compte les séries au-delà du plafond comme `truncated` ; (8) une exception inattendue dans un client (`side_effect=RuntimeError`) ne remonte pas ; (9) `PROCESS_STARTED_AT` est aware UTC et `uptime_seconds >= 0` ; (10) `diagnostics_context_sources_total` incrémenté par source et statut.
- [ ] Vert ; panneau `16-meta-health.json` (`sum by (source, status) (increase(diagnostics_context_sources_total[$__range])) or vector(0)`) ; ratchet métriques vert.
- [ ] Point de contrôle.

### Tâche C4 : la pompe de diagnostic remet le dossier au modèle et le conserve

**Fichiers :**
- Modifier : `apps/api/src/domains/diagnostics/diagnosis.py` (`_build_human_message(incident, runbook, context)`, `diagnose_incidents` : collecte **une fois par incident**, avant la boucle des langues, réutilisée pour chaque langue ; `record["context"] = context` ; `evidence_for` inchangé côté stockage)
- Modifier : `apps/api/src/domains/agents/prompts/v1/diagnostician_prompt.txt` (nouveau paragraphe : les sections « Breakdown metrics », « Recent log lines » et « Runtime » sont des données citées, bornées, éventuellement `unavailable` ; le modèle nomme la cause quand le dossier la porte, et sinon dit précisément quelle mesure manque — sans nombre en dur)
- Modifier : `apps/api/src/domains/diagnostics/checks.py:evidence_for` (ajouter `window_minutes` depuis `check.params`, omettre `detail` vide)
- Modifier : `apps/api/src/infrastructure/scheduler/diagnostics_self_check.py` (construire `PrometheusClient` et `LokiClient` depuis `settings` et les passer à `diagnose_incidents(..., prom_client=..., loki_client=...)`)
- Tests : `test_diagnosis_language_and_evidence.py` (remplacer `test_recent_platform_errors_are_quoted_as_DATA` par le contrat réel : `context["logs"]["counts"]` rendu, encadré de « quoted data » ; contexte absent → message produit), `test_diagnosis.py::TestBudget` (le collecteur est appelé **une** fois pour deux langues ; un collecteur qui lève n'empêche pas le diagnostic ; `record["context"]` stocké), `test_checks.py`/`test_incident_sync.py` (`window_minutes` présent, `detail` absent quand vide).

- [ ] Rouge → implémentation → vert sur `tests/unit/domains/diagnostics` et `tests/unit/infrastructure/scheduler/test_diagnostics_self_check*.py`.
- [ ] Point de contrôle.

### Tâche C5 : l'administrateur voit ce que le diagnosticien a vu

**Fichiers :**
- Modifier : `apps/web/src/hooks/useDiagnostics.ts` (type `DiagnosisContext` optionnel sur `diagnosis.context`), `apps/web/src/components/settings/AdminDiagnosticsSection.tsx` (sous le diagnostic, un `SettingsDisclosure` « Evidence the diagnostician read » : ligne runtime, une ligne par série métrique `title · labels → value`, une ligne par `counts` de logs `event × count — head`, mention `unavailable`/`skipped` par source)
- Locales ×6 : `settings.admin.diagnostics.contextTitle`, `contextRuntime`, `contextMetrics`, `contextLogs`, `contextUnavailable`, `contextSkipped`, `contextTruncated`
- Test : `AdminDiagnosticsSection.test.tsx` (`describe('what the diagnostician read')` : rend les séries et les comptes ; une source `unavailable` est dite, jamais rendue comme « zéro » ; aucun contexte → le bloc n'apparaît pas)

- [ ] Rouge → implémentation → `task test:frontend` + `task lint:frontend` + `task lint:i18n` verts.
- [ ] Point de contrôle.

---

## Lot D — Documentation, runbook, mémoire

### Tâche D1 : ADR-266 et documents impactés

- Créer : `docs/architecture/ADR-266-Diagnosis-Evidence-At-Diagnosis-Time-And-Exact-Str-Embedding-Inputs.md` — contexte (F1-F13 en tableau), décisions : (1) l'entonnoir normalise le type, pas les appelants ; (2) le dossier est collecté au moment du diagnostic, par recette déclarée, en échec ouvert, et STOCKÉ ; (3) ce qui est refusé (plancher d'échantillons, reclassification du 500, LogQL libre, Loki à l'instant du contrôle — révision explicite du choix ADR-254 avec sa mesure : 4 diagnostics sur 4 sans cause alors que Loki portait la réponse) ; (4) les runbooks sont livrés par `prepare-prod.ps1` et leur absence est visible.
- Modifier : `docs/architecture/ADR_INDEX.md`, `docs/INDEX.md`, `docs/technical/DIAGNOSTICS_DOMAIN.md` (module map : `evidence_recipes.py`, `context_collector.py` ; « Operations » : runbooks staged by prepare-prod, `runbooks_available`), `docs/runbooks/alerts/EmbeddingOperationsFailing.md` (§3 : « `500 INTERNAL` sur `embed_query` seulement, `aembed_documents` sain → une entrée qui n'est pas un `str` exact ; mesuré 2026-09-05 »), `CHANGELOG.md` (entrée proposée ci-dessous, l'utilisateur choisit la version), `CLAUDE.md` (pointeur ADR-266 dans « Useful Documentation Pointers » + une ligne dans « Systemic Rules › Tools » : *« What reaches a provider SDK is an exact `str` : `HumanMessage.text` is a `str` subclass and google-genai drops it on the wire — normalise at the funnel, never at the callers »*) puis `task docs:sync-agents`, `task release:sync-counts`.
- Vérifier : `task lint:docs:preview` (fichiers non encore stagés).

Entrée CHANGELOG proposée (à placer par l'utilisateur) :

> **Fix (RAG)** : chaque tour de chat perdait son contexte RAG — le SDK Gemini vide la requête quand le texte est une sous-classe de `str` (`HumanMessage.text`), et répond `500 INTERNAL`. L'entonnoir des embeddings normalise désormais le type (ADR-266). **Diagnostics** : le diagnosticien reçoit un dossier de preuves collecté au moment du diagnostic (ventilations Prometheus, extrait Loki borné et pseudonymisé, version et âge du processus), déclaré par recette et scellé par un assert au boot ; le dossier est stocké et affiché à l'administrateur. Les runbooks sont enfin livrés en production.

### Tâche D2 : mémoire de session

- Mettre à jour `project_self_diagnostics_adr247.md` et `project_embedding_convergence_adr254.md` (révision du choix Loki, mesure), créer `reference_str_subclass_dropped_by_google_genai.md` (PIÈGE MAJEUR) et l'indexer dans `MEMORY.md`.

---

## Lot E — Vérification (avant de rendre la main)

| Porte | Commande | Attendu |
|---|---|---|
| Statique | `task lint` | 0 erreur (ruff, black, mypy strict, i18n parité, docs, ratchets) |
| Backend ciblé | `cd apps/api && .venv/Scripts/pytest tests/unit/infrastructure/llm tests/unit/domains/diagnostics tests/unit/domains/agents/services/test_response_context.py tests/unit/infrastructure/scheduler -q` | vert |
| Backend rapide | `task test:backend:unit:fast` | vert, aucun `PytestUnraisableExceptionWarning`, rien après le résumé |
| Angle mort | `cd apps/api && .venv/Scripts/pytest tests/agents -q -x` | vert (suite hors hook, a déjà frappé 4 fois) |
| Ratchets | `pytest tests/unit/test_metric_coverage_ratchet_guard.py tests/unit/test_file_size_ratchet_guard.py` | vert sans toucher aux baselines |
| Déploiement | `task test:deploy` | vert (Pester runbooks) |
| Front | `task test:frontend`, `task lint:frontend` | vert |
| Docs | `task lint:docs:preview` | 0 finding |
| Pré-push | `task ci:fast` | vert |

**Preuve d'exécution (obligatoire, non remplaçable par les tests) :**
1. Conteneur dev (`docker restart lia-api-dev` puis `docker logs lia-api-dev | grep -E "application_ready|diagnostics_"`) — SI Docker Desktop local est relancé ; sinon, le dire dans le rapport.
2. Après déploiement par l'utilisateur : (a) un tour avec un espace RAG actif produit `rag_injection_completed` ou aucun `rag_injection_failed`, et `embedding_call_outcomes_total{outcome="failed"}` reste plat ; (b) `docker exec lia-api-prod ls /app/docs/runbooks/alerts | wc -l` ≥ 40 ; (c) une alerte synthétique via le webhook (procédure ADR-247) ouvre un incident dont le diagnostic porte `had_runbook: true` et un `context` avec `metrics` et `logs.status == "ok"` ; (d) le panneau admin affiche le dossier.

## Plan de test — synthèse par risque

| Risque | Test qui le ferme |
|---|---|
| Régression : un appelant repasse une sous-classe de `str` | A1 (entonnoir, 4 méthodes, `TextAccessor` réel) |
| Régression : `extract_last_user_message` rend autre chose qu'un `str` | A2 |
| Un `500` de contenu vide reste indistinguable dans les métriques | A3 (`reason="http_500"`) |
| Les runbooks disparaissent à nouveau du bundle | B1 (Pester) ; B2 (compte visible) |
| Une alerte cœur sans recette / une recette qui nomme une requête ou un événement inexistant | C2-1..4 |
| Un assert de complétude qui ne bloque pas le boot | C2-5 |
| Loki ou Prometheus indisponible casse le diagnostic | C3-2, C3-8, C4 |
| PII dans le dossier | C3-4, C3-6 |
| Dossier non borné (coût de prompt, taille JSONB) | C3-5, C3-7 |
| Dossier collecté N fois pour N langues | C4 |
| Une source `unavailable` affichée comme un zéro | C5 |
| Nouvelle métrique aveugle | ratchet métriques |
| Parité i18n | `task lint:i18n` |
| Angle mort `tests/agents/` | Lot E |

## Auto-revue du plan

- Couverture : F1-F8 → A1/A2 ; F9/F12 → C1-C5 ; F10 → B1/B2 ; F11 → décision « pas de plancher » + ventilation visible ; F13 → A1 rend l'audit des appelants non nécessaire à la correction.
- Cohérence des noms : `collect_diagnosis_context`, `EVIDENCE_RECIPES`, `assert_evidence_recipes_completeness`, `embedding_provider_errors_total`, `diagnostics_context_sources_total`, `PROCESS_STARTED_AT`, `runbooks_available`, `record["context"]` — utilisés à l'identique dans C2→C5 et B2.
- Placeholders : deux noms d'événements (`llm_call_failed`, `http_request_failed`) sont à confirmer contre `src/` pendant C2 ; le test C2-3 refuse un nom inexistant, donc l'erreur ne peut pas passer.

## Journal d'exécution (2026-09-05, livré, non commité)

| Lot | État | Preuve |
|---|---|---|
| A1 entonnoir `str` exact | fait | `test_gemini_embeddings_input_type.py` (7), suites embeddings 888 verts |
| A2 point d'extraction | fait | `TestExtractLastUserMessageIsAPlainStr`, `test_response_context.py` + windowing 66 verts |
| A3 `embedding_provider_errors_total{reason}` | fait | `test_embedding_provider_errors_metric.py` (5), panneau 133 du tableau 05, ratchet métriques vert |
| B1 runbooks stagés | fait | `prepare-prod.ps1` [8b/9], Pester « stages the per-alert runbooks », `task test:deploy` 149 verts |
| B2 compte visible | fait | `count_runbooks`, `runbooks_available`, avertissement `diagnostics_runbooks_missing` (capture_logs), notice admin (6 langues) |
| C1 ventilations | fait | 4 requêtes, `TestBreakdownQueriesForTheDiagnosisContext` |
| C2 recettes | fait | `evidence_recipes.py`, assert au boot câblé, `test_evidence_recipes.py` (16) sur les 24 alertes chargées + événements réels |
| C3 collecteur | fait | `context_collector.py`, `core/process_info.py`, `diagnostics_context_sources_total`, rangée « Self-Diagnostics » (tableau 16, 6 panneaux), baseline 56 → 51, `test_context_collector.py` (17) |
| C4 pompe + prompt | fait | contexte collecté une fois par incident après la porte budgétaire, stocké dans `diagnosis.context`, rendu « quoted data », prompt enrichi ; `detail` vide omis + `window_minutes` |
| C5 front | fait | `DiagnosisEvidence.tsx`, types du hook, 10 clés × 6 langues, `AdminDiagnosticsSection.test.tsx` 24 verts |
| D docs | fait | ADR-266 (numéro réel : 264 et 265 existaient), index, `DIAGNOSTICS_DOMAIN.md`, runbook §3, CHANGELOG « Unreleased », CLAUDE.md (règle + pointeur) → `AGENTS.md` régénéré, `release:sync-counts`, connaissance 34 |
| E portes | fait | `task lint` vert, `task test:backend:unit:fast` 22 206 verts (1 rouge = miroir AGENTS.md avant régénération, revérifié vert), `tests/agents` 1 131 verts, `task test:frontend` 7 390 verts, `task test:deploy` 149 verts, `lint:docs:preview` 0 vivant |

Défauts trouvés par la revue à froid, après portes vertes : (1) un dossier `{"status": "unavailable"}` se rendait comme « aucune recette » (corrigé, test ajouté) ; (2) le balayage des littéraux d'événements partait de `apps/api` (venv compris) au lieu de `src` (corrigé, assert sur le nom du répertoire) ; (3) les fixtures de pompe laissaient les tests unitaires joindre `prometheus:9090` (collecteur neutralisé dans les trois fixtures).

Preuve d'exécution restante : voir « Preuve d'exécution » ci-dessus (conteneur dev indisponible ce jour ; prod après déploiement par le propriétaire).

### Seconde revue à froid (même jour), après la première clôture

| Trouvaille | Preuve | Correction |
|---|---|---|
| `stream_error` figurait dans deux recettes alors que ce n'est qu'une valeur de métadonnée (`error_type`), jamais un événement de log : la recette n'aurait rien lu | grep des sites d'émission ; le test ne vérifiait qu'un littéral | test durci (premier argument d'un appel `logger.*` ou `log_event=`), entrée retirée |
| La durée de fonctionnement s'affichait en `M:SS` (« up for 47:00 »), ambigu dans une phrase | lecture du rendu | `lib/format-uptime.ts` sur `Intl.NumberFormat` (unité localisée, aucune clé i18n), 4 tests |
| Une valeur de ratio se rendait sans unité (« Embedding failure rate : 25 ») dans le prompt et dans le panneau | simulation bout en bout avec les vrais analyseurs Loki/Prometheus | l'unité du catalogue voyage dans le bloc métrique ; rendu « 25 percent » côté prompt, suffixe « 25% » côté panneau ; table de suffixes FACTORISÉE (`lib/diagnostics-units.ts`) entre les lignes de contrôle et le dossier |
| `level` est bien un label de flux Loki (promtail `level: level`) : le filtre par niveau du collecteur s'applique ; tous les événements des recettes sont émis en `warning`/`error`/`exception` | promtail-config.yml, grep des niveaux | aucune |

Simulation bout en bout (analyseurs réels, charges de la forme réelle du 05/09) : dossier 3 347 octets, prompt 2 907 caractères, aucune donnée personnelle (le champ `user_email` d'une ligne de log n'apparaît nulle part), les 8 × `500 INTERNAL`, les 4 `rag_injection_failed`, la ventilation 2 / 6 et le régulateur sain lisibles d'un coup d'œil. Docker Desktop : montage du lecteur D: cassé (`mkdir /run/desktop/mnt/host/d: file exists`), donc aucune preuve d'exécution en conteneur dev ce jour ; elle reste due après déploiement.

