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
| **API** | FastAPI (Python 3.12) | Horizontal (3+ instances) | ✅ Load balanced |
| **Web** | Next.js 16 | Horizontal (2+ instances) | ✅ Load balanced |
| **Database** | PostgreSQL 16 + pgvector | Vertical + Replicas | ✅ Primary + Replicas |
| **Cache** | Redis 7 | Cluster mode | ✅ Redis Sentinel |
| **Load Balancer** | NGINX / AWS ALB | N/A | ✅ Managed service |
| **Monitoring** | Prometheus + Grafana | N/A | ✅ Persistent storage |

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

# OpenAI
OPENAI_API_KEY=<YOUR_OPENAI_API_KEY>
OPENAI_ORG_ID=<YOUR_OPENAI_ORG_ID>  # Optional

# Anthropic
ANTHROPIC_API_KEY=<YOUR_ANTHROPIC_API_KEY>

# DeepSeek
DEEPSEEK_API_KEY=<YOUR_DEEPSEEK_API_KEY>

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
OTEL_EXPORTER_OTLP_PROTOCOL=grpc
OTEL_SDK_DISABLED=false  # Set to true to disable tracing

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
HITL_ENABLED=true
TOOL_APPROVAL_ENABLED=true

# MCP (Model Context Protocol)
MCP_ENABLED=false                    # Active les serveurs MCP admin
MCP_USER_ENABLED=false               # Active le MCP per-user (requiert MCP_ENABLED=true)
MCP_MAX_TOOLS_PER_SERVER=50          # Limite tools par serveur
MCP_CONNECTION_TIMEOUT=30            # Timeout connexion (secondes)
MCP_APPS_MAX_HTML_SIZE=500000        # Taille max HTML pour MCP Apps (bytes)

# Multi-Channel Messaging (Telegram)
CHANNELS_ENABLED=false               # Active les canaux de messagerie externes
TELEGRAM_BOT_TOKEN=                  # Token du bot Telegram (@BotFather)
TELEGRAM_WEBHOOK_SECRET=             # Secret pour valider les webhooks Telegram

# Heartbeat Autonome (Notifications Proactives)
HEARTBEAT_ENABLED=false              # Active les notifications proactives LLM-driven
HEARTBEAT_INTERVAL_MINUTES=60        # Intervalle entre executions
HEARTBEAT_MAX_PER_DAY=3              # Max notifications par utilisateur par jour
HEARTBEAT_NOTIFY_START_HOUR=8        # Debut plage horaire notifications
HEARTBEAT_NOTIFY_END_HOUR=22         # Fin plage horaire notifications

# Actions Planifiees
SCHEDULED_ACTIONS_ENABLED=false      # Active les actions planifiees recurrentes

# Push Notifications (Firebase)
FCM_NOTIFICATIONS_ENABLED=false      # Active les push notifications Firebase
```

### Configuration Frontend (.env.local)

```bash
# Next.js Environment Variables

# API Backend URL
NEXT_PUBLIC_API_URL=https://api.yourdomain.com

# Application URL
NEXT_PUBLIC_APP_URL=https://app.yourdomain.com

# Environment
NEXT_PUBLIC_ENVIRONMENT=production

# Feature Flags
NEXT_PUBLIC_ANALYTICS_ENABLED=true

# Disable Next.js telemetry
NEXT_TELEMETRY_DISABLED=1
```

### Validation Configuration

**Script de validation** :

```python
# scripts/validate_env.py
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
python scripts/validate_env.py
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
docker-compose exec api python scripts/create_admin.py

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
COPY --from=dependencies /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
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

### Frontend Dockerfile (Next.js 16)

```dockerfile
# apps/web/Dockerfile

# ============================================================================
# Stage 1: Base image with Node.js and pnpm
# ============================================================================
FROM node:20-alpine AS base

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

      - name: Set up Python 3.12
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'

      - name: Install dependencies
        working-directory: ./apps/api
        run: |
          pip install -e ".[dev]"

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

      - name: Set up Python 3.12
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'

      - name: Install dependencies
        working-directory: ./apps/api
        run: pip install -e ".[dev]"

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

---

## Secrets Management

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

**Endpoint /health** :

```python
# apps/api/src/api/health.py
from fastapi import APIRouter, status
from sqlalchemy import text

router = APIRouter()

@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check(db: AsyncSession = Depends(get_db)):
    """
    Health check endpoint.

    Verifies:
    - API is responsive
    - Database connection OK
    - Redis connection OK
    """
    try:
        # Check database
        await db.execute(text("SELECT 1"))

        # Check Redis
        await redis_client.ping()

        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "version": "1.0.0",
        }
    except Exception as e:
        logger.error("health_check_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service unhealthy"
        )
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
# scripts/smoke_test.sh

API_URL="https://api.yourdomain.com"

echo "🔍 Running smoke tests..."

# 1. Health check
echo "Testing /health endpoint..."
curl -f "$API_URL/health" || exit 1

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
2. **Wrong health endpoint** : verify /health returns 200
3. **Database connection fail** : check DATABASE_URL

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
