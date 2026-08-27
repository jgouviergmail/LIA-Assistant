# Guide de Développement - LIA

> Guide complet du workflow de développement : environnement, Git, tests, CI/CD, et bonnes pratiques

**Version**: 2.0
**Date**: 2026-02-03
**Compatibilité**: LIA v6.0.x

## 📋 Table des Matières

- [Environnement de Développement](#-environnement-de-développement)
- [Workflow Git](#-workflow-git)
- [Standards de Code](#-standards-de-code)
- [Tests](#-tests)
- [Pre-commit Hook](#-pre-commit-hook)
- [CI/CD Pipeline](#-cicd-pipeline)
- [Debugging](#-debugging)
- [Performance Profiling](#-performance-profiling)
- [Documentation](#-documentation)
- [Code Review](#-code-review)

---

## 💻 Environnement de Développement

### Setup Initial

**Prérequis** :
- Python 3.14
- Node.js 24+
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
python -m venv .venv
source .venv/bin/activate    # Windows : .venv/Scripts/activate

# Installer les dépendances depuis le lockfile compilé (runtime + dev)
pip install --require-hashes -r requirements-dev.lock.txt

# Vérifier installation
python --version  # 3.12+
pip list | grep fastapi
pip list | grep langgraph
pip list | grep pytest
```

> Équivalent une commande : `task setup:backend` (depuis la racine du monorepo).
> `pyproject.toml` ne contient **pas** de dépendances — il ne sert qu'à la
> configuration des outils (black, ruff, mypy, pytest).

### Gestion des Dépendances Python (lockfiles)

Quatre fichiers dans `apps/api/`, deux rôles distincts :

| Fichier | Rôle |
|---------|------|
| `requirements.txt` | **Manifeste** d'intention runtime (pins souples `>=` autorisés) |
| `requirements-dev.txt` | **Manifeste** dev (inclut `-r requirements.txt`) |
| `requirements.lock.txt` | **Lockfile** compilé — installé par `Dockerfile.prod` (pip) |
| `requirements-dev.lock.txt` | **Lockfile** compilé — installé par `Dockerfile.dev`, la CI et le venv |

Les lockfiles sont générés par `uv pip compile --universal` : un seul fichier
multi-plateforme (linux/amd64, linux/arm64, Windows, Python ≥ 3.12) avec
markers d'environnement et hashes SHA256, installable par pip vanilla.
On ne les édite **jamais à la main**.

**Process de bump d'une dépendance** :

```bash
# 1. Modifier le pin dans le manifeste (requirements.txt ou requirements-dev.txt)
# 2. Régénérer les lockfiles (stable : ne bumpe QUE ce que le manifeste impose)
task deps:lock

# Bump ciblé d'un paquet (dans les bornes du manifeste) sans toucher au manifeste :
task deps:upgrade -- pillow mcp

# Bump global de tous les paquets (à réserver aux mises à jour planifiées) :
task deps:upgrade:all

# 3. Réinstaller le venv local puis lancer les tests
pip install --require-hashes -r apps/api/requirements-dev.lock.txt
task test:backend:unit:fast

# 4. Committer manifeste ET lockfiles ensemble
```

Le job CI `code-hygiene` appelle `task lint:lockfiles`
(`scripts/check_requirements_lock.py`) et échoue si un manifeste a changé sans
régénération des lockfiles (pin absent, pin non satisfait, ou lock dev
désynchronisé du lock runtime). Jouable en local avec la même commande.
Décision et détails : `docs/architecture/ADR-112-Python-Dependency-Locking.md`.

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

**Scripts `apps/web/package.json`** — passer par les tâches plutôt que par
`pnpm` directement : elles neutralisent `NEXT_PUBLIC_API_URL`, que le
`dotenv: - .env` global du Taskfile injecterait sinon et qui change la
couverture de branches mesurée.

| Script | Rôle | Tâche équivalente |
|---|---|---|
| `lint` | ESLint sur `src` | `task lint:frontend` (+ les 3 ratchets + `type-check`) |
| `a11y:ratchet` / `react-hooks:ratchet` / `cc:ratchet` | Ratchets shrink-only | incluses dans `task lint:frontend` |
| `type-check` | `tsc --noEmit --incremental false` | incluse dans `task lint:frontend` |
| `test` / `test:watch` / `test:coverage` | Vitest | `task test:frontend` / `task test:frontend:coverage` |
| `format` | Prettier sur `src` | `task format:frontend` |
| `dev` / `build` / `start` | Next.js | `task dev:web` |

Le `type-check` est **non incrémental** délibérément : `tsconfig.json` pose
`"incremental": true` et `*.tsbuildinfo` est git-ignoré, donc un run local sur
cache pourrait passer là où le runner, à froid, échoue.

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
# (DATABASE_URL_SYNC ne se definit PAS : c'est une propriete calculee de
#  Settings, derivee de DATABASE_URL, utilisee par alembic/env.py)

# Redis (local Docker)
REDIS_URL=redis://localhost:6379/0

# LLM (vos clés de dev)
# Les clés des providers de chat (Anthropic, DeepSeek, Qwen) se saisissent dans
# l'admin LLM, pas ici : la table chiffrée `provider_api_keys` est la source de
# vérité depuis la migration `migrate_env_keys_to_db`.
OPENAI_API_KEY=sk-proj-...

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
# (pas de NEXT_PUBLIC_DEFAULT_LOCALE : la langue par defaut vient du routage
#  [lng] et des locales sous apps/web/locales/, pas d'une variable)
```

---

## 🌿 Workflow Git

### Branching Strategy

**Branche principale** :
- `main` — seule branche longue durée. Il n'y a **pas** de branche `develop`
  (vérifié : `git branch -a` n'en liste aucune, et `ci.yml` ne se déclenche que
  sur `main`). Tout part de `main` et y revient.

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

git add apps/api/tests/unit/domains/agents/tools/test_emails_tools.py
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

#### Dates & heures (doctrine timezone-aware)

Toutes les datetimes sont **timezone-aware**. `datetime.utcnow()`, `datetime.now()` sans
argument tz et `date.today()` sont interdits dans `src/` : un garde AST en CI
(`apps/api/tests/unit/test_no_hardcoded_timezone_guard.py`) fait échouer le build sur
chaque occurrence — ainsi que sur tout littéral `"Europe/Paris"` en dur (le fuseau
d'affichage vient des préférences utilisateur, à défaut `DEFAULT_USER_DISPLAY_TIMEZONE`).

```python
from datetime import UTC, datetime

from src.core.time_utils import now_in_timezone

# ✅ Timestamps techniques (clés de cache, TTL, comparaisons) : UTC
now = datetime.now(UTC)

# ✅ Tout ce qui est affiché ou énoncé à l'utilisateur : SON timezone
local_now = now_in_timezone(user_timezone)  # None → DEFAULT_USER_DISPLAY_TIMEZONE

# ✅ Date « du jour » : toujours dérivée d'une datetime aware
today = now_in_timezone(user_timezone).date()

# ❌ INTERDITS (le garde CI casse le build)
# datetime.utcnow() / datetime.now() / date.today() / default="Europe/Paris"
```

`src/core/time_utils.py` est la source unique de vérité (parsing, conversion,
formatage localisé 6 langues) — lire sa docstring de module avant tout nouveau code
manipulant des dates.

#### Exceptions avalées (doctrine `contextlib.suppress`)

Un handler `except` dont le corps est un simple `pass` est interdit dans `src/` : un
garde AST en CI (`apps/api/tests/unit/test_no_empty_except_guard.py`) fait échouer le
build sur chaque occurrence (193 sites purgés en v1.21.24, classe CodeQL
`py/empty-except` fermée).

```python
from contextlib import suppress

# ✅ Avalement best-effort intentionnel (métriques, invalidation de cache, teardown)
# metrics must never break the request path
with suppress(Exception):
    my_counter.labels(kind=kind).inc()

# ✅ Multi-handler : suppress() IMBRIQUÉ dans le try — même ordre de capture
try:
    with suppress(asyncio.CancelledError):
        await task
except Exception as exc:
    logger.debug("teardown_failed", error=str(exc))

# ❌ INTERDITS (le garde CI casse le build)
# try: ...           # noqa / pragma ne changent rien : l'AST ne voit
# except Exception:  # que les statements — le commentaire de justification
#     pass           # se place AU-DESSUS du bloc suppress()
```

Si le silence masque un vrai signal, ce n'est ni `pass` ni `suppress` : c'est un
`logger.debug(...)` avec contexte. Exemples canoniques :
`infrastructure/database/session.py` (métriques), `agents/api/sse_keepalive.py`
(teardown multi-handler).

#### Variables locales potentiellement non liées

**Une variable se déclare au niveau où elle est LUE**, pas dans la branche qui la
calcule. Deux `UnboundLocalError` de cette classe ont été trouvés dans `src/` :

```python
# ❌ Déclarée dans une branche, lue plus haut : une réponse vide saute le `elif`
#    (il n'y a pas de `else`) et la lecture lève UnboundLocalError
if hitl_interrupt:
    ...
elif response_content.strip():
    card_url: str | None = None      # ← trop profond
    ...
if not hitl_interrupt:
    if card_url:                     # ← UnboundLocalError

# ✅ Déclarée au niveau de lecture, à côté de ses pairs
card_url: str | None = None
```

Le cas le plus vicieux est le **handler qui lit une variable assignée par son propre
`try`** : si l'affectation est la première instruction du bloc, l'exception survient
avant, et `except (ValueError, RuntimeError)` **n'attrape pas `NameError`** — le chemin
de secours plante la requête qu'il devait sauver. C'est ce qui s'était produit dans le
fallback HITL de `streaming/service.py`.

**Outillage.** MyPy et Ruff ne voient pas cette classe (vérifié en retirant un correctif :
les deux restent muets). Deux détecteurs fonctionnent :

- **CodeQL** (`py/uninitialized-local-variable`) — en CI, mais il a manqué le cas HITL ;
- **pyright** (`reportPossiblyUnboundVariable`) — non intégré à la CI, à lancer
  ponctuellement : `npx pyright@latest src/`.

Le scan produit surtout des faux positifs, à trier à la main : imports locaux dans un
`try/except ImportError` gardés par un flag, boucles `for … in range(N)` non vides,
corrélations de gardes (`if cond:` deux fois de suite), affectation en première
instruction d'un `try` dont le handler ne peut être atteint qu'après elle. **Avant de
corriger un signalement, vérifier qu'il est atteignable** — un `walrus` dans une
expression conditionnelle est signalé alors que Python évalue bien la condition d'abord.

#### Taille des fichiers (doctrine ratchet)

**Un fichier logique ne grossit plus : on extrait.** Un garde CI
(`apps/api/tests/unit/test_file_size_ratchet_guard.py`) fait échouer le build dès qu'un
fichier de `src/` dépasse son plafond de SLOC logiques (tokenize + AST, hors
docstrings/commentaires/lignes vides — la sémantique de `scripts/audit/measure_sloc.py`,
partagée avec le protocole d'audit ; l'instrument jumeau pour la complexité cyclomatique
par fonction est `scripts/audit/measure_cc.py`, utile pour cibler puis valider une
décomposition — non câblé en CI) :

- **600 SLOC logiques** pour tout fichier, y compris tout nouveau fichier ;
- les fichiers historiques au-dessus sont **gelés** à leur taille auditée +2 % dans
  `apps/api/tests/unit/file_size_baseline.json` — ils peuvent décroître, jamais croître ;
- les modules de données (`core/i18n_*`, `core/config/`, `core/constants`,
  `domains/llm_config/constants`) sont exemptés : données déclaratives à complexité
  ~nulle, dont le levier de remédiation est un changement de format, pas une
  décomposition (mêmes exemptions que le scoring « god file » de l'audit).

```bash
# ✅ Après avoir fait maigrir un fichier gelé : abaisser son plafond
task ratchet:update   # ne peut QUE baisser les plafonds (et purger les entrées mortes)

# ❌ INTERDITS (le garde CI casse le build)
# gonfler un fichier gelé « parce que la feature va là » → extraire un module cohérent
# monter un plafond dans file_size_baseline.json sans justification explicite en PR
```

Contexte : l'audit 2026-07 a mesuré 41 fichiers ≥ 800 SLOC concentrant 27 % du code
backend, et ADR-117 a fait grossir `stream_chat` de 335 → 412 SLOC sans rencontrer
d'obstacle. Le ratchet est le mécanisme qui a déjà inversé ce type de dérive ici
(couverture backend 43 → 45, seuils vitest verrouillés à 100 % sur les machines à
états) — il s'applique désormais à la taille des fichiers.

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
├── unit/                        # Tests unitaires (rapides, sans DB réelle)
│   ├── test_auth_service.py
│   ├── test_session_store.py
│   └── test_config.py
├── integration/                 # Tests intégration (DB réelle, Redis)
│   ├── test_auth.py
│   ├── test_pricing_service.py
│   └── test_conversations.py
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
# apps/api/tests/agents/test_message_windowing.py

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
# exemple de test d'intégration (fichier illustratif)

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
from httpx import ASGITransport, AsyncClient

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

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
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

## 🪝 Pre-commit Hook

Le projet n'utilise **pas** le framework [pre-commit](https://pre-commit.com/) :
il n'y a pas de `.pre-commit-config.yaml`. Le hook est un script shell versionné
dans le dépôt, activé en pointant `core.hooksPath` vers `.github/hooks/`.

### Installation

```bash
task setup:hooks    # git config core.hooksPath .github/hooks
```

Vérifier : `git config core.hooksPath` doit répondre `.github/hooks`.

### Ce que le hook exécute

**Fichier** : `.github/hooks/pre-commit`

Il ne travaille que sur les fichiers **stagés** et s'adapte à leur type — un
commit qui ne touche que des `.md` ne déclenche ni pytest ni tsc. Détail complet
des étapes et de leur caractère bloquant : [CI_CD.md](../technical/CI_CD.md).

| Déclencheur | Étapes |
|---|---|
| Toujours | `.bak`, secrets (grep), infos d'infrastructure/personnelles réelles |
| `.py` stagés | Ruff, Black, MyPy, tests unitaires rapides, patterns critiques, complétude `.env.example` |
| `locales/` stagés | Parité stricte des clés i18n |
| `alembic/versions/` stagés | Conflits de préfixe de date entre migrations |
| `.ts`/`.tsx` stagés | ESLint, `tsc --noEmit` |

Le hook détecte Windows (Git Bash) et adapte les chemins de binaires :
`.venv/Scripts/` d'un côté, `.venv/bin/` de l'autre.

### Ses limites, et le gate qui les couvre

Le hook vise ~5 minutes. Il saute donc délibérément les ratchets, le gate de
markers, les tests de déploiement et les seuils de couverture frontend — tous
ont déjà fait rougir un build après un commit vert. Avant un push :

```bash
task ci:fast    # ~10 min, tous les gates CI ne nécessitant aucun service
```

### Bypass

```bash
git commit --no-verify    # urgences uniquement
```

`--no-verify` est **interdit** par les règles du projet : corriger la cause, pas
la contourner. La CI rattrape de toute façon, plus tard et plus cher.

---

## 🔄 CI/CD Pipeline

**Documentation complète** : [CI_CD.md](../technical/CI_CD.md) — c'est la source
de vérité pour les workflows, les jobs et leurs dépendances.

Ce guide ne recopie volontairement **pas** le contenu de
`.github/workflows/ci.yml`. Une copie de workflow dans un guide est une seconde
implémentation libre de dériver : celle qui vivait ici annonçait encore des
branches `develop`, des actions non épinglées et un `ruff check src` sans
`tests/`, aucun de ces points n'étant vrai depuis longtemps.

### Le principe à retenir (ADR-151)

**Le workflow orchestre, le Taskfile implémente.** Chaque étape `run:` de
`ci.yml` est un appel `task <nom>` ; la logique vit dans `Taskfile.yml`. La CI
exécute donc littéralement la commande que vous lancez en local.

Conséquence pratique quand un job est rouge : lire l'appel `task ...` de l'étape
concernée et le rejouer tel quel. Il n'y a aucune traduction à faire.

Conséquence quand vous **ajoutez** un gate : il va dans une tâche, pas dans le
YAML. `task lint:ci-parity` échoue sur toute étape `run:` qui n'est ni un appel
de tâche, ni un provisionnement de runner déclaré, ni une exception motivée par
écrit dans `CI_ONLY` (`scripts/audit/check_ci_parity.py`).

### Les trois filets

```bash
task pre-commit    # ~5 min — ce que le hook git exécute
task ci:fast       # ~10 min — tous les gates CI sans service externe (avant un push)
task ci            # + PostgreSQL, Redis, Docker, navigateur
```

Le hook est délibérément plus étroit que `ci:fast` : il saute les ratchets, le
gate de markers, les tests de déploiement et les seuils de couverture frontend
pour tenir dans son budget. Chacun de ces gates a déjà fait rougir un build
après un local vert — d'où `ci:fast`.

### Quality Gates

Gates bloquants sur `main` :

- [ ] Toutes les suites passent (unit, agents, intégration, E2E)
- [ ] Couverture backend >= **67 %** (source de vérité : `apps/api/pyproject.toml`)
- [ ] Seuils de couverture frontend par fichier (`apps/web/vitest.config.ts`)
- [ ] Ruff, Black, MyPy strict, ESLint, `tsc --noEmit` non incrémental
- [ ] Ratchets shrink-only : a11y, react-hooks, complexité (front et back), dette MyPy, taille de fichiers
- [ ] Parité stricte des clés i18n sur les 6 langues
- [ ] Hygiène de code, lockfiles Python en phase avec leurs manifestes, parité CI/local
- [ ] Aucun secret détecté (Gitleaks), scans CodeQL / Trivy / pip-audit / pnpm audit
- [ ] Build Docker (API + Web) réussit

Aucun seuil ni baseline ne se relève : la doctrine ratchet est *shrink-only*.

---

## 🐛 Debugging

### Logs Structurés

```python
# apps/api/src/infrastructure/observability/logging.py

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
- **Task** (le lanceur de tous les gates) : https://taskfile.dev/

---

**GUIDE_DEVELOPPEMENT.md** - Version 1.1 - 2025-12-27

*Workflow de Développement LIA*
