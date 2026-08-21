# Stack Technique - Reference Complete

> **Version**: 2.0
> **Date**: 2026-07-11
> **Statut**: Reference officielle des versions

---

## Vue d'Ensemble

Ce document constitue la **reference officielle** des versions de toutes les technologies utilisees dans LIA. Il sert de source de verite pour :

- La verification de compatibilite
- La planification des mises a jour
- L'onboarding des nouveaux developpeurs
- Les audits de securite

---

## Runtime & Package Managers

| Technologie | Version Requise | Notes |
|-------------|-----------------|-------|
| **Node.js** | >=22.0.0 | LTS recommande |
| **pnpm** | 10.x | Workspace monorepo |
| **Python** | 3.14 (`>=3.14,<3.15`) | async/await natif |

---

## Frontend (apps/web)

### Framework Core

| Technologie | Version | Role |
|-------------|---------|------|
| **Next.js** | 16.2.10 | Framework React SSR/SSG |
| **React** | 19.2.7 | UI Library |
| **TypeScript** | 6.0.2 | Type safety |
| **Tailwind CSS** | 4.3.2 | Utility-first CSS |

### State & Data

| Technologie | Version | Role |
|-------------|---------|------|
| **@tanstack/react-query** | 5.101.x | Server state management |
| **Zod** | 4.4.x | Schema validation |
| **react-hook-form** | 7.81.x | Form management |

### UI Components

| Technologie | Version | Role |
|-------------|---------|------|
| **Radix UI** | 1.x-2.x | Accessible primitives |
| **lucide-react** | 1.23.x | Icons |
| **sonner** | 2.0.x | Toast notifications |
| **next-themes** | 0.4.x | Dark mode |

### Internationalization

| Technologie | Version | Role |
|-------------|---------|------|
| **i18next** | 26.x | i18n framework |
| **react-i18next** | 17.0.x | React bindings |

### Dev Tools

| Technologie | Version | Role |
|-------------|---------|------|
| **ESLint** | 9.x | Linting |
| **Vitest** | 4.x | Unit testing |

---

## Backend (apps/api)

### Core Framework

| Technologie | Version | Role |
|-------------|---------|------|
| **FastAPI** | 0.136.3 | Web framework async |
| **Uvicorn** | 0.48.0 | ASGI server |
| **Pydantic** | 2.13.4 | Data validation |
| **pydantic-settings** | 2.14.x | Configuration |

### Base de Donnees

| Technologie | Version | Role |
|-------------|---------|------|
| **SQLAlchemy** | 2.0.50 | ORM async |
| **Alembic** | 1.18.4 | Migrations |
| **asyncpg** | 0.31.0 | PostgreSQL driver async |
| **psycopg** | 3.3.x | PostgreSQL driver |
| **psycopg-pool** | 3.3.x | Pool de connexions async (checkpointer & store LangGraph, ADR-111) |
| **pgvector** | 0.4.2 | Vector similarity search |

### Cache & Sessions

| Technologie | Version | Role |
|-------------|---------|------|
| **redis** (Python) | 8.0.1 | Redis client |

### AI/ML Stack (LangChain Ecosystem)

| Technologie | Version | Role |
|-------------|---------|------|
| **langchain-core** | 1.5.5 | Core abstractions |
| **langchain** | 1.3.15 | LLM framework |
| **langgraph** | 1.2.11 | Agent orchestration |
| **langgraph-checkpoint** | 4.2.0 | Checkpoint serialization |
| **langgraph-checkpoint-postgres** | 3.1.2 | State persistence |
| **langgraph-prebuilt** | 1.1.0 | Prebuilt agent components |

### LLM Providers

| Technologie | Version | Provider |
|-------------|---------|----------|
| **langchain-openai** | 1.5.1 | OpenAI GPT-4/5 |
| **langchain-anthropic** | 1.5.6 | Claude |
| **langchain-google-genai** | 4.3.4 | Gemini |
| **langchain-deepseek** | 1.1.0 | DeepSeek |
| **openai** | 2.54.0 | OpenAI SDK |
| **anthropic** | 0.122.0 | Claude SDK direct |
| **tiktoken** | 0.13.x | Token counting |

### Embeddings & ML

| Technologie | Version | Role |
|-------------|---------|------|
| **langchain-google-genai** | 4.3.4 | Google gemini-embedding-001 (1536 dims par defaut, configurable 768/1536/3072, RETRIEVAL task types) |

### Observabilite

| Technologie | Version | Role |
|-------------|---------|------|
| **structlog** | 25.x | Structured logging |
| **prometheus-client** | 0.25.x | Metrics |
| **langfuse** | 4.7.1 | LLM observability |
| **opentelemetry-api** | 1.42.1 | Distributed tracing |
| **opentelemetry-sdk** | 1.42.1 | Tracing SDK |
| **opentelemetry-instrumentation-fastapi** | 0.63b1 | FastAPI auto-instrumentation |
| **opentelemetry-exporter-otlp** | 1.42.1 | OTLP export |

### Securite & Auth

| Technologie | Version | Role |
|-------------|---------|------|
| **python-jose** | 3.5.0 | JWT handling |
| **passlib** | 1.7.x | Password hashing |
| **cryptography** | 48.x | Encryption |

### Utilitaires

| Technologie | Version | Role |
|-------------|---------|------|
| **httpx** | 0.28.x | HTTP client async |
| **apscheduler** | 3.11.2 | Background jobs |
| **edge-tts** | 7.2.8 | Text-to-Speech |
| **firebase-admin** | 7.4.0 | Firebase integration |

### Dev Tools Python

| Technologie | Version | Role |
|-------------|---------|------|
| **black** | 26.x | Code formatter |
| **ruff** | 0.15.15 | Fast linter |
| **mypy** | 1.20.1 | Type checker |
| **pytest** | 9.0.3 | Testing framework |
| **pytest-asyncio** | 1.4.0 | Async test support |
| **pytest-cov** | 7.1.0 | Coverage |
| **pytest-mock** | 3.15.1 | Mocking |

| **safety** | 3.8.1 | Dependency scanner |

---

## Infrastructure Docker

### Services Core

| Service | Image | Role |
|---------|-------|------|
| **PostgreSQL** | `pgvector/pgvector:pg16` | Base de donnees principale + vectors |
| **postgres-backup** | `prodrigestivill/postgres-backup-local:16-alpine` | Sauvegardes pg_dump planifiees, rotation daily/weekly/monthly (ADR-109) |
| **Redis** | `redis:7.4-alpine` | Cache, sessions, rate limiting |

### Observabilite Stack

| Service | Image | Role |
|---------|-------|------|
| **Prometheus** | `prom/prometheus:v3.0.0` | Metrics collection |
| **Alertmanager** | `prom/alertmanager:v0.27.0` | Alert routing (14-alert core by email, ADR-119) |
| **blackbox-exporter** | `prom/blackbox-exporter:v0.25.0` | HTTP probes (backup healthcheck, public URL/TLS) |
| **Grafana** | `grafana/grafana:11.3.0` | Dashboards & visualization |
| **Loki** | `grafana/loki:3.2.1` | Log aggregation |
| **Promtail** | `grafana/promtail:3.2.1` | Log shipper |
| **Tempo** | `grafana/tempo:2.6.1` | Distributed tracing |

### Exporters

| Service | Image | Role |
|---------|-------|------|
| **cAdvisor** | `gcr.io/cadvisor/cadvisor:v0.49.1` | Container metrics |
| **postgres-exporter** | `prometheuscommunity/postgres-exporter:v0.15.0` | PostgreSQL metrics |
| **redis-exporter** | `oliver006/redis_exporter:v1.62.0` | Redis metrics |
| **node-exporter** | `prom/node-exporter:v1.8.2` | Host metrics |

### LLM Observability

| Service | Image | Role |
|---------|-------|------|
| **Langfuse Web** | `langfuse/langfuse:latest` | LLM tracing UI |
| **Langfuse Worker** | `langfuse/langfuse-worker:3` | Background processing |
| **ClickHouse** | `clickhouse/clickhouse-server` | Analytics storage |

### Utilitaires

| Service | Image | Role |
|---------|-------|------|
| **pgAdmin** | `dpage/pgadmin4:9.9` | PostgreSQL admin UI |
| **MinIO** | `minio/minio:latest` | S3-compatible storage |
| **Portainer** | `portainer/portainer-ce:2.39.0` | Container management |

---

## Compatibilite & Notes

### Python & Redis

> **Note**: La version Redis Python client (8.0.1) differe de l'image Docker (7.4-alpine).
> Le client 8.x est compatible avec Redis server 7.x.

### LangGraph & Checkpointing

> **Important**: `langgraph-checkpoint-postgres` 3.1.0 requiert PostgreSQL 14+ avec support JSON.
> Compatible avec pgvector 0.4.2+.

### Embeddings

> Google `gemini-embedding-001` (1536 dims par defaut) is used for all semantic embeddings (memory, tool routing, interests, journals, RAG spaces) with RETRIEVAL task types and dual-vector search.
> Replaced OpenAI text-embedding-3-small in v1.14.1. See [ADR-069](../architecture/ADR-069-Gemini-Embedding-Migration.md).

---

## Mises a Jour Planifiees

### Priorite Haute

| Composant | Actuel | Cible | Impact |
|-----------|--------|-------|--------|
| **pgvector** | 0.4.2 | 0.8.1 | Performance HNSW |

### Priorite Moyenne

| Composant | Actuel | Cible | Impact |
|-----------|--------|-------|--------|
| **Prometheus** | 3.0.0 | 3.9.1 | New features |
| **Loki/Promtail** | 3.2.1 | 3.6.x | Performance |
| **Tempo** | 2.6.1 | 2.9.x | New features |

### Futures (Major)

| Composant | Actuel | Cible | Notes |
|-----------|--------|-------|-------|
| **PostgreSQL** | 16 | 18 | Tester migrations + pgvector |
| **Redis** | 7.4 | 8.x | Nouvelle licence, evaluer impact |
| **Grafana** | 11.3.0 | 12.x | Breaking changes possibles |

---

## Verification des Versions

### Backend (requirements.lock.txt — versions effectivement installées)

```bash
cd apps/api
pip list | grep -E "fastapi|langgraph|langchain|pydantic|sqlalchemy"
```

### Frontend (package.json)

```bash
cd apps/web
pnpm list next react typescript tailwindcss
```

### Docker

```bash
docker compose ps --format "table {{.Name}}\t{{.Image}}\t{{.Status}}"
```

---

## Voir Aussi

- [GETTING_STARTED.md](../GETTING_STARTED.md) - Installation et configuration
- [ARCHITECTURE.md](../ARCHITECTURE.md) - Architecture globale
- [README_OBSERVABILITY.md](../readme/README_OBSERVABILITY.md) - Stack observabilite
- [DEPLOYMENT_INSTRUCTIONS.md](./DEPLOYMENT_INSTRUCTIONS.md) - Deploiement production
