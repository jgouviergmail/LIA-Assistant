# Stack Technique - Reference Complete

> **Version**: 1.0
> **Date**: 2026-01-12
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
| **Node.js** | >=20.0.0 | LTS recommande |
| **pnpm** | 10.x | Workspace monorepo |
| **Python** | >=3.12 | async/await natif |

---

## Frontend (apps/web)

### Framework Core

| Technologie | Version | Role |
|-------------|---------|------|
| **Next.js** | 16.1.1 | Framework React SSR/SSG |
| **React** | 19.2.3 | UI Library |
| **TypeScript** | 5.9.3 | Type safety |
| **Tailwind CSS** | 4.1.18 | Utility-first CSS |

### State & Data

| Technologie | Version | Role |
|-------------|---------|------|
| **@tanstack/react-query** | 5.90.x | Server state management |
| **Zod** | 4.3.x | Schema validation |
| **react-hook-form** | 7.70.x | Form management |

### UI Components

| Technologie | Version | Role |
|-------------|---------|------|
| **Radix UI** | 1.x-2.x | Accessible primitives |
| **lucide-react** | 0.562.x | Icons |
| **sonner** | 2.0.x | Toast notifications |
| **next-themes** | 0.4.x | Dark mode |

### Internationalization

| Technologie | Version | Role |
|-------------|---------|------|
| **i18next** | 25.x | i18n framework |
| **react-i18next** | 16.5.x | React bindings |

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
| **FastAPI** | 0.135.1 | Web framework async |
| **Uvicorn** | 0.41.0 | ASGI server |
| **Pydantic** | 2.12.5 | Data validation |
| **pydantic-settings** | 2.10.x | Configuration |

### Base de Donnees

| Technologie | Version | Role |
|-------------|---------|------|
| **SQLAlchemy** | 2.0.45 | ORM async |
| **Alembic** | 1.14.0 | Migrations |
| **asyncpg** | 0.31.0 | PostgreSQL driver async |
| **psycopg** | 3.3.x | PostgreSQL driver |
| **pgvector** | 0.4.2 | Vector similarity search |

### Cache & Sessions

| Technologie | Version | Role |
|-------------|---------|------|
| **redis** (Python) | 7.3.0 | Redis client |
| **cachetools** | 5.5.x | In-memory caching |

### AI/ML Stack (LangChain Ecosystem)

| Technologie | Version | Role |
|-------------|---------|------|
| **langchain-core** | 1.2.19 | Core abstractions |
| **langchain** | 1.2.12 | LLM framework |
| **langgraph** | 1.1.2 | Agent orchestration |
| **langgraph-checkpoint** | 4.0.1 | Checkpoint serialization |
| **langgraph-checkpoint-postgres** | 3.0.4 | State persistence |
| **langgraph-prebuilt** | 1.0.8 | Prebuilt agent components |
| **langmem** | 0.0.30+ | Long-term memory |

### LLM Providers

| Technologie | Version | Provider |
|-------------|---------|----------|
| **langchain-openai** | 1.1.11 | OpenAI GPT-4/5 |
| **langchain-anthropic** | 1.3.5 | Claude |
| **langchain-google-genai** | 4.2.1 | Gemini |
| **langchain-deepseek** | 1.0.1 | DeepSeek |
| **openai** | 2.20.0 | OpenAI SDK |
| **anthropic** | 0.84.0 | Claude SDK direct |
| **tiktoken** | 0.8.x | Token counting |

### Embeddings & ML

| Technologie | Version | Role |
|-------------|---------|------|
| **sentence-transformers** | 5.3.0 | Local E5 embeddings |

### Observabilite

| Technologie | Version | Role |
|-------------|---------|------|
| **structlog** | 25.x | Structured logging |
| **prometheus-client** | 0.21.x | Metrics |
| **langfuse** | 3.14.5 | LLM observability |
| **opentelemetry-api** | 1.40.0 | Distributed tracing |
| **opentelemetry-sdk** | 1.40.0 | Tracing SDK |
| **opentelemetry-instrumentation-fastapi** | 0.61b0 | FastAPI auto-instrumentation |
| **opentelemetry-exporter-otlp** | 1.40.0 | OTLP export |

### Securite & Auth

| Technologie | Version | Role |
|-------------|---------|------|
| **python-jose** | 3.5.0 | JWT handling |
| **passlib** | 1.7.x | Password hashing |
| **cryptography** | 44.x | Encryption |

### Utilitaires

| Technologie | Version | Role |
|-------------|---------|------|
| **httpx** | 0.28.x | HTTP client async |
| **slowapi** | 0.1.x | Rate limiting |
| **apscheduler** | 3.11.2 | Background jobs |
| **edge-tts** | 7.2.7 | Text-to-Speech |
| **firebase-admin** | 7.2.0 | Firebase integration |
| **phonenumbers** | 8.13.x | Phone validation |

### Dev Tools Python

| Technologie | Version | Role |
|-------------|---------|------|
| **black** | 24.x | Code formatter |
| **ruff** | 0.15.6 | Fast linter |
| **mypy** | 1.19.1 | Type checker |
| **pytest** | 9.0.2 | Testing framework |
| **pytest-asyncio** | 1.3.0 | Async test support |
| **pytest-cov** | 7.0.0 | Coverage |
| **pytest-mock** | 3.15.1 | Mocking |
| **bandit** | 1.9.4 | Security linter |
| **safety** | 3.7.0 | Dependency scanner |

---

## Infrastructure Docker

### Services Core

| Service | Image | Role |
|---------|-------|------|
| **PostgreSQL** | `pgvector/pgvector:pg16` | Base de donnees principale + vectors |
| **Redis** | `redis:7.4-alpine` | Cache, sessions, rate limiting |

### Observabilite Stack

| Service | Image | Role |
|---------|-------|------|
| **Prometheus** | `prom/prometheus:v3.0.0` | Metrics collection |
| **Alertmanager** | `prom/alertmanager:v0.27.0` | Alert routing |
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
| **Portainer** | `portainer/portainer-ce:latest` | Container management |

---

## Compatibilite & Notes

### Python & Redis

> **Note**: La version Redis Python client (7.3.0) differe de l'image Docker (7.4-alpine).
> Le client 7.3.0 est compatible avec Redis server 7.x.

### LangGraph & Checkpointing

> **Important**: `langgraph-checkpoint-postgres` 3.0.2 requiert PostgreSQL 14+ avec support JSON.
> Compatible avec pgvector 0.4.2+.

### Embeddings Local

> **sentence-transformers** 5.0+ utilise le modele `intfloat/multilingual-e5-small` pour les embeddings locaux.
> Zero API cost pour le semantic routing.

---

## Mises a Jour Planifiees

### Priorite Haute

| Composant | Actuel | Cible | Impact |
|-----------|--------|-------|--------|
| **Alembic** | 1.14.0 | 1.18.0 | Bug fixes migrations |
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

### Backend (requirements.txt)

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
