# Guide de Développement - LIA

> Guide complet du workflow de développement : environnement, Git, tests, CI/CD, et bonnes pratiques

**Version**: 2.0
**Date**: 2026-02-03
**Compatibilité**: LIA v6.0.x

## 📋 Table des Matières

- [Environnement de Développement](#environnement-de-développement)
- [Workflow Git](#workflow-git)
- [Standards de Code](#standards-de-code)
- [Tests](#tests)
- [Pre-commit Hooks](#pre-commit-hooks)
- [CI/CD Pipeline](#cicd-pipeline)
- [Debugging](#debugging)
- [Performance Profiling](#performance-profiling)
- [Documentation](#documentation)
- [Code Review](#code-review)

---

## 💻 Environnement de Développement

### Setup Initial

**Prérequis** :
- Python 3.12+
- Node.js 20+
- Docker & Docker Compose
- Git 2.40+
- VS Code (recommandé) ou PyCharm

**Extensions VS Code Recommandées** :
```json
{
  "recommendations": [
    "ms-python.python",
    "ms-python.vscode-pylance",
    "ms-python.black-formatter",
    "charliermarsh.ruff",
    "dbaeumer.vscode-eslint",
    "esbenp.prettier-vscode",
    "bradlc.vscode-tailwindcss",
    "ms-azuretools.vscode-docker",
    "github.copilot"
  ]
}
```

### Configuration Backend

```bash
cd apps/api

# Créer venv
python -m venv venv
source venv/bin/activate

# Installer dependencies + dev tools
pip install -e ".[dev]"

# Vérifier installation
python --version  # 3.12+
pip list | grep fastapi
pip list | grep langgraph
pip list | grep pytest
```

**Requirements Structure** :
```toml
# pyproject.toml

[project]
name = "lia-api"
version = "6.0.0"
requires-python = ">=3.12"

dependencies = [
    "fastapi==0.135.1",
    "langgraph==1.0.10",
    "langchain==1.2.10",
    "langchain-core==1.2.17",
    "sqlalchemy[asyncio]==2.0.40",
    "pydantic==2.10.0",
    "redis==5.3.0",
    # ... autres dependencies (voir pyproject.toml pour liste complète)
]

[project.optional-dependencies]
dev = [
    "pytest==8.3.0",
    "pytest-asyncio==0.24.0",
    "pytest-cov==5.0.0",
    "ruff==0.9.0",
    "black==25.1.0",
    "mypy==1.14.0",
    "pre-commit==4.0.0",
    "httpx",
]
```

### Configuration Frontend

```bash
cd apps/web

# Installer dependencies
pnpm install

# Vérifier installation
node --version  # 20+
pnpm list next
pnpm list react
```

**package.json Scripts** :
```json
{
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "eslint src",
    "type-check": "tsc --noEmit",
    "test": "vitest",
    "test:ui": "vitest --ui",
    "format": "prettier --write \"**/*.{ts,tsx,js,jsx,json,css,md}\""
  }
}
```

### Configuration IDE

#### VS Code settings.json

```json
{
  // Python
  "python.defaultInterpreterPath": "${workspaceFolder}/apps/api/venv/bin/python",
  "python.linting.enabled": true,
  "python.linting.ruffEnabled": true,
  "python.formatting.provider": "black",
  "python.formatting.blackPath": "${workspaceFolder}/apps/api/venv/bin/black",
  "python.testing.pytestEnabled": true,
  "python.testing.unittestEnabled": false,

  // Format on save
  "editor.formatOnSave": true,
  "editor.codeActionsOnSave": {
    "source.organizeImports": "explicit",
    "source.fixAll": "explicit"
  },

  // TypeScript/JavaScript
  "typescript.tsdk": "node_modules/typescript/lib",
  "javascript.updateImportsOnFileMove.enabled": "always",
  "typescript.updateImportsOnFileMove.enabled": "always",

  // Tailwind
  "tailwindCSS.experimental.classRegex": [
    ["cva\\(([^)]*)\\)", "[\"'`]([^\"'`]*).*?[\"'`]"],
    ["cx\\(([^)]*)\\)", "(?:'|\"|`)([^']*)(?:'|\"|`)"]
  ],

  // Files
  "files.exclude": {
    "**/__pycache__": true,
    "**/*.pyc": true,
    "**/node_modules": true,
    "**/.next": true
  },

  // Git
  "git.enableSmartCommit": true,
  "git.confirmSync": false,
  "git.autofetch": true
}
```

### Variables d'Environnement

**Backend .env** :
```bash
# Development-specific
ENVIRONMENT=development
DEBUG=true
LOG_LEVEL=DEBUG

# Database (local Docker)
DATABASE_URL=postgresql+asyncpg://lia:lia@localhost:5432/lia
DATABASE_URL_SYNC=postgresql+psycopg2://lia:lia@localhost:5432/lia

# Redis (local Docker)
REDIS_URL=redis://localhost:6379/0

# LLM (vos clés de dev)
OPENAI_API_KEY=sk-proj-...
ANTHROPIC_API_KEY=sk-ant-...

# OAuth (credentials de dev)
GOOGLE_CLIENT_ID=...apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=http://localhost:8000/api/v1/connectors/google/callback

# Security (générer pour dev)
FERNET_KEY=...
SECRET_KEY=...

# Observability (optionnel en dev)
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com

# Frontend URL (pour CORS)
CORS_ORIGINS=http://localhost:3000,http://localhost:3001
```

**Frontend .env.local** :
```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_DEFAULT_LOCALE=fr
```

---

## 🌿 Workflow Git

### Branching Strategy

**Main Branches** :
- `main` - Production-ready code
- `develop` - Integration branch (si utilisé)

**Feature Branches** :
```bash
# Pattern: feature/description-courte
git checkout -b feature/add-weather-agent
git checkout -b fix/router-confidence-bug
git checkout -b refactor/extract-hitl-service
git checkout -b docs/update-architecture
```

### Conventional Commits

**Format** : `<type>(<scope>): <description>`

**Types** :
- `feat` - Nouvelle fonctionnalité
- `fix` - Bug fix
- `refactor` - Refactoring (pas de changement fonctionnel)
- `docs` - Documentation uniquement
- `test` - Ajout/modification de tests
- `chore` - Maintenance (dependencies, config)
- `perf` - Performance improvement
- `style` - Formatting, missing semi-colons, etc.

**Examples** :
```bash
feat(agents): add weather agent with OpenWeatherMap integration
fix(router): correct confidence threshold fallback logic
refactor(hitl): extract question generator to separate service
docs(architecture): update LangGraph flow diagram
test(tools): add unit tests for search_contacts_tool
chore(deps): upgrade LangGraph to 1.0.2
perf(planner): reduce prompt size by 70% with v2 optimization
```

### Workflow Complet

```bash
# 1. Sync avec main
git checkout main
git pull origin main

# 2. Créer feature branch
git checkout -b feature/add-email-support

# 3. Développer avec commits atomiques
git add apps/api/src/domains/agents/tools/emails_tools.py
git commit -m "feat(tools): add send_email_tool implementation"

git add apps/api/src/domains/agents/tools/emails_tools.py
git commit -m "feat(tools): add get_email_tool implementation"

git add apps/api/tests/agents/tools/test_emails_tools.py
git commit -m "test(tools): add tests for Emails tools"

# 4. Push feature branch
git push origin feature/add-email-support

# 5. Créer Pull Request sur GitHub
# Via interface GitHub ou gh CLI:
gh pr create --title "feat: Add Gmail email support" --body "..."

# 6. Après review et CI/CD success
# Merge via GitHub (Squash and merge)

# 7. Cleanup local
git checkout main
git pull origin main
git branch -d feature/add-email-support
```

### Pre-Push Checklist

Avant chaque `git push` :

- [ ] Tests passent : `pytest apps/api/tests`
- [ ] Linting pass : `ruff check apps/api/src`
- [ ] Formatting : `black apps/api/src`
- [ ] Type checking : `mypy apps/api/src`
- [ ] Pre-commit hooks passent
- [ ] Commit message suit conventions
- [ ] Pas de secrets dans le code
- [ ] Documentation à jour si API change

---

## 📏 Standards de Code

### Python (Backend)

#### Style Guide

**Base** : PEP 8 + Black formatting

**Naming Conventions** :
```python
# Modules : lowercase_with_underscores
# my_module.py

# Classes : PascalCase
class UserRepository:
    pass

# Functions/methods : snake_case
def get_user_by_id(user_id: UUID):
    pass

# Constants : UPPER_CASE_WITH_UNDERSCORES
MAX_RETRIES = 3
DEFAULT_TIMEOUT = 30

# Private : _leading_underscore
def _internal_helper():
    pass

# Type vars : PascalCase
ModelType = TypeVar("ModelType")
```

#### Type Hints (Obligatoire)

```python
# ✅ GOOD: Type hints complets
async def get_user_by_id(
    user_id: UUID,
    session: AsyncSession
) -> User | None:
    """Get user by ID."""
    result = await session.execute(
        select(User).where(User.id == user_id)
    )
    return result.scalars().first()

# ❌ BAD: Pas de type hints
async def get_user_by_id(user_id, session):
    result = await session.execute(...)
    return result.scalars().first()
```

#### Docstrings (Google Style)

```python
def process_message(
    conversation_id: UUID,
    message: str,
    user_id: UUID,
    max_tokens: int = 1000
) -> dict:
    """
    Process user message through LangGraph.

    Args:
        conversation_id: Conversation UUID for checkpoint loading
        message: User message text
        user_id: User UUID for permissions
        max_tokens: Maximum tokens for response (default: 1000)

    Returns:
        Dictionary containing:
            - response: Generated response text
            - tokens_used: Token count
            - cost_usd: Estimated cost

    Raises:
        ConversationNotFoundError: If conversation doesn't exist
        PermissionDeniedError: If user doesn't own conversation
        RateLimitExceededError: If user exceeded rate limit

    Example:
        >>> result = await process_message(
        ...     conversation_id=uuid4(),
        ...     message="Hello",
        ...     user_id=uuid4()
        ... )
        >>> print(result["response"])
        "Bonjour! Comment puis-je t'aider?"
    """
    pass
```

#### Error Handling

```python
# ✅ GOOD: Specific exceptions, logged
try:
    user = await uow.users.get_by_id(user_id)
    if not user:
        raise UserNotFoundError(f"User {user_id} not found")

    result = await process(user)
    return result

except UserNotFoundError as e:
    logger.warning("user_not_found", user_id=user_id)
    raise  # Re-raise pour HTTP 404

except DatabaseError as e:
    logger.error("database_error", error=str(e), exc_info=True)
    raise InternalServerError("Database error occurred")

except Exception as e:
    logger.error("unexpected_error", error=str(e), exc_info=True)
    raise InternalServerError("Unexpected error occurred")

# ❌ BAD: Bare except, no logging
try:
    result = await process(user)
    return result
except:
    return None
```

#### Async Best Practices

```python
# ✅ GOOD: async/await properly used
async def fetch_multiple_contacts(contact_ids: list[str]) -> list[Contact]:
    """Fetch multiple contacts in parallel."""
    tasks = [fetch_contact(cid) for cid in contact_ids]
    contacts = await asyncio.gather(*tasks, return_exceptions=True)
    return [c for c in contacts if not isinstance(c, Exception)]

# ❌ BAD: Sequential when parallel possible
async def fetch_multiple_contacts(contact_ids: list[str]) -> list[Contact]:
    contacts = []
    for cid in contact_ids:
        contact = await fetch_contact(cid)  # Sequential! Slow!
        contacts.append(contact)
    return contacts

# ✅ GOOD: Proper async context manager
async with AsyncSession() as session:
    user = await session.get(User, user_id)
    # Auto-close on exit

# ❌ BAD: Manual session management
session = AsyncSession()
try:
    user = await session.get(User, user_id)
finally:
    await session.close()
```

### TypeScript/React (Frontend)

#### Naming Conventions

```typescript
// Components : PascalCase
function ChatMessage() {}

// Hooks : camelCase avec "use" prefix
function useChat() {}

// Types/Interfaces : PascalCase
interface User {}
type ChatState = {}

// Constants : UPPER_CASE
const MAX_MESSAGE_LENGTH = 5000

// Functions/variables : camelCase
const fetchMessages = async () => {}
const userMessages = []
```

#### Component Structure

```typescript
// ✅ GOOD: Typed props, proper exports
import { FC } from 'react'

interface ChatMessageProps {
  message: Message
  isStreaming?: boolean
  onRetry?: () => void
}

export const ChatMessage: FC<ChatMessageProps> = ({
  message,
  isStreaming = false,
  onRetry
}) => {
  // Component logic
  return (
    <div className="message">
      {/* JSX */}
    </div>
  )
}

// ❌ BAD: Any types, no interface
export function ChatMessage({ message, isStreaming, onRetry }: any) {
  return <div>{/* JSX */}</div>
}
```

---

## 🧪 Tests

### Structure Tests

```
apps/api/tests/
├── conftest.py                  # Fixtures globales
├── unit/                        # Tests unitaires (rapides)
│   ├── test_auth_service.py
│   ├── test_pricing_service.py
│   └── test_message_windowing.py
├── integration/                 # Tests intégration (DB, Redis)
│   ├── test_auth_flow.py
│   ├── test_oauth_callback.py
│   └── test_conversation_persistence.py
├── agents/                      # Tests agents/tools
│   ├── tools/
│   │   └── test_google_contacts_tools.py
│   ├── nodes/
│   │   └── test_router_node_v3.py
│   └── integration/
│       └── test_hitl_streaming_e2e.py
└── e2e/                         # Tests end-to-end
    └── test_complete_conversation_flow.py
```

### Pyramid de Tests

```
        /\
       /  \  E2E (2%)
      /____\
     /      \  Integration (12%)
    /________\
   /          \  Unit (86%)
  /__________  \
```

### Écrire un Test Unitaire

```python
# apps/api/tests/unit/test_message_windowing.py

import pytest
from domains.agents.utils.message_windowing import (
    get_windowed_messages,
    filter_conversational_messages
)
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

def test_get_windowed_messages_basic():
    """Test basic windowing avec 5 turns."""
    # Arrange
    messages = [
        SystemMessage(content="System prompt"),
        HumanMessage(content="Message 1"),
        AIMessage(content="Response 1"),
        HumanMessage(content="Message 2"),
        AIMessage(content="Response 2"),
        # ... 10 more turns
        HumanMessage(content="Message 10"),
        AIMessage(content="Response 10"),
    ]

    # Act
    windowed = get_windowed_messages(messages, window_size=5)

    # Assert
    assert len(windowed) == 11  # 1 system + 5 turns × 2 = 11
    assert isinstance(windowed[0], SystemMessage)
    assert windowed[0].content == "System prompt"

    # Check only last 5 turns present
    human_messages = [m for m in windowed if isinstance(m, HumanMessage)]
    assert len(human_messages) == 5
    assert "Message 6" in human_messages[0].content

@pytest.mark.parametrize("window_size,expected_count", [
    (1, 3),   # 1 system + 1 turn × 2
    (3, 7),   # 1 system + 3 turns × 2
    (5, 11),  # 1 system + 5 turns × 2
    (10, 21), # 1 system + 10 turns × 2
])
def test_get_windowed_messages_parametrized(window_size, expected_count):
    """Test windowing avec différentes tailles."""
    messages = [SystemMessage(content="System")]
    for i in range(15):  # 15 turns
        messages.append(HumanMessage(content=f"H{i}"))
        messages.append(AIMessage(content=f"A{i}"))

    windowed = get_windowed_messages(messages, window_size=window_size)

    assert len(windowed) == expected_count
```

### Écrire un Test d'Intégration

```python
# apps/api/tests/integration/test_oauth_callback.py

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

@pytest.mark.integration
@pytest.mark.asyncio
async def test_google_oauth_callback_success(
    async_client: AsyncClient,
    async_session: AsyncSession,
    test_user,
    mock_google_oauth_server
):
    """Test OAuth callback flow complet."""
    # Arrange: Initiate OAuth flow
    response = await async_client.get(
        "/api/v1/connectors/google/initiate",
        params={"connector_type": "contacts"}
    )
    assert response.status_code == 200

    auth_url = response.json()["authorization_url"]
    state = extract_state_from_url(auth_url)

    # Act: Simulate Google callback
    callback_response = await async_client.get(
        "/api/v1/connectors/google/callback",
        params={
            "code": "mock_auth_code",
            "state": state
        }
    )

    # Assert: Connector created
    assert callback_response.status_code == 200

    # Check DB
    from domains.connectors.models import Connector
    connector = await async_session.execute(
        select(Connector).where(
            Connector.user_id == test_user.id,
            Connector.connector_type == "GOOGLE_CONTACTS"
        )
    )
    connector = connector.scalars().first()

    assert connector is not None
    assert connector.is_active
    assert connector.credentials_encrypted is not None
```

### Fixtures Réutilisables

```python
# apps/api/tests/conftest.py

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from httpx import AsyncClient

@pytest.fixture
async def async_session():
    """Provide async session with rollback."""
    engine = create_async_engine(test_database_url)

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Provide session
    async with AsyncSession(engine) as session:
        yield session
        await session.rollback()

    # Cleanup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest.fixture
async def async_client(async_session):
    """Provide HTTP client with dependency overrides."""
    from main import app

    # Override get_session dependency
    app.dependency_overrides[get_session] = lambda: async_session

    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()

@pytest.fixture
def test_user(async_session):
    """Provide test user."""
    user = User(
        email="test@example.com",
        hashed_password=hash_password("password123"),
        is_active=True
    )
    async_session.add(user)
    await async_session.flush()
    await async_session.refresh(user)
    return user
```

### Lancer les Tests

```bash
# Tous les tests
pytest

# Tests unitaires uniquement
pytest tests/unit -v

# Tests avec coverage
pytest --cov=src --cov-report=html --cov-report=term

# Tests d'un fichier spécifique
pytest tests/unit/test_message_windowing.py -v

# Test d'une fonction spécifique
pytest tests/unit/test_message_windowing.py::test_get_windowed_messages_basic -v

# Tests avec output détaillé
pytest -vv -s

# Tests en parallèle (plus rapide)
pytest -n auto

# Tests avec markers
pytest -m integration  # Seulement integration tests
pytest -m "not slow"   # Skip slow tests
```

### Coverage Target

**Minimum** : 30% (CI gate)
**Objectif** : 85%
**Priorité** :
1. Business logic (services) : 90%+
2. API routes : 80%+
3. Utils : 85%+
4. Models : 60%+ (generated code)

---

## 🪝 Pre-commit Hooks

### Configuration

**Fichier** : `.pre-commit-config.yaml`

```yaml
repos:
  # Ruff (linting + formatting)
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.5.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  # Black (formatting backup)
  - repo: https://github.com/psf/black
    rev: 24.0.0
    hooks:
      - id: black
        language_version: python3.12

  # MyPy (type checking)
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.10.0
    hooks:
      - id: mypy
        additional_dependencies: [types-all]
        args: [--ignore-missing-imports, --check-untyped-defs]

  # Secrets detection
  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.4.0
    hooks:
      - id: detect-secrets
        args: ['--baseline', '.secrets.baseline']

  # General hooks
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
        args: ['--maxkb=500']
      - id: check-merge-conflict
      - id: check-json

  # Frontend (ESLint + Prettier)
  # Note: ESLint 9 with flat config requires local installation
  # Use 'pnpm lint' in apps/web instead of pre-commit ESLint hook
  - repo: local
    hooks:
      - id: eslint
        name: ESLint (Next.js)
        entry: bash -c 'cd apps/web && pnpm lint'
        language: system
        files: \.(js|jsx|ts|tsx)$
        pass_filenames: false

  - repo: https://github.com/pre-commit/mirrors-prettier
    rev: v4.0.0-alpha.8
    hooks:
      - id: prettier
        files: \.(js|jsx|ts|tsx|json|css|md)$
```

### Installation

```bash
cd apps/api

# Installer pre-commit
pip install pre-commit

# Installer hooks
pre-commit install

# Tester sur tous les fichiers
pre-commit run --all-files

# Update hooks to latest versions
pre-commit autoupdate
```

### Bypass (si nécessaire)

```bash
# Skip pre-commit hooks (NE PAS ABUSER!)
git commit -m "message" --no-verify

# Ou skip specific hook
SKIP=mypy git commit -m "message"
```

---

## 🔄 CI/CD Pipeline

### GitHub Actions Workflows

#### ci.yml (Main Pipeline)

```yaml
# .github/workflows/ci.yml

name: CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  lint-backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: |
          cd apps/api
          pip install -e ".[dev]"

      - name: Run Ruff
        run: |
          cd apps/api
          ruff check src

      - name: Run Black
        run: |
          cd apps/api
          black --check src

      - name: Run MyPy
        run: |
          cd apps/api
          mypy src

  test-backend:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: pgvector/pgvector:pg16
        env:
          POSTGRES_USER: lia
          POSTGRES_PASSWORD: lia
          POSTGRES_DB: lia_test
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432

      redis:
        image: redis:7-alpine
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 6379:6379

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: |
          cd apps/api
          pip install -e ".[dev]"

      - name: Run tests with coverage
        env:
          DATABASE_URL: postgresql+asyncpg://lia:lia@localhost:5432/lia_test
          REDIS_URL: redis://localhost:6379/0
        run: |
          cd apps/api
          pytest --cov=src --cov-report=xml --cov-report=term

      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v4
        with:
          file: ./apps/api/coverage.xml
          fail_ci_if_error: true

  lint-frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'

      - name: Install pnpm
        uses: pnpm/action-setup@v3
        with:
          version: 8

      - name: Install dependencies
        run: |
          cd apps/web
          pnpm install

      - name: Run ESLint
        run: |
          cd apps/web
          pnpm lint

      - name: Run TypeScript check
        run: |
          cd apps/web
          pnpm type-check

  security-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run pip-audit
        run: |
          cd apps/api
          pip install pip-audit
          pip-audit

      - name: Run Bandit
        run: |
          cd apps/api
          pip install bandit
          bandit -r src

      - name: Run Trivy
        uses: aquasecurity/trivy-action@master
        with:
          scan-type: 'fs'
          scan-ref: '.'
          severity: 'CRITICAL,HIGH'

  build-push:
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    needs: [lint-backend, test-backend, lint-frontend, security-scan]
    steps:
      - uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Login to Docker Hub
        uses: docker/login-action@v3
        with:
          username: ${{ secrets.DOCKER_USERNAME }}
          password: ${{ secrets.DOCKER_PASSWORD }}

      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: ./apps/api
          push: true
          tags: |
            lia/api:latest
            lia/api:${{ github.sha }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

### Quality Gates

**Gates obligatoires** :
- [ ] Tous les tests passent
- [ ] Coverage >= 30%
- [ ] Linting (Ruff/Black) passe
- [ ] Type checking (MyPy) passe
- [ ] Security scan (Bandit/Trivy) passe
- [ ] Pas de secrets détectés
- [ ] Build Docker réussit

---

## 🐛 Debugging

### Logs Structurés

```python
# apps/api/src/infrastructure/observability/logging_config.py

import structlog

logger = structlog.get_logger()

# ✅ GOOD: Logs structurés avec contexte
logger.info(
    "user_message_processed",
    user_id=user_id,
    conversation_id=conversation_id,
    message_length=len(message),
    tokens_used=tokens,
    cost_usd=cost,
    duration_ms=duration
)

# ❌ BAD: Logs non-structurés
logger.info(f"User {user_id} processed message in {duration}ms")
```

### Debug avec VS Code

**launch.json** :
```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "FastAPI Dev Server",
      "type": "python",
      "request": "launch",
      "module": "uvicorn",
      "args": [
        "src.main:app",
        "--reload",
        "--port", "8000",
        "--log-level", "debug"
      ],
      "jinja": true,
      "justMyCode": false,
      "cwd": "${workspaceFolder}/apps/api",
      "env": {
        "PYTHONPATH": "${workspaceFolder}/apps/api"
      }
    },
    {
      "name": "Pytest Current File",
      "type": "python",
      "request": "launch",
      "module": "pytest",
      "args": [
        "${file}",
        "-v",
        "-s"
      ],
      "console": "integratedTerminal",
      "cwd": "${workspaceFolder}/apps/api"
    }
  ]
}
```

### Debug LangGraph

```python
# Activer debug logging pour LangGraph
import logging

logging.basicConfig(level=logging.DEBUG)
logging.getLogger("langgraph").setLevel(logging.DEBUG)

# Ajouter breakpoint
import pdb; pdb.set_trace()

# Ou utiliser VS Code breakpoints
```

### Monitoring Local

```bash
# Lancer Grafana local
docker-compose up -d grafana prometheus

# Accéder Grafana
open http://localhost:3001

# Login: admin/admin

# Importer dashboards
# Navigate to Dashboards > Import
# Sélectionner infrastructure/observability/grafana/dashboards/*.json
```

---

## ⚡ Performance Profiling

### cProfile

```python
# Profile une fonction
import cProfile
import pstats

cProfile.run('my_function()', 'profile_stats')

# Analyser
p = pstats.Stats('profile_stats')
p.sort_stats('cumulative').print_stats(20)
```

### py-spy

```bash
# Install
pip install py-spy

# Profile running process
py-spy top --pid <PID>

# Generate flamegraph
py-spy record -o profile.svg --pid <PID>

# Profile specific command
py-spy record -o profile.svg -- python script.py
```

### Memory Profiling

```python
# memory_profiler
from memory_profiler import profile

@profile
def my_function():
    # Function code
    pass

# Run avec:
# python -m memory_profiler script.py
```

---

## 📝 Documentation

### Docstrings Obligatoires

Pour :
- Toutes les fonctions publiques
- Toutes les classes
- Tous les modules (module-level docstring)

### API Documentation (OpenAPI)

FastAPI génère automatiquement :
- Swagger UI : http://localhost:8000/docs
- ReDoc : http://localhost:8000/redoc
- OpenAPI JSON : http://localhost:8000/openapi.json

**Améliorer docs API** :
```python
@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Process user message",
    description="Process user message through LangGraph multi-agent system",
    responses={
        200: {"description": "Message processed successfully"},
        404: {"description": "Conversation not found"},
        429: {"description": "Rate limit exceeded"},
    },
    tags=["chat"]
)
async def process_message(
    request: ChatRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Process user message with full context.

    Returns streaming SSE events avec:
    - Partial responses
    - Token tracking
    - Cost estimation
    """
    pass
```

---

## 👀 Code Review

### Checklist Reviewer

- [ ] **Fonctionnel** : Code fait ce qu'il doit faire
- [ ] **Tests** : Tests ajoutés/modifiés, passent
- [ ] **Performance** : Pas de régression évidente
- [ ] **Sécurité** : Pas de vulnérabilités introduites
- [ ] **Style** : Suit conventions du projet
- [ ] **Documentation** : API changes documentés
- [ ] **Breaking Changes** : Identifiés et justifiés
- [ ] **Dependencies** : Nouvelles deps justifiées
- [ ] **Logs** : Logs appropriés ajoutés
- [ ] **Error Handling** : Erreurs gérées proprement

### Approuver une PR

```bash
# Via gh CLI
gh pr review <PR_NUMBER> --approve --body "LGTM! Good work on the token optimization."

# Ou via GitHub web interface
```

### Demander des Changes

```bash
gh pr review <PR_NUMBER> --request-changes --body "Please add tests for the new function."
```

---

## 🎓 Ressources

### Documentation Interne
- [GETTING_STARTED.md](../GETTING_STARTED.md)
- [ARCHITECTURE.md](../ARCHITECTURE.md)
- [GUIDE_TESTING.md](./GUIDE_TESTING.md)

### Outils Externes
- **Ruff** : https://docs.astral.sh/ruff/
- **Black** : https://black.readthedocs.io/
- **MyPy** : https://mypy.readthedocs.io/
- **Pytest** : https://docs.pytest.org/
- **Pre-commit** : https://pre-commit.com/

---

**GUIDE_DEVELOPPEMENT.md** - Version 1.1 - 2025-12-27

*Workflow de Développement LIA*
