# Guide Pratique : Déploiement et CI/CD

**Version** : 1.1
**Dernière mise à jour** : 2025-12-27
**Statut** : ✅ Stable

---

## Table des matières

1. [Introduction](#introduction)
2. [Architecture de Déploiement](#architecture-de-déploiement)
3. [Configuration Environnement](#configuration-environnement)
4. [Déploiement Local (Docker Compose)](#déploiement-local-docker-compose)
5. [Build Docker Images](#build-docker-images)
6. [Déploiement Production](#déploiement-production)
7. [CI/CD Pipeline](#cicd-pipeline)
8. [Migrations Base de Données](#migrations-base-de-données)
9. [Secrets Management](#secrets-management)
10. [Monitoring Post-Déploiement](#monitoring-post-déploiement)
11. [Rollback Strategy](#rollback-strategy)
12. [Health Checks](#health-checks)
13. [Troubleshooting Déploiement](#troubleshooting-déploiement)
14. [Références](#références)

---

## Introduction

### Objectif du guide

Ce guide fournit une approche complète pour **déployer LIA** en local et en production. Il couvre :

- **Docker** : multi-stage builds, optimisation images
- **Docker Compose** : orchestration locale complète
- **CI/CD** : GitHub Actions pipelines automatisés
- **Production** : déploiement cloud, scaling, haute disponibilité
- **Migrations** : Alembic migrations PostgreSQL
- **Monitoring** : health checks, observabilité post-déploiement

### Public cible

- **DevOps Engineers** : déploiement production, infrastructure
- **Développeurs** : déploiement local, debugging
- **SRE** : monitoring, incidents, rollbacks
- **Tech Leads** : architecture déploiement, stratégie

### Prérequis

- **Docker 24+** : containerization
- **Docker Compose 2.20+** : orchestration locale
- **Git** : versioning
- **Accès cloud** : AWS/GCP/Azure (production)
- **Connaissances** : Docker, Kubernetes (optionnel), CI/CD

### Installateur self-host guidé (`./install.sh`)

L'installateur guidé (ADR-215) couvre le déploiement production complet sur
machine vierge. Sa règle de mode est conditionnelle et reste vraie avant et
après la qualification d'une release :

- un **checkout source complet** installe par défaut en **build local** ;
- un **répertoire de release officiel** installe par défaut en **digests
  prébuilts** uniquement quand son `lia-self-host-manifest.json` adjacent
  est qualifié (`qualification="passed"`) ; manifest absent ou candidat →
  build local ;
- `./install.sh --local-build` dans un répertoire de release construit
  depuis le **contexte source embarqué vérifié** de la release ;
- sans checkout complet ni contexte embarqué valide, l'échec survient
  **avant toute mutation** avec le nom exact de l'asset de release qualifié
  à télécharger.

Reprise : `./install.sh --resume` (seuls les secrets éphémères sont
redemandés si le bootstrap n'était pas terminé) ; ajustements réseau/
capacités : `./install.sh --reconfigure` (jamais de re-seed ni de rotation
de secrets).

---

## Architecture de Déploiement

### Vue d'Ensemble

```mermaid
graph TB
    subgraph "User Traffic"
        User[👤 User]
    end

    subgraph "Load Balancer"
        LB[NGINX/ALB]
    end

    subgraph "Application Layer"
        API1[API Instance 1<br/>FastAPI]
        API2[API Instance 2<br/>FastAPI]
        API3[API Instance 3<br/>FastAPI]
        WEB[Web Frontend<br/>Next.js]
    end

    subgraph "Data Layer"
        PG[(PostgreSQL<br/>Primary)]
        PG_REPLICA[(PostgreSQL<br/>Replica)]
        REDIS[(Redis<br/>Cache)]
    end

    subgraph "Observability"
        PROM[Prometheus]
        GRAF[Grafana]
        LOKI[Loki]
        TEMPO[Tempo]
    end

    User --> LB
    LB --> WEB
    LB --> API1
    LB --> API2
    LB --> API3

    API1 --> PG
    API2 --> PG
    API3 --> PG

    API1 --> REDIS
    API2 --> REDIS
    API3 --> REDIS

    PG --> PG_REPLICA

    API1 --> PROM
    API2 --> PROM
    API3 --> PROM

    PROM --> GRAF
    LOKI --> GRAF
    TEMPO --> GRAF
```

### Composants

| Composant | Technologie | Scaling | Haute Disponibilité |
|-----------|-------------|---------|---------------------|
| **API** | FastAPI (Python 3.14) | Horizontal (3+ instances) | ✅ Load balanced |
| **Web** | Next.js 16 | Horizontal (2+ instances) | ✅ Load balanced |
| **Database** | PostgreSQL 16 + pgvector | Vertical + Replicas | ✅ Primary + Replicas |
| **Cache** | Redis 7 | Cluster mode | ✅ Redis Sentinel |
| **Load Balancer** | NGINX / AWS ALB | N/A | ✅ Managed service |
| **Monitoring** | Prometheus + Grafana | N/A | ✅ Persistent storage |

### Exposition réseau (production)

En production, `cloudflared` est le seul point d'entrée public : tous les
services internes (Postgres, Grafana, Prometheus, Loki, Tempo, Portainer,
cAdvisor, exporters) sont liés à `127.0.0.1` dans `docker-compose.prod.yml`.
**Attention : Docker contourne ufw** (chaîne iptables `DOCKER` évaluée avant
le firewall) — un port publié en `0.0.0.0` est joignable depuis le LAN même
si ufw le refuse. Détails, tunnels SSH et règle `DOCKER-USER` :
[infrastructure/README.md](../../infrastructure/README.md).

### WebAuthn / Passkeys en production (activation de MFA_ENABLED)

Chromium refuse toute cérémonie WebAuthn sur un certificat TLS non approuvé.
En production **aucune manipulation de certificat n'est nécessaire** : le TLS
public est terminé par Cloudflare avec un certificat valide sur le domaine du
front (`FRONTEND_URL`) — vérifiable par `curl -sI https://<front> -w
"%{ssl_verify_result}"` qui doit répondre `0` (sans `-k`).

Checklist d'activation post-release (les flags livrés `false` par défaut) :

1. `MFA_ENABLED=true` (et `ACCOUNT_EXPORT_ENABLED=true` pour l'export) dans le
   `.env` prod, puis recréation des conteneurs (`restart` ne recharge pas
   l'env compose).
2. `WEBAUTHN_RP_ID` / `WEBAUTHN_EXPECTED_ORIGIN` restent **vides** : le rpId
   se dérive du hostname de `FRONTEND_URL` et l'origin attendu de
   `FRONTEND_URL` — correct avec un front et une API sur des domaines
   distincts (la cérémonie s'exécute sur l'origin du front). Ne les poser
   que pour un override délibéré, et **jamais de commentaire inline sur une
   variable vide** (garde CI `test_env_example_inline_comment_guard.py` ; le
   validator `MFASettings` refuse de booter sur une valeur polluée).
3. Smoke : `GET /auth/features` → `{"mfa_enabled": true}`, puis un
   enrôlement passkey réel de bout en bout depuis le domaine public.

Seul le contexte **dev** (certificat self-signed) exige d'approuver le
certificat : `task dev:trust-cert` (voir GETTING_STARTED, « WebAuthn /
Passkeys in Development »).

### Environnements

1. **Development** : local laptop, Docker Compose
2. **Staging** : cloud preview, CI/CD automatique
3. **Production** : cloud production, HA, auto-scaling

---

## Configuration Environnement

### Variables d'Environnement (.env)

**Créer .env à partir du template** :

```bash
# Backend
cd apps/api
cp .env.example .env

# Frontend
cd apps/web
cp .env.example .env
```

### Configuration Backend (.env)

```bash
# ============================================================================
# ENVIRONMENT & LOGGING
# ============================================================================

ENVIRONMENT=production  # development | staging | production
DEBUG=false
LOG_LEVEL=INFO  # DEBUG | INFO | WARNING | ERROR

# ============================================================================
# API CONFIGURATION
# ============================================================================

API_HOST=0.0.0.0
API_PORT=8000
API_PREFIX=/api/v1

CORS_ORIGINS=https://app.yourdomain.com
FRONTEND_URL=https://app.yourdomain.com
API_URL=https://api.yourdomain.com

# ============================================================================
# SECURITY & AUTHENTICATION
# ============================================================================

# Generate with: openssl rand -base64 32
SECRET_KEY=<GENERATE_SECURE_KEY>
# HMAC only (HS256 / HS384 / HS512) — enforced by a Literal in SecuritySettings.
# An EC/RSA value would route python-jose through its ecdsa backend, whose
# CVE-2024-23342 is exempted in CI on the strength of this constraint.
ALGORITHM=HS256

# Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
FERNET_KEY=<GENERATE_FERNET_KEY>

# Session Cookie Configuration
SESSION_COOKIE_NAME=lia_session
SESSION_COOKIE_SECURE=true  # ⚠️ MUST be true in production (HTTPS required)
SESSION_COOKIE_HTTPONLY=true
SESSION_COOKIE_SAMESITE=lax
SESSION_COOKIE_DOMAIN=.yourdomain.com  # Enable cross-subdomain cookies

# ============================================================================
# DATABASE CONFIGURATION
# ============================================================================

# Production: use managed service (RDS, Cloud SQL, etc.)
DATABASE_URL=postgresql+asyncpg://user:password@db-host:5432/lia

# Connection pool settings (tune based on load)
DATABASE_POOL_SIZE=20  # Default: 5 (local), 20+ (production)
DATABASE_MAX_OVERFLOW=40  # Default: 10, 40+ (production)

# ============================================================================
# REDIS CONFIGURATION
# ============================================================================

# Production: use managed service (ElastiCache, MemoryStore, etc.)
REDIS_URL=redis://redis-host:6379/0

# ============================================================================
# LLM PROVIDERS
# ============================================================================
#
# ATTENTION — les cles des providers LLM ne se configurent PLUS ici.
# Depuis la migration `2026_03_08_0002-migrate_env_keys_to_db.py`, la table
# `provider_api_keys` (chiffree) est la SEULE source de verite : les cles se
# saisissent depuis l'interface d'administration LLM. `ANTHROPIC_API_KEY` et
# `DEEPSEEK_API_KEY` ne sont plus lus depuis l'environnement et sont absents de
# `.env.example` — les definir ici n'a aucun effet.
#
# OPENAI_API_KEY reste present dans `.env.example` (usages hors chat, embeddings).
OPENAI_API_KEY=<YOUR_OPENAI_API_KEY>

# ============================================================================
# OAUTH CONFIGURATION
# ============================================================================

# Google OAuth
GOOGLE_CLIENT_ID=<YOUR_GOOGLE_CLIENT_ID>
GOOGLE_CLIENT_SECRET=<YOUR_GOOGLE_CLIENT_SECRET>
GOOGLE_REDIRECT_URI=https://api.yourdomain.com/api/v1/auth/google/callback

# ============================================================================
# OBSERVABILITY
# ============================================================================

# OpenTelemetry
OTEL_SERVICE_NAME=lia-api
OTEL_EXPORTER_OTLP_ENDPOINT=http://tempo:4317
OTEL_SDK_DISABLED=false  # Set to true to disable tracing
# (pas de OTEL_EXPORTER_OTLP_PROTOCOL : non lu, le protocole suit l'endpoint)

# Langfuse
LANGFUSE_PUBLIC_KEY=<YOUR_LANGFUSE_PUBLIC_KEY>
LANGFUSE_SECRET_KEY=<YOUR_LANGFUSE_SECRET_KEY>
LANGFUSE_HOST=https://cloud.langfuse.com  # Or self-hosted URL
LANGFUSE_ENABLED=true

# ============================================================================
# FEATURE FLAGS
# ============================================================================

# LLM Caching
LLM_CACHE_ENABLED=true
LLM_CACHE_TTL_SECONDS=300  # 5 minutes

# HITL
# (pas de HITL_ENABLED ni de TOOL_APPROVAL_ENABLED : ces variables n'existent
#  pas. Le HITL au niveau outil est TOUJOURS actif — cf. la note du routeur
#  "Tool approval is always enabled". Voir MCP_HITL_REQUIRED pour le cas MCP.)

# MCP (Model Context Protocol)
MCP_ENABLED=false                    # Active les serveurs MCP admin
MCP_USER_ENABLED=false               # Active le MCP per-user (requiert MCP_ENABLED=true)
MCP_MAX_TOOLS_PER_SERVER=50          # Limite tools par serveur
MCP_TOOL_TIMEOUT_SECONDS=30          # Timeout d'appel outil (PAS "MCP_CONNECTION_TIMEOUT")
MCP_APP_MAX_HTML_SIZE=500000         # Taille max HTML MCP Apps (APP au singulier)

# Multi-Channel Messaging (Telegram)
CHANNELS_ENABLED=false               # Active les canaux de messagerie externes
TELEGRAM_BOT_TOKEN=                  # Token du bot Telegram (@BotFather)
TELEGRAM_WEBHOOK_SECRET=             # Secret pour valider les webhooks Telegram

# Heartbeat Autonome (Notifications Proactives)
# Noms verifies contre .env.example le 2026-07-20. Les anciens noms documentes
# ici (HEARTBEAT_INTERVAL_MINUTES, HEARTBEAT_MAX_PER_DAY, HEARTBEAT_NOTIFY_
# START_HOUR/END_HOUR) n'existent pas — la cadence se regle par intervalle +
# cooldowns, pas par un quota journalier ni une plage horaire.
HEARTBEAT_ENABLED=false                      # Active les notifications proactives LLM-driven
HEARTBEAT_NOTIFICATION_INTERVAL_MINUTES=60   # Intervalle entre executions
HEARTBEAT_NOTIFICATION_BATCH_SIZE=...        # Utilisateurs traites par execution
HEARTBEAT_GLOBAL_COOLDOWN_HOURS=...          # Delai minimum entre 2 notifications
HEARTBEAT_ACTIVITY_COOLDOWN_MINUTES=...      # Silence apres une activite utilisateur
HEARTBEAT_INACTIVE_SKIP_DAYS=...             # Ignore les utilisateurs inactifs
# Liste complete (contexte, meteo, enrichissement) : grep '^HEARTBEAT_' .env.example

# Actions Planifiees
# (pas de SCHEDULED_ACTIONS_ENABLED : la variable n'existe pas, les actions
#  planifiees sont toujours actives ; seuls les timeouts sont parametrables)

# Push Notifications (Firebase)
FCM_ENABLED=false                    # Active les push Firebase (PAS "FCM_NOTIFICATIONS_ENABLED")
FCM_DEFAULT_TTL=...                  # TTL des messages
FCM_TOKEN_CLEANUP_DAYS=...           # Purge des tokens inactifs
```

### Configuration Frontend (.env.local)

```bash
# Next.js Environment Variables

# API Backend URL
NEXT_PUBLIC_API_URL=https://api.yourdomain.com

# Application URL
NEXT_PUBLIC_APP_URL=https://app.yourdomain.com

# (pas de NEXT_PUBLIC_ENVIRONMENT ni de NEXT_PUBLIC_ANALYTICS_ENABLED :
#  ces variables ne sont lues nulle part. Variables reellement exposees au
#  frontend : grep '^NEXT_PUBLIC_' .env.example)

# Disable Next.js telemetry
NEXT_TELEMETRY_DISABLED=1
```

### Validation Configuration

**Script de validation** :

```python
# apps/api/scripts/validate_config.py
import os
import sys

REQUIRED_VARS = [
    "SECRET_KEY",
    "FERNET_KEY",
    "DATABASE_URL",
    "REDIS_URL",
    "OPENAI_API_KEY",
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
]

def validate_env():
    """Validate required environment variables."""
    missing = []

    for var in REQUIRED_VARS:
        value = os.getenv(var)
        if not value:
            missing.append(var)
        elif var.endswith("_KEY") and len(value) < 32:
            print(f"⚠️  WARNING: {var} is too short (< 32 chars)")

    if missing:
        print(f"❌ Missing required environment variables:")
        for var in missing:
            print(f"   - {var}")
        sys.exit(1)

    print("✅ Environment validation passed")

if __name__ == "__main__":
    validate_env()
```

**Usage** :

```bash
# Validate before deployment
python apps/api/scripts/validate_config.py
```

---

## Déploiement Local (Docker Compose)

### Architecture Docker Compose

**Fichier docker-compose.yml** (simplifié) :

```yaml
version: '3.8'

services:
  # ============================================================================
  # Application Services
  # ============================================================================

  api:
    build:
      context: ./apps/api
      dockerfile: Dockerfile
    container_name: lia-api
    ports:
      - "8000:8000"
    env_file:
      - ./apps/api/.env
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ./apps/api:/app  # Hot reload in dev
    networks:
      - lia-network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  web:
    build:
      context: ./apps/web
      dockerfile: Dockerfile
    container_name: lia-web
    ports:
      - "3000:3000"
    env_file:
      - ./apps/web/.env.local
    depends_on:
      - api
    networks:
      - lia-network

  # ============================================================================
  # Data Layer
  # ============================================================================

  postgres:
    image: pgvector/pgvector:pg16
    container_name: lia-postgres
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: lia
    ports:
      - "5432:5432"
    volumes:
      - postgres-data:/var/lib/postgresql/data
    networks:
      - lia-network
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    container_name: lia-redis
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data
    networks:
      - lia-network
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  # ============================================================================
  # Observability Stack
  # ============================================================================

  prometheus:
    image: prom/prometheus:latest
    container_name: lia-prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./infrastructure/observability/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus-data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--web.enable-lifecycle'
    networks:
      - lia-network

  grafana:
    image: grafana/grafana:latest
    container_name: lia-grafana
    ports:
      - "3001:3000"
    environment:
      GF_SECURITY_ADMIN_PASSWORD: admin
      GF_USERS_ALLOW_SIGN_UP: false
    volumes:
      - ./infrastructure/observability/grafana/provisioning:/etc/grafana/provisioning
      - grafana-data:/var/lib/grafana
    depends_on:
      - prometheus
    networks:
      - lia-network

  loki:
    image: grafana/loki:latest
    container_name: lia-loki
    ports:
      - "3100:3100"
    volumes:
      - ./infrastructure/observability/loki/loki-config.yml:/etc/loki/local-config.yaml
      - loki-data:/loki
    networks:
      - lia-network

  tempo:
    image: grafana/tempo:latest
    container_name: lia-tempo
    ports:
      - "4317:4317"  # OTLP gRPC
      - "4318:4318"  # OTLP HTTP
    volumes:
      - ./infrastructure/observability/tempo/tempo-config.yml:/etc/tempo/tempo.yaml
      - tempo-data:/var/tempo
    networks:
      - lia-network

volumes:
  postgres-data:
  redis-data:
  prometheus-data:
  grafana-data:
  loki-data:
  tempo-data:

networks:
  lia-network:
    driver: bridge
```

### Démarrage Local

```bash
# 1. Clone repository
git clone https://github.com/yourusername/lia.git
cd lia

# 2. Configure environment
cp apps/api/.env.example apps/api/.env
cp apps/web/.env.example apps/web/.env.local

# Edit .env files with your values
nano apps/api/.env

# 3. Build and start services
docker-compose up -d

# 4. Verify services health
docker-compose ps

# Expected output:
# NAME                  STATUS              PORTS
# lia-api        Up (healthy)        0.0.0.0:8000->8000/tcp
# lia-web        Up                  0.0.0.0:3000->3000/tcp
# lia-postgres   Up (healthy)        0.0.0.0:5432->5432/tcp
# lia-redis      Up (healthy)        0.0.0.0:6379->6379/tcp
# lia-prometheus Up                  0.0.0.0:9090->9090/tcp
# lia-grafana    Up                  0.0.0.0:3001->3000/tcp
# ...

# 5. Run database migrations
docker-compose exec api alembic upgrade head

# 6. Create initial admin user (optional)
docker-compose exec api python scripts/data/create_admin.py

# 7. Access services
# - Frontend: http://localhost:3000
# - API: http://localhost:8000
# - API Docs: http://localhost:8000/docs
# - Grafana: http://localhost:3001 (admin/admin)
# - Prometheus: http://localhost:9090
```

### Logs et Debugging

```bash
# View logs for all services
docker-compose logs -f

# View logs for specific service
docker-compose logs -f api

# Follow logs with timestamps
docker-compose logs -f --timestamps api

# View last 100 lines
docker-compose logs --tail=100 api

# Execute command in running container
docker-compose exec api bash

# Restart specific service
docker-compose restart api

# Rebuild and restart
docker-compose up -d --build api
```

---

## Build Docker Images

### Backend Dockerfile (Multi-stage)

```dockerfile
# apps/api/Dockerfile

# ============================================================================
# Stage 1: Base image with Python and system dependencies
# ============================================================================
FROM python:3.12-slim AS base

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# ============================================================================
# Stage 2: Dependencies installation
# ============================================================================
FROM base AS dependencies

# Copy dependency files
COPY pyproject.toml ./

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e ".[prod]"

# ============================================================================
# Stage 3: Production image
# ============================================================================
FROM base AS production

# Copy installed dependencies from dependencies stage
COPY --from=dependencies /usr/local/lib/python3.14/site-packages /usr/local/lib/python3.14/site-packages
COPY --from=dependencies /usr/local/bin /usr/local/bin

# Copy application code
COPY . /app

# Create non-root user for security
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run application
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

> **Prometheus multi-worker** : avec `--workers`, `docker-entrypoint.sh` active automatiquement le
> mode multiprocess de `prometheus_client` (`PROMETHEUS_MULTIPROC_DIR`, RAM `/dev/shm`, non-fatal)
> pour que les métriques des 4 workers soient agrégées sur le port 9091. Aucune action requise en
> dev (mono-worker `--reload`). Pour une très forte cardinalité, augmenter le `shm_size` du
> conteneur API ou surcharger `PROMETHEUS_MULTIPROC_DIR`. Détails :
> [ADR-089](../architecture/ADR-089-Prometheus-Multiprocess-Metrics.md).

### Frontend Dockerfile (Next.js 16)

```dockerfile
# apps/web/Dockerfile

# ============================================================================
# Stage 1: Base image with Node.js and pnpm
# ============================================================================
FROM node:24-alpine AS base

# Install pnpm
RUN corepack enable && corepack prepare pnpm@10.18.3 --activate

# ============================================================================
# Stage 2: Install dependencies
# ============================================================================
FROM base AS deps

RUN apk add --no-cache libc6-compat
WORKDIR /app

# Copy package files
COPY package.json pnpm-lock.yaml* ./
RUN pnpm install --frozen-lockfile

# ============================================================================
# Stage 3: Build application
# ============================================================================
FROM base AS builder

WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Set environment variables for build
ENV NEXT_TELEMETRY_DISABLED=1

# Build the application
RUN pnpm run build

# ============================================================================
# Stage 4: Production runner
# ============================================================================
FROM base AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Create non-root user
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

# Copy built application
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["node", "server.js"]
```

### Build et Push Images

```bash
# 1. Login to container registry (GitHub Container Registry)
echo $GITHUB_TOKEN | docker login ghcr.io -u USERNAME --password-stdin

# 2. Build images with tags
docker build -t ghcr.io/yourusername/lia-api:latest \
             -t ghcr.io/yourusername/lia-api:v1.0.0 \
             ./apps/api

docker build -t ghcr.io/yourusername/lia-web:latest \
             -t ghcr.io/yourusername/lia-web:v1.0.0 \
             ./apps/web

# 3. Push images
docker push ghcr.io/yourusername/lia-api:latest
docker push ghcr.io/yourusername/lia-api:v1.0.0

docker push ghcr.io/yourusername/lia-web:latest
docker push ghcr.io/yourusername/lia-web:v1.0.0

# 4. Verify images
docker images | grep lia
```

### Optimisation Images

**Best Practices** :

1. **Multi-stage builds** : réduire taille finale (800MB → 200MB)
2. **Layer caching** : copier dependencies avant code
3. **Non-root user** : sécurité (appuser, nextjs)
4. **.dockerignore** : exclure node_modules, __pycache__, .git

**Exemple .dockerignore** :

```
# apps/api/.dockerignore
__pycache__/
*.py[cod]
*.so
.env
.venv/
venv/
.git/
.gitignore
.mypy_cache/
.pytest_cache/
.coverage
htmlcov/
*.log
```

---

## Déploiement Production

### Architecture Production (AWS)

```mermaid
graph TB
    subgraph "AWS Cloud"
        subgraph "Availability Zone 1"
            ALB1[Application Load Balancer]
            API1[ECS/Fargate API]
            WEB1[ECS/Fargate Web]
        end

        subgraph "Availability Zone 2"
            API2[ECS/Fargate API]
            WEB2[ECS/Fargate Web]
        end

        subgraph "Data Layer"
            RDS[(RDS PostgreSQL<br/>Multi-AZ)]
            ELASTICACHE[(ElastiCache Redis<br/>Cluster)]
        end

        subgraph "Storage"
            S3[S3 Bucket<br/>Static Assets]
        end

        subgraph "Monitoring"
            CW[CloudWatch]
            XR[X-Ray]
        end
    end

    ALB1 --> API1
    ALB1 --> API2
    ALB1 --> WEB1
    ALB1 --> WEB2

    API1 --> RDS
    API2 --> RDS

    API1 --> ELASTICACHE
    API2 --> ELASTICACHE

    WEB1 --> S3
    WEB2 --> S3

    API1 --> CW
    API2 --> CW
    API1 --> XR
    API2 --> XR
```

### Déploiement ECS/Fargate (AWS)

**Task Definition (task-definition.json)** :

```json
{
  "family": "lia-api",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "1024",
  "memory": "2048",
  "executionRoleArn": "arn:aws:iam::ACCOUNT_ID:role/ecsTaskExecutionRole",
  "taskRoleArn": "arn:aws:iam::ACCOUNT_ID:role/ecsTaskRole",
  "containerDefinitions": [
    {
      "name": "api",
      "image": "ghcr.io/yourusername/lia-api:v1.0.0",
      "portMappings": [
        {
          "containerPort": 8000,
          "protocol": "tcp"
        }
      ],
      "environment": [
        {
          "name": "ENVIRONMENT",
          "value": "production"
        },
        {
          "name": "LOG_LEVEL",
          "value": "INFO"
        }
      ],
      "secrets": [
        {
          "name": "SECRET_KEY",
          "valueFrom": "arn:aws:secretsmanager:REGION:ACCOUNT_ID:secret:lia/secret-key"
        },
        {
          "name": "DATABASE_URL",
          "valueFrom": "arn:aws:secretsmanager:REGION:ACCOUNT_ID:secret:lia/database-url"
        },
        {
          "name": "OPENAI_API_KEY",
          "valueFrom": "arn:aws:secretsmanager:REGION:ACCOUNT_ID:secret:lia/openai-key"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/lia-api",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "ecs"
        }
      },
      "healthCheck": {
        "command": ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"],
        "interval": 30,
        "timeout": 10,
        "retries": 3,
        "startPeriod": 60
      }
    }
  ]
}
```

**Déploiement avec AWS CLI** :

```bash
# 1. Register task definition
aws ecs register-task-definition \
  --cli-input-json file://task-definition.json

# 2. Create or update service
aws ecs create-service \
  --cluster lia-cluster \
  --service-name lia-api \
  --task-definition lia-api:1 \
  --desired-count 3 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx,subnet-yyy],securityGroups=[sg-zzz],assignPublicIp=ENABLED}" \
  --load-balancers "targetGroupArn=arn:aws:elasticloadbalancing:...,containerName=api,containerPort=8000"

# 3. Deploy new version (blue/green deployment)
aws ecs update-service \
  --cluster lia-cluster \
  --service lia-api \
  --task-definition lia-api:2 \
  --desired-count 3 \
  --deployment-configuration "maximumPercent=200,minimumHealthyPercent=100"

# 4. Monitor deployment
aws ecs describe-services \
  --cluster lia-cluster \
  --services lia-api \
  --query 'services[0].deployments'
```

### Auto-scaling Configuration

```bash
# Application Auto Scaling
aws application-autoscaling register-scalable-target \
  --service-namespace ecs \
  --resource-id service/lia-cluster/lia-api \
  --scalable-dimension ecs:service:DesiredCount \
  --min-capacity 2 \
  --max-capacity 10

# CPU-based scaling policy
aws application-autoscaling put-scaling-policy \
  --service-namespace ecs \
  --resource-id service/lia-cluster/lia-api \
  --scalable-dimension ecs:service:DesiredCount \
  --policy-name cpu-scaling \
  --policy-type TargetTrackingScaling \
  --target-tracking-scaling-policy-configuration '{
    "TargetValue": 70.0,
    "PredefinedMetricSpecification": {
      "PredefinedMetricType": "ECSServiceAverageCPUUtilization"
    },
    "ScaleInCooldown": 300,
    "ScaleOutCooldown": 60
  }'
```

---

### Le pilote auto-hébergé : exécution détachée et verdict lu (ADR-250)

`task deploy:prod` (`scripts/deploy/deploy-prod.ps1`) ne tient plus le
déploiement dans une session SSH bloquante. Le travail est **lancé détaché** sur
l'hôte, et le pilote **lit** un verdict que le distant a écrit.

**Pourquoi** : `ssh` propage fidèlement tout code distant **sauf 255**, qu'il
emploie aussi pour ses propres échecs de transport — sur 255, l'appelant ne sait
rien. Et le travail ne survivait pas à sa connexion : tuer le client fait mourir
le script distant par **SIGPIPE (exit 141) en ~6 s** (mesure 2026-08-29), soit
bien avant tout keepalive. Détaché, le même travail survit à la destruction de
tous les clients `ssh` et rend son code exact.

**Ce que le pilote peut dire, et ce qu'il refuse de dire** :

| Verdict affiché | Ce qui est établi | Conduite |
|-----------------|-------------------|----------|
| `OK: Deploiement termine` | le distant a écrit `0` | rien |
| `Echec du deploiement (exit code: N)` | le distant a écrit `N` | **seul** cas où « le déploiement a échoué » est vrai ; lire le journal distant indiqué |
| `deja en cours` | un autre déploiement tient le verrou | le vôtre **n'a pas eu lieu** ; attendre |
| `interrompu sans rendre de verdict` | processus disparu sans écrire | verdict **inconnu** ; ne pas relancer |
| `budget de scrutation epuise` | il tourne **encore** | attendre, ou relancer avec `-DeployBudgetSeconds` plus grand |
| `contact perdu` (ADR-250) | la connexion est tombée **au lancement** | l'hôte a pu forker le travail ; ne pas relancer |

> **Les quatre derniers ne sont pas des échecs.** Les présenter comme tels serait
> un diagnostic inventé. Sur chacun, le pilote imprime les trois commandes qui
> tranchent (journal distant, `docker compose ps`, `release-manifest.json`) et
> demande de **ne pas relancer** : l'étape 7 effacerait le répertoire de staging
> sous un build encore en vol.

**Un seul déploiement à la fois** est garanti par un `flock` pris par le
processus détaché. Le verrou est géré par le noyau, donc libéré même si le
processus est tué : il n'y a jamais de verrou fantôme à nettoyer à la main.

**Paramètres** :

```powershell
# Attendre plus longtemps (défaut : 2700 s) — un Pi chargé dépasse les ~11 min
# mesurées, et « budget épuisé » veut dire « il tourne encore », pas « il a raté ».
.\scripts\deploy\deploy-prod.ps1 -DeployBudgetSeconds 5400
# Rythme de scrutation (défaut : 5 s)
.\scripts\deploy\deploy-prod.ps1 -DeployPollSeconds 10
```

---

## CI/CD Pipeline

### GitHub Actions Workflow

**Fichier .github/workflows/ci.yml** :

```yaml
name: CI/CD Pipeline

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

env:
  REGISTRY: ghcr.io
  IMAGE_NAME_API: ${{ github.repository }}/api
  IMAGE_NAME_WEB: ${{ github.repository }}/web

jobs:
  # ============================================================================
  # Lint & Type Check
  # ============================================================================

  lint-backend:
    name: Lint Backend
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python 3.14
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'

      - name: Install dependencies
        working-directory: ./apps/api
        run: |
          # ADR-112 : on installe le LOCKFILE compile, pas pyproject
          # (pyproject ne declare aucune dependance).
          pip install --require-hashes --no-binary urllib3-future -r requirements-dev.lock.txt

      - name: Run Ruff
        working-directory: ./apps/api
        run: ruff check .

      - name: Run Black
        working-directory: ./apps/api
        run: black --check .

      - name: Run MyPy
        working-directory: ./apps/api
        run: mypy src

  # ============================================================================
  # Tests
  # ============================================================================

  test-backend:
    name: Test Backend
    runs-on: ubuntu-latest
    services:
      postgres:
        image: pgvector/pgvector:pg16
        env:
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
          POSTGRES_DB: test
        ports:
          - 5432:5432
        options: --health-cmd pg_isready --health-interval 10s --health-timeout 5s --health-retries 5

      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379
        options: --health-cmd "redis-cli ping" --health-interval 10s --health-timeout 5s --health-retries 5

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python 3.14
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'

      - name: Install dependencies
        working-directory: ./apps/api
        run: pip install --require-hashes --no-binary urllib3-future -r requirements-dev.lock.txt   # ADR-112

      - name: Run tests with coverage
        working-directory: ./apps/api
        env:
          DATABASE_URL: postgresql+asyncpg://test:test@localhost:5432/test
          REDIS_URL: redis://localhost:6379/15
        run: |
          pytest --cov=src --cov-report=xml --cov-report=term-missing

      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v4
        with:
          file: ./apps/api/coverage.xml
          flags: backend

  # ============================================================================
  # Build & Push Docker Images
  # ============================================================================

  build-api:
    name: Build API Image
    runs-on: ubuntu-latest
    needs: [lint-backend, test-backend]
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    permissions:
      contents: read
      packages: write

    steps:
      - uses: actions/checkout@v4

      - name: Log in to GitHub Container Registry
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Extract metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME_API }}
          tags: |
            type=ref,event=branch
            type=sha,prefix={{branch}}-
            type=semver,pattern={{version}}
            type=semver,pattern={{major}}.{{minor}}

      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: ./apps/api
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

  build-web:
    name: Build Web Image
    runs-on: ubuntu-latest
    needs: [lint-backend]  # Frontend has own lint job
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    permissions:
      contents: read
      packages: write

    steps:
      - uses: actions/checkout@v4

      - name: Log in to GitHub Container Registry
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Extract metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME_WEB }}

      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: ./apps/web
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}

  # ============================================================================
  # Deploy to Production (ECS)
  # ============================================================================

  deploy-production:
    name: Deploy to Production
    runs-on: ubuntu-latest
    needs: [build-api, build-web]
    if: github.ref == 'refs/heads/main'
    environment:
      name: production
      url: https://app.yourdomain.com

    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: us-east-1

      - name: Deploy API to ECS
        run: |
          aws ecs update-service \
            --cluster lia-cluster \
            --service lia-api \
            --force-new-deployment

      - name: Wait for deployment
        run: |
          aws ecs wait services-stable \
            --cluster lia-cluster \
            --services lia-api

      - name: Notify success
        if: success()
        run: echo "✅ Deployment successful!"
```

### Pipeline Stages

1. **Lint & Type Check** : Ruff, Black, MyPy, ESLint
2. **Tests** : Pytest (backend), Vitest (frontend), coverage ≥80%
3. **Build** : Docker multi-stage builds
4. **Push** : GitHub Container Registry (ghcr.io)
5. **Deploy** : ECS Fargate update-service
6. **Verify** : Health checks, smoke tests

---

## Migrations Base de Données

### Alembic Migrations

**Créer nouvelle migration** :

```bash
# 1. Create migration
cd apps/api
alembic revision --autogenerate -m "Add user_statistics table"

# 2. Review generated migration
cat alembic/versions/20250115_1234_add_user_statistics_table.py

# 3. Edit if needed (add data migrations, indexes, etc.)
nano alembic/versions/20250115_1234_add_user_statistics_table.py

# 4. Test migration locally
alembic upgrade head

# 5. Test rollback
alembic downgrade -1
alembic upgrade head
```

**Déployer migration en production** :

```bash
# Option 1: Run migration in ECS task (preferred)
aws ecs run-task \
  --cluster lia-cluster \
  --task-definition lia-migration \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx],securityGroups=[sg-yyy]}" \
  --overrides '{
    "containerOverrides": [{
      "name": "migration",
      "command": ["alembic", "upgrade", "head"]
    }]
  }'

# Option 2: Run migration via docker-compose (staging)
docker-compose exec api alembic upgrade head

# Option 3: Manual migration (emergency)
docker exec -it lia-api alembic upgrade head
```

### Migration Best Practices

1. **Backward compatible** : nouvelles migrations ne cassent pas code existant
2. **Idempotent** : peut être exécutée plusieurs fois sans effet
3. **Testée** : rollback testé en local avant production
4. **Data migration** : séparer schema migration et data migration
5. **Indexes** : créer indexes en CONCURRENTLY (PostgreSQL)

**Exemple migration avec index concurrent** :

```python
# alembic/versions/xxx_add_index.py
from alembic import op

def upgrade():
    # Create index concurrently (no table lock)
    op.execute(
        "CREATE INDEX CONCURRENTLY idx_conversations_user_id "
        "ON conversations (user_id)"
    )

def downgrade():
    op.drop_index("idx_conversations_user_id", table_name="conversations")
```

### Migration qui réécrit de la configuration : le contrôle d'instance

Une migration de **schéma** se vérifie en local : `task db:migrate:replay-check`
rejoue toute la chaîne et compare le schéma obtenu à celui des modèles. Une
migration qui réécrit des **lignes de configuration** ne se vérifie pas comme
ça, parce que les lignes en question ne sont pas les mêmes ici et là-bas : la
configuration réelle des agents vit dans `llm_config_overrides`, en base, et
**dev et prod n'exécutent pas les mêmes modèles**. Un compteur nul en dev ne dit
rien de prod.

`task llm:catalogue:preflight` est ce contrôle : lecture seule, il interroge la
base pointée par `DATABASE_URL` et répond aux questions dont la réponse dépend
de l'instance — quelles lignes la migration réécrirait, quels modèles seraient
désactivés, et **pour quels slots la profondeur de raisonnement demandée par
l'administrateur serait corrigée par le runtime**.

Il doit tourner depuis un checkout du **code qu'on s'apprête à déployer**,
contre la base **pas encore migrée** : c'est cet appariement qui le rend
prédictif.

`DATABASE_URL` désigne l'instance examinée, et **il doit être résoluble depuis
là où le script tourne**. Le `.env` du dépôt nomme le service Compose
(`postgres:5432`), qui ne se résout que dans le réseau Docker : depuis l'hôte,
il faut donc fournir la sienne. Une variable d'environnement explicite l'emporte
sur celle que le Taskfile charge (mesuré), donc `task` reste utilisable :

```bash
# dev, depuis l'hôte — Compose publie la base sur la boucle locale
DATABASE_URL=postgresql+asyncpg://<user>:<pass>@127.0.0.1:5432/<db> task llm:catalogue:preflight
```

La base de production, elle, n'est publiée que sur la boucle locale du Pi : on
passe par le tunnel que `docker-compose.prod.yml` documente à côté de son
binding.

```bash
# terminal 1 — laisser ouvert
ssh -p 2222 -L 15432:127.0.0.1:5432 <user>@<host> -N

# terminal 2
DATABASE_URL=postgresql+asyncpg://<user>:<pass>@127.0.0.1:15432/<db> task llm:catalogue:preflight
```

Une adresse injoignable donne une phrase, pas une trace asyncio : le script
nomme l'hôte tenté et rappelle d'où vient l'adresse — jamais les identifiants.

**Une limite, qui ne peut pas être supprimée** : seule la *base* est celle de
la cible. Les modèles par slot, le modèle de résumé et la chaîne de repli sont
des *settings* — ils vivent dans le `.env` de l'instance, et le processus lit
le sien. Le rapport imprime les trois qu'il a supposés (`env: summarisation=`,
`env: failover=`, `env: N slots`) précisément pour qu'on puisse vérifier qu'ils
sont bien ceux de l'instance examinée ; sinon, fournir les valeurs de la cible
à côté de `DATABASE_URL`.

Le verdict final (`N item(s) need attention`) compte ce qui demande une décision
humaine ; les autres rubriques sont informatives et ne bloquent jamais. Un
non-zéro n'interdit pas de déployer : il dit qu'une configuration existante ne
fera pas exactement ce que son auteur avait écrit, et que quelqu'un doit
l'accepter ou la corriger **avant** que le déploiement ne l'applique.

---

## Secrets Management

### Permissions du fichier `.env` en production (SEC-013)

Le `.env` de production contient **tous** les secrets applicatifs et
d'intégration. Il doit rester lisible par son seul propriétaire.

Le script de déploiement (`scripts/deploy/deploy-prod.ps1`, étape 8.5) applique
automatiquement, **après** avoir finalisé le `.env` distant et **avant** le
`docker compose up`, un durcissement idempotent et non bloquant :

- `.env` → `0600` (lecture/écriture propriétaire uniquement) ;
- répertoire de déploiement → `0700` ;
- `~/.claude/.credentials.json` → `0600`, `~/.claude` → `0700`.

Le démon Docker s'exécute en `root` et lit toujours les bind mounts ; `docker
compose` s'exécute sous le propriétaire et traverse son propre répertoire
`0700` — ces permissions ne cassent donc aucun accès légitime.

**Vérification / correction manuelle** (sur le serveur, si un `.env` a été posé
hors du script) :

```bash
# Doit afficher 600 pour le .env et 700 pour le répertoire
stat -c '%a %n' ~/<deploy-dir>/.env ~/<deploy-dir>
# Correction si nécessaire
chmod 600 ~/<deploy-dir>/.env && chmod 700 ~/<deploy-dir>
```

> Après la fermeture de tout chemin d'accès élargi aux secrets (p. ex. retrait
> du socket Docker de l'API), prévoir une **rotation** des secrets qui ont pu
> être exposés. La rotation est hors périmètre du durcissement de permissions.

### Le secret déchiffré ne survit pas à l'exécution (SEC-040)

`PROD/.env` est le fichier d'environnement de production **en clair** : l'étape 4
y renomme le `.env.prod` déchiffré. L'étape 10 supprime tout le bundle — mais
elle ne s'exécute que sur le chemin nominal, alors que le pilote a **14 sorties
prématurées** (11 `exit`, 3 `throw`).

Tant que `task deploy:prod` se terminait sur un faux échec (ADR-250), le chemin
d'échec **était** le chemin nominal : la fuite était systématique. Mesure du
2026-07-28 — **434 Mo de bundle** survivant à un déploiement qui avait pourtant
abouti, portant tous les identifiants de production sur le poste du développeur.

Un `finally` de premier niveau couvre désormais **toutes** les sorties.
PowerShell l'exécute sur `exit` comme sur un `throw` non rattrapé, en préservant
le code de retour (vérifié sur Windows PowerShell 5.1 **et** pwsh 7).

Trois propriétés, chacune apprise d'un défaut :

- **La liste est exacte, jamais un glob.** `provenance.env` vit dans le même
  répertoire, n'est pas un secret, et quatre tests le lisent.
- **Deux ensembles, et leur différence est le sujet.** La purge pré-transfert
  exclut délibérément `.env.prod` : l'étape 4 doit encore le renommer en `.env`.
  Les confondre supprime la source avant son renommage — le bundle part **sans
  fichier d'environnement** et le déploiement échoue à distance.
- **Le nettoyage est chirurgical.** Un `Remove-Item PROD` complet détruirait le
  bundle qu'un opérateur inspecte après un échec.

`-DryRun` en est exempt par contrat : une simulation doit laisser un `PROD/`
préexistant strictement intact, clés comprises.

**Vérification manuelle** (sur le poste, après une exécution interrompue) :

```powershell
# Ne doit rien lister : ni .env, ni .env.prod, ni keys/, ni .sops.yaml
Get-ChildItem PROD -Force -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -in @(".env", ".env.prod", ".env.prod.encrypted", ".sops.yaml", "keys") }
```

### AWS Secrets Manager

**Créer secrets** :

```bash
# 1. Create secret
aws secretsmanager create-secret \
  --name lia/secret-key \
  --secret-string "your-generated-secret-key-here"

aws secretsmanager create-secret \
  --name lia/database-url \
  --secret-string "postgresql+asyncpg://user:pass@rds-endpoint:5432/lia"

aws secretsmanager create-secret \
  --name lia/openai-key \
  --secret-string "sk-..."

# 2. Grant ECS task access (IAM policy)
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": [
        "arn:aws:secretsmanager:REGION:ACCOUNT:secret:lia/*"
      ]
    }
  ]
}

# 3. Reference in task definition (see above)
```

### Environment Variables Precedence

```
1. Secrets Manager (production)    ← Highest priority
2. .env file (local/staging)
3. Default values (code)            ← Lowest priority
```

---

## Monitoring Post-Déploiement

### Health Checks

The API exposes three endpoints (implementation: `apps/api/src/api/health.py`, contract: ADR-115):

| Endpoint | Role | Behavior |
|---|---|---|
| `GET /health` | **Liveness** | Always `200` while the process serves requests — even when PostgreSQL/Redis are down (payload: `status: healthy\|degraded` + per-dependency `checks`). Consumed by the Docker healthchecks. |
| `GET /ready` | **Readiness** | `200` + `status: ready` only when PostgreSQL **and** Redis answer their probe; `503` + `status: not_ready` otherwise. Poll it for deploy verification and user-impact monitoring. |
| `GET /api/v1/health` | Static process check | `200` with service name + version (OpenAPI-documented). No dependency probing. |

Docker healthchecks stay on `/health` on purpose: restarting the API cannot fix
a dependency outage, so a dependency failure must never send the container into
a restart loop. Anything that asks "can the service actually serve users?" —
post-deploy smoke tests, uptime monitoring — polls `/ready` instead.

```bash
curl -s http://localhost:8000/health
# {"status":"degraded","environment":"production","checks":{"redis":"unhealthy","database":"healthy"}}

curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/ready
# 200 (all dependencies up) / 503 (PostgreSQL or Redis down)
```

### Metrics Post-Déploiement

**Dashboard Grafana "Deployment Tracking"** :

```promql
# 1. Request rate (should spike after deployment)
rate(http_requests_total[5m])

# 2. Error rate (should stay low)
rate(http_requests_total{status=~"5.."}[5m]) /
rate(http_requests_total[5m]) * 100

# 3. P95 latency (should not increase)
histogram_quantile(0.95,
  sum(rate(http_request_duration_seconds_bucket[5m])) by (le)
)

# 4. Active connections
sum(http_active_connections)

# 5. CPU/Memory usage (ECS metrics)
aws_ecs_service_cpu_utilization
aws_ecs_service_memory_utilization
```

### Smoke Tests Post-Déploiement

```bash
#!/bin/bash
# smoke test ad hoc (exemple, non commité)

API_URL="https://api.yourdomain.com"

echo "🔍 Running smoke tests..."

# 1. Readiness check (200 only when PostgreSQL AND Redis answer — /health
#    would pass even with a dependency down, it is a liveness probe)
echo "Testing /ready endpoint..."
curl -f "$API_URL/ready" || exit 1

# 2. Authentication
echo "Testing authentication..."
TOKEN=$(curl -s -X POST "$API_URL/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"test"}' \
  | jq -r '.access_token')

if [ -z "$TOKEN" ]; then
  echo "❌ Authentication failed"
  exit 1
fi

# 3. Chat endpoint
echo "Testing chat endpoint..."
curl -f -X POST "$API_URL/api/v1/agents/chat" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message":"Hello"}' || exit 1

echo "✅ All smoke tests passed!"
```

### DevOps Claude CLI (v1.13.0)

Administrators can diagnose server issues directly from the LIA chat using natural language. Claude Code CLI is installed in the API Docker image and runs locally inside the container.

**First-time setup** (one-time per environment):
1. Install Claude CLI on the host machine (for OAuth only): `npm install -g @anthropic-ai/claude-code`
2. Authenticate: `claude auth login`
3. Credentials are mounted into the container automatically via `docker-compose`

**Configuration**: Set `DEVOPS_ENABLED=true` and configure `DEVOPS_SERVERS` in `.env`.

See [GUIDE_DEVOPS_CLAUDE_CLI.md](./GUIDE_DEVOPS_CLAUDE_CLI.md) for full setup instructions.

---

## Rollback Strategy

### ECS Rollback

```bash
# 1. List deployments
aws ecs describe-services \
  --cluster lia-cluster \
  --services lia-api \
  --query 'services[0].deployments'

# 2. Rollback to previous task definition
PREVIOUS_TASK_DEF=$(aws ecs describe-services \
  --cluster lia-cluster \
  --services lia-api \
  --query 'services[0].deployments[1].taskDefinition' \
  --output text)

aws ecs update-service \
  --cluster lia-cluster \
  --service lia-api \
  --task-definition $PREVIOUS_TASK_DEF \
  --force-new-deployment

# 3. Verify rollback
aws ecs wait services-stable \
  --cluster lia-cluster \
  --services lia-api
```

### Database Rollback

```bash
# Downgrade to previous migration
docker exec lia-api alembic downgrade -1

# Or specific version
docker exec lia-api alembic downgrade abc123def456
```

### Database Restore (depuis backup)

Quand un downgrade Alembic ne suffit pas (données corrompues, volume perdu), restaurer
depuis les sauvegardes automatiques du sidecar `postgres-backup` (ADR-109) : dumps
`pg_dump` quotidiens avec rotation daily/weekly/monthly, restauration en une commande,
vérification par `task backup:verify` (restauration réelle dans un conteneur jetable).
Procédure complète (arrêt API, restore, migrations auto au restart, flush Redis) :
[DATABASE_BACKUP_RESTORE.md](../runbooks/DATABASE_BACKUP_RESTORE.md).

---

## Troubleshooting Déploiement

### Problème : Container ne démarre pas

**Diagnostic** :

```bash
# 1. Check logs
docker logs lia-api

# 2. Check health check
docker inspect lia-api | jq '.[0].State.Health'

# 3. Exec into container
docker exec -it lia-api bash

# 4. Check environment
docker exec lia-api env | grep DATABASE_URL
```

### Problème : Migration échoue

**Solution** :

```bash
# 1. Check current migration version
docker exec lia-api alembic current

# 2. Check migration history
docker exec lia-api alembic history

# 3. Manual migration
docker exec -it lia-api bash
alembic upgrade head --sql  # Preview SQL
alembic upgrade head  # Apply
```

### Problème : Load balancer health check fail

**Causes** :

1. **Container not ready** : increase start_period
2. **Wrong health endpoint** : verify /health returns 200 (liveness — always 200 while the process is up; use /ready to test dependencies)
3. **Database connection fail** : check DATABASE_URL (visible in the /health payload `checks.database`, and /ready returns 503)

**Fix** :

```yaml
# docker-compose.yml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 60s  # ✅ Increase if slow startup
```

---

## Références

### Documentation Officielle

- **Docker** : [https://docs.docker.com](https://docs.docker.com)
- **Docker Compose** : [https://docs.docker.com/compose](https://docs.docker.com/compose)
- **GitHub Actions** : [https://docs.github.com/actions](https://docs.github.com/actions)
- **AWS ECS** : [https://docs.aws.amazon.com/ecs](https://docs.aws.amazon.com/ecs)
- **Alembic** : [https://alembic.sqlalchemy.org](https://alembic.sqlalchemy.org)

### Documentation Interne

- [CONTRIBUTING.md](../../CONTRIBUTING.md) : workflow contribution et CI/CD
- [GUIDE_DEBUGGING.md](./GUIDE_DEBUGGING.md) : debugging production
- [GUIDE_TESTING.md](./GUIDE_TESTING.md) : tests avant déploiement
- [DATABASE_SCHEMA.md](../technical/DATABASE_SCHEMA.md) : migrations Alembic

### Outils

- **Terraform** : Infrastructure as Code (IaC)
- **Ansible** : configuration management
- **Kubernetes** : alternative à ECS pour orchestration

---

**Fin du Guide Pratique : Déploiement et CI/CD**

Pour toute question, consulter :
- **DevOps Team** : déploiement production, infrastructure
- **GitHub Actions** : logs CI/CD, debugging pipelines
- **AWS Support** : incidents production, scaling
