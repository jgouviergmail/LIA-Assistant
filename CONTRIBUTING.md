# Contributing Guide - LIA

> Complete guide for contributing to the LIA project: code standards, Git workflow, review process, and best practices

**Version**: 2.1
**Date**: 2026-02-04
**Last updated**: Google API Tracking, Consumption Exports, Skills System, FOR_EACH Pattern, Voice HD Mode

---

## Table of Contents

- [Welcome](#-welcome)
- [Code of Conduct](#-code-of-conduct)
- [Technical Prerequisites](#-technical-prerequisites)
- [Environment Setup](#-environment-setup)
- [Development Workflow](#-development-workflow)
- [Code Standards](#-code-standards)
- [Tests](#-tests)
- [Pre-commit Hooks](#-pre-commit-hooks)
- [Review Process](#-review-process)
- [CI/CD Pipeline](#-cicd-pipeline)
- [Documentation](#-documentation)
- [Security](#-security)
- [Communication](#-communication)
- [FAQ](#-faq)
- [Resources](#-resources)

---

## Welcome

Thank you for your interest in contributing to **LIA**! This project is a multi-agent conversational platform built on **LangGraph 1.0**, **FastAPI 0.128**, and **Next.js 16**, with a complete DDD (Domain-Driven Design) architecture.

### Accepted Contribution Types

| Type | Description | GitHub Label |
|------|-------------|--------------|
| Bug fixes | Bug corrections | `bug` |
| Features | New features | `enhancement` |
| Documentation | Documentation improvements | `documentation` |
| Tests | Adding tests | `tests` |
| UI/UX | Interface improvements | `ui/ux` |
| Performance | Optimizations | `performance` |
| Security | Security improvements | `security` |
| i18n | Translations (6 languages) | `i18n` |

### Especially Welcome Contributions

- **Agents**: Creating new agents (business domains)
- **Tools**: Creating new tools for connectors
- **Skills**: Creating Claude skills (`.claude/skills/`)
- **Prompts**: Improving LLM prompts
- **Dashboards**: New Grafana dashboards
- **HITL**: New Human-in-the-Loop strategies
- **Cost Tracking**: New pricing endpoints or consumption metrics

---

## Code of Conduct

This project adheres to the [Contributor Covenant Code of Conduct](./CODE_OF_CONDUCT.md). By participating, you agree to uphold this code.

**Key principles**:

- Respect and kindness toward all contributors
- Constructive and professional feedback
- Focus on what is best for the community
- Empathy toward other members

**Report an issue**: [conduct@lia-assistant.dev](mailto:conduct@lia-assistant.dev)

---

## Technical Prerequisites

### Required Software

| Software | Version | Usage |
|----------|---------|-------|
| **Python** | 3.12+ | Backend (modern type hints) |
| **Node.js** | 20+ | Frontend (LTS) |
| **pnpm** | 10+ | Frontend package manager |
| **Docker** | 24+ | Infrastructure |
| **Docker Compose** | v2+ | Service orchestration |
| **Git** | 2.40+ | Version control |
| **PostgreSQL** | 16+ | Database + pgvector |
| **Redis** | 7+ | Cache + sessions |

### Recommended Software

| Software | Usage |
|----------|-------|
| VS Code | IDE with Python, Ruff, ESLint extensions |
| Taskfile | Automation (`task` CLI) |
| pre-commit | Git hooks (installed automatically) |

### Recommended Technical Knowledge

#### Backend

| Technology | Level |
|------------|-------|
| Python async/await | Required |
| FastAPI + Pydantic v2 | Required |
| SQLAlchemy 2.0 async | Required |
| LangGraph + LangChain | Recommended |
| PostgreSQL + Alembic | Recommended |
| Redis | Recommended |
| Pytest async | Recommended |
| Prometheus + Grafana | Optional |

#### Frontend

| Technology | Level |
|------------|-------|
| React 19+ hooks | Required |
| TypeScript 5+ | Required |
| TailwindCSS 4+ | Required |
| Next.js 16 App Router | Recommended |
| TanStack Query | Recommended |
| SSE Streaming | Optional |

#### Architecture

| Concept | Level |
|---------|-------|
| Domain-Driven Design (DDD) | Recommended |
| CQRS pattern | Optional |
| Multi-agent orchestration | Optional |

---

## Environment Setup

### 1. Fork and Clone

```bash
# Fork the repo on GitHub (via the GitHub UI)

# Clone your fork
git clone https://github.com/YOUR-USERNAME/LIA-Assistant.git
cd LIA-Assistant

# Add the upstream remote
git remote add upstream https://github.com/jgouviergmail/LIA-Assistant.git
git fetch upstream
```

### 2. Backend Setup

```bash
cd apps/api

# Create Python 3.12 virtualenv
python3.12 -m venv .venv

# Activate venv
source .venv/bin/activate  # Linux/macOS
# or
.venv\Scripts\activate     # Windows

# Install dependencies + dev tools
pip install --upgrade pip
pip install -e ".[dev]"

# Verify installation
python --version  # 3.12.x
pip list | grep -E "(fastapi|langgraph|pytest)"
```

### 3. Frontend Setup

```bash
cd apps/web

# Install pnpm if needed
npm install -g pnpm@10

# Install dependencies
pnpm install --frozen-lockfile

# Verify installation
pnpm list | grep -E "(react|typescript)"
```

### 4. Infrastructure Setup

```bash
# Return to root
cd ../..

# Copy configuration
cp .env.example apps/api/.env
cp apps/web/.env.example apps/web/.env

# Start infrastructure
docker-compose up -d postgres redis prometheus grafana

# Verify services
docker-compose ps
```

**Available services**:

| Service | URL |
|---------|-----|
| PostgreSQL | localhost:5432 |
| Redis | localhost:6379 |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3001 (admin/admin) |

### 5. Database Setup

```bash
cd apps/api

# Create tables via Alembic
alembic upgrade head

# Seed data (LLM pricing, currency rates)
python -m src.scripts.seed_llm_pricing
```

### 6. Install Pre-commit Hooks

```bash
# Return to root
cd ../..

# Install pre-commit hooks
pre-commit install

# Test hooks (optional)
pre-commit run --all-files
```

### 7. Verify Installation

```bash
# Test backend
cd apps/api
pytest tests/unit/ -v --tb=short

# Test frontend
cd ../web
pnpm build

# Start services
# Terminal 1 - Backend:
cd apps/api && uvicorn src.main:app --reload --port 8000

# Terminal 2 - Frontend:
cd apps/web && pnpm dev
```

**Development URLs**:

| Service | URL |
|---------|-----|
| API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |
| Frontend | http://localhost:3000 |

---

## Development Workflow

### Standard Git Workflow

```bash
# 1. Sync with upstream
git checkout main
git pull upstream main
git push origin main

# 2. Create a branch
git checkout -b feature/new-feature
# or
git checkout -b fix/fix-bug-xyz

# 3. Develop
# ... code ...

# 4. Commit (pre-commit hooks run automatically)
git add .
git commit -m "feat(agents): add new HITL strategy"

# 5. Push
git push origin feature/new-feature

# 6. Create Pull Request on GitHub
```

### Branch Naming

**Format**: `<type>/<short-description>`

| Type | Usage |
|------|-------|
| `feature/` | New feature |
| `fix/` | Bug fix |
| `docs/` | Documentation only |
| `refactor/` | Refactoring without behavior change |
| `perf/` | Performance optimization |
| `test/` | Adding tests |
| `chore/` | Maintenance (deps, config) |

**Examples**:

```
feature/add-weather-agent
fix/oauth-token-refresh-loop
docs/update-hitl-guide
refactor/extract-pricing-service
perf/optimize-planner-retry
test/add-message-windowing-tests
chore/upgrade-langchain
```

### Commit Convention

We follow **Conventional Commits**: `<type>(<scope>): <description>`

#### Commit Types

| Type | Description | Version |
|------|-------------|---------|
| `feat` | New feature | MINOR |
| `fix` | Bug fix | PATCH |
| `docs` | Documentation | - |
| `style` | Formatting | - |
| `refactor` | Refactoring | - |
| `perf` | Performance | - |
| `test` | Tests | - |
| `chore` | Maintenance | - |
| `build` | Build system | - |
| `ci` | CI/CD | - |

#### Scopes (DDD Domains)

| Scope | Domain |
|-------|--------|
| `agents` | LangGraph agents |
| `auth` | Authentication |
| `connectors` | OAuth connectors |
| `conversations` | Conversation management |
| `llm` | LLM providers/pricing |
| `users` | User management |
| `hitl` | Human-in-the-Loop |
| `voice` | Voice/TTS |
| `interests` | Interest Learning |
| `observability` | Metrics/Logs |
| `security` | Security |

#### Examples

```bash
feat(agents): add weather forecast agent with 5-day prediction
fix(auth): resolve session cookie expiration race condition
docs(hitl): update HITL.md with plan-level approval flow
refactor(llm): extract AsyncPricingService into separate module
perf(planner): optimize domain filtering with LRU cache
test(connectors): add OAuth token refresh integration tests
chore(deps): upgrade langchain from 0.3.0 to 0.3.1
```

#### Breaking Changes

```bash
feat(api)!: migrate authentication from JWT to BFF Pattern

BREAKING CHANGE: All clients must now use HTTP-only cookies instead of
JWT tokens in Authorization headers. See MIGRATION.md for upgrade guide.
```

---

## Code Standards

### Backend (Python)

#### Linters & Formatters

| Tool | Role | Configuration |
|------|------|---------------|
| **Ruff** | Ultra-fast linter | `pyproject.toml` |
| **Black** | Formatter | `pyproject.toml` |
| **MyPy** | Type checker (strict) | `pyproject.toml` |

#### Python Conventions

**Mandatory type hints**:

```python
# GOOD
from uuid import UUID
from typing import Sequence

async def get_user_conversations(
    user_id: UUID,
    limit: int = 10,
    offset: int = 0
) -> Sequence[ConversationRead]:
    """Retrieve user conversations with pagination."""
    ...

# BAD
async def get_user_conversations(user_id, limit=10, offset=0):
    ...
```

**Google Style docstrings**:

```python
async def execute_plan_step(
    state: MessagesState,
    step: ExecutionStep,
    config: RunnableConfig
) -> dict[str, Any]:
    """Execute a single step from the execution plan.

    Args:
        state: Current graph state with messages and context
        step: Execution step to run
        config: LangGraph runnable configuration

    Returns:
        dict with execution result:
            - success: bool
            - result: Any
            - metadata: dict

    Raises:
        ToolExecutionError: If tool execution fails
        ValidationError: If step validation fails
    """
    ...
```

**Constants and configuration**:

```python
# GOOD - Constants in src/core/constants.py
from src.core import constants

MAX_RETRIES = constants.PLANNER_MAX_RETRIES  # 3
WINDOW_SIZE_ROUTER = constants.WINDOW_SIZE_ROUTER  # 5

# BAD - Magic numbers
if retry_count > 3:  # What does 3 mean?
    ...
```

**Error handling**:

```python
# GOOD - Specific exceptions
from src.core.exceptions import ToolExecutionError

try:
    result = await execute_tool(tool_name, params)
except httpx.HTTPStatusError as e:
    logger.error("Tool HTTP error", tool=tool_name, status=e.response.status_code)
    raise ToolExecutionError(f"HTTP {e.response.status_code}") from e

# BAD - Silent catch-all
try:
    result = await execute_tool(tool_name, params)
except Exception:
    pass  # Silent fail
```

**Async best practices**:

```python
# GOOD - Gather for parallel operations
import asyncio

results = await asyncio.gather(
    pricing_service.get_model_price(model_a),
    pricing_service.get_model_price(model_b),
    return_exceptions=True
)

# GOOD - Async context manager
async with get_redis_session() as redis:
    await redis.set(key, value, ex=3600)

# BAD - Unnecessary sequential calls
price_a = await pricing_service.get_model_price(model_a)
price_b = await pricing_service.get_model_price(model_b)
```

#### Modular Configuration Architecture (ADR-009)

Configuration is split into **9 thematic modules** in `src/core/config/`:

```python
# Unified import (backward compatible)
from src.core.config import settings

# Direct access (unchanged)
settings.openai_api_key
settings.postgres_url
settings.redis_url

# Internal structure (9 modules via multiple inheritance)
# - security.py      : OAuth, JWT, session cookies
# - database.py      : PostgreSQL, Redis
# - observability.py : OTEL, Prometheus, Langfuse
# - llm.py           : LLM providers configs
# - agents.py        : SSE, HITL, Router, Planner
# - connectors.py    : Google APIs, rate limiting
# - voice.py         : TTS Standard/HD, Voice settings
# - advanced.py      : Pricing, i18n, feature flags
```

### Frontend (TypeScript/React)

#### Linters & Formatters

| Tool | Role |
|------|------|
| **ESLint** | Linter |
| **Prettier** | Formatter |
| **TypeScript** | Type checker |

#### TypeScript/React Conventions

**Type safety**:

```typescript
// GOOD - Explicit types
interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
}

interface ChatProps {
  conversationId: string;
  initialMessages?: Message[];
  onMessageSent?: (message: Message) => void;
}

const Chat: React.FC<ChatProps> = ({ conversationId, initialMessages = [], onMessageSent }) => {
  // ...
};

// BAD - any types
const Chat = ({ conversationId, initialMessages, onMessageSent }: any) => {
  // ...
};
```

**Custom hooks**:

```typescript
// GOOD - Reusable custom hook
interface UseSSEOptions {
  url: string;
  onMessage: (event: MessageEvent) => void;
  onError?: (error: Event) => void;
}

function useSSE({ url, onMessage, onError }: UseSSEOptions) {
  const [isConnected, setIsConnected] = useState(false);

  useEffect(() => {
    const es = new EventSource(url);
    es.onopen = () => setIsConnected(true);
    es.onmessage = onMessage;
    es.onerror = (error) => {
      setIsConnected(false);
      onError?.(error);
    };
    return () => es.close();
  }, [url, onMessage, onError]);

  return { isConnected };
}
```

---

## Tests

### Testing Strategy (Test Pyramid)

```
      /\
     /E2E\        ~2%  - End-to-End
    /------\
   /Integ. \      ~12% - Integration
  /----------\
 /   Unit     \   ~86% - Unit tests
/--------------\
```

**Target coverage**: **>= 80%** for all new code

### Backend Test Organization

```
apps/api/tests/
├── conftest.py                 # Global fixtures
├── unit/                       # Unit tests (86%)
│   ├── core/                   # Core module tests
│   ├── domains/                # Domain tests
│   └── infrastructure/         # Infrastructure tests
├── integration/                # Integration tests (12%)
│   ├── test_auth.py
│   └── test_conversations.py
├── agents/                     # LangGraph agent tests
│   ├── test_graph_build.py
│   ├── test_planner.py
│   └── services/
└── helpers/                    # Test helpers
    └── llm_helpers.py
```

### Running Tests

```bash
cd apps/api

# Unit tests (fast, ~30s)
pytest tests/unit/ -v

# Integration tests (PostgreSQL + Redis required)
pytest tests/integration/ -v

# Agent tests
pytest tests/agents/ -v

# All tests with coverage
pytest --cov=src --cov-report=html -v

# Parallel tests
pytest -n auto --cov=src -v

# Specific test
pytest tests/unit/test_pricing_service.py::test_calculate_cost_usd -v
```

### Unit Test Example

```python
import pytest
from decimal import Decimal
from src.domains.llm.pricing_service import AsyncPricingService

@pytest.mark.asyncio
async def test_calculate_cost_with_cached_tokens():
    """Test cost calculation excludes cached tokens."""
    service = AsyncPricingService()

    cost_without_cache = await service.calculate_cost(
        model="gpt-4.1-mini",
        input_tokens=1000,
        output_tokens=500,
        cached_tokens=0,
        currency="USD"
    )

    cost_with_cache = await service.calculate_cost(
        model="gpt-4.1-mini",
        input_tokens=1000,
        output_tokens=500,
        cached_tokens=800,  # 80% cached
        currency="USD"
    )

    assert cost_with_cache < cost_without_cache
```

### Frontend Tests

```bash
cd apps/web

# Tests in watch mode
pnpm test

# Tests with coverage
pnpm test:coverage
```

---

## Pre-commit Hooks

### Hooks Executed on Commit

1. **Secret detection** (passwords, API keys)
2. **Backend checks** (`.py` files):
   - Ruff linter
   - Black formatter
   - MyPy type checker
   - Unit tests
3. **Frontend checks** (`.ts`/`.tsx` files):
   - ESLint
   - TypeScript type check

### Typical Output

```
Running pre-commit checks...

Checking for secrets...
✓ No secrets detected

Running backend checks...
  Running Ruff...
✓ Ruff passed
  Running Black...
✓ Black passed
  Running MyPy...
✓ MyPy passed
  Running unit tests...
✓ Unit tests passed

✓ All pre-commit checks passed!
```

### Bypassing Hooks (Not Recommended)

```bash
git commit --no-verify -m "WIP: work in progress"
```

> Hooks will be verified in the GitHub Actions CI.

---

## Review Process

### Pull Request Template

```markdown
## Description
<!-- Describe your changes -->

Closes #<issue-number>

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update
- [ ] Refactoring
- [ ] Performance improvement

## Checklist
- [ ] Code follows project conventions
- [ ] Self-review completed
- [ ] Documentation updated if necessary
- [ ] Tests added covering the changes
- [ ] All tests pass locally
- [ ] CHANGELOG.md updated (if applicable)

## Tests
<!-- Describe the tests added/modified -->

## Screenshots (if applicable)
<!-- Add screenshots for UI changes -->
```

### Acceptance Criteria

| Criterion | Required |
|-----------|----------|
| CI checks pass | Yes |
| Coverage >= 80% maintained | Yes |
| >= 1 maintainer approval | Yes |
| No conflicts with `main` | Yes |
| Documentation up to date | If necessary |
| No performance regression | Yes |

### Guidelines for Reviewers

**Focus on**:
- Business logic and edge cases
- Security (OWASP Top 10, PII)
- Performance (N+1, memory, latency)
- Test coverage and quality
- Readability and maintainability
- Architecture (DDD, SOLID)

**Avoid**:
- Style comments (handled by linters)
- Non-constructive criticism
- Blocking nitpicks

**Constructive comment template**:

```markdown
**Issue**: The `execute_tool` function does not handle the case where the tool does not exist.

**Suggestion**:
```python
if tool_name not in self.registry:
    raise ToolNotFoundError(f"Tool '{tool_name}' not found")
```

**Reason**: Avoid an unclear `KeyError`.

**Priority**: Red: Blocking / Yellow: Suggested / Green: Nitpick
```

---

## CI/CD Pipeline

### GitHub Actions Workflows

| Workflow | Triggers | Jobs |
|----------|----------|------|
| **CI/CD Pipeline** | Push `main`, PRs | lint, test, security, build, deploy |
| **Code Quality** | PRs | coverage, complexity, vulnerabilities |
| **Tests Matrix** | PRs | Python 3.12/3.13, PostgreSQL 15/16 |
| **CodeQL Security** | PRs, schedule | Static security analysis |

### CI/CD Jobs

1. **lint-backend**: Ruff + Black + MyPy
2. **lint-frontend**: ESLint + TypeScript
3. **test-backend**: Pytest + Coverage (PostgreSQL + Redis)
4. **test-frontend**: Vitest
5. **security-scan**: pip-audit + safety + bandit + Trivy
6. **sbom-generate**: CycloneDX SBOM
7. **build-push**: Docker images -> GHCR
8. **deploy**: Production (if `main`)

### Required Status Checks

| Check | Required |
|-------|----------|
| `lint-backend` | Yes |
| `lint-frontend` | Yes |
| `test-backend` | Yes |
| `security-scan` | Yes |
| >= 1 approval | Yes |

---

## Documentation

### Required Documentation

For each feature:

| Element | Required |
|---------|----------|
| Google style docstrings | Yes |
| Complete type hints | Yes |
| README if new domain | Yes |
| Update `docs/` if architecture change | Yes |
| ADR if architectural decision | Yes |

### Documentation Structure

See [docs/INDEX.md](docs/INDEX.md) for the complete structure.

### ADR Example

```markdown
# ADR-009: Redis Cache for Router Decisions

**Status**: Accepted
**Date**: 2025-11-15
**Authors**: @maintainers

## Context
Router Node calls an LLM for each message (300-500ms latency).
Some queries are repetitive ("Hello", "Thanks").

## Decision
Implement a Redis cache for Router decisions with:
- Key: SHA-256 of message (normalized)
- TTL: 24h
- Eviction: LRU

## Consequences
**Positive**:
- P95 latency: 500ms -> 50ms
- Cost: -40% on repetitive queries

**Negative**:
- Complexity: +1 Redis dependency
- Cache invalidation if prompt changes
```

---

## Security

### Reporting a Vulnerability

> **DO NOT create a public GitHub Issue for vulnerabilities.**

**Email**: security@lia-assistant.dev

**Include**:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Your name (for credit) or "Anonymous"

**Process**:
1. Response within 48 hours
2. Patch developed
3. CVE published (if applicable)
4. Credit in CHANGELOG

### Security Checklist

Before submitting a PR:

| Check | Verified |
|-------|----------|
| No plaintext secrets | [ ] |
| No PII logged | [ ] |
| Input validation via Pydantic/Zod | [ ] |
| SQL injection protection (ORM) | [ ] |
| XSS protection | [ ] |
| CSRF protection (SameSite cookies) | [ ] |
| Rate limiting on public endpoints | [ ] |
| AuthN/AuthZ verified | [ ] |
| HTTPS only | [ ] |
| Dependencies up to date (no CVEs) | [ ] |

### OWASP Top 10 2024

See [docs/technical/SECURITY.md](docs/technical/SECURITY.md) for details.

---

## Communication

### Channels

| Channel | Usage |
|---------|-------|
| **GitHub Issues** | Bugs, feature requests |
| **GitHub Discussions** | Ideas, help, show & tell |
| **GitHub PRs** | Code review |
| **contact@lia-assistant.dev** | General inquiries |
| **security@lia-assistant.dev** | Security |

### Bug Report Template

```markdown
**Description**
Brief description of the bug.

**To Reproduce**
1. Go to '...'
2. Click on '...'
3. See the error

**Expected Behavior**
What you expected to happen.

**Environment**
- OS: [e.g., Ubuntu 22.04]
- Python: [e.g., 3.12.1]
- API version: [e.g., 6.0.0]
- Browser: [e.g., Chrome 120]

**Additional Context**
Logs, stack traces, screenshots.
```

### Feature Request Template

```markdown
**Problem Statement**
What problem does this feature solve?

**Proposed Solution**
Description of the proposed solution.

**Alternatives Considered**
Other approaches considered.

**Additional Context**
Mockups, examples, references.
```

---

## FAQ

### Frequently Asked Questions

**Q: Can I contribute without being a Python/TypeScript expert?**

A: Yes! Documentation, tests, i18n translations, and bug reports are valuable. Start with `good-first-issue` issues.

**Q: How long does a PR review take?**

A: Generally 48-72 hours for an initial review. Complex PRs may take longer.

**Q: My pre-commit hook takes 2 minutes, is that normal?**

A: Yes, unit tests can take 30-60 seconds. For a quick WIP commit: `git commit --no-verify`.

**Q: How do I test without calling the LLMs?**

A: Use the mocks in `tests/helpers/llm_helpers.py`:

```python
from tests.helpers.llm_helpers import MockChatOpenAI

with patch("src.domains.agents.nodes.planner.planner_llm", MockChatOpenAI()):
    result = await planner_node(state)
```

**Q: Git conflict with `main`?**

A:
```bash
git checkout main
git pull upstream main
git checkout my-branch
git rebase main
# Resolve conflicts
git push origin my-branch --force-with-lease
```

**Q: How do I add a Prometheus metric?**

A: See [OBSERVABILITY_AGENTS.md](docs/technical/OBSERVABILITY_AGENTS.md):
1. Define in `metrics_agents.py`
2. Instrument with `@track_metrics`
3. Add to Grafana dashboard
4. Document in `METRICS_REFERENCE.md`

**Q: What is the versioning policy?**

A: [Semantic Versioning 2.0.0](https://semver.org/):
- **MAJOR**: Breaking changes
- **MINOR**: New features (backward compatible)
- **PATCH**: Bug fixes

---

## Resources

### Project Documentation

| Document | Description |
|----------|-------------|
| [README.md](README.md) | Project overview |
| [docs/INDEX.md](docs/INDEX.md) | Documentation index (115+ docs) |
| [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md) | Detailed installation guide |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System architecture |

### Creation Guides

| Guide | Description |
|-------|-------------|
| [GUIDE_AGENT_CREATION](docs/guides/GUIDE_AGENT_CREATION.md) | Creating an agent |
| [GUIDE_TOOL_CREATION](docs/guides/GUIDE_TOOL_CREATION.md) | Creating a tool |
| [HITL](docs/technical/HITL.md) | Human-in-the-Loop strategies |
| [PLANNER](docs/technical/PLANNER.md) | ExecutionPlan DSL |
| [GOOGLE_API_TRACKING](docs/technical/GOOGLE_API_TRACKING.md) | Google API consumption tracking |
| [LLM_PRICING_MANAGEMENT](docs/technical/LLM_PRICING_MANAGEMENT.md) | Pricing and consumption exports |

### External Standards

| Standard | URL |
|----------|-----|
| Conventional Commits | https://www.conventionalcommits.org/ |
| Google Python Style | https://google.github.io/styleguide/pyguide.html |
| OWASP Top 10 | https://owasp.org/www-project-top-ten/ |

---

## Acknowledgments

Thank you to all contributors who make LIA a quality project!

**Maintainers**:
- @maintainers - Lead maintainer

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| **2.1** | 2026-02-04 | Google API Tracking, Consumption Exports, new `google_api/` domain |
| 2.0 | 2026-02-03 | Complete restructuring, Skills System, FOR_EACH, Voice HD, Modular Config |
| 1.0 | 2025-11-14 | Initial version |

---

<p align="center">
  <strong>LIA</strong> — Contribute to the next-generation AI assistant
</p>

<p align="center">
  Questions: contact@lia-assistant.dev
</p>

<p align="center">
  <a href="#table-of-contents">Back to top</a>
</p>
