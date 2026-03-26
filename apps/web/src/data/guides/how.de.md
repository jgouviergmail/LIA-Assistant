# LIA — Vollständiger technischer Leitfaden

> Architektur, Patterns und Engineering-Entscheidungen eines KI-Multi-Agent-Assistenten der nächsten Generation.
>
> Technische Präsentationsdokumentation für Architekten, Ingenieure und technische Experten.

**Version**: 2.1
**Datum**: 2026-03-25
**Application**: LIA v1.12.3
**Lizenz**: AGPL-3.0 (Open Source)

---

## Inhaltsverzeichnis

1. [Kontext und grundlegende Entscheidungen](#1-kontext-und-grundlegende-entscheidungen)
2. [Technologie-Stack](#2-technologie-stack)
3. [Backend-Architektur: Domain-Driven Design](#3-backend-architektur-domain-driven-design)
4. [LangGraph: Multi-Agent-Orchestrierung](#4-langgraph-multi-agent-orchestrierung)
5. [Die konversationelle Ausführungspipeline](#5-die-konversationelle-ausführungspipeline)
6. [Das Planungssystem (ExecutionPlan DSL)](#6-das-planungssystem-executionplan-dsl)
7. [Smart Services: intelligente Optimierung](#7-smart-services-intelligente-optimierung)
8. [Semantisches Routing und lokale Embeddings](#8-semantisches-routing-und-lokale-embeddings)
9. [Human-in-the-Loop: 6-Schichten-Architektur](#9-human-in-the-loop-6-schichten-architektur)
10. [State-Management und Message Windowing](#10-state-management-und-message-windowing)
11. [Gedächtnissystem und psychologisches Profil](#11-gedächtnissystem-und-psychologisches-profil)
12. [Multi-Provider-LLM-Infrastruktur](#12-multi-provider-llm-infrastruktur)
13. [Konnektoren: Multi-Provider-Abstraktion](#13-konnektoren-multi-provider-abstraktion)
14. [MCP: Model Context Protocol](#14-mcp-model-context-protocol)
15. [Sprachsystem (STT/TTS)](#15-sprachsystem-stttts)
16. [Proaktivität: Heartbeat und geplante Aktionen](#16-proaktivität-heartbeat-und-geplante-aktionen)
17. [RAG Spaces und hybride Suche](#17-rag-spaces-und-hybride-suche)
18. [Browser Control und Web Fetch](#18-browser-control-und-web-fetch)
19. [Sicherheit: Defence in Depth](#19-sicherheit-defence-in-depth)
20. [Observability und Monitoring](#20-observability-und-monitoring)
21. [Performance: Optimierungen und Metriken](#21-performance-optimierungen-und-metriken)
22. [CI/CD und Qualität](#22-cicd-und-qualität)
23. [Übergreifende Engineering-Patterns](#23-übergreifende-engineering-patterns)
24. [Architekturentscheidungen (ADR)](#24-architekturentscheidungen-adr)
25. [Evolutionspotenzial und Erweiterbarkeit](#25-evolutionspotenzial-und-erweiterbarkeit)

---

## 1. Kontext und grundlegende Entscheidungen

### 1.1. Warum diese Entscheidungen?

Jede technische Entscheidung in LIA antwortet auf eine konkrete Anforderung. Das Projekt zielt auf einen Multi-Agent-KI-Assistenten, der **auf bescheidener Hardware selbst gehostet werden kann** (Raspberry Pi 5, ARM64), mit vollständiger Transparenz, Datensouveränität und Multi-Provider-LLM-Unterstützung. Diese Anforderungen haben den gesamten Stack bestimmt.

| Anforderung | Architektonische Konsequenz |
|------------|--------------------------|
| Self-Hosting ARM64 | Docker Multi-Arch, lokale E5-Embeddings (keine API-Abhängigkeit), Playwright Chromium Cross-Platform |
| Datensouveränität | Lokales PostgreSQL (kein SaaS-DB), Fernet-Verschlüsselung im Ruhezustand, lokale Redis-Sessions |
| Multi-Provider-LLM | Factory Pattern mit 7 Adaptern, Konfiguration pro Knoten, keine enge Kopplung an einen Provider |
| Vollständige Transparenz | 350+ Prometheus-Metriken, eingebettetes Debug-Panel, Token-für-Token-Tracking |
| Produktionszuverlässigkeit | 59 ADRs, 2 300+ Tests, native Observability, HITL auf 6 Ebenen |
| Kontrollierte Kosten | Smart Services (89 % Token-Einsparung), lokale Embeddings, Prompt Caching, Katalogfilterung |

### 1.2. Architekturprinzipien

| Prinzip | Implementierung |
|----------|----------------|
| **Domain-Driven Design** | Bounded Contexts in `src/domains/`, explizite Aggregate, Schichten Router/Service/Repository/Model |
| **Hexagonale Architektur** | Ports (Python-Protokolle) und Adapter (konkrete Google/Microsoft/Apple-Clients) |
| **Event-Driven** | SSE-Streaming, ContextVar-Propagation, Fire-and-Forget-Hintergrundaufgaben |
| **Defence in Depth** | 5 Schichten für Usage Limits, 6 HITL-Ebenen, 3 Anti-Halluzinations-Schichten |
| **Feature Flags** | Jedes Subsystem aktivierbar/deaktivierbar (`{FEATURE}_ENABLED`) |
| **Configuration as Code** | Pydantic BaseSettings zusammengesetzt via MRO, Prioritätskette APPLICATION > .ENV > CONSTANT |

### 1.3. Codebase-Metriken

| Metrik | Wert |
|----------|--------|
| Tests | 2 300+ (Unit, Integration, Agents, Benchmark) |
| Wiederverwendbare Fixtures | 170+ |
| Dokumentationsdokumente | 190+ |
| ADRs (Architecture Decision Records) | 59 |
| Prometheus-Metriken | 350+ Definitionen |
| Grafana-Dashboards | 18 |
| Unterstützte Sprachen (i18n) | 6 (fr, en, de, es, it, zh) |

---

## 2. Technologie-Stack

### 2.1. Backend

| Technologie | Version | Rolle | Warum diese Wahl |
|-------------|---------|------|-------------------|
| Python | 3.12+ | Runtime | Reichstes ML/KI-Ökosystem, natives Async, vollständiges Typing |
| FastAPI | 0.135.1 | REST-API + SSE | Automatische Pydantic-Validierung, OpenAPI-Docs, Async-First, Performance |
| LangGraph | 1.1.2 | Multi-Agent-Orchestrierung | Einziges Framework mit nativer State-Persistenz + Zyklen + Interrupts (HITL) |
| LangChain Core | 1.2.19 | LLM/Tools-Abstraktionen | `@tool`-Decorator, Nachrichtenformate, standardisierte Callbacks |
| SQLAlchemy | 2.0.48 | Async ORM | `Mapped[Type]` + `mapped_column()`, Async Sessions, `selectinload()` |
| PostgreSQL | 16 + pgvector | Datenbank + Vektorsuche | Native LangGraph-Checkpoints, semantische HNSW-Suche, Reife |
| Redis | 7.3.0 | Cache, Sessions, Rate Limiting | O(1)-Operationen, atomisches Sliding Window (Lua), SETNX Leader Election |
| Pydantic | 2.12.5 | Validierung + Serialisierung | `ConfigDict`, `field_validator`, Settings-Komposition via MRO |
| structlog | latest | Strukturiertes Logging | JSON-Ausgabe mit automatischer PII-Filterung, snake_case Events |
| sentence-transformers | 5.0+ | Lokale Embeddings | E5-small multilingual (384d), null API-Kosten, ~50 ms auf ARM64 |
| Playwright | latest | Browser-Automatisierung | Chromium Headless, CDP Accessibility Tree, Cross-Platform |
| APScheduler | 3.x | Hintergrund-Jobs | Cron/Interval-Trigger, kompatibel mit Redis Leader Election |

### 2.2. Frontend

| Technologie | Version | Rolle |
|-------------|---------|------|
| Next.js | 16.1.7 | App Router, SSR, ISR |
| React | 19.2.4 | UI mit Server Components |
| TypeScript | 5.9.3 | Striktes Typing |
| TailwindCSS | 4.2.1 | Utility-First CSS |
| TanStack Query | 5.90 | Server State Management, Cache, Mutations |
| Radix UI | v2 | Barrierefreie UI-Primitives |
| react-i18next | 16.5 | i18n (6 Sprachen), Namespace-basiert |
| Zod | 3.x | Runtime-Validierung der Debug-Schemata |

### 2.3. Unterstützte LLM-Provider

| Provider | Modelle | Besonderheiten |
|----------|---------|-------------|
| OpenAI | GPT-5.4, GPT-5.4-mini, GPT-5.x, GPT-4.1-x, o1, o3-mini | Natives Prompt Caching, Responses API, reasoning_effort |
| Anthropic | Claude Opus 4.6/4.5/4, Sonnet 4.6/4.5/4, Haiku 4.5 | Extended Thinking, Prompt Caching |
| Google | Gemini 3.1/3/2.5 Pro, Flash 3/2.5/2.0 | Multimodal, TTS HD |
| DeepSeek | V3 (Chat), R1 (Reasoner) | Reduzierte Kosten, natives Reasoning |
| Perplexity | sonar-small/large-128k-online | Search-Augmented Generation |
| Qwen | qwen3-max, qwen3.5-plus, qwen3.5-flash | Thinking Mode, Tools + Vision (Alibaba Cloud) |
| Ollama | Jedes lokale Modell (dynamische Erkennung) | Null API-Kosten, Self-Hosted |

**Warum 7 Provider?** Die Auswahl ist kein Selbstzweck. Es ist eine Resilienzstrategie: Jeder Knoten der Pipeline kann einem anderen Provider zugewiesen werden. Wenn OpenAI die Preise erhöht, wechselt der Router auf DeepSeek. Wenn Anthropic einen Ausfall hat, wird die Antwort auf Gemini umgeleitet. Die LLM-Abstraktion (`src/infrastructure/llm/factory.py`) verwendet das Factory Pattern mit `init_chat_model()`, überschrieben durch spezifische Adapter (`ResponsesLLM` für die OpenAI Responses API, Eligibility per Regex `^(gpt-4\.1|gpt-5|o[1-9])`).

---

## 3. Backend-Architektur: Domain-Driven Design

### 3.1. Domänenstruktur

```
apps/api/src/
├── core/                         # Übergreifender technischer Kern
│   ├── config/                   # 9 Pydantic BaseSettings-Module zusammengesetzt via MRO
│   │   ├── __init__.py           # Settings-Klasse (finale MRO)
│   │   ├── agents.py, database.py, llm.py, mcp.py, voice.py, usage_limits.py, ...
│   ├── constants.py              # 1 000+ zentralisierte Konstanten
│   ├── exceptions.py             # Zentralisierte Exceptions (raise_user_not_found, etc.)
│   └── i18n.py                   # i18n-Bridge → Settings
│
├── domains/                      # Bounded Contexts (DDD)
│   ├── agents/                   # HAUPTDOMÄNE — LangGraph-Orchestrierung
│   │   ├── nodes/                # 7+ Graphknoten
│   │   ├── services/             # Smart Services, HITL, Context Resolution
│   │   ├── tools/                # Werkzeuge nach Domäne (@tool + ToolResponse)
│   │   ├── orchestration/        # ExecutionPlan, Parallel Executor, Validators
│   │   ├── registry/             # AgentRegistry, domain_taxonomy, Catalogue
│   │   ├── semantic/             # Semantic Router, Expansion Service
│   │   ├── middleware/           # Memory Injection, Personality Injection
│   │   ├── prompts/v1/           # 57 versionierte .txt-Prompt-Dateien
│   │   ├── graphs/               # 15 Agent-Builder (einer pro Domäne)
│   │   ├── context/              # Context Store (Data Registry), Decorators
│   │   └── models.py             # MessagesState (TypedDict + Custom Reducer)
│   ├── auth/                     # OAuth 2.1, BFF-Sessions, RBAC
│   ├── connectors/               # Multi-Provider-Abstraktion (Google/Apple/Microsoft)
│   ├── rag_spaces/               # Upload, Chunking, Embedding, hybrides Retrieval
│   ├── journals/                 # Introspektive Tagebücher
│   ├── interests/                # Erlernen von Interessensgebieten
│   ├── heartbeat/                # LLM-gesteuerte proaktive Benachrichtigungen
│   ├── channels/                 # Multi-Kanal (Telegram)
│   ├── voice/                    # TTS Factory, STT Sherpa, Wake Word
│   ├── skills/                   # Standard agentskills.io
│   ├── sub_agents/               # Spezialisierte persistente Agenten
│   ├── usage_limits/             # Kontingente pro Benutzer (5-Layer Defence)
│   └── ...                       # conversations, reminders, scheduled_actions, users, user_mcp
│
└── infrastructure/               # Übergreifende Schicht
    ├── llm/                      # Factory, Providers, Adapter, Embeddings, Tracking
    ├── cache/                    # Redis Sessions, LLM Cache, JSON Helpers
    ├── mcp/                      # MCP Client Pool, Auth, SSRF, Tool Adapter, Excalidraw
    ├── browser/                  # Playwright Session Pool, CDP, Anti-Erkennung
    ├── rate_limiting/            # Verteiltes Redis Sliding Window
    ├── scheduler/                # APScheduler, Leader Election, Locks
    └── observability/            # 17+ Prometheus-Metrik-Dateien, OTel-Tracing
```

### 3.2. Konfigurationsprioritätskette

Eine fundamentale Invariante durchzieht das gesamte Backend. Sie wurde in v1.9.4 systematisch durchgesetzt, mit ~291 Korrekturen in ~80 Dateien, da Abweichungen zwischen Konstanten und tatsächlicher Produktionskonfiguration stille Fehler verursachten:

```
APPLICATION (Admin UI / DB) > .ENV (settings) > CONSTANT (fallback)
```

**Warum diese Kette?** Die Konstanten (`src/core/constants.py`) dienen ausschließlich als Fallback für Pydantic-`Field(default=...)`- und SQLAlchemy-`server_default=`-Werte. Ein Administrator, der ein LLM-Modell über die Oberfläche ändert, muss diese Änderung sofort wirksam sehen, ohne erneutes Deployment. Zur Laufzeit liest jeglicher Code `settings.field_name`, niemals direkt eine Konstante.

### 3.3. Schichten-Patterns

| Schicht | Verantwortlichkeit | Schlüssel-Pattern |
|--------|---------------|-------------|
| **Router** | HTTP-Validierung, Auth, Serialisierung | `Depends(get_current_active_session)`, `check_resource_ownership()` |
| **Service** | Geschäftslogik, Orchestrierung | Konstruktor erhält `AsyncSession`, erstellt Repositories, zentralisierte Exceptions |
| **Repository** | Datenzugriff | Erbt von `BaseRepository[T]`, Paginierung `tuple[list[T], int]` |
| **Model** | DB-Schema | `Mapped[Type]` + `mapped_column()`, `UUIDMixin`, `TimestampMixin` |
| **Schema** | I/O-Validierung | Pydantic v2, `Field()` mit Beschreibung, getrennte Request/Response |

---

## 4. LangGraph: Multi-Agent-Orchestrierung

### 4.1. Warum LangGraph? (ADR-001)

Die Wahl von LangGraph anstelle von LangChain allein, CrewAI oder AutoGen basiert auf drei nicht verhandelbaren Anforderungen:

1. **State Persistence**: `TypedDict` mit Custom Reducers, persistiert über PostgreSQL-Checkpoints — ermöglicht die Wiederaufnahme einer Konversation nach HITL-Unterbrechung
2. **Zyklen und Interrupts**: Native Unterstützung von Schleifen (HITL-Ablehnung → Neuplanung) und des `interrupt()`-Patterns — ohne das der HITL mit 6 Schichten unmöglich wäre
3. **SSE-Streaming**: Native Integration mit Callback Handlers — entscheidend für die Echtzeit-UX

CrewAI und AutoGen waren einfacher in der Einarbeitung, aber keines von beiden unterstützte das Interrupt/Resume-Pattern, das für HITL auf Plan-Ebene erforderlich ist. Diese Entscheidung hat ihren Preis: Die Lernkurve ist steiler (Graph-Konzepte, bedingte Kanten, State-Schemata).

### 4.2. Der Hauptgraph

```
                    ┌──────────────────────────────────┐
                    │        Router Node (v3)            │
                    │  Binär: conversation|actionable    │
                    │  Konfidenz: high > 0.85            │
                    └──────┬──────────┬─────────────────┘
                           │          │
              conversation │          │ actionable
                           │          │
                    ┌──────▼──┐  ┌───▼───────────────────┐
                    │ Response │  │  QueryAnalyzer          │
                    │  Node    │  │  + SmartPlanner          │
                    └──────────┘  └───┬───────────────────┘
                                      │
                                ┌─────▼───────────────────┐
                                │  Semantic Validator       │
                                └─────┬───────────────────┘
                                      │
                                ┌─────▼───────────────────┐
                                │   Approval Gate           │
                                │   (HITL interrupt)        │
                                └─────┬───────────────────┘
                                      │
                                ┌─────▼───────────────────┐
                                │  Task Orchestrator        │
                                │  (parallel executor)      │
                                └─────┬───────────────────┘
                                      │
                    ┌─────────────────▼────────────────────┐
                    │      15 Domain Agents                  │
                    │  + MCP dynamic agents                  │
                    │  + Sub-agent delegation                │
                    └─────────────────┬────────────────────┘
                                      │
                                ┌─────▼───────────────────┐
                                │   Response Node           │
                                │  (anti-hallucination)     │
                                └───────────────────────────┘
```

### 4.3. Graphknoten

| Knoten | Datei | Rolle | Windowing |
|------|---------|------|-----------|
| Router v3 | `router_node_v3.py` | Binäre Klassifikation conversation/actionable | 5 Turns |
| QueryAnalyzer | `query_analyzer_service.py` | Domänenerkennung, Intent-Extraktion | — |
| Planner v3 | `planner_node_v3.py` | ExecutionPlan-DSL-Generierung | 10 Turns |
| Semantic Validator | `semantic_validator.py` | Validierung von Abhängigkeiten und Kohärenz | — |
| Approval Gate | `hitl_dispatch_node.py` | HITL interrupt(), 6 Genehmigungsebenen | — |
| Task Orchestrator | `task_orchestrator_node.py` | Parallele Ausführung, Kontextweitergabe | — |
| Response | `response_node.py` | Anti-Halluzinations-Synthese, 3 Schutzschichten | 20 Turns |

### 4.4. AgentRegistry und Domain Taxonomy

Die `AgentRegistry` zentralisiert die Registrierung von Agenten (`registry.register_agent()` in `main.py`), den `ToolManifest`-Katalog und die `domain_taxonomy.py`, die jede Domäne mit ihrem `result_key` und ihren Aliasen definiert.

**Warum ein zentralisiertes Register?** Ohne dieses erforderte das Hinzufügen eines Agenten die Änderung von 5+ Dateien. Mit dem Register deklariert sich ein neuer Agent an einem einzigen Punkt und ist automatisch für Routing, Planung und Ausführung verfügbar.

### 4.5. Domain Taxonomy

Jede Domain ist eine deklarative `DomainConfig`: Name, Agents, `result_key` (kanonischer Schlüssel für `$steps`-Referenzen), `related_domains`, Priorität und Routingfähigkeit. Die `DOMAIN_REGISTRY` ist die einzige Wahrheitsquelle, die von drei Subsystemen konsumiert wird: SmartCatalogue (Filterung), semantische Expansion (benachbarte Domains) und Initiative-Phase (struktureller Vorfilter).

### 4.6. Tool Manifests

Jedes Tool deklariert ein `ToolManifest` über einen fluenten `ToolManifestBuilder`: Parameter, Outputs, Kostenprofil, Berechtigungen und mehrsprachige `semantic_keywords` für das Routing. Manifeste werden vom Planner (Katalog-Injektion), dem semantischen Router (Keyword-Matching) und dem Agent-Builder (Tool-Verdrahtung) konsumiert. Siehe Abschnitt 23 für die vollständige Tool-Architektur.

---

## 5. Die konversationelle Ausführungspipeline

### 5.1. Detaillierter Ablauf einer aktionsfähigen Anfrage

1. **Empfang**: Benutzernachricht → SSE-Endpunkt `/api/v1/chat/stream`
2. **Kontext**: `request_tool_manifests_ctx` ContextVar wird einmalig aufgebaut (ADR-061: 3-Layer Defence)
3. **Router**: Binäre Klassifikation mit Konfidenz-Scoring (high > 0.85, medium > 0.65)
4. **QueryAnalyzer**: Identifiziert Domänen via LLM + Post-Expansion-Validierung (Gate-Keeper, der deaktivierte Domänen filtert)
5. **SmartPlanner**: Generiert einen `ExecutionPlan` (strukturiertes JSON-DSL)
   - Pattern Learning: Konsultiert den bayesschen Cache (Bypass bei Konfidenz > 90 %)
   - Skill Detection: Deterministische Skills werden über `_has_potential_skill_match()` geschützt
6. **Semantic Validator**: Überprüft die Kohärenz der Abhängigkeiten zwischen Schritten
7. **HITL Dispatch**: Klassifiziert die Genehmigungsebene, `interrupt()` bei Bedarf
8. **Task Orchestrator**: Führt Schritte in parallelen Wellen via `asyncio.gather()` aus
   - Filtert übersprungene Schritte VOR dem Gather (ADR-005 — behebt einen Bug der doppelten Ausführung Plan+Fallback)
   - Kontextweitergabe über Data Registry (InMemoryStore)
   - FOR_EACH-Pattern für Masseniterationen
9. **Response Node**: Synthetisiert die Ergebnisse, Injection von Gedächtnis + Journalen + RAG
10. **SSE Stream**: Token für Token zum Frontend
11. **Hintergrundaufgaben** (Fire-and-Forget): Gedächtnisextraktion, Journalextraktion, Interessenerkennung

### 5.2. ContextVar: implizite Zustandspropagation

Ein kritischer Mechanismus ist die Verwendung von Python-`ContextVar` zur Zustandspropagation ohne Parameter-Threading:

| ContextVar | Rolle | Warum |
|------------|------|----------|
| `current_tracker` | TrackingContext für LLM-Token-Tracking | Vermeidet die Weitergabe eines Trackers durch 15 Funktionsschichten |
| `request_tool_manifests_ctx` | Pro Anfrage gefilterte Tool-Manifeste | Einmal aufgebaut, von 7+ Verbrauchern gelesen (eliminiert Duplikation ADR-061) |

Dieser Ansatz gewährleistet eine Isolation pro Anfrage in einem asyncio-Kontext, ohne Funktionssignaturen zu verunreinigen.

---

## 6. Das Planungssystem (ExecutionPlan DSL)

### 6.1. Planstruktur

```python
ExecutionPlan(
    steps=[
        ExecutionStep(
            step_id="get_meetings",
            tool_name="get_events",
            parameters={"date": "tomorrow"},
            dependencies=[]
        ),
        ExecutionStep(
            step_id="send_reminders",
            tool_name="send_email",
            parameters={"subject": "Rappel réunion"},
            dependencies=["get_meetings"],
            for_each="$steps.get_meetings.events",
            for_each_max=10
        )
    ]
)
```

### 6.2. FOR_EACH-Pattern

**Warum ein dediziertes Pattern?** Massenoperationen (eine E-Mail an 12 Kontakte senden) können nicht als 12 statische Schritte geplant werden — die Anzahl der Elemente ist vor der Ausführung des vorherigen Schritts unbekannt. FOR_EACH löst dieses Problem mit Schutzmaßnahmen:
- HITL-Schwelle: Jede Mutation >= 1 Element löst eine obligatorische Genehmigung aus
- Konfigurierbares Limit: `for_each_max` verhindert unbegrenzte Ausführungen
- Dynamische Referenz: `$steps.{step_id}.{field}` für Ergebnisse vorheriger Schritte

### 6.3. Parallele Ausführung in Wellen

Der `parallel_executor.py` organisiert die Schritte in Wellen (DAG):
1. Identifiziert Schritte ohne unaufgelöste Abhängigkeiten → nächste Welle
2. Filtert übersprungene Schritte (nicht erfüllte Bedingungen, Fallback-Zweige) — **vor** `asyncio.gather()`, nicht danach (ADR-005: behebt einen Bug, der 2x API-Aufrufe und 2x Kosten verursachte)
3. Führt die Welle mit Fehlerisolation pro Schritt aus
4. Speist die Data Registry mit den Ergebnissen
5. Wiederholt bis zur vollständigen Planabarbeitung

### 6.4. Semantischer Validator

Vor der HITL-Genehmigung prüft ein dediziertes LLM (vom Planner getrennt, um Selbstvalidierungs-Bias zu vermeiden) den Plan anhand von 14 Problemtypen in vier Kategorien: **Kritisch** (halluzinierte Fähigkeit, Geistabhängigkeit, logischer Zyklus), **Semantisch** (Kardinalitäts-Mismatch, Scope-Overflow/-Underflow, falsche Parameter), **Sicherheit** (gefährliche Mehrdeutigkeit, implizite Annahme) und **FOR_EACH** (fehlende Kardinalität, ungültige Referenz). Short-Circuit für triviale Pläne (1 Schritt), optimistisches 1-s-Timeout.

### 6.5. Referenzvalidierung

Schrittübergreifende Referenzen (`$steps.get_meetings.events[0].title`) werden zur Planzeit mit strukturierten Fehlermeldungen validiert: ungültiges Feld, verfügbare Alternativen und korrigierte Beispiele — damit der Planner sich beim Retry selbst korrigieren kann, statt stille Fehler zu produzieren.

### 6.6. Adaptiver Re-Planner (Panic Mode)

Bei Ausführungsfehlern klassifiziert ein regelbasierter Analysator (kein LLM) das Fehlermuster (leere Ergebnisse, Teilausfall, Timeout, Referenzfehler) und wählt eine Recovery-Strategie: identischer Retry, Replan mit erweitertem Scope, Eskalation an den Benutzer oder Abbruch. Im **Panic Mode** erweitert der SmartCatalogue alle Tools für einen einzigen Retry — für Fälle, in denen die Domain-Filterung zu aggressiv war.

---

## 7. Smart Services: intelligente Optimierung

### 7.1. Das gelöste Problem

Ohne Optimierung ließen die Skalierung auf 10+ Domänen die Kosten explodieren: Der Übergang von 3 Tools (Kontakte) auf 30+ Tools (10 Domänen) verzehnfachte die Prompt-Größe und damit die Kosten pro Anfrage (ADR-003). Die Smart Services wurden entwickelt, um diese Kosten auf das Niveau eines Einzeldomänensystems zurückzubringen.

| Service | Rolle | Mechanismus | Gemessener Gewinn |
|---------|------|-----------|-------------|
| `QueryAnalyzerService` | Routing-Entscheidung | LRU-Cache (TTL 5 Min.) | ~35 % Cache Hit |
| `SmartPlannerService` | Plangenerierung | Bayessches Pattern Learning | Bypass > 90 % Konfidenz |
| `SmartCatalogueService` | Tool-Filterung | Filterung nach Domäne | 96 % Token-Reduktion |
| `PlanPatternLearner` | Lernen | Bayessches Scoring Beta(2,1) | ~2 300 eingesparte Tokens pro Replan |

### 7.2. PlanPatternLearner

**Funktionsweise**: Wenn ein Plan validiert und erfolgreich ausgeführt wird, wird seine Tool-Sequenz in Redis gespeichert (Hash `plan:patterns:{tool→tool}`, TTL 30 Tage). Für zukünftige Anfragen wird ein bayesscher Score berechnet: `Konfidenz = (α + Erfolge) / (α + β + Erfolge + Misserfolge)`. Über 90 % wird der Plan direkt ohne LLM-Aufruf wiederverwendet.

**Schutzmaßnahmen**: K-Anonymität (mindestens 3 Beobachtungen für Vorschlag, 10 für Bypass), exaktes Domänen-Matching, maximal 3 injizierte Patterns (~45 Token Overhead), striktes Timeout von 5 ms.

**Bootstrapping**: 50+ vordefinierte Golden Patterns beim Start, jeweils mit 20 simulierten Erfolgen (= 95,7 % anfängliche Konfidenz).

### 7.3. QueryIntelligence

Der QueryAnalyzer liefert weit mehr als Domain-Erkennung — er erzeugt eine tiefe `QueryIntelligence`-Struktur: unmittelbare Absicht vs. Endziel (`UserGoal`: FIND_INFORMATION, TAKE_ACTION, COMMUNICATE...), implizite Absichten (z.B. „Kontakt finden" bedeutet wahrscheinlich „etwas senden"), antizipierte Fallback-Strategien, FOR_EACH-Kardinalitätshinweise und softmax-kalibrierte Domain-Konfidenzwerte. Dies gibt dem Planner ein reicheres Bild als einfache Keyword-Extraktion.

### 7.4. Semantischer Pivot

Anfragen in jeder Sprache werden automatisch ins Englische übersetzt, bevor Embedding-Vergleiche stattfinden, was die sprachübergreifende Genauigkeit verbessert. Redis-gecacht (TTL 5 Min, ~5 ms bei Hit vs ~500 ms bei Miss), über ein schnelles LLM.

---

## 8. Semantisches Routing und lokale Embeddings

### 8.1. Warum lokale Embeddings? (ADR-049)

Das rein LLM-basierte Routing hatte zwei Probleme: Kosten (jede Anfrage = ein LLM-Aufruf) und Genauigkeit (das LLM lag bei ~20 % der Multi-Domänen-Fälle falsch). Lokale Embeddings lösen beide Probleme:

| Eigenschaft | Wert |
|-----------|--------|
| Modell | multilingual-e5-small |
| Dimensionen | 384 |
| Latenz | ~50 ms (ARM64 Pi 5) |
| API-Kosten | Null |
| Sprachen | 100+ |
| Genauigkeitsgewinn | +48 % bei Q/A-Matching vs. LLM-Routing allein |

### 8.2. Semantic Tool Router (ADR-048)

Jedes `ToolManifest` besitzt mehrsprachige `semantic_keywords`. Die Anfrage wird in ein Embedding transformiert und dann per Kosinusähnlichkeit mit **Max-Pooling** verglichen (Score = MAX pro Tool, nicht Durchschnitt — vermeidet semantische Verwässerung). Doppelschwelle: >= 0.70 = hohe Konfidenz, 0.60-0.70 = Unsicherheit.

### 8.3. Semantische Expansion

Der `expansion_service.py` reichert die Ergebnisse an, indem er benachbarte Domänen exploriert. Die Post-Expansion-Validierung (ADR-061, Layer 1) filtert vom Administrator deaktivierte Domänen — behebt einen Bug, bei dem das LLM oder die Expansion deaktivierte Domänen wieder einführen konnten.

---

## 9. Human-in-the-Loop: 6-Schichten-Architektur

### 9.1. Warum auf Plan-Ebene? (Phase 7 → Phase 8)

Der ursprüngliche Ansatz (Phase 7) unterbrach die Ausführung **während** der Tool-Aufrufe — jedes sensible Tool erzeugte eine Unterbrechung. Die UX war unzureichend (unerwartete Pausen) und die Kosten hoch (Overhead pro Tool).

Phase 8 (aktuell) legt den **vollständigen Plan** dem Benutzer **vor** jeder Ausführung vor. Eine einzige Unterbrechung, ein Gesamtüberblick, die Möglichkeit, Parameter zu bearbeiten. Der Kompromiss: Man muss darauf vertrauen, dass der Planner einen getreuen Plan erstellt.

### 9.2. Die 6 Genehmigungstypen

| Typ | Auslöser | Mechanismus |
|------|-------------|-----------|
| `PLAN_APPROVAL` | Destruktive Aktionen | `interrupt()` mit PlanSummary |
| `CLARIFICATION` | Erkannte Mehrdeutigkeit | `interrupt()` mit LLM-Frage |
| `DRAFT_CRITIQUE` | E-Mail-/Event-/Kontakt-Entwurf | `interrupt()` mit serialisiertem Entwurf + Markdown-Template |
| `DESTRUCTIVE_CONFIRM` | Löschung >= 3 Elemente | `interrupt()` mit Irreversibilitätswarnung |
| `FOR_EACH_CONFIRM` | Massenmutationen | `interrupt()` mit Operationszählung |
| `MODIFIER_REVIEW` | Von KI vorgeschlagene Änderungen | `interrupt()` mit Vorher/Nachher-Vergleich |

### 9.3. Erweitertes Draft Critique

Für Entwürfe generiert ein dedizierter Prompt eine strukturierte Kritik mit Markdown-Templates pro Domäne, Feld-Emojis, Vorher/Nachher-Vergleich mit Durchstreichen für Aktualisierungen und Irreversibilitätswarnungen. Die Post-HITL-Ergebnisse zeigen i18n-Labels und anklickbare Links an.

### 9.4. Antwortklassifikation

Wenn der Benutzer auf einen Genehmigungsprompt antwortet, kategorisiert ein Full-LLM-Klassifikator (kein Regex) die Antwort in 5 Entscheidungen: **APPROVE**, **REJECT**, **EDIT** (gleiche Aktion, andere Parameter), **REPLAN** (völlig andere Aktion) oder **AMBIGUOUS**. Eine Degradierungslogik verhindert False Positives: ein EDIT mit fehlenden Parametern wird zu AMBIGUOUS herabgestuft, was eine Klärungsnachfrage auslöst.

### 9.5. Compaction Safety

4 Bedingungen verhindern die LLM-Komprimierung (Zusammenfassung alter Nachrichten) während aktiver Genehmigungsflüsse. Ohne diesen Schutz könnte eine Zusammenfassung den kritischen Kontext einer laufenden Unterbrechung löschen.

---

## 10. State-Management und Message Windowing

### 10.1. MessagesState und Custom Reducer

Der LangGraph-State ist ein `TypedDict` mit einem Reducer `add_messages_with_truncate`, der tokenbasierte Trunkierung, Validierung von OpenAI-Nachrichtensequenzen und Deduplizierung von Tool-Nachrichten verwaltet.

### 10.2. Warum Windowing pro Knoten? (ADR-007)

**Das Problem**: Eine Konversation mit 50+ Nachrichten erzeugte 100k+ Token Kontext, mit einer Latenz > 10 s für den Router und explodierenden Kosten.

**Die Lösung**: Jeder Knoten operiert auf einem anderen Fenster, kalibriert auf seinen tatsächlichen Bedarf:

| Knoten | Turns | Begründung |
|------|-------|---------------|
| Router | 5 | Schnelle Entscheidung, minimaler Kontext genügt |
| Planner | 10 | Kontextbedarf für die Planung, aber nicht die gesamte Historie |
| Response | 20 | Reicher Kontext für natürliche Synthese |

**Gemessene Auswirkung**: E2E-Latenz -50 % (10 s → 5 s), Kosten -77 % bei langen Konversationen, Qualität erhalten dank Data Registry, die Tool-Ergebnisse unabhängig von Nachrichten speichert.

### 10.3. Context Compaction

Wenn die Token-Anzahl einen dynamischen Schwellenwert überschreitet (Verhältnis zum Context Window des Antwortmodells), wird eine LLM-Zusammenfassung generiert. Kritische Identifikatoren (UUIDs, URLs, E-Mails) werden beibehalten. Einsparverhältnis: ~60 % pro Komprimierung. Befehl `/resume` für manuelles Auslösen.

### 10.4. PostgreSQL-Checkpointing

Vollständiger State wird nach jedem Knoten checkpointet. P95 Save < 50 ms, P95 Load < 100 ms, durchschnittliche Größe ~15 KB/Konversation.

---

## 11. Gedächtnissystem und psychologisches Profil

### 11.1. Architektur

```
AsyncPostgresStore + Semantic Index (pgvector)
├── Namespace: (user_id, "memories")        → Psychologisches Profil
├── Namespace: (user_id, "documents", src)  → Dokumenten-RAG
└── Namespace: (user_id, "context", domain) → Tool-Kontext (Data Registry)
```

### 11.2. Erweitertes Gedächtnisschema

Jede Erinnerung ist ein strukturiertes Dokument mit:
- `content`, `category` (Präferenz, Fakt, Persönlichkeit, Beziehung, Sensibilität...)
- `importance` (1-10), `emotional_weight` (-10 bis +10)
- `usage_nuance`: Wie diese Information auf einfühlsame Weise verwendet werden soll
- Embedding `text-embedding-3-small` (1536d) via pgvector HNSW

**Warum ein emotionales Gewicht?** Ein Assistent, der weiß, dass Ihre Mutter krank ist, diese Tatsache aber wie jede andere Information behandelt, ist bestenfalls unbeholfen, schlimmstenfalls verletzend. Das emotionale Gewicht ermöglicht die Aktivierung der `DANGER_DIRECTIVE` (Verbot zu scherzen, zu minimieren, zu vergleichen, zu bagatellisieren), wenn ein sensibles Thema berührt wird.

### 11.3. Extraktion und Injection

**Extraktion**: Nach jeder Konversation analysiert ein Hintergrundprozess die letzte Benutzernachricht, angepasst an die aktive Persönlichkeit. Kosten werden über `TrackingContext` verfolgt.

**Injection**: Die Middleware `memory_injection.py` sucht semantisch ähnliche Erinnerungen, baut das injizierbare psychologische Profil auf und aktiviert bei Bedarf die `DANGER_DIRECTIVE`. Injection in den System-Prompt des Response Node.

### 11.4. Hybride Suche BM25 + Semantisch

Kombination mit konfigurierbarem Alpha (Standard 0.6 semantisch / 0.4 BM25). 10 % Boost, wenn beide Signale stark sind (> 0.5). Graceful Fallback auf rein semantische Suche, wenn BM25 fehlschlägt. Performance: 40-90 ms mit Cache.

### 11.5. Tagebücher (Journals)

Der Assistent führt introspektive Reflexionen in vier ausgewogenen Themen (Selbstreflexion, Benutzerbeobachtungen, Ideen/Analysen, Erkenntnisse). Zwei Auslöser: Post-Konversations-Extraktion + periodische Konsolidierung (4h). OpenAI-Embeddings 1536d mit `search_hints` (LLM-Schlüsselwörter im Benutzervokabular). Injection in den Prompt des **Response Node und des Planner Node** — letzterer verwendet `intelligence.original_query` als semantische Anfrage.

**Semantischer Dedup-Guard** (v1.12.1): Bevor ein neuer Eintrag erstellt wird, prüft das System die semantische Ähnlichkeit mit bestehenden Einträgen. Überschreitet ein Treffer den konfigurierbaren Schwellenwert (`JOURNAL_DEDUP_SIMILARITY_THRESHOLD`, Standard 0.72), fusioniert ein Merge-LLM alle übereinstimmenden Einträge zu einer einzigen angereicherten Direktive — N→1-Konsolidierung mit Löschung der sekundären Einträge. Graceful Degradation bei Fehler.

Anti-Halluzinations-UUID: `field_validator`, Referenz-ID-Tabelle, Filterung nach bekannten IDs bei Extraktion und Konsolidierung.

### 11.6. Interessensystem

Erkennung durch Analyse der Anfragen mit bayesscher Gewichtsentwicklung (Decay 0.01/Tag). Proaktive Multi-Source-Benachrichtigungen (Wikipedia, Perplexity, LLM). Benutzerfeedback (Daumen hoch/runter/blockieren) passt die Gewichtungen an.

---

## 12. Multi-Provider-LLM-Infrastruktur

### 12.1. Factory Pattern

```python
llm = get_llm(provider="openai", model="gpt-5.4", temperature=0.7, streaming=True)
```

`get_llm()` löst die effektive Konfiguration über `get_llm_config_for_agent(settings, agent_type)` auf (Code-Defaults → DB-Admin-Overrides), instanziiert das Modell und wendet die spezifischen Adapter an.

### 12.2. 34 LLM-Konfigurationstypen

Jeder Knoten der Pipeline ist über die Admin-UI unabhängig konfigurierbar — ohne erneutes Deployment:

| Kategorie | Konfigurierbare Typen |
|-----------|-------------------|
| Pipeline | router, query_analyzer, planner, semantic_validator, context_resolver |
| Antwort | response, hitl_question_generator |
| Hintergrund | memory_extraction, interest_extraction, journal_extraction, journal_consolidation |
| Agenten | contacts_agent, emails_agent, calendar_agent, browser_agent, etc. |

### 12.3. Token Tracking

Der `TrackingContext` verfolgt jeden LLM-Aufruf mit `call_type` ("chat"/"embedding"), `sequence` (monotoner Zähler), `duration_ms`, Tokens (Input/Output/Cache) und aus den DB-Tarifen berechnetem Preis. Tracker teilen eine `run_id` für die Aggregation. Das Debug-Panel zeigt alle Aufrufe (Pipeline + Hintergrundaufgaben) in einer einheitlichen chronologischen Ansicht an.

---

## 13. Konnektoren: Multi-Provider-Abstraktion

### 13.1. Architektur über Protokolle

```
ConnectorTool (base.py) → ClientRegistry → resolve_client(type) → Protocol
     ├── GoogleGmailClient       implements EmailClientProtocol
     ├── MicrosoftOutlookClient  implements EmailClientProtocol
     ├── AppleEmailClient        implements EmailClientProtocol
     └── PhilipsHueClient        implements SmartHomeClientProtocol
```

**Warum Python-Protokolle?** Das strukturelle Duck Typing ermöglicht das Hinzufügen eines neuen Providers, ohne den aufrufenden Code zu ändern. Der `ProviderResolver` garantiert, dass nur ein Anbieter pro funktionaler Kategorie aktiv ist.

### 13.2. Normalizer

Jeder Provider gibt Daten in seinem eigenen Format zurück. Dedizierte Normalizer (`calendar_normalizer`, `contacts_normalizer`, `email_normalizer`, `tasks_normalizer`) konvertieren providerspezifische Antworten in einheitliche Domain-Modelle. Ein neuer Provider erfordert nur die Implementierung des Protokolls und seines Normalizers — der aufrufende Code bleibt unverändert.

### 13.3. Wiederverwendbare Patterns

`BaseOAuthClient` (Template Method mit 3 Hooks), `BaseGoogleClient` (Paginierung via pageToken), `BaseMicrosoftClient` (OData). Circuit Breaker, verteiltes Redis Rate Limiting, Refresh Token mit Double-Check-Pattern und Redis Locking gegen den Thundering-Herd-Effekt.

---

## 14. MCP: Model Context Protocol

### 14.1. Architektur

Der `MCPClientManager` verwaltet den Lifecycle der Verbindungen (Exit Stacks), die Tool-Erkennung (`session.list_tools()`) und die automatische LLM-gestützte Generierung von Domänenbeschreibungen. Der `ToolAdapter` normalisiert MCP-Tools auf das LangChain-`@tool`-Format mit strukturiertem Parsing der JSON-Antworten in einzelne Items.

### 14.2. MCP-Sicherheit

Obligatorisches HTTPS, SSRF-Prävention (DNS-Auflösung + IP-Blocklist), Fernet-Verschlüsselung der Credentials, OAuth 2.1 (DCR + PKCE S256), Redis Rate Limiting pro Server/Tool, API Guard 403 auf Proxy-Endpunkte für deaktivierte Server (ADR-061 Layer 3).

### 14.3. MCP Iterative Mode (ReAct)

MCP-Server mit `iterative_mode: true` verwenden einen dedizierten ReAct-Agenten (Observe/Think/Act-Schleife) anstelle des statischen Planners. Der Agent liest zunächst die Serverdokumentation, versteht das erwartete Format und ruft dann die Tools mit den richtigen Parametern auf. Besonders effektiv für Server mit komplexer API (z. B. Excalidraw). Pro Server in der Admin- oder Benutzerkonfiguration aktivierbar. Angetrieben vom generischen `ReactSubAgentRunner` (geteilt mit dem Browser Agent).

---

## 15. Sprachsystem (STT/TTS)

### 15.1. STT

Wake Word ("OK Guy") über Sherpa-onnx WASM im Browser (kein externer Versand). Whisper-Small-Transkription (99+ Sprachen, offline) im Backend via ThreadPoolExecutor. Per-User STT Language mit thread-sicherem `OfflineRecognizer`-Cache pro Sprache.

**Latenzoptimierungen**: Wiederverwendung des KWS-Mikrofonstreams → Aufnahme (~200-800 ms eingespart), WebSocket-Vorverbindung, `getUserMedia` + WS parallelisiert via `Promise.allSettled`, AudioWorklet-Cache.

### 15.2. TTS

Factory Pattern: `TTSFactory.create(mode)` mit automatischem Fallback HD → Standard. Standard = Edge TTS (kostenlos), HD = OpenAI TTS oder Gemini TTS (Premium).

---

## 16. Proaktivität: Heartbeat und geplante Aktionen

### 16.1. Heartbeat: 2-Phasen-Architektur

**Phase 1 — Entscheidung** (kosteneffektiv, gpt-4.1-mini):
1. `EligibilityChecker`: Opt-in, Zeitfenster, Cooldown (2h global, 30 Min. pro Typ), kürzliche Aktivität
2. `ContextAggregator`: 7 Quellen parallel (`asyncio.gather`): Calendar, Weather (Änderungserkennung), Tasks, Emails, Interests, Memories, Journals
3. LLM Structured Output: `skip` | `notify` mit Anti-Redundanz (injizierter aktueller Verlauf)

**Phase 2 — Generierung** (bei Notify): LLM schreibt mit Persönlichkeit + Benutzersprache um. Multi-Kanal-Dispatch.

### 16.2. Agent Initiative (ADR-062)

LangGraph-Node nach der Ausführung: Nach jedem aktionsfähigen Turn analysiert die Initiative die Ergebnisse und überprüft proaktiv domänenübergreifende Informationen (schreibgeschützt). Beispiele: Regenvorhersage → Kalender auf Outdoor-Aktivitäten prüfen, E-Mail mit Terminerwähnung → Verfügbarkeit prüfen, Aufgabe mit Deadline → Kontext in Erinnerung rufen. 100 % prompt-gesteuert (keine hardcodierte Logik), struktureller Vorfilter (benachbarte Domänen), Injection von Gedächtnis + Interessensgebieten, Vorschlagsfeld für Write-Aktionen. Konfigurierbar über `INITIATIVE_ENABLED`, `INITIATIVE_MAX_ITERATIONS`, `INITIATIVE_MAX_ACTIONS`.

### 16.3. Geplante Aktionen

APScheduler mit Redis Leader Election (SETNX, TTL 120s, Recheck 5s). `FOR UPDATE SKIP LOCKED` für Isolation. Auto-Approve der Pläne (`plan_approved=True` in den State injiziert). Auto-Disable nach 5 aufeinanderfolgenden Fehlern. Retry bei transienten Fehlern.

---

## 17. RAG Spaces und hybride Suche

### 17.1. Pipeline

Upload → Chunking → Embedding (text-embedding-3-small, 1536d) → pgvector HNSW → Hybride Suche (Cosine + BM25 mit Alpha-Fusion) → Kontextinjection in den **Response Node**.

Hinweis: Die RAG-Injection erfolgt im Antwortknoten, nicht im Planner. Der Planner erhält stattdessen die Injection der persönlichen Journale über `build_journal_context()`.

### 17.2. System RAG Spaces (ADR-058)

Integrierte FAQ (119+ Q/A, 17 Abschnitte), indexiert aus `docs/knowledge/`. Erkennung `is_app_help_query` durch QueryAnalyzer, Rule 0 Override im RoutingDecider, App Identity Prompt (~200 Token, Lazy Loading). SHA-256 Staleness Detection, Auto-Indexierung beim Start.

---

## 18. Browser Control und Web Fetch

### 18.1. Web Fetch

URL → SSRF-Validierung (DNS + IP-Blocklist + Post-Redirect-Recheck) → Readability-Extraktion (Fallback Full Page) → HTML-Bereinigung → Markdown → `<external_content>`-Wrapping (Prompt-Injection-Prävention). Redis-Cache 10 Min.

### 18.2. Browser Control (ADR-059)

Autonomer ReAct-Agent (Playwright Chromium Headless). Redis-gesicherter Session Pool mit Cross-Worker-Recovery. CDP Accessibility Tree für elementbasierte Interaktion. Anti-Erkennung (Chrome UA, Webdriver-Flag-Entfernung, dynamische Locale/Timezone). Automatisches Cookie-Banner-Dismiss (20+ mehrsprachige Selektoren). Separates Read/Write Rate Limiting (je 40 pro Session).

---

## 19. Sicherheit: Defence in Depth

### 19.1. BFF-Authentifizierung (ADR-002)

**Warum BFF statt JWT?** JWT in localStorage = XSS-anfällig, 90 % Overhead in der Größe, Widerruf unmöglich. Das BFF-Pattern mit HTTP-only Cookies + Redis-Sessions eliminiert alle drei Probleme. Migration v0.3.0: Speicher -90 % (1.2 MB → 120 KB), Session Lookup P95 < 5 ms, OWASP-Score B+ → A.

### 19.2. Usage Limits: 5-Layer Defence in Depth

| Schicht | Abfangpunkt | Warum diese Schicht |
|--------|---------------------|-----------------------|
| Layer 0 | Chat Router (HTTP 429) | Blockieren, bevor der SSE-Stream überhaupt beginnt |
| Layer 1 | Agent Service (SSE Error) | Abdeckung geplanter Aktionen, die den Router umgehen |
| Layer 2 | `invoke_with_instrumentation()` | Zentraler Guard für alle Hintergrunddienste |
| Layer 3 | Proactive Runner | Überspringen für blockierte Benutzer |
| Layer 4 | Direkte Migration `.ainvoke()` | Abdeckung nicht zentralisierter Aufrufe |

**Fail-Open**-Design: Infrastrukturausfälle blockieren keine Benutzer.

### 19.3. Angriffsprävention

| Vektor | Schutz |
|---------|------------|
| XSS | HTTP-only Cookies, CSP |
| CSRF | SameSite=Lax |
| SQL Injection | SQLAlchemy ORM (parametrisierte Abfragen) |
| SSRF | DNS-Auflösung + IP-Blocklist (Web Fetch, MCP, Browser) |
| Prompt Injection | `<external_content>` Safety Markers |
| Rate Limiting | Verteiltes Redis Sliding Window (atomisches Lua) |
| Supply Chain | SHA-gepinnte GitHub Actions, Dependabot wöchentlich |

---

## 20. Observability und Monitoring

### 20.1. Stack

| Technologie | Rolle |
|-------------|------|
| Prometheus | 350+ benutzerdefinierte Metriken (RED Pattern) |
| Grafana | 18 produktionsreife Dashboards |
| Loki | Aggregierte strukturierte JSON-Logs |
| Tempo | Verteiltes Cross-Service-Tracing (OTLP gRPC) |
| Langfuse | LLM-spezifisches Tracing (Prompt-Versionen, Token-Nutzung) |
| structlog | Strukturiertes Logging mit PII-Filterung |

### 20.2. Eingebettetes Debug-Panel

Das Debug-Panel in der Chat-Oberfläche bietet Echtzeit-Introspektion pro Konversation: Intent-Analyse, Ausführungspipeline, LLM-Pipeline (chronologische Zusammenführung aller LLM- + Embedding-Aufrufe), Kontext/Gedächtnis, Intelligenz (Cache Hits, Pattern Learning), Journale (Injection + Hintergrund-Extraktion), Lifecycle-Timing.

Die Debug-Metriken werden in `sessionStorage` persistiert (maximal 50 Einträge).

**Warum ein Debug-Panel in der UI?** In einem Ökosystem, in dem KI-Agenten notorisch schwer zu debuggen sind (nicht-deterministisches Verhalten, undurchsichtige Aufrufketten), eliminiert die direkte Zugänglichkeit der Metriken in der Oberfläche die Reibung, Grafana öffnen oder Logs lesen zu müssen. Der Operator sieht sofort, warum eine Anfrage teuer war oder warum der Router eine bestimmte Domäne gewählt hat.

---

## 21. Performance: Optimierungen und Metriken

### 21.1. Schlüsselmetriken (P95)

| Metrik | Wert | SLO |
|----------|--------|-----|
| API-Latenz | 450 ms | < 500 ms |
| TTFT (Time To First Token) | 380 ms | < 500 ms |
| Router-Latenz | 800 ms | < 2 s |
| Planner-Latenz | 2.5 s | < 5 s |
| E5 Embedding (lokal) | ~50 ms | < 100 ms |
| Checkpoint Save | < 50 ms | P95 |
| Redis Session Lookup | < 5 ms | P95 |

### 21.2. Implementierte Optimierungen

| Optimierung | Gemessener Gewinn | Kompromiss |
|-------------|-------------|-----------|
| Message Windowing | -50 % Latenz, -77 % Kosten | Verlust von altem Kontext (kompensiert durch Data Registry) |
| Smart Catalogue | 96 % Token-Reduktion | Panic Mode erforderlich bei zu aggressiver Filterung |
| Pattern Learning | 89 % LLM-Einsparungen | Bootstrapping erforderlich (Golden Patterns) |
| Prompt Caching | 90 % Rabatt | Abhängig von Provider-Unterstützung |
| Lokale Embeddings | Null API-Kosten | ~470 MB Speicher, 9s initiale Ladezeit |
| Parallele Ausführung | Latenz = max(Schritte) | Komplexität der Abhängigkeitsverwaltung |
| Context Compaction | ~60 % pro Komprimierung | Informationsverlust (abgemildert durch ID-Beibehaltung) |

---

## 22. CI/CD und Qualität

### 22.1. Pipeline

```
Pre-commit (lokal)                GitHub Actions CI
========================          =========================
.bak files check                  Lint Backend (Ruff + Black + MyPy strict)
Secrets grep                      Lint Frontend (ESLint + TypeScript)
Ruff + Black + MyPy               Unit Tests + Coverage (43 %)
Schnelle Unit Tests               Code Hygiene (i18n, Alembic, .env.example)
Erkennung kritischer Patterns     Docker Build Smoke Test
Sync i18n-Schlüssel               Secret Scan (Gitleaks)
Alembic-Migrationskonflikte       ─────────────────────────
.env.example-Vollständigkeit      Security Workflow (wöchentlich)
ESLint + TypeScript Check           CodeQL (Python + JS)
                                    pip-audit + pnpm audit
                                    Trivy Filesystem Scan
                                    SBOM-Generierung
```

### 22.2. Standards

| Aspekt | Tool | Konfiguration |
|--------|-------|---------------|
| Python-Formatierung | Black | line-length=100 |
| Python-Linting | Ruff | E, W, F, I, B, C4, UP |
| Typprüfung | MyPy | Strict Mode |
| Commits | Conventional Commits | `feat(scope):`, `fix(scope):` |
| Tests | pytest | `asyncio_mode = "auto"` |
| Coverage | Minimum 43 % | In CI erzwungen |

---

## 23. Übergreifende Engineering-Patterns

### 23.1. Tool-System: 5-Schichten-Architektur

Das Tool-System ist in fünf komponierbaren Schichten aufgebaut und reduziert den Boilerplate pro Tool von ~150 Zeilen auf ~8 Zeilen (94 % Reduktion):

| Schicht | Komponente | Rolle |
|---------|-----------|------|
| 1 | `ConnectorTool[ClientType]` | Generische Basis: OAuth Auto-Refresh, Client-Caching, Dependency Injection |
| 2 | `@connector_tool` | Meta-Dekorator: `@tool` + Metriken + Rate Limiting + Kontextspeicherung |
| 3 | Formatter | `ContactFormatter`, `EmailFormatter`... — domänenspezifische Ergebnisnormalisierung |
| 4 | `ToolManifest` + Builder | Deklarative Deklaration: Parameter, Outputs, Kosten, Berechtigungen, semantische Keywords |
| 5 | Catalogue Loader | Dynamische Introspektion, Manifest-Generierung, Domain-Gruppierung |

Rate Limits sind kategoriebasiert: Read (20/Min), Write (5/Min), Expensive (2/5 Min). Tools können entweder einen String (Legacy) oder ein strukturiertes `UnifiedToolOutput` (Data-Registry-Modus) erzeugen.

### 23.2. Data Registry

Die Data Registry (`InMemoryStore`) entkoppelt Tool-Ergebnisse von der Nachrichtenhistorie. Ergebnisse werden per Request über `@auto_save_context` gespeichert und überleben das Message-Windowing — das macht aggressives knotenweises Windowing (5/10/20 Turns) ohne Verlust des Tool-Output-Kontexts möglich. Schrittübergreifende Referenzen (`$steps.X.field`) lösen gegen die Registry auf, nicht gegen Nachrichten.

### 23.3. Fehlerarchitektur

Alle Tools geben `ToolResponse` (Erfolg) oder `ToolErrorModel` (Fehler) mit einem `ToolErrorCode`-Enum (18+ Typen: INVALID_INPUT, RATE_LIMIT_EXCEEDED, TEMPLATE_EVALUATION_FAILED...) und einem `recoverability`-Flag zurück. Auf API-Seite ersetzen zentralisierte Exception-Raiser (`raise_user_not_found`, `raise_permission_denied`...) überall rohe HTTPExceptions — für konsistente Fehlerverträge.

### 23.4. Prompt-System

57 versionierte `.txt`-Dateien in `src/domains/agents/prompts/v1/`, geladen über `load_prompt()` mit LRU-Cache (32 Einträge). Versionen konfigurierbar über Umgebungsvariablen.

### 23.5. Zentralisierte Komponentenaktivierung (ADR-061)

3-Schichten-System zur Lösung eines Duplikationsproblems: Vor ADR-061 war die Filterung aktivierter/deaktivierter Komponenten über 7+ Stellen verstreut. Jetzt:

| Schicht | Mechanismus |
|---------|-----------|
| Schicht 1 | Domain-Gatekeeper: validiert LLM-Domains gegen `available_domains` |
| Schicht 2 | `request_tool_manifests_ctx`: ContextVar einmalig pro Request erstellt |
| Schicht 3 | API-Guard 403 auf MCP-Proxy-Endpoints |

### 23.6. Feature Flags

Jedes optionale Subsystem wird durch ein `{FEATURE}_ENABLED`-Flag gesteuert, geprüft beim Start (Scheduler-Registrierung), bei der Routen-Verdrahtung und beim Knoteneintritt (sofortiger Short-Circuit). Dies ermöglicht das Deployment der vollständigen Codebasis bei schrittweiser Subsystem-Aktivierung.

---

## 24. Architekturentscheidungen (ADR)

59 ADRs im MADR-Format dokumentieren die wichtigsten Architekturentscheidungen. Einige repräsentative Beispiele:

| ADR | Entscheidung | Gelöstes Problem | Gemessene Auswirkung |
|-----|----------|----------------|---------------|
| 001 | LangGraph für Orchestrierung | Bedarf an State-Persistenz + HITL-Interrupts | Checkpoints P95 < 50 ms |
| 002 | BFF-Pattern (JWT → Redis) | JWT XSS-anfällig, Widerruf unmöglich | Speicher -90 %, OWASP A |
| 003 | Dynamische Filterung nach Domäne | 10x Prompt-Größe = 10x Kosten | 73-83 % Katalogreduktion |
| 005 | Filterung VOR asyncio.gather | Plan + Fallback parallel ausgeführt = 2x Kosten | -50 % Kosten für Fallback-Pläne |
| 007 | Message Windowing pro Knoten | Lange Konversationen = 100k+ Token | -50 % Latenz, -77 % Kosten |
| 048 | Semantic Tool Router | Ungenaues LLM-Routing bei Multi-Domäne | +48 % Genauigkeit |
| 049 | Lokale E5-Embeddings | API-Embedding-Kosten + Netzwerklatenz | Null Kosten, 50 ms lokal |
| 057 | Personal Journals | Keine Reflexionskontinuität zwischen Sessions | Injection in Planner + Response |
| 061 | Centralized Component Activation | 7+ duplizierte Filterstellen | Einzelquelle, 3 Schichten |

---

## 25. Evolutionspotenzial und Erweiterbarkeit

### 25.1. Erweiterungspunkte

| Erweiterung | Schnittstelle | Dokumentation |
|-----------|-----------|---------------|
| Neuer Konnektor | `OAuthProvider` Protocol + Client Protocol | `GUIDE_CONNECTOR_IMPLEMENTATION.md` + Checkliste |
| Neuer Agent | `register_agent()` + ToolManifest | `GUIDE_AGENT_CREATION.md` |
| Neues Tool | `@tool` + ToolResponse/ToolErrorModel | `GUIDE_TOOL_CREATION.md` |
| Neuer Kanal | `BaseChannelSender` + `BaseChannelWebhookHandler` | `NEW_CHANNEL_CHECKLIST.md` |
| Neuer LLM-Provider | Adapter + Model Profiles | Erweiterbare Factory |
| Neue proaktive Aufgabe | `ProactiveTask` Protocol | `NEW_PROACTIVE_TASK_CHECKLIST.md` |

### 25.2. Skalierbarkeit

| Dimension | Aktuelle Strategie | Mögliche Weiterentwicklung |
|-----------|-------------------|-------------------|
| Horizontal | 4 Uvicorn Worker + Redis Leader Election | Kubernetes + HPA |
| Daten | PostgreSQL + pgvector | Sharding, Read Replicas |
| Cache | Redis Single Instance | Redis Cluster |
| Observability | Vollständiger eingebetteter Stack | Managed Grafana Cloud |

---

## Fazit

LIA ist eine Software-Engineering-Übung, die versucht, ein konkretes Problem zu lösen: einen produktionsreifen, transparenten, sicheren und erweiterbaren Multi-Agent-KI-Assistenten zu bauen, der auf einem Raspberry Pi laufen kann.

Die 59 ADRs dokumentieren nicht nur die getroffenen Entscheidungen, sondern auch die verworfenen Alternativen und die akzeptierten Kompromisse. Die 2 300+ Tests, die vollständige CI/CD-Pipeline und der strikte MyPy-Modus sind keine Eitelkeitsmetriken — sie sind die Mechanismen, die es ermöglichen, ein System dieser Komplexität ohne Regressionen weiterzuentwickeln.

Die Verflechtung der Subsysteme — psychologisches Gedächtnis, bayessches Lernen, semantisches Routing, systematisches HITL, LLM-gesteuerte Proaktivität, introspektive Journale — schafft ein System, in dem jede Komponente die anderen verstärkt. Das HITL speist das Pattern Learning, das die Kosten senkt, was mehr Funktionalitäten ermöglicht, die mehr Daten für das Gedächtnis generieren, das die Antworten verbessert. Dies ist ein Tugendkreis durch Design, nicht durch Zufall.

---

*Dokument verfasst auf Grundlage der Analyse des Quellcodes (`apps/api/src/`, `apps/web/src/`), der technischen Dokumentation (190+ Dokumente), der 63 ADRs und des Changelogs (v1.0 bis v1.12.3). Alle genannten Metriken, Versionen und Patterns sind in der Codebase verifizierbar.*
