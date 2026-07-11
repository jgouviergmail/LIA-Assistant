# Index de la Documentation LIA

> Carte complète de toute la documentation du projet LIA - Assistant IA multi-agent avec LangGraph

**Version**: 7.10
**Dernière mise à jour**: 2026-07-09
**Statut**: Complète (190+ documents)

---

## Vue d'Ensemble

Cette documentation couvre l'intégralité du projet **LIA** : un assistant IA conversationnel multi-agent basé sur **LangGraph 1.2.4**, **FastAPI 0.136.3**, et **Next.js 16**.

| Métrique | Valeur |
|----------|--------|
| Documents totaux | 190+ |
| Documents techniques | 50+ |
| Guides pratiques | 15+ |
| Runbooks | 35+ |
| ADRs | 116 |
| Skills Claude | 10 |

---

## Par Où Commencer ?

### Pour les Nouveaux Développeurs

| Étape | Document | Description |
|-------|----------|-------------|
| 1 | [GETTING_STARTED.md](./GETTING_STARTED.md) | Installation et premiers pas |
| 2 | [ARCHITECTURE.md](./ARCHITECTURE.md) | Architecture globale du projet |
| 3 | [STACK_TECHNIQUE.md](./technical/STACK_TECHNIQUE.md) | Référence versions technologies |
| 4 | [GUIDE_DEVELOPPEMENT.md](./guides/GUIDE_DEVELOPPEMENT.md) | Workflow de développement |
| 5 | [GUIDE_API.md](./guides/GUIDE_API.md) | Guide de l'API REST |

### Pour les Architectes

| Document | Description |
|----------|-------------|
| [ARCHITECTURE.md](./ARCHITECTURE.md) | Architecture globale |
| [GRAPH_AND_AGENTS_ARCHITECTURE.md](./technical/GRAPH_AND_AGENTS_ARCHITECTURE.md) | Système multi-agents LangGraph |
| [STATE_AND_CHECKPOINT.md](./technical/STATE_AND_CHECKPOINT.md) | State management et persistence |
| [ADR_INDEX.md](./architecture/ADR_INDEX.md) | Architecture Decision Records (110) |

### Pour les Product Managers

| Document | Description |
|----------|-------------|
| [HITL.md](./technical/HITL.md) | Human-in-the-Loop (approbations utilisateur) |
| [LLM_PRICING_MANAGEMENT.md](./technical/LLM_PRICING_MANAGEMENT.md) | Gestion des coûts LLM |
| [GOOGLE_API_TRACKING.md](./technical/GOOGLE_API_TRACKING.md) | Suivi consommation Google Maps Platform |
| [METRICS_REFERENCE.md](./technical/METRICS_REFERENCE.md) | Métriques business |

### Pour les DevOps / SRE

| Document | Description |
|----------|-------------|
| [GETTING_STARTED.md](./GETTING_STARTED.md) | Déploiement Docker |
| [CI_CD.md](./technical/CI_CD.md) | Pipeline CI, pre-commit, branch protection |
| [OBSERVABILITY_AGENTS.md](./technical/OBSERVABILITY_AGENTS.md) | Stack observabilité complète |
| [TIMEOUT_REGISTRY.md](./technical/TIMEOUT_REGISTRY.md) | Référence centralisée de tous les timeouts backend (HTTP, tools, locks, scheduler, SSE/WS) — Settings, ranges, defaults, cascades |
| [README_OBSERVABILITY.md](./readme/README_OBSERVABILITY.md) | Guide observabilité quickstart |
| [runbooks/](./runbooks/) | Runbooks opérationnels (34+ procédures) |
| [audit/](./audit/README.md) | **Audit technique 360° public** — rapport (8.5/10, 24 périmètres ISO 25010) + [protocole reproductible](./audit/AUDIT_PROTOCOL.md) et pipeline de republication |

---

## Documentation Principale

| Document | Description | Statut |
|----------|-------------|--------|
| [GETTING_STARTED.md](./GETTING_STARTED.md) | Guide d'installation complet | ✅ |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | Architecture globale, patterns, technologies | ✅ |
| [INDEX.md](./INDEX.md) | Ce document - carte de la documentation | ✅ |

---

## Documentation Technique

### Architecture & Système

| Document | Description | Statut |
|----------|-------------|--------|
| [GRAPH_AND_AGENTS_ARCHITECTURE.md](./technical/GRAPH_AND_AGENTS_ARCHITECTURE.md) | LangGraph, nodes, routing, orchestration | ✅ |
| [STATE_AND_CHECKPOINT.md](./technical/STATE_AND_CHECKPOINT.md) | MessagesState, reducers, PostgreSQL checkpointing | ✅ |
| [MESSAGE_WINDOWING_STRATEGY.md](./technical/MESSAGE_WINDOWING_STRATEGY.md) | Windowing par node, truncation, compaction intelligente (F4), performance | ✅ |
| [COMPACTION_v2.md](./technical/COMPACTION_v2.md) | Compaction v2 — hardening (timeouts, retry, truncation fallback), SSE events, keepalive concurrent, sonner toast UX, runbook (2026-05) | ✅ |
| [CONVERSATION_HISTORY_PAGINATION.md](./technical/CONVERSATION_HISTORY_PAGINATION.md) | Keyset (scroll-up) pagination on `/conversations/me/messages` — has_more/next_cursor contract, frontend sentinel + scroll-preservation, env-tunable bounds (2026-05) | ✅ |
| [TOKEN_TRACKING_AND_COUNTING.md](./technical/TOKEN_TRACKING_AND_COUNTING.md) | Token tracking, alignment DB/Prometheus | ✅ |
| [DATABASE_SCHEMA.md](./technical/DATABASE_SCHEMA.md) | Schema PostgreSQL complet, migrations Alembic | ✅ |
| [STACK_TECHNIQUE.md](./technical/STACK_TECHNIQUE.md) | Référence complète versions technologies | ✅ |
| [REACT_EXECUTION_MODE.md](./technical/REACT_EXECUTION_MODE.md) | ReAct execution mode — 4-node loop, pipeline vs ReAct, tools, HITL, skills | ✅ |
| [LATENCY_PLAN.md](./optim/LATENCY_PLAN.md) | Latency/TTFT optimization lot — per-stage instrumentation (`langgraph_stage_duration_seconds`), reproducible protocol (`scripts/perf/measure_ttft.py`), quantified shortlist & before/after | 🚧 |
| [BACKGROUND_RUNS.md](./technical/BACKGROUND_RUNS.md) | Exécution détachée du chat (ADR-117) — producteur + Redis Streams, archive-first, drain shutdown, flag `BACKGROUND_RUNS_ENABLED` | ✅ |

### Agents & Outils

| Document | Description | Statut |
|----------|-------------|--------|
| [AGENTS.md](./technical/AGENTS.md) | Architecture multi-agent, AgentRegistry | ✅ |
| [TOOLS.md](./technical/TOOLS.md) | Architecture tools, @connector_tool | ✅ |
| [AGENT_MANIFEST.md](./technical/AGENT_MANIFEST.md) | ToolManifest, catalogue, domain taxonomy | ✅ |
| [GOOGLE_CONTACTS_INTEGRATION.md](./technical/GOOGLE_CONTACTS_INTEGRATION.md) | Intégration Google Contacts | ✅ |
| [EMAIL_FORMATTER.md](./technical/EMAIL_FORMATTER.md) | Formatage emails, templates | ✅ |
| [CONNECTORS_PATTERNS.md](./technical/CONNECTORS_PATTERNS.md) | Patterns connecteurs OAuth/API Key | ✅ |
| [CONNECTOR_PHILIPS_HUE.md](./connectors/CONNECTOR_PHILIPS_HUE.md) | Philips Hue smart lighting connector (local + remote) | ✅ |
| [MICROSOFT_365_INTEGRATION.md](./technical/MICROSOFT_365_INTEGRATION.md) | Intégration Microsoft 365 (Outlook, Calendar, Contacts, To Do) | ✅ |
| [VOICE.md](./technical/VOICE.md) | Voice/TTS catalogue-driven (Edge / OpenAI / ElevenLabs, ADR-081), per-message attribution, progressive sentence streaming (ADR-082) | ✅ |
| [VOICE_MODE.md](./technical/VOICE_MODE.md) | STT (local Sherpa + remote ElevenLabs Scribe), Wake Word, Push-to-Talk, voice_stt_mode opt-in (v1.20.x) | ✅ |
| [ROUTES.md](./technical/ROUTES.md) | Google Routes API, directions | ✅ |
| [WEB_FETCH.md](./technical/WEB_FETCH.md) | Extraction contenu pages web (URL → Markdown), SSRF prevention | ✅ |
| [BROWSER_CONTROL.md](./technical/BROWSER_CONTROL.md) | Browser automation (Playwright) — navigation, interaction, extraction JS, progressive screenshots (SSE side-channel) — evolution F7 | ✅ |
| [MCP_INTEGRATION.md](./technical/MCP_INTEGRATION.md) | MCP (Model Context Protocol) — Serveurs d'outils externes, MCP Apps, Excalidraw | ✅ |
| [CHANNELS_INTEGRATION.md](./technical/CHANNELS_INTEGRATION.md) | Canaux de messagerie externes (Telegram) — evolution F3 | ✅ |
| [ATTACHMENTS_INTEGRATION.md](./technical/ATTACHMENTS_INTEGRATION.md) | Pièces jointes (images, PDF) avec analyse vision LLM — evolution F4 | ✅ |
| [IMAGE_GENERATION.md](./technical/IMAGE_GENERATION.md) | AI Image Generation — multi-provider, cost tracking, attachment storage | ✅ |
| [HEARTBEAT_AUTONOME.md](./technical/HEARTBEAT_AUTONOME.md) | Notifications proactives LLM-driven (Heartbeat) — evolution F5 | ✅ |
| [HEALTH_METRICS.md](./technical/HEALTH_METRICS.md) | Health Metrics — iPhone Shortcuts ingestion, per-user tokens, charts, aggregation; assistant integrations (agents + Heartbeat + journal + memory) + `HEALTH_KINDS` registry (v1.17.2) | ✅ |
| [LANDING_PAGE.md](./technical/LANDING_PAGE.md) | Architecture Landing Page — composants React, SEO, OpenGraph | ✅ |
| [LLM_CONFIG_ADMIN.md](./technical/LLM_CONFIG_ADMIN.md) | Administration dynamique des configurations LLM (34 types, 8 providers) | ✅ |
| [SKILLS_INTEGRATION.md](./technical/SKILLS_INTEGRATION.md) | Skills system (agentskills.io standard) — SKILL.md files, activation, scripts, rich outputs (frames + images), runtime conventions, hardened import pipeline + chat-driven install + dialogue skills (ADR-118) | ✅ |

### Cost Tracking & Billing

| Document | Description | Statut |
|----------|-------------|--------|
| [LLM_PRICING_MANAGEMENT.md](./technical/LLM_PRICING_MANAGEMENT.md) | Pricing LLM, token counting, exports | ✅ |
| [LLM_PRICING_TEMPLATES.md](./technical/LLM_PRICING_TEMPLATES.md) | Reasoning shape templates dans l'admin Pricing — Template/Custom modes, snapshot semantics, fingerprint dédupliqué | ✅ |
| [GOOGLE_API_TRACKING.md](./technical/GOOGLE_API_TRACKING.md) | Google Maps Platform tracking, pricing admin, consumption exports (admin + user v1.9.1) | ✅ |

### LLM & Intelligence

| Document | Description | Statut |
|----------|-------------|--------|
| [LLM_PROVIDERS.md](./technical/LLM_PROVIDERS.md) | Providers LLM, modèles, configuration (Admin UI + .env fallback), compatibilité | ✅ |
| [LLM_PROVIDER_CONSTRAINTS.md](./technical/LLM_PROVIDER_CONSTRAINTS.md) | Contraintes de paramétrage LLM par provider et par modèle (matrice complète) | ✅ |
| [PROMPTS.md](./technical/PROMPTS.md) | Système prompts, versioning, unified planner, memory extraction prompt | ✅ |
| [PLANNER.md](./technical/PLANNER.md) | Planner node, ExecutionPlan DSL, FOR_EACH | ✅ |
| [PLAN_PATTERN_LEARNER.md](./technical/PLAN_PATTERN_LEARNER.md) | Apprentissage patterns, Bayesian | ✅ |
| [PATTERN_LEARNER_TRAINING.md](./technical/PATTERN_LEARNER_TRAINING.md) | Training automatisé, Golden Patterns | ✅ |
| [RESPONSE.md](./technical/RESPONSE.md) | Response node, anti-hallucination | ✅ |
| [ROUTER.md](./technical/ROUTER.md) | Router node, binary routing | ✅ |
| [SMART_SERVICES.md](./technical/SMART_SERVICES.md) | QueryAnalyzer, SmartPlanner, SmartCatalogue | ✅ |
| [SEMANTIC_ROUTER.md](./technical/SEMANTIC_ROUTER.md) | Semantic Tool Router, max-pooling | ✅ |
| [SEMANTIC_INTENT_DETECTION.md](./technical/SEMANTIC_INTENT_DETECTION.md) | Semantic Intent Detection | ✅ |
| [LOCAL_EMBEDDINGS.md](./technical/LOCAL_EMBEDDINGS.md) | OpenAI embeddings (migrated from E5) | ✅ |
| [MULTI_DOMAIN_ARCHITECTURE.md](./technical/MULTI_DOMAIN_ARCHITECTURE.md) | Architecture multi-domaines | ✅ |
| [LANGFUSE.md](./technical/LANGFUSE.md) | Langfuse integration | ✅ |

### Mémoire & Contexte

| Document | Description | Statut |
|----------|-------------|--------|
| [LONG_TERM_MEMORY.md](./technical/LONG_TERM_MEMORY.md) | Mémoire long-terme, profil psychologique | ✅ |
| [MEMORY_RESOLUTION.md](./technical/MEMORY_RESOLUTION.md) | Résolution références, relations — architecture 3 phases (LLM extraction + recherche ciblée + résolution) | ✅ |
| [INTERESTS.md](./technical/INTERESTS.md) | Système apprentissage centres d'intérêt | ✅ |
| [SCHEDULED_ACTIONS.md](./technical/SCHEDULED_ACTIONS.md) | Actions planifiées récurrentes | ✅ |
| [SUB_AGENTS.md](./technical/SUB_AGENTS.md) | Persistent specialized sub-agents (F6) | ✅ |
| [HYBRID_SEARCH.md](./technical/HYBRID_SEARCH.md) | Recherche hybride BM25 + sémantique | ✅ |
| [JOURNALS.md](./technical/JOURNALS.md) | Personal Journals — carnets de bord introspectifs, injection sémantique | ✅ |
| [USAGE_LIMITS.md](./technical/USAGE_LIMITS.md) | Per-user usage limits — tokens, messages, cost quotas with 5-layer enforcement | ✅ |
| [PSYCHE_ENGINE.md](./technical/PSYCHE_ENGINE.md) | Psyche Engine — complete functional & technical documentation with scenarios | ✅ |
| [ADR-068-Psyche-Engine.md](./architecture/ADR-068-Psyche-Engine.md) | Psyche Engine — architectural decision record | ✅ |
| [ADR-104-Psyche-De-Saturation.md](./architecture/ADR-104-Psyche-De-Saturation.md) | Psyche de-saturation — source-level fix for the confined-mood failure (prod baseline, decisions, readjustment matrix) | ✅ |
| [ADR-105-Psyche-Embodied-Expression.md](./architecture/ADR-105-Psyche-Embodied-Expression.md) | Psyche embodied expression layer (A-E) — concrete voice grammar replacing adjective directives (blind-eval validated) | ✅ |
| [ADR-106-HITL-Contract-Coherence.md](./architecture/ADR-106-HITL-Contract-Coherence.md) | HITL contract coherence — `hitl_required` = pre-exec non-draft only (invariant-locked), ReAct mutation gate unified on `tool_confirmation`, batch draft-critique wording from the ADR-085 registry | ✅ |
| [ADR-069-Gemini-Embedding-Migration.md](./architecture/ADR-069-Gemini-Embedding-Migration.md) | Gemini embedding migration (OpenAI → Google) — ADR | ✅ |
| [ADR-075-Rich-Skill-Outputs.md](./architecture/ADR-075-Rich-Skill-Outputs.md) | Rich Skill Outputs — SkillScriptOutput JSON contract, SKILL_APP registry type, sandboxed iframe widget, theme/locale sync (v1.16.8) | ✅ |
| [ADR-079-Stratified-Journal-Consciousness.md](./architecture/ADR-079-Stratified-Journal-Consciousness.md) | Stratified Journal Consciousness — L0/L1/L2/L3 levels, epistemic status, deferred self-evaluation, ambient portrait diffusion | ✅ |
| [ADR-080-Voice-STT-Remote-Pricing-Unit.md](./architecture/ADR-080-Voice-STT-Remote-Pricing-Unit.md) | Remote Voice STT (ElevenLabs Scribe) opt-in per user + `pricing_unit` extension on `llm_model_pricing` (per_1m_tokens / per_audio_minute / per_audio_hour); per-message cost attribution on `conversation_messages.stt_*`; CSV exports | ✅ |
| [ADR-081-Voice-TTS-Catalogue-Driven.md](./architecture/ADR-081-Voice-TTS-Catalogue-Driven.md) | Voice TTS migrated to the LLM catalogue: `voice_tts` LLM type (kind=tts), Edge/OpenAI/ElevenLabs seeded with prices, voice + tuning in `provider_config` JSONB, dynamic admin voice picker (`/admin/voice/voices?provider=X`), retirement of `system_settings.voice_tts_mode` and 14 `VOICE_TTS_*` env vars | ✅ |
| [ADR-082-Progressive-Sentence-Streaming.md](./architecture/ADR-082-Progressive-Sentence-Streaming.md) | Progressive sentence streaming for low-latency TTS — `ProgressiveSentenceStreamer` (in-order delivery, lock-protected drain, sentinel idempotence), persistent httpx ElevenLabs client, voice LLM in `astream`, 5× TTFA reduction in chat mode, 2× in agent mode | ✅ |
| [ADR-083-Sub-Agent-Delegation-React.md](./architecture/ADR-083-Sub-Agent-Delegation-React.md) | Sub-Agent Delegation — from ReAct loop (Phase 1, 2026-05-13) to one-shot expert LLM call (Phase 1bis, 2026-05-14). `delegate_to_sub_agent_tool` is a single LLM invocation with persona+expertise written by the principal and all data inlined in instruction; no tools, no graph. Phase 2 cleanup deleted the legacy persistent F6 plumbing | ✅ |
| [ADR-084-Indexable-vs-Semantic-Criteria.md](./architecture/ADR-084-Indexable-vs-Semantic-Criteria.md) | Universal planning principle (`INDEXABLE vs SEMANTIC CRITERIA`) + 4-layer defense (prompt section, structured `semantic_filter_terms` hint emitted by the query analyzer, universal `PlanValidator._check_semantic_leak` gated by `PLANNER_SEMANTIC_LEAK_MODE` in `off`/`observe`/`autocorrect`, `ToolManifest.text_search_mode` opt-out). Catches semantic qualifiers (medical, urgent, important) leaked into literal-search `query` params on any connector. Phase 1 shipped 2026-05-15 in `observe` mode (zero plan mutation); Phase 2 promotion to `autocorrect` gated on operational telemetry | ✅ |
| [ADR-085-Draft-Display-Registry.md](./architecture/ADR-085-Draft-Display-Registry.md) | Single declarative registry (`DRAFT_DISPLAY_REGISTRY`) for post-HITL rendering of every `DraftType`: domain emoji, item label fields, optional secondary datetime, detail fields, noun/verb keys for localized header composition. Replaces 4 disjoint legacy tables (`DRAFT_TYPE_EMOJIS`, `_DRAFT_RESULT_FIELD_CONFIG`, hardcoded label-extraction chain) with structural exhaustivity assertion at lifespan startup + CI. Adds 2 grammar i18n tables (`DRAFT_RESULT_NOUNS` with gender/plural per language, `DRAFT_RESULT_VERBS_PAST` with gender/number forms for fr/es/it) and per-language pluralization rule + word-order template — produces correct `3 rappels supprimés` / `1 tâche créée` / `3 reminders deleted` / `已删除 3 个提醒` headers | ✅ |
| [ADR-088-Journal-Restraint-And-Level-Routed-Injection.md](./architecture/ADR-088-Journal-Restraint-And-Level-Routed-Injection.md) | Journal refinement (amends ADR-079): restraint-first extraction (default `[]`, explicit-signal grounding bar, generic capability prohibition, capped L0 release valve), de-pressured consolidation (conditional L2, no synthesis quota), operational injection restricted to L1/L2 (`JOURNAL_OPERATIONAL_INJECTION_EXCLUDE_LEVELS`), and ReAct directive coherence (`JOURNAL_REACT_CONTEXT_MAX_ENTRIES`, count cap, no truncation). No schema change | ✅ |
| [ADR-090-Semantic-Layer-Governance.md](./architecture/ADR-090-Semantic-Layer-Governance.md) | Semantic type consumers = ontology `used_in_tools` ∪ manifest parameter `semantic_type` annotations (live, rename-proof, request-scoped), shared by the planner, the initiative `<SemanticBridges>` section (pre-computed connection candidates) and the ReAct prompt (`<CrossDomainDataTypes>` + PRECISION rule). 12 phantom tool names fixed (~50% of used_in_tools, v3.2 rename drift); 5 test-enforced integrity locks (tools exist, singular domain vocabulary, manifest types registered, internal refs, taxonomy bridges with conscious allowlist); NO taxonomy/registry merge. Enrichment rule: annotate manifests, not core_types | ✅ |
| [ADR-091-Response-Context-Prefetch.md](./architecture/ADR-091-Response-Context-Prefetch.md) | Response-node user-context injections (embedding, memory, user/system RAG, journal, portrait, psyche) extracted into `services/response_context.py` and prefetched from the initiative node — overlapping the ~12s initiative LLM call in BOTH modes with zero graph topology change (graph fan-out evaluated and rejected). Bounded process-local task registry keyed by run_id, consume-once pop with timeout, identical inline fallback on any miss. Also indexes the 2026-07 latency campaign: LLM instance cache, reasoning-stream negative cache, non-blocking contacts warmup, RAG query-embedding single-flight, reducer tiktoken memoization, frontend SSE token batching, externalized `.lia-response` CSS | ✅ |
| [ADR-092-Replay-Safe-HITL-Interrupts.md](./architecture/ADR-092-Replay-Safe-HITL-Interrupts.md) | Normative HITL pattern: ONE `interrupt()` per node execution, loop state through checkpointed state returns + conditional self-loop edges (LangGraph resume re-executes the whole node). Applied to draft critique (single-pass `_handle_draft_critique`, edit/replan/clarify persist then self-loop — past LLM `modify()` calls never replay, clarify finally displays its question) and FOR_EACH bulk confirmation (dedicated `for_each_confirm` node; orchestrator pre-executes providers ONCE into `for_each_hitl_ctx` guarded by plan_id+turn_id; approve resumes with no re-fetch, edit runs the item filter once with cumulative indices). Invariant: what the user last saw is exactly what executes. Proven by compiled replay harnesses | ✅ |
| [ADR-093-Security-Hardening-Proxy-XSS.md](./architecture/ADR-093-Security-Hardening-Proxy-XSS.md) | Two coupled posture hardenings. Trusted proxy chain: prod ports 8000/9091 loopback-bound (cloudflared = single public entry; compose-internal SSR/scrape traffic unaffected) + uvicorn `--proxy-headers --forwarded-allow-ips="*"` (safe ONLY due to the loopback binding) + no application code reads raw X-Forwarded-For — `request.client.host` is the single client-IP source (per-IP rate limiting effective, GeoIP/logs real). XSS boundary: `rehype-sanitize` in the chat markdown pipeline (`rehypeRaw → rehypeSanitize → rehypeMathInText → rehypeKatex`) with a schema audited against all legitimate card/rich-HTML markup (className freed on the 7 defaultSchema-constrained tags); script/iframe/form/handlers dropped, legacy `<style>` stripped; `rehypeMathInText` renders `$…$`/`$$…$$` inside the assistant's raw HTML (sanitize-exempt but reads only already-sanitized text); MCP/Skill Apps stay outside markdown (sentinel → sandboxed widget) | ✅ |
| [ADR-094-Remove-Dead-Per-Node-Windowing-Helpers.md](./architecture/ADR-094-Remove-Dead-Per-Node-Windowing-Helpers.md) | Wave-1 audit dead-code removal: the never-wired per-node message-windowing helpers (`get_router/planner/orchestrator_windowed_messages`) + their settings/constants/`.env`/tests deleted (token growth already bounded by the state-level `add_messages_with_truncate` reducer); live `get_windowed_messages` / `get_response_windowed_messages` kept. Deliberate per-node windowing deferred to the latency effort with benchmarks | ✅ |
| [ADR-095-Systemic-Guards-Wave2-Audit.md](./architecture/ADR-095-Systemic-Guards-Wave2-Audit.md) | Wave-2 audit: closes 7 systemic defect classes, each with a permanent guard. JSONB in-place mutation (silent write loss) → AST CI test; PII at INFO → level-sensitive redaction net in `pii_filter.py` (content fields redacted at INFO+, allowed at DEBUG); silent tool-import loss → raise-outside-prod + `tool_module_import_failures_total` + 3-layer registry smoke test; billing-cycle counter leak → single `reset_cycle()` by column introspection + multi-silo test; zh/zh-CN divergence → one canonical `normalize_language`; non-localized fallback → 6-language `get_simple_fallback_message`; 5 lying docstrings corrected. Most structural change = the platform-wide PII logging boundary. No schema/migration/`.env` change; 1 new Prometheus metric | ✅ |
| [ADR-096-Performance-Boundary-Hardening-Wave3-Audit.md](./architecture/ADR-096-Performance-Boundary-Hardening-Wave3-Audit.md) | Wave-3 audit: three boundaries + 4 localized perf/correctness fixes, each measured before/after and red-first tested. Event-loop blocking (Firebase send / Pillow resize / sync embeddings froze SSE) → `asyncio.to_thread` + native async embeddings, guarded by event-loop stall tests (261→11, 496→12, 251→11 ms); per-call User query + invalid locale (`en-EN`/`zh-ZH`) → per-worker TTL cache + `LANGUAGE_TO_LOCALE`; sequential domain scan → `gather` (631→63 ms); Gmail N+1 fetch → bounded `gather` (331→62 ms); broadcast re-translated per read → persisted JSONB `message_translations` + migration (0 LLM on re-read); unregistered translation LLM → `personality_translation` slot in registry + versioned prompt; 13 LAN-exposed ports → loopback-bound (cloudflared sole entry, ufw/DOCKER-USER documented); LLM greeting XSS → auto-escaped children + strict CSP. One migration + two `.env` cache keys | ✅ |
| [ADR-097-Concurrency-GDPR-Sandbox-Wave4-Audit.md](./architecture/ADR-097-Concurrency-GDPR-Sandbox-Wave4-Audit.md) | Wave-4 audit: the most insidious class — defects visible only under concurrency or in account-lifecycle scenarios, each reproduced by a concurrency/integration test before the fix. Shared `AsyncSession` under `asyncio.gather` (health overview + heartbeat aggregator, silent `failed_sources`) → sequential loop + one `get_db_context()` session per fetcher (7 lost sources → 0); GDPR purge gap → `health_samples`/`health_metric_tokens` + `last_known_location` purged on account deletion + owner-state token auth (`is_active AND NOT deleted`); per-request state on singletons (journal/runtime/metrics cross-user leak) → explicit parameter + task-local ContextVars; orphan tool messages (400) → atomic AIMessage↔ToolMessage units + `enforce_tool_message_pairing`; frozen build-time datetime + quadratic token counting → `DynamicDatetimeMiddleware` + index-diff (also fixed a dormant `ContextEditingMiddleware` crash of every agent model call); skill sandbox vs Docker socket → privilege drop (`setgroups`/`setgid`/`setuid`) + RLIMIT AS/NPROC/FSIZE/CPU. mypy `platform=linux`. No schema/migration; opt-outable sandbox `.env` keys | ✅ |
| [ADR-098-CSP-Widget-Airlock.md](./architecture/ADR-098-CSP-Widget-Airlock.md) | Fixes the three runtime regressions shipped by the wave-3 strict CSP and closes the class. Voice (PTT + wake-word): 5 code paths load JS from `blob:` (AudioWorklets + Sherpa glue loader) governed by `script-src` (not `worker-src`) → `blob:` added; interactive-map: missing `frame-src` fell back to `default-src` → explicit `frame-src 'self' https://www.google.com`; MCP App widgets (Excalidraw): `srcDoc` inherits the parent CSP with no escape while widgets load CDN runtimes → **widget airlock**: sandboxed iframe pointed at a same-origin static shell (`public/widget-frame.html`) whose response carries its own permissive CSP (dedicated `headers()` entry, negative-lookahead global rule), widget HTML delivered by `postMessage` + `document.write` (same Window → JSON-RPC bridge untouched). Isolation stays the sandbox (opaque origin), shell hardened by 5 locks + `frame-ancestors 'self'`. Both policies extracted to `src/lib/csp.ts`, every feature-bearing directive pinned by non-regression tests (22). E2E-validated (esm.sh module + importmap through the airlock, worklet, Maps embed, spoof rejected). No migration, no `.env` key | ✅ |
| [ADR-099-Remove-Dead-Nginx-Config.md](./architecture/ADR-099-Remove-Dead-Nginx-Config.md) | Deletes `infrastructure/nginx/` (Dockerfile + nginx.conf) — shipped with v1.0.0, never wired in any Compose file across the repo's entire history, and actively misleading: its permissive global CSP contradicted the real strict policy (`src/lib/csp.ts`) and cost real analysis time during the ADR-098 investigation. `infrastructure/ssl/` kept (live dev-HTTPS cert generator). Single source of truth for response headers: `next.config.ts` (web) + `core/middleware.py` (API) | ✅ |
| [ADR-100-Structured-Output-Prompt-Conflict-Guard.md](./architecture/ADR-100-Structured-Output-Prompt-Conflict-Guard.md) | Fixes a five-defect incident (diagram request hung 2 min then rendered a map). Systemic class (D5): native `get_structured_output` (forced tool call) against prompts instructing "Output JSON only" made `deepseek-v4-flash` answer in text 2/3 of the time → `None` → validator failed **open** (silently dead). Two guards: a runtime rescue net (`include_raw` + `_rescue_structured_from_text` salvages JSON from the raw message — fences, prose-embedded, Gemini list-content) protecting all native consumers; and a prompt convention (native structured output ⇒ never instruct JSON-text) — 4 prompts cleaned (validator, memory-reference, heartbeat-decision, hitl-classifier), 5 left as-is (they parse JSON manually — legitimate). Also D1 (MCP `*_task` timeout family 300/600 s + plan budget 600 s), D2 (drop plan skill_name incoherent with detection), D3 (no skill activation on a totally-failed plan), D4 (honest replanner logs + dead inline-French removed). Repro on real model 3/3 ×3. New `mcp_react_step_max_timeout_seconds`, no migration | ✅ |
| [ADR-101-Calendar-Search-Hardening.md](./architecture/ADR-101-Calendar-Search-Hardening.md) | Calendar search worked in ReAct but failed randomly in Pipeline ("mes prochains rdv médicaux", "le rdv hotel particulier"). Per-API analysis → four deterministic fixes (calendar-scoped) + one cross-cutting cap fix. (1) The tool no longer sends free-text to the weak Google Calendar `q` — only a PERSON resolved to an attendee email is kept, the rest is dropped and the Response LLM filters the concept (Tasks/ReAct list-and-filter model); removes hardcoded `GENERIC_CALENDAR_QUERY_TERMS`. (2) New analyzer boolean `has_temporal_reference` (12/12) drives a validator reset that empties a manifest-declared `search_role="range_end"` bound (`time_max`) for open/relative queries while preserving explicit dates; kill switch `planner_open_query_date_reset`. (3) Volumetry cap centralized via `apply_max_items_limit` — 5 bypasses fixed (Google Calendar, Apple ×3, Microsoft calendar) + AST guard + ceiling 10→25 (global + calendar, `.env`). (4) `truncated` flag + searched window in metadata for a transparent "period covered". Gmail/Tasks/Contacts/Drive untouched | ✅ |
| [ADR-102-Domain-Vocabulary-Single-Source.md](./architecture/ADR-102-Domain-Vocabulary-Single-Source.md) | Domain names live on two axes derived from `DOMAIN_REGISTRY` — singular name (`primary_domain`/`domains`) and plural `result_key` (`$context`, `CONTEXT_DOMAIN_*`). Four derived tables compared a token against the wrong axis → silently-never-matching conditions: `CROSS_DOMAIN_MAPPINGS` (`places`→`place`, revives the LLM bypass), `_GOAL_PATTERNS` (plural/`drive`→singular), `valid_context_domains` (`drive`→`files`), `_detect_domain_from_agent_results` (→result_keys). Permanent axis-aware parity guard (ADR-085 model); kill switch `planner_cross_domain_bypass_enabled` | ✅ |
| [ADR-103-HITL-Backend-i18n.md](./architecture/ADR-103-HITL-Backend-i18n.md) | Eliminates hardcoded French from the backend HITL layer for the five other languages. Two-category rule (per `core/i18n.py`): LLM-facing scaffolding → English (draft_modifier, classifier few-shot externalized to a versioned prompt + action descriptions); emitted/visible messages → 6 languages via `HitlMessages` (EDIT reformulations keyed by `ReformulationKind` StrEnum, REJECT enriched message, rejection fallback), language read from the checkpointed `MessagesState.user_language`. New backend i18n parity guard (all-6-languages + within-language key parity, `i18n_patterns` excluded) — found and fixed a real `zh-CN` gap | ✅ |

### Human-in-the-Loop (HITL)

| Document | Description | Statut |
|----------|-------------|--------|
| [HITL.md](./technical/HITL.md) | Architecture HITL, 6 couches, plan approval | ✅ |
| [PLAN_HITL_STREAMING_VALIDATION.md](./technical/PLAN_HITL_STREAMING_VALIDATION.md) | Validation plan streaming HITL | ✅ |

### Sécurité & Authentification

| Document | Description | Statut |
|----------|-------------|--------|
| [OAUTH.md](./technical/OAUTH.md) | OAuth 2.1, PKCE, Google provider | ✅ |
| [AUTHENTICATION.md](./technical/AUTHENTICATION.md) | BFF Pattern, sessions Redis | ✅ |
| [SECURITY.md](./technical/SECURITY.md) | Sécurité globale, encryption, compliance | ✅ |
| [PII_LOGGING_SECURITY.md](./technical/PII_LOGGING_SECURITY.md) | PII filtering, GDPR | ✅ |
| [RATE_LIMITING.md](./technical/RATE_LIMITING.md) | Rate limiting Redis distribué | ✅ |
| [OAUTH_HEALTH_CHECK.md](./technical/OAUTH_HEALTH_CHECK.md) | Surveillance connecteurs OAuth | ✅ |

### Observabilité & Monitoring

| Document | Description | Statut |
|----------|-------------|--------|
| [OBSERVABILITY_AGENTS.md](./technical/OBSERVABILITY_AGENTS.md) | Stack Prometheus/Grafana/Loki/Tempo | ✅ |
| [METRICS_REFERENCE.md](./technical/METRICS_REFERENCE.md) | 500+ métriques documentées | ✅ |
| [GRAFANA_DASHBOARDS.md](./technical/GRAFANA_DASHBOARDS.md) | 20 dashboards Grafana | ✅ |
| [README_OBSERVABILITY.md](./readme/README_OBSERVABILITY.md) | Guide observabilité quickstart | ✅ |
| [README_GRAFANA_LANGFUSE.md](./readme/README_GRAFANA_LANGFUSE.md) | Intégration Grafana + Langfuse | ✅ |
| [README_ALERTING.md](./readme/README_ALERTING.md) | Chaîne d'alerte (ADR-119) : Alertmanager e-mail, validation, troubleshooting | ✅ |
| [README_PROMETHEUS_THRESHOLDS.md](./readme/README_PROMETHEUS_THRESHOLDS.md) | Seuils alertes par environnement | ✅ |

### CI/CD & Déploiement

| Document | Description | Statut |
|----------|-------------|--------|
| [CI_CD.md](./technical/CI_CD.md) | Pipeline CI, pre-commit hook, branch protection, Dependabot | ✅ |
| [DEPLOYMENT_INSTRUCTIONS.md](./technical/DEPLOYMENT_INSTRUCTIONS.md) | Instructions déploiement production | ✅ |

---

## Guides Pratiques

### Développement

| Guide | Description | Statut |
|-------|-------------|--------|
| [GUIDE_DEVELOPPEMENT.md](./guides/GUIDE_DEVELOPPEMENT.md) | Workflow dev, git, pre-commit, CI/CD | ✅ |
| [GUIDE_API.md](./guides/GUIDE_API.md) | Guide utilisation API REST | ✅ |
| [GUIDE_AGENT_CREATION.md](./guides/GUIDE_AGENT_CREATION.md) | Créer un nouvel agent de A à Z | ✅ |
| [GUIDE_TOOL_CREATION.md](./guides/GUIDE_TOOL_CREATION.md) | Créer un nouveau tool | ✅ |
| [GUIDE_PROMPTS.md](./guides/GUIDE_PROMPTS.md) | Optimiser les prompts, versioning | ✅ |
| [GUIDE_TESTING.md](./guides/GUIDE_TESTING.md) | Tests unitaires, integration, E2E, frontend (Vitest) | ✅ |
| [GUIDE_DESIGN_SYSTEM.md](./guides/GUIDE_DESIGN_SYSTEM.md) | Design System v4 — HTML card components | ✅ |
| [GUIDE_DEBUGGING.md](./guides/GUIDE_DEBUGGING.md) | Debug LangGraph, logs, breakpoints | ✅ |
| [GUIDE_CONNECTOR_IMPLEMENTATION.md](./guides/GUIDE_CONNECTOR_IMPLEMENTATION.md) | Implémenter un nouveau connecteur | ✅ |
| [GUIDE_CONFIG_ARCHITECTURE.md](./guides/GUIDE_CONFIG_ARCHITECTURE.md) | Architecture configuration modulaire | ✅ |
| [GUIDE_MIGRATION.md](./guides/GUIDE_MIGRATION.md) | Guide migrations Alembic | ✅ |
| [GUIDE_PERFORMANCE_TUNING.md](./guides/GUIDE_PERFORMANCE_TUNING.md) | Optimisation performance LLM | ✅ |
| [GUIDE_MCP_INTEGRATION.md](./guides/GUIDE_MCP_INTEGRATION.md) | Guide pratique MCP (admin + per-user + MCP Apps + Excalidraw) | ✅ |
| [GUIDE_TELEGRAM_INTEGRATION.md](./guides/GUIDE_TELEGRAM_INTEGRATION.md) | Guide pratique Telegram (bot, webhook, OTP, HITL) | ✅ |
| [GUIDE_HEARTBEAT_PROACTIVE_NOTIFICATIONS.md](./guides/GUIDE_HEARTBEAT_PROACTIVE_NOTIFICATIONS.md) | Guide pratique Heartbeat (ProactiveTask, ContextAggregator) | ✅ |
| [GUIDE_IPHONE_SHORTCUTS_HEALTH.md](./guides/GUIDE_IPHONE_SHORTCUTS_HEALTH.md) | Guide pas-à-pas — configurer l'automatisation iPhone pour pousser FC + pas vers LIA | ✅ |
| [GUIDE_SCHEDULED_ACTIONS.md](./guides/GUIDE_SCHEDULED_ACTIONS.md) | Guide pratique Actions Planifiees (recurrentes, timezone, retry) | ✅ |
| [GUIDE_RAG_SPACES.md](./guides/GUIDE_RAG_SPACES.md) | Guide RAG Spaces (espaces de connaissances, upload, hybrid search) | ✅ |
| [GUIDE_DEVOPS_CLAUDE_CLI.md](./guides/GUIDE_DEVOPS_CLAUDE_CLI.md) | Guide DevOps Claude CLI (remote server management, setup, security) | ✅ |
| [docs/knowledge/](./knowledge/) | System Knowledge: FAQ Markdown files for system RAG indexation (24 files, 200+ Q/A) | ✅ |

### Operations

| Guide | Description | Statut |
|-------|-------------|--------|
| [GUIDE_DEPLOYMENT.md](./guides/GUIDE_DEPLOYMENT.md) | Déploiement production | ✅ |
| [GUIDE_BACKGROUND_JOBS_APSCHEDULER.md](./guides/GUIDE_BACKGROUND_JOBS_APSCHEDULER.md) | Background jobs APScheduler | ✅ |
| [GUIDE_FCM_PUSH_NOTIFICATIONS.md](./guides/GUIDE_FCM_PUSH_NOTIFICATIONS.md) | Push notifications Firebase | ✅ |

### Langfuse

| Guide | Description | Statut |
|-------|-------------|--------|
| [GUIDE_BEST_PRACTICES.md](./langfuse/GUIDE_BEST_PRACTICES.md) | Best practices Langfuse | ✅ |
| [GUIDE_PROMPT_VERSIONING.md](./langfuse/GUIDE_PROMPT_VERSIONING.md) | Versioning prompts Langfuse | ✅ |

---

## Architecture Decision Records (ADR)

### Index Principal

| ADR | Description | Statut |
|-----|-------------|--------|
| [ADR_INDEX.md](./architecture/ADR_INDEX.md) | Index complet des ADRs (ADR-126 le plus récent) | ✅ |

### ADRs Récents (2026)

| ADR | Titre | Date |
|-----|-------|------|
| ADR-126 | Auth/Users Domain Decoupling — remédiation de la violation des dépendances stables du cycle 3 (auth : Ca=26 et Ce=14, 11 des 31 cycles) en 3 lots à comportement identique : frontière **auth = identité/session, users = agrégat User + cycle de vie**, modèle `User` déplacé byte-identique vers users (~84 sites migrés, zéro migration DB), `user_location_service` et provisioning de création (`AccountProvisioningService`, flag `commit_per_step` préservant les 2 topologies transactionnelles) rejoignent users, `haversine_distance` et sonde de clé provider promues dans core ; résultat : Ce(auth) 14→2, Ca(auth) 26→0, plus aucun cycle impliquant auth (relocalisation assumée des paires de hub vers users, all 31→32 / runtime 24→31, documentée), instrument `scripts/audit/measure_coupling.py` committé (reproduction exacte du cycle 3 + split runtime/typing) | 2026-07 |
| ADR-125 | Draft Preview Renderer Extraction — extraction n°2 de la série complexité (audit cycle 3) : `Draft.get_detailed_preview` (CC ≈ 93, cascade de 14 `elif`, logique de présentation dans un module models) vers `drafts/preview_renderer.py` en dispatch table + 3 helpers « modifié ✏️ / préservé », filet golden byte-identique vert à l'identique avant/après (cas mixtes anti-câblage-croisé, 16 DraftType, 6 langues), assert de complétude boot-time pattern ADR-085, `models.py` 803 → 579 SLOC (sort du registre des fichiers gelés), CC max 9 par fonction ; follow-up même livraison : 3 comportements épinglés corrigés (clé i18n `no_subject` ×6 langues assainissant 5 couches de français en dur, body `None` rendu vide, reminder vide → `?`) avec diff golden chirurgical, + instrument `scripts/audit/measure_cc.py` committé | 2026-07 |
| ADR-124 | Router/Service Error Contract (règle #18 phase 2) — élimination des 33 `raise HTTPException` bruts restants (13 fichiers) vers la taxonomie centralisée `core/exceptions.py`, contrat byte-identique prouvé par 33 tests de pin écrits AVANT migration + parité edge des 8 nouvelles classes (`StructuredValidationError` 422 dict, `PayloadTooLargeError` 413, `BadGatewayError` 502, `GoneError` 410, …), façade `_exceptions_base`/`exceptions_domains` pour le ratchet (aucun import consommateur modifié), garde grep CI code-hygiene, fix approuvé du 422 heartbeat avalé en 500 | 2026-07 |
| ADR-123 | Lifespan Startup Decomposition — extraction verbatim du 2e monolithe du backend (`main.py::lifespan`, ~780 SLOC, 23 étapes startup + 20 shutdown) vers `src/infrastructure/startup/` (7 modules par sous-système, une fonction typée par segment contigu), lifespan = séquence de ~25 appels dans l'ordre historique exact + commentaire de tête documentant les 8 dépendances d'ordre, mêmes événements structlog / try-except / flags, sémantique des objets partiels préservée, diff des logs de boot avant/après = 0 | 2026-07 |
| ADR-122 | AgentService Stream Decomposition (B2) — extraction neutre de la coordination voix/TTS de `_stream_with_new_services` (1 135 SLOC, plus grosse fonction du backend) vers `VoiceStreamCoordinator` + `voice_stream_helpers` (interface typée, 11 variables d'état encapsulées), filet golden de 11 scénarios SSE vert à l'identique avant/après, `service.py` −35 % (1 585 → 1 031 SLOC), coutures suivantes : finalisation/archivage puis setup | 2026-07 |
| ADR-121 | Semantic Annotation Back-fill — rétro-annotation `semantic_type` de 15 manifests (~120 annotations, params 14→53 %, outputs 22→40 %, 72/100 types consommés), chaînages vitrine épinglés par tests (participants→mail, expéditeur→invités, destination→météo), promotion `emails[].from`, entité `EmailMessage` comme évidence d'expansion, fixture de tests linking réparée (registre vide) | 2026-07 |
| ADR-120 | Semantic Evidence Expansion & Param Guard — déclencheur d'expansion sémantique rendu déterministe (évidence memory resolver ∪ analyzer), expansion evidence-driven ontology-based sous flag (entité référencée → domaines fournisseurs, cap + métrique), garde runtime manifest-driven (nom de personne sur paramètre adresse/e-mail bloqué avant l'appel API, pipeline + react), `get_route` refuse les destinations non résolues (fin du géocodage arbitraire mis en cache) | 2026-07 |
| ADR-119 | Alerting Reactivation — réactivation de la chaîne d'alerte (éteinte 2026-01 sans ADR) : noyau de 13 alertes vitales évaluées par Prometheus → Alertmanager e-mail en prod, blackbox-exporter (backup + URL publique), seuils `ALERT_CORE_*` en .env, seuils legacy corrompus documentés, répertoire prometheus/ assaini | 2026-07 |
| ADR-118 | Chat-Driven Skill Import — le skill-generator installe directement les skills générées (outil `import_user_skill`), pipeline d'import unique durci (S1 path traversal corrigé, conflits 409, gardes zip, install atomique avec rollback), dialogues multi-tours (`dialogue: true` + historique au runner) | 2026-07 |
| ADR-117 | Background Chat Runs — génération détachée de la connexion HTTP (producteur + Redis Streams), reprise live, bouton stop cross-worker, archive-first, facturation honnête sur interruption | 2026-07 |
| ADR-116 | Frontend Test Foundation — gate de couverture ratchet vitest (100 % verrouillé sur reducers/sse-handlers/stores), symétrie du contrat SSE exécutable, purge des types morts | 2026-07 |
| ADR-115 | Liveness/Readiness Probe Split — /health toujours 200 (liveness Docker), nouveau /ready 503 si PostgreSQL ou Redis down | 2026-07 |
| ADR-114 | Connector Client Domain Error Contract — 28 HTTPException bruts → taxonomie BaseAPIException, contrat API préservé par construction | 2026-07 |
| ADR-113 | Backend Test Suite Rehabilitation — job CI integration, fin des quarantaines `--ignore`, ratchet couverture 45 % | 2026-07 |
| ADR-112 | Python Dependency Locking — lockfiles universels uv, installés par pip partout, garde CI | 2026-07 |
| ADR-111 | LangGraph Postgres Connection Pooling — pools checkpointer & store, override `_cursor` pool-aware | 2026-07 |
| ADR-110 | Backup Encryption — analyse d'options (rclone crypt local / age / LUKS), différée | 2026-07 |
| ADR-109 | PostgreSQL Backup Strategy — pg_dump sidecar, rétention .env-driven, restauration testée | 2026-07 |
| ADR-089 | Multi-Worker Prometheus Metrics — multiprocess aggregation + per-gauge modes | 2026-06 |
| ADR-088 | Journal Write Restraint + Level-Routed Injection + ReAct Coherence | 2026-06 |
| ADR-085 | Draft Display Registry — single source of truth for post-HITL rendering | 2026-05 |
| ADR-084 | Indexable vs Semantic Criteria — universal planning principle + leak detector | 2026-05 |
| ADR-083 | Sub-Agent Delegation — from ReAct loop to one-shot expert LLM call | 2026-05 |
| ADR-082 | Progressive sentence streaming for low-latency TTS | 2026-05 |
| ADR-081 | Voice TTS configuration driven by the LLM catalogue | 2026-05 |
| ADR-080 | Remote Voice STT (ElevenLabs Scribe) and pricing-unit extension | 2026-05 |
| ADR-079 | Stratified Journal Consciousness | 2026-05 |
| ADR-078 | LLM Catalogue DB-Source-of-Truth | 2026-05 |
| ADR-077 | Today Briefing as a Standalone Bounded Context | 2026-04 |
| ADR-076 | Health Metrics Ingestion via Per-User Tokens | 2026-04 |
| ADR-075 | Rich Skill Outputs — Interactive Frames and Images | 2026-04 |
| ADR-074 | `structured_data` Contract for Tool Outputs | 2026-04 |
| ADR-073 | Last-Known Location Persistence for Proactive Weather | 2026-04 |
| ADR-072 | Tool Context Manager — Two-Keys Simplification | 2026-04 |
| ADR-071 | Skill Semantic Identification | 2026-04 |
| ADR-070 | ReAct Execution Mode | 2026-04 |
| ADR-069 | Gemini Embedding Migration (OpenAI → Google) | 2026-04 |
| ADR-068 | Psyche Engine — Dynamic Psychological State | 2026-04 |
| ADR-067 | Account Lifecycle (Active / Deactivated / Deleted / Erased) | 2026-03 |
| ADR-066 | Memory Storage Migration — LangGraph Store to PostgreSQL Custom | 2026-03 |
| ADR-065 | Legacy Domain Agent LangGraph Nodes — Dead Code Analysis | 2026-03 |
| ADR-063 | Cross-Worker Cache Invalidation via Redis Pub/Sub | 2026-03 |
| ADR-062 | Agent Initiative Phase + MCP Iterative Sub-Agent | 2026-03 |
| ADR-061 | Centralized Component Activation/Deactivation Control | 2026-03 |
| ADR-059 | Browser Control Architecture (Playwright) | 2026-03 |
| ADR-058 | System RAG Spaces for App Self-Knowledge | 2026-03 |
| ADR-057 | Personal Journals (Carnets de Bord) | 2026-03 |
| ADR-056 | RAG Spaces — Google Drive Folder Sync | 2026-03 |
| ADR-055 | RAG Spaces Architecture | 2026-03 |
| ADR-054 | Voice Input Architecture | 2026-01 |
| ADR-053 | Interest Learning System | 2026-01 |
| ADR-052 | Union Validation Strategy AgentResult | 2026-01 |
| ADR-051 | Reminder & Notification System | 2025-12 |
| ADR-050 | Voice Domain TTS Architecture | 2025-12 |
| ADR-049 | Embeddings (migrated to OpenAI text-embedding-3-small) | 2025-12 |
| ADR-048 | Semantic Tool Router | 2025-12 |

### ADRs Fondamentaux

| ADR | Titre |
|-----|-------|
| [ADR-001](./architecture/ADR-001-LangGraph-Multi-Agent-System.md) | LangGraph Multi-Agent System |
| [ADR-003](./architecture/ADR-003-Human-in-the-Loop-Plan-Level.md) | Human-in-the-Loop Plan-Level |
| [ADR-006](./architecture/ADR-006-Message-Windowing-Strategy.md) | Message Windowing Strategy |
| [ADR-009](./architecture/ADR-009-Config-Module-Split.md) | Config Module Split |
| [ADR-037](./architecture/ADR-037-Semantic-Memory-Store.md) | Semantic Memory Store |

---

## Runbooks Opérationnels

### Opérations

| Runbook | Description |
|---------|-------------|
| [DATABASE_BACKUP_RESTORE.md](./runbooks/DATABASE_BACKUP_RESTORE.md) | Backup PostgreSQL automatisé (sidecar pg_dump, ADR-109) — backup manuel, restauration testée, vérification d'intégrité |
| [CLOUDFLARE_TUNNEL.md](./runbooks/CLOUDFLARE_TUNNEL.md) | Tunnel Cloudflare prod (systemd, QUIC, incidents) |
| [LAST_KNOWN_LOCATION.md](./runbooks/LAST_KNOWN_LOCATION.md) | Persistance last-known location (météo proactive) |

### Alertes Générales

| Runbook | Description |
|---------|-------------|
| [TEMPLATE.md](./runbooks/alerts/TEMPLATE.md) | Template pour nouveaux runbooks |
| [PRIORITIZATION.md](./runbooks/alerts/PRIORITIZATION.md) | Guide priorisation alertes |
| [HighErrorRate.md](./runbooks/alerts/HighErrorRate.md) | Taux d'erreur élevé |
| [CriticalLatencyP99.md](./runbooks/alerts/CriticalLatencyP99.md) | Latence P99 critique |
| [ServiceDown.md](./runbooks/alerts/ServiceDown.md) | Service indisponible |
| [DatabaseDown.md](./runbooks/alerts/DatabaseDown.md) | Base de données indisponible |
| [ContainerDown.md](./runbooks/alerts/ContainerDown.md) | Container Docker down |
| [HighCPUUsage.md](./runbooks/alerts/HighCPUUsage.md) | Utilisation CPU élevée |
| [HighMemoryUsage.md](./runbooks/alerts/HighMemoryUsage.md) | Utilisation mémoire élevée |
| [DiskSpaceCritical.md](./runbooks/alerts/DiskSpaceCritical.md) | Espace disque critique |
| [BackupFailed.md](./runbooks/alerts/BackupFailed.md) | Échec backup PostgreSQL (sidecar ADR-109) |
| [PublicEndpointDown.md](./runbooks/alerts/PublicEndpointDown.md) | URL publique injoignable (tunnel/certificat) |
| [AlertmanagerDown.md](./runbooks/alerts/AlertmanagerDown.md) | Chaîne de notification down (méta, ADR-119) |

### Alertes Base de Données

| Runbook | Description |
|---------|-------------|
| [CriticalDatabaseConnections.md](./runbooks/alerts/CriticalDatabaseConnections.md) | Connexions DB critiques |
| [HighDatabaseConnections.md](./runbooks/alerts/HighDatabaseConnections.md) | Connexions DB élevées |
| [CheckpointSaveSlowCritical.md](./runbooks/alerts/CheckpointSaveSlowCritical.md) | Checkpoint lent |

### Alertes LLM & Agents

| Runbook | Description |
|---------|-------------|
| [LLMAPIFailureRateHigh.md](./runbooks/alerts/LLMAPIFailureRateHigh.md) | Taux échec API LLM |
| [DailyCostBudgetExceeded.md](./runbooks/alerts/DailyCostBudgetExceeded.md) | Budget quotidien dépassé |
| [AgentsRouterLatencyHigh.md](./runbooks/alerts/AgentsRouterLatencyHigh.md) | Latence router élevée |
| [AgentsRouterLowConfidenceHigh.md](./runbooks/alerts/AgentsRouterLowConfidenceHigh.md) | Confiance router faible |
| [AgentsStreamingErrorRateHigh.md](./runbooks/alerts/AgentsStreamingErrorRateHigh.md) | Erreurs streaming |
| [AgentsTTFTViolation.md](./runbooks/alerts/AgentsTTFTViolation.md) | Violation TTFT |
| [HighConversationResetRate.md](./runbooks/alerts/HighConversationResetRate.md) | Taux reset conversations |

### Alertes Redis

| Runbook | Description |
|---------|-------------|
| [RedisDown.md](./runbooks/alerts/RedisDown.md) | Redis indisponible |
| [RedisConnectionPoolExhaustion.md](./runbooks/alerts/RedisConnectionPoolExhaustion.md) | Pool Redis épuisé |
| [RedisRateLimitHighHitRate.md](./runbooks/redis/RedisRateLimitHighHitRate.md) | Rate limit hits élevés |
| [RedisRateLimitCheckLatencyHigh.md](./runbooks/redis/RedisRateLimitCheckLatencyHigh.md) | Latence rate limit |

### Runbooks LangGraph

| Runbook | Description |
|---------|-------------|
| [README.md](./runbooks/langgraph/README.md) | Index runbooks LangGraph |
| [high-error-rate.md](./runbooks/langgraph/high-error-rate.md) | Taux d'erreur graphe |
| [high-latency.md](./runbooks/langgraph/high-latency.md) | Latence graphe élevée |
| [low-success-rate.md](./runbooks/langgraph/low-success-rate.md) | Taux succès faible |
| [recursion-error.md](./runbooks/langgraph/recursion-error.md) | Erreurs récursion |
| [state-size-critical.md](./runbooks/langgraph/state-size-critical.md) | Taille state critique |

---

## Templates & Checklists

| Template | Description |
|----------|-------------|
| [NEW_CONNECTOR_CHECKLIST.md](./templates/NEW_CONNECTOR_CHECKLIST.md) | Checklist creation d'un nouveau connecteur OAuth/API Key |
| [NEW_MCP_SERVER_CHECKLIST.md](./templates/NEW_MCP_SERVER_CHECKLIST.md) | Checklist integration d'un nouveau serveur MCP |
| [NEW_PROACTIVE_TASK_CHECKLIST.md](./templates/NEW_PROACTIVE_TASK_CHECKLIST.md) | Checklist creation d'une nouvelle notification proactive |
| [NEW_CHANNEL_CHECKLIST.md](./templates/NEW_CHANNEL_CHECKLIST.md) | Checklist ajout d'un nouveau canal de messagerie |

---

## README Specialises

| README | Description |
|--------|-------------|
| [README_ALERTING.md](./readme/README_ALERTING.md) | Chaîne d'alerte : config e-mail, routing, tests |
| [README_DOMAIN_AGENT_MIXINS.md](./readme/README_DOMAIN_AGENT_MIXINS.md) | Mixins agents domaine |
| [README_LOAD_TESTING.md](./readme/README_LOAD_TESTING.md) | Tests de charge |
| [README_OBSERVABILITY.md](./readme/README_OBSERVABILITY.md) | Stack observabilité |
| [README_GRAFANA_DASHBOARD.md](./readme/README_GRAFANA_DASHBOARD.md) | Configuration dashboards |
| [README_RUNBOOK.md](./readme/README_RUNBOOK.md) | Index runbooks |
| [README_SCRIPTS.md](./readme/README_SCRIPTS.md) | Documentation scripts |
| [README_TESTS.md](./readme/README_TESTS.md) | Guide tests global |
| [README_TESTS_AGENTS.md](./readme/README_TESTS_AGENTS.md) | Tests agents |
| [README_TESTS_AGENT_MIXINS.md](./readme/README_TESTS_AGENT_MIXINS.md) | Tests agent mixins |
| [README_WORKFLOW.md](./readme/README_WORKFLOW.md) | Workflow développement |
| [README_BENCHMARK.md](./readme/README_BENCHMARK.md) | Benchmarks performance |
| [README_REMINDERS.md](./readme/README_REMINDERS.md) | Système de rappels |

---

## Stack Technologique

### Backend (apps/api/)

| Technologie | Version | Usage |
|-------------|---------|-------|
| Python | ≥3.12 | Runtime |
| FastAPI | 0.135.3 | Framework API |
| LangGraph | 1.1.6 | Orchestration multi-agents |
| langchain-core | 1.2.28 | Core abstractions |
| SQLAlchemy | 2.0.49 | ORM async |
| PostgreSQL | 16 + pgvector | Database + vector search |
| Redis | 7.3.0 | Cache, sessions, rate limiting |
| Pydantic | 2.12.5 | Validation données |
| openai | 1.x | OpenAI text-embedding-3-small (1536 dims) |
| Langfuse | 3.14.5 | LLM tracing |
| Edge TTS | 6.1+ | Synthèse vocale (gratuit) |

### Frontend (apps/web/)

| Technologie | Version | Usage |
|-------------|---------|-------|
| Next.js | 16.1.7 | Framework React |
| React | 19.2.4 | UI Library |
| TypeScript | 5.9.3 | Typage |
| Tailwind CSS | 4.2.1 | Styling |
| Radix UI | v2 | Composants UI |
| TanStack Query | 5.90 | State management |
| react-i18next | 16.5 | Internationalisation |

### Observabilité

| Technologie | Usage |
|-------------|-------|
| Prometheus | 500+ métriques |
| Grafana | 20 dashboards |
| Loki | Logs agrégés |
| Tempo | Traces distribuées |
| Langfuse | LLM observability |
| OpenTelemetry | Instrumentation |

### LLM Providers

| Provider | Models | Usage |
|----------|--------|-------|
| OpenAI | GPT-4.1, GPT-4.1-mini | Principal |
| Anthropic | Claude 3.5 | Alternatif |
| DeepSeek | V3, Reasoner | Économique |
| Perplexity | sonar-pro | Recherche web |
| Google | Gemini 2.0 | Multimodal |

---

## Structure du Projet

```
LIA/
├── apps/
│   ├── api/                    # Backend FastAPI + LangGraph
│   │   ├── src/
│   │   │   ├── core/           # Configuration, security, middleware
│   │   │   ├── domains/        # DDD: agents, auth, chat, connectors, google_api, etc.
│   │   │   └── infrastructure/ # Database, cache, LLM, observability
│   │   ├── tests/              # Tests pytest (~9,992 collected, 448 files)
│   │   └── alembic/            # Migrations DB
│   └── web/                    # Frontend Next.js
│       ├── src/
│       │   ├── app/            # App Router ([lng]/)
│       │   ├── components/     # Composants React
│       │   ├── hooks/          # Custom hooks
│       │   └── lib/            # API client, utils
│       └── locales/            # Traductions i18n (6 langues)
├── docs/                       # Documentation (ce répertoire)
│   ├── technical/              # Docs techniques détaillées (50+)
│   ├── guides/                 # Guides pratiques (15+)
│   ├── architecture/           # ADRs (109)
│   ├── runbooks/               # Procédures opérationnelles (34+)
│   └── readme/                 # README spécialisés (15+)
├── infrastructure/             # Docker, observabilité
│   └── observability/          # Prometheus, Grafana, Loki, Tempo
├── .claude/                    # Skills Claude (10)
│   └── skills/                 # analyzing-bugs, developing-code, etc.
└── PROD/                       # Configuration production
```

---

## Documentation Externe

### Technologies Principales

| Technologie | Documentation |
|-------------|---------------|
| LangGraph | https://langchain-ai.github.io/langgraph/ |
| LangChain | https://python.langchain.com/ |
| FastAPI | https://fastapi.tiangolo.com/ |
| Next.js | https://nextjs.org/docs |
| SQLAlchemy | https://docs.sqlalchemy.org/en/20/ |
| Pydantic | https://docs.pydantic.dev/ |

### Observabilité

| Technologie | Documentation |
|-------------|---------------|
| Prometheus | https://prometheus.io/docs/ |
| Grafana | https://grafana.com/docs/ |
| Langfuse | https://langfuse.com/docs |
| Loki | https://grafana.com/docs/loki/ |
| Tempo | https://grafana.com/docs/tempo/ |
| OpenTelemetry | https://opentelemetry.io/docs/ |

### LLM Providers

| Provider | Documentation |
|----------|---------------|
| OpenAI | https://platform.openai.com/docs/ |
| Anthropic | https://docs.anthropic.com/ |
| Google Gemini | https://ai.google.dev/docs |
| DeepSeek | https://platform.deepseek.com/docs/ |
| Perplexity | https://docs.perplexity.ai/ |

---

## Comment Contribuer à la Documentation

### Ajouter un Nouveau Document

1. **Créer le fichier** dans le bon répertoire :
   - `docs/technical/` - Documentation technique
   - `docs/guides/` - Guides pratiques
   - `docs/architecture/` - ADRs
   - `docs/runbooks/` - Procédures opérationnelles
   - `docs/readme/` - README spécialisés

2. **Suivre le template standard** :

```markdown
# Titre du Document

> Description courte

**Version**: 1.0
**Date**: YYYY-MM-DD
**Statut**: ✅ Complète

---

## Table des Matières
...
```

3. **Mettre à jour cet INDEX.md**

4. **Créer une PR** avec label `documentation`

### Standards de Qualité

| Standard | Règle |
|----------|-------|
| Format | CommonMark Markdown |
| Langue | Français (sauf code/termes techniques anglais) |
| Code Examples | Testés et fonctionnels |
| Diagrammes | Mermaid pour architecture |
| Liens | Toujours relatifs dans le projet |

---

## Contact

Questions ou suggestions ? Créer une issue GitHub avec le label `documentation`

---

<p align="center">
  <strong>LIA</strong> — Documentation complète pour l'assistant IA de nouvelle génération
</p>

<p align="center">
  <a href="#vue-densemble">⬆️ Retour en haut</a>
</p>
