# CI/CD Workflows Documentation

This directory contains GitHub Actions workflows for the LIA project. The workflows provide comprehensive automation for continuous integration, code quality, testing, security scanning, dependency management, and deployment.

## Table of Contents

- [Workflows Overview](#workflows-overview)
- [Workflow Details](#workflow-details)
  - [1. CI/CD Pipeline](#1-cicd-pipeline-ciyml)
  - [2. Code Quality Analysis](#2-code-quality-analysis-code-qualityyml)
  - [3. Tests](#3-tests-testsyml)
  - [4. Mixin Tests](#4-mixin-tests-mixin-testsyml)
  - [5. CodeQL Security Analysis](#5-codeql-security-analysis-codeqlyml)
  - [6. Dependabot](#6-dependabot-dependabotyml)
- [Required Secrets](#required-secrets)
- [Environment Variables](#environment-variables)
- [GitHub Actions Versions](#github-actions-versions)
- [Local Testing](#local-testing)
- [Troubleshooting](#troubleshooting)
- [Security Best Practices](#security-best-practices)
- [Badges](#badges)

---

## Workflows Overview

| Workflow | File | Triggers | Purpose |
|----------|------|----------|---------|
| CI/CD Pipeline | `ci.yml` | Push to `main`, PR to `main` | Main pipeline: lint, test, security scan, build, deploy |
| Code Quality Analysis | `code-quality.yml` | Push to `main`/`develop`, PR, manual | Deep code quality checks with multiple tools |
| Tests | `tests.yml` | Push to `main`/`develop`/`feature/*`, PR | Comprehensive test suite with coverage |
| Mixin Tests | `mixin-tests.yml` | Push/PR with mixin-related changes | Specialized mixin testing (unit, integration, e2e) |
| CodeQL Analysis | `codeql.yml` | Push to `main`, PR to `main`, Schedule (Mon 9am) | Security vulnerability scanning |
| Dependabot | `dependabot.yml` | Schedule (Mon 9am) | Automated dependency updates |

---

## Workflow Details

### 1. CI/CD Pipeline (`ci.yml`)

**Main continuous integration and deployment pipeline**

#### Triggers
- **Push** to `main` branch
- **Pull requests** to `main` branch

#### Jobs

##### 1.1. `lint-backend` - Backend Linting
**Runs on:** `ubuntu-latest`
**Working directory:** `./apps/api`

**Steps:**
1. Checkout code (`actions/checkout@v4`)
2. Set up Python 3.12 (`actions/setup-python@v5`) with pip cache
3. Install dependencies: `pip install -e ".[dev]"`
4. Run **Ruff** linter: `ruff check .`
5. Run **Black** formatter check: `black --check .`
6. Run **MyPy** type checker: `mypy src --config-file=pyproject.toml`

**Dependencies:** None
**Runs in parallel:** Yes

---

##### 1.2. `lint-frontend` - Frontend Linting
**Runs on:** `ubuntu-latest`
**Working directory:** `./apps/web`

**Steps:**
1. Checkout code (`actions/checkout@v4`)
2. Install pnpm (`pnpm/action-setup@v4`)
3. Set up Node.js 20 (`actions/setup-node@v4`) with pnpm cache
4. Install dependencies: `pnpm install --frozen-lockfile`
5. Run **ESLint**: `pnpm run lint`
6. Run **TypeScript** type check: `pnpm run type-check`

**Dependencies:** None
**Runs in parallel:** Yes

---

##### 1.3. `test-backend` - Backend Tests with Coverage
**Runs on:** `ubuntu-latest`
**Working directory:** `./apps/api`

**Services:**
- **PostgreSQL** (`pgvector/pgvector:pg16`)
  - Port: 5432
  - User: `test_user`
  - Password: `test_password`
  - Database: `test_db`
  - Health check: `pg_isready` (10s interval, 5s timeout, 5 retries)

- **Redis** (`redis:7-alpine`)
  - Port: 6379
  - Health check: `redis-cli ping` (10s interval, 5s timeout, 5 retries)

**Steps:**
1. Checkout code (`actions/checkout@v4`)
2. Set up Python 3.12 (`actions/setup-python@v5`) with pip cache
3. Install dependencies: `pip install -e ".[dev]"`
4. Run tests with coverage:
   ```bash
   pytest --cov=src --cov-report=xml --cov-report=term-missing -v
   ```
5. Upload coverage to Codecov (`codecov/codecov-action@v4`)
   - Flags: `backend`
   - File: `./apps/api/coverage.xml`
   - Token: `CODECOV_TOKEN` (optional, from secrets)
   - Fail on error: `false`

**Environment variables:**
- `DATABASE_URL`: `postgresql+asyncpg://test_user:test_password@localhost:5432/test_db`
- `REDIS_URL`: `redis://localhost:6379`
- `SECRET_KEY`: `test-secret-key-minimum-32-characters-long-for-testing`
- `FERNET_KEY`: `test-fernet-key-32-bytes-base64==`
- `ENVIRONMENT`: `test`

**Dependencies:** None
**Runs in parallel:** Yes

---

##### 1.4. `test-frontend` - Frontend Tests
**Runs on:** `ubuntu-latest`
**Working directory:** `./apps/web`

**Steps:**
1. Checkout code (`actions/checkout@v4`)
2. Install pnpm (`pnpm/action-setup@v4`)
3. Set up Node.js 20 (`actions/setup-node@v4`) with pnpm cache
4. Install dependencies: `pnpm install --frozen-lockfile`
5. Run tests (placeholder - Vitest tests to be implemented)

**Note:** Frontend tests are currently a placeholder. The workflow echoes "Frontend tests will be run here (vitest)" and will execute `pnpm run test` when implemented.

**Dependencies:** None
**Runs in parallel:** Yes

---

##### 1.5. `security-scan` - Security Scanning
**Runs on:** `ubuntu-latest`

**Steps:**
1. Checkout code (`actions/checkout@v4`)
2. Set up Python 3.12 (`actions/setup-python@v5`)
3. Install security tools: `pip install pip-audit safety bandit[toml]`
4. **Run pip-audit** on backend
   - Working directory: `./apps/api`
   - Command: `pip-audit --desc`
   - Purpose: Check for known vulnerabilities in Python packages
5. **Run safety check** on backend
   - Working directory: `./apps/api`
   - Command: `safety check --json`
   - Continue on error: `true` (warning only)
6. **Run Bandit** security linter on backend
   - Working directory: `./apps/api`
   - Command: `bandit -r src/ -f json -o bandit-report.json`
   - Formats: JSON (artifact) + screen output
   - Continue on error: `true` (warning only)
7. Upload Bandit results as artifact (`actions/upload-artifact@v4`)
   - Name: `bandit-security-report`
   - Path: `./apps/api/bandit-report.json`
   - Retention: 30 days
8. **Run Trivy** filesystem scan (`aquasecurity/trivy-action@0.29.0`)
   - Scan type: `fs`
   - Scan ref: `.` (entire repository)
   - Format: `sarif`
   - Output: `trivy-results.sarif`
   - Severity: `CRITICAL,HIGH`
9. Upload Trivy results to GitHub Security (`github/codeql-action/upload-sarif@v3`)
   - File: `trivy-results.sarif`
   - Always uploads (even if previous steps fail)

**Dependencies:** None
**Runs in parallel:** Yes

---

##### 1.6. `sbom-generate` - SBOM Generation
**Runs on:** `ubuntu-latest`

**Steps:**
1. Checkout code (`actions/checkout@v4`)
2. Set up Python 3.12 (`actions/setup-python@v5`)
3. Install cyclonedx-bom: `pip install cyclonedx-bom`
4. Generate SBOM for backend:
   - Working directory: `./apps/api`
   - Commands:
     ```bash
     pip install -e .
     cyclonedx-py requirements -o sbom-backend.json
     ```
5. Upload SBOM artifact (`actions/upload-artifact@v4`)
   - Name: `sbom-backend`
   - Path: `./apps/api/sbom-backend.json`
   - Retention: 90 days

**Format:** CycloneDX JSON
**Dependencies:** None
**Runs in parallel:** Yes

---

##### 1.7. `build-push` - Build and Push Docker Images
**Runs on:** `ubuntu-latest`
**Condition:** Only runs on `main` branch (`if: github.ref == 'refs/heads/main'`)

**Required permissions:**
- `contents: read`
- `packages: write`

**Dependencies:**
- `lint-backend`
- `lint-frontend`
- `test-backend`
- `test-frontend`
- `security-scan`

**Steps:**
1. Checkout code (`actions/checkout@v4`)
2. Set up QEMU (`docker/setup-qemu-action@v3`) for multi-architecture builds
3. Set up Docker Buildx (`docker/setup-buildx-action@v3`)
4. Log in to GitHub Container Registry (`docker/login-action@v3`)
   - Registry: `ghcr.io`
   - Username: `github.actor`
   - Password: `GITHUB_TOKEN` (auto-provided)
5. **Build API Image:**
   - Extract metadata (`docker/metadata-action@v5`)
   - Tags: `latest`, `main-{sha}`
   - Build and push (`docker/build-push-action@v6`)
     - Context: `./apps/api`
     - Dockerfile: `./apps/api/Dockerfile.prod`
     - Platforms: `linux/amd64`, `linux/arm64`
     - Push: `true`
     - Cache: Registry cache (mode=max)
6. **Build Web Image:**
   - Extract metadata (`docker/metadata-action@v5`)
   - Tags: `latest`, `main-{sha}`
   - Build and push (`docker/build-push-action@v6`)
     - Context: `./apps/web`
     - Dockerfile: `./apps/web/Dockerfile.prod`
     - Platforms: `linux/amd64`, `linux/arm64`
     - Push: `true`
     - Cache: Registry cache (mode=max)

**Registry:** `ghcr.io`
**Images produced:**
- `ghcr.io/{repository}/api:latest`
- `ghcr.io/{repository}/api:main-{sha}`
- `ghcr.io/{repository}/web:latest`
- `ghcr.io/{repository}/web:main-{sha}`

---

##### 1.8. `deploy` - Deploy to Production
**Runs on:** `ubuntu-latest`
**Condition:** Only runs on `main` branch (`if: github.ref == 'refs/heads/main'`)

**Environment:**
- Name: `production`
- URL: `https://lia.example.com`

**Dependencies:**
- `build-push`

**Required secrets:**
- `DEPLOY_HOST`: Production server hostname or IP
- `DEPLOY_USER`: SSH user for deployment
- `DEPLOY_SSH_KEY`: Private SSH key (no passphrase)

**Steps:**
1. Checkout code (`actions/checkout@v4`)
2. Deploy to production server:
   - Install SSH key (save to `~/.ssh/deploy_key`, chmod 600)
   - Add host to known_hosts (`ssh-keyscan`)
   - Make deployment script executable
   - Execute `./scripts/deploy.sh`
3. Verify deployment (placeholder for health check)

**Note:** Email notifications are currently disabled due to SMTP authentication issues. There's a TODO to fix SMTP credentials or migrate to an alternative notification service.

---

### 2. Code Quality Analysis (`code-quality.yml`)

**Deep code quality analysis with multiple specialized tools**

#### Triggers
- **Pull requests** to `main` or `develop` (only if Python or TypeScript files changed)
- **Push** to `main` or `develop` branches
- **Manual workflow dispatch**

**Path filters:**
- `apps/api/src/**/*.py`
- `apps/web/src/**/*.{ts,tsx}`

#### Jobs

##### 2.1. `python-quality` - Python Code Quality
**Runs on:** `ubuntu-latest`
**Working directory:** `./apps/api`

**Steps:**
1. Checkout code (`actions/checkout@v4`)
2. Set up Python 3.12 (`actions/setup-python@v5`) with pip cache
3. Install dependencies:
   ```bash
   pip install -e ".[dev]"
   pip install vulture
   ```
4. **Run Ruff** (linting + import checking)
   - Command: `ruff check src/ --output-format=github`
   - Uses GitHub Actions annotations
5. **Run Ruff** (formatting check)
   - Command: `ruff format --check src/`
6. **Run MyPy** (type checking)
   - Command: `mypy src/ --config-file=pyproject.toml`
   - Continue on error: `true` (warning only, doesn't fail build)
7. **Run Vulture** (dead code detection)
   - Command: `vulture src/ --min-confidence 80 --sort-by-size`
   - Ignored names: `serialized`, `prompts`, `parent_run_id`, `tags`, `method_name`
   - Continue on error: `true` (warning only)
8. **Run Tests with Coverage**
   - Command: `pytest --cov=src --cov-report=term-missing --cov-report=xml`
9. Upload Coverage to Codecov (`codecov/codecov-action@v4`)
   - File: `./apps/api/coverage.xml`
   - Flags: `api`
   - Fail on error: `false`

**Tools used:**
- **Ruff**: Fast Python linter and formatter
- **MyPy**: Static type checker
- **Vulture**: Dead code detector
- **Pytest**: Test runner with coverage

---

##### 2.2. `typescript-quality` - TypeScript Code Quality
**Runs on:** `ubuntu-latest`
**Working directory:** `./apps/web`

**Steps:**
1. Checkout code (`actions/checkout@v4`)
2. Setup pnpm (`pnpm/action-setup@v4`)
3. Setup Node.js 20 (`actions/setup-node@v4`) with pnpm cache
4. Install dependencies: `pnpm install --frozen-lockfile`
5. **Run TypeScript Compiler**
   - Command: `pnpm run type-check`
6. **Run ESLint**
   - Command: `pnpm lint --format=compact`
   - Continue on error: `true` (warning only)
7. **Run Prettier** check
   - Command: `pnpm prettier --check "src/**/*.{ts,tsx,json,css}"`
8. **Run Depcheck** (unused dependencies)
   - Command: `npx depcheck --ignores="@types/*,eslint-*,prettier"`
   - Continue on error: `true` (warning only)

**Tools used:**
- **TypeScript Compiler (tsc)**: Type checking
- **ESLint**: Linting
- **Prettier**: Code formatting
- **Depcheck**: Unused dependency detection

---

##### 2.3. `security-scan` - Security Vulnerability Scan
**Runs on:** `ubuntu-latest`

**Required permissions:**
- `contents: read`
- `security-events: write`

**Steps:**
1. Checkout code (`actions/checkout@v4`)
2. Run Trivy vulnerability scanner (`aquasecurity/trivy-action@0.29.0`)
   - Scan type: `fs`
   - Scan ref: `.`
   - Format: `sarif`
   - Output: `trivy-results.sarif`
   - Severity: `CRITICAL,HIGH`
3. Upload Trivy results to GitHub Security (`github/codeql-action/upload-sarif@v3`)
   - File: `trivy-results.sarif`
   - Always uploads

---

##### 2.4. `quality-summary` - Quality Summary
**Runs on:** `ubuntu-latest`
**Condition:** Always runs (`if: always()`)

**Dependencies:**
- `python-quality`
- `typescript-quality`

**Steps:**
1. Generate summary in GitHub Actions summary view:
   - Lists all quality checks completed
   - Python tools: Ruff, MyPy, Vulture, Pytest
   - TypeScript tools: TSC, ESLint, Prettier, Depcheck
   - Security: Trivy vulnerability scan

---

### 3. Tests (`tests.yml`)

**Comprehensive test suite with multiple test categories**

#### Triggers
- **Push** to `main`, `develop`, or `feature/*` branches
- **Pull requests** to `main` or `develop` branches

#### Jobs

##### 3.1. `test` - Comprehensive Test Suite
**Runs on:** `ubuntu-latest`
**Working directory:** `./apps/api`

**Strategy:**
- Matrix: `python-version: ["3.12"]`
- Single Python version tested (can be expanded)

**Steps:**
1. Checkout code (`actions/checkout@v4`)
2. Set up Python (`actions/setup-python@v5`) with pip cache
3. Install dependencies: `pip install -e ".[dev]"`
4. **Run Unit Tests:**
   ```bash
   pytest tests/core/ tests/domains/agents/api/mixins/ -v \
     --cov=src/core --cov=src/domains/agents/api/mixins \
     --cov-report=term-missing
   ```
   - Continue on error: `false` (strict)
5. **Run Integration Tests:**
   ```bash
   pytest tests/integration/ -v -m integration \
     --cov=src --cov-append --cov-report=term-missing
   ```
   - Continue on error: `false` (strict)
   - Marker: `integration`
6. **Run E2E Tests:**
   ```bash
   pytest tests/e2e/ tests/agents/ -v -m e2e \
     --cov=src --cov-append --cov-report=xml --cov-report=term-missing
   ```
   - Continue on error: `false` (strict)
   - Marker: `e2e`
7. **Run All Other Tests:**
   ```bash
   pytest tests/ -v \
     --ignore=tests/core/ --ignore=tests/domains/agents/api/mixins/ \
     --ignore=tests/integration/ --ignore=tests/e2e/ --ignore=tests/agents/ \
     --cov=src --cov-append --cov-report=xml --cov-report=term-missing
   ```
   - Continue on error: `false` (strict)
8. Upload coverage to Codecov (`codecov/codecov-action@v4`)
   - File: `./apps/api/coverage.xml`
   - Flags: `unittests`
   - Name: `codecov-umbrella`
   - Fail on error: `false`
9. **Check Minimum Coverage:**
   ```bash
   coverage report --fail-under=30
   ```
   - Minimum required: 30%
10. Generate test summary (always runs, even on failure)

**Test Categories:**
- **Unit tests**: Core logic and mixins
- **Integration tests**: Component interactions (marked with `@pytest.mark.integration`)
- **E2E tests**: End-to-end scenarios (marked with `@pytest.mark.e2e`)
- **Other tests**: Remaining test files

**Note:** Email notifications are disabled (SMTP authentication issues).

---

### 4. Mixin Tests (`mixin-tests.yml`)

**Specialized testing workflow for agent API mixins**

#### Triggers
- **Push** to `main`, `develop`, or `feature/*` branches (when mixin files change)
- **Pull requests** to `main` or `develop` (when mixin files change)

**Path filters:**
- `apps/api/src/domains/agents/api/mixins/**`
- `apps/api/tests/domains/agents/api/mixins/**`
- `apps/api/tests/integration/test_mixins_integration.py`
- `apps/api/tests/e2e/test_hitl_flows_e2e.py`

#### Jobs

##### 4.1. `mixin-unit-tests` - Mixin Unit Tests
**Runs on:** `ubuntu-latest`
**Working directory:** `./apps/api`

**Strategy:**
- Matrix: `python-version: ["3.12"]`

**Steps:**
1. Checkout code (`actions/checkout@v4`)
2. Set up Python (`actions/setup-python@v5`) with pip cache
3. Install dependencies: `pip install -e ".[dev]"`
4. **Run HITLManagementMixin tests:**
   ```bash
   pytest tests/domains/agents/api/mixins/test_hitl_management.py -v \
     --cov=src/domains/agents/api/mixins/hitl_management \
     --cov-report=term-missing
   ```
   - Tests: 33
5. **Run GraphManagementMixin tests:**
   ```bash
   pytest tests/domains/agents/api/mixins/test_graph_management.py -v \
     --cov=src/domains/agents/api/mixins/graph_management \
     --cov-report=term-missing
   ```
   - Tests: 14
6. **Run StreamingMixin tests:**
   ```bash
   pytest tests/domains/agents/api/mixins/test_streaming.py -v \
     --cov=src/domains/agents/api/mixins/streaming \
     --cov-report=term-missing
   ```
   - Tests: 16
7. Generate unit test summary:
   - Total: 63 tests

---

##### 4.2. `mixin-integration-tests` - Mixin Integration Tests
**Runs on:** `ubuntu-latest`
**Working directory:** `./apps/api`

**Dependencies:** `mixin-unit-tests`

**Strategy:**
- Matrix: `python-version: ["3.12"]`

**Steps:**
1. Checkout code (`actions/checkout@v4`)
2. Set up Python (`actions/setup-python@v5`) with pip cache
3. Install dependencies: `pip install -e ".[dev]"`
4. **Run Mixin Integration Tests:**
   ```bash
   pytest tests/integration/test_mixins_integration.py -v -m integration \
     --cov=src/domains/agents/api/mixins --cov-report=xml --cov-report=term-missing
   ```
   - HITLManagementMixin Redis integration: 7 tests
   - StreamingMixin DB integration: 3 tests
   - Mixin composition: 4 tests
   - Total: 14 tests
5. Upload coverage (`codecov/codecov-action@v4`)
   - File: `./apps/api/coverage.xml`
   - Flags: `mixin-integration`
   - Name: `mixin-integration-coverage`
6. Generate integration test summary

---

##### 4.3. `mixin-e2e-tests` - Mixin E2E Tests
**Runs on:** `ubuntu-latest`
**Working directory:** `./apps/api`

**Dependencies:** `mixin-integration-tests`

**Strategy:**
- Matrix: `python-version: ["3.12"]`

**Steps:**
1. Checkout code (`actions/checkout@v4`)
2. Set up Python (`actions/setup-python@v5`) with pip cache
3. Install dependencies: `pip install -e ".[dev]"`
4. **Run HITL E2E Flow Tests:**
   ```bash
   pytest tests/e2e/test_hitl_flows_e2e.py -v -m e2e \
     --cov=src/domains/agents/api/mixins --cov-report=xml --cov-report=term-missing
   ```
   - HITL APPROVE flow: 2 scenarios
   - HITL REJECT flow: 2 scenarios
   - HITL EDIT flow: 3 scenarios
   - HITL streaming integration: 1 scenario
   - Security validation: 2 scenarios
   - Total: 10 scenarios
5. Upload coverage (`codecov/codecov-action@v4`)
   - File: `./apps/api/coverage.xml`
   - Flags: `mixin-e2e`
   - Name: `mixin-e2e-coverage`
6. Generate E2E test summary

---

##### 4.4. `mixin-tests-summary` - Complete Summary
**Runs on:** `ubuntu-latest`
**Condition:** Always runs (`if: always()`)

**Dependencies:**
- `mixin-unit-tests`
- `mixin-integration-tests`
- `mixin-e2e-tests`

**Steps:**
1. Generate final summary:
   - Unit Tests: 63
   - Integration Tests: 14
   - E2E Scenarios: 10
   - **Total: 87 tests**
   - Coverage: Comprehensive for all mixins
   - Reference: `docs/MIXIN_TESTS_SUMMARY.md`

---

### 5. CodeQL Security Analysis (`codeql.yml`)

**Advanced security vulnerability scanning using CodeQL**

#### Triggers
- **Push** to `main` branch
- **Pull requests** to `main` branch
- **Schedule**: Every Monday at 9:00 AM UTC (cron: `0 9 * * 1`)

#### Jobs

##### 5.1. `analyze-python` - Analyze Python (Backend)
**Runs on:** `ubuntu-latest`

**Required permissions:**
- `actions: read`
- `contents: read`
- `security-events: write`

**Strategy:**
- `fail-fast: false` (both languages analyzed independently)

**Steps:**
1. Checkout code (`actions/checkout@v4`)
2. Initialize CodeQL (`github/codeql-action/init@v3`)
   - Languages: `python`
   - Queries: `+security-and-quality`
   - Config file: `./.github/codeql/codeql-config.yml`
3. Autobuild (`github/codeql-action/autobuild@v3`)
4. Perform CodeQL Analysis (`github/codeql-action/analyze@v3`)
   - Category: `/language:python`

**Configuration (from `.github/codeql/codeql-config.yml`):**
- **Paths ignored:**
  - `**/test/**`, `**/tests/**`
  - `**/node_modules/**`
  - `**/dist/**`, `**/build/**`
  - `**/__pycache__/**`
  - `**/migrations/**`, `**/alembic/versions/**`
- **Paths included:**
  - `apps/api/src/**`
  - `apps/web/src/**`
- **Queries:**
  - `security-and-quality`
  - `security-extended`
- **Query filters:**
  - Excludes: `py/unused-import`

---

##### 5.2. `analyze-javascript` - Analyze JavaScript/TypeScript (Frontend)
**Runs on:** `ubuntu-latest`

**Required permissions:**
- `actions: read`
- `contents: read`
- `security-events: write`

**Strategy:**
- `fail-fast: false`

**Steps:**
1. Checkout code (`actions/checkout@v4`)
2. Initialize CodeQL (`github/codeql-action/init@v3`)
   - Languages: `javascript`
   - Queries: `+security-and-quality`
   - Config file: `./.github/codeql/codeql-config.yml`
3. Autobuild (`github/codeql-action/autobuild@v3`)
4. Perform CodeQL Analysis (`github/codeql-action/analyze@v3`)
   - Category: `/language:javascript`

**Analysis Output:**
- Results uploaded to GitHub Security tab
- Available in repository's Security > Code scanning alerts

---

### 6. Dependabot (`dependabot.yml`)

**Automated dependency updates across all ecosystems**

#### Configuration
- **Version**: 2
- **Schedule**: Weekly, every Monday at 9:00 AM
- **Reviewers**: `lia-team`
- **Commit message prefix**: `chore(deps)`

#### Ecosystems

##### 6.1. Python Dependencies (Backend)
- **Package ecosystem**: `pip`
- **Directory**: `/apps/api`
- **Open PR limit**: 10
- **Labels**: `dependencies`, `backend`, `python`
- **Ignored updates:**
  - `fastapi`: Major version updates
  - `sqlalchemy`: Major version updates

##### 6.2. NPM Dependencies (Frontend)
- **Package ecosystem**: `npm`
- **Directory**: `/apps/web`
- **Open PR limit**: 10
- **Labels**: `dependencies`, `frontend`, `npm`
- **Ignored updates:**
  - `next`: Major version updates
  - `react`: Major version updates
  - `react-dom`: Major version updates

##### 6.3. Docker Dependencies (Backend)
- **Package ecosystem**: `docker`
- **Directory**: `/apps/api`
- **Open PR limit**: 5
- **Labels**: `dependencies`, `docker`

##### 6.4. Docker Dependencies (Frontend)
- **Package ecosystem**: `docker`
- **Directory**: `/apps/web`
- **Open PR limit**: 5
- **Labels**: `dependencies`, `docker`

##### 6.5. GitHub Actions
- **Package ecosystem**: `github-actions`
- **Directory**: `/` (root)
- **Open PR limit**: 5
- **Labels**: `dependencies`, `github-actions`

---

## Required Secrets

Configure these secrets in your GitHub repository settings (`Settings > Secrets and variables > Actions`):

### For CI/CD Pipeline (`ci.yml`)

| Secret | Required | Purpose | Notes |
|--------|----------|---------|-------|
| `CODECOV_TOKEN` | Optional (Recommended) | Upload coverage reports to Codecov | Without this, coverage upload may fail |
| `DEPLOY_HOST` | Required for deployment | Production server hostname or IP | Only needed for `main` branch deploys |
| `DEPLOY_USER` | Required for deployment | SSH username for deployment | E.g., `deploy`, `ubuntu` |
| `DEPLOY_SSH_KEY` | Required for deployment | Private SSH key for deployment | Must not have a passphrase |
| `GITHUB_TOKEN` | Auto-provided | GitHub Container Registry authentication | Automatically provided by GitHub Actions |

### For Email Notifications (Currently Disabled)

**Note:** Email notifications are temporarily disabled due to SMTP authentication issues. The following secrets would be required if re-enabled:

| Secret | Purpose |
|--------|---------|
| `SMTP_SERVER` | SMTP server address |
| `SMTP_PORT` | SMTP server port |
| `SMTP_USERNAME` | SMTP username |
| `SMTP_PASSWORD` | SMTP password |
| `ALERT_EMAIL` | Email address for failure notifications |

**TODO:** Fix SMTP credentials or migrate to alternative notification service (e.g., Slack, Discord, GitHub Discussions).

---

## Environment Variables

### Global Environment Variables

These are set at the workflow level in `ci.yml`:

| Variable | Value | Purpose |
|----------|-------|---------|
| `REGISTRY` | `ghcr.io` | GitHub Container Registry URL |
| `IMAGE_NAME_API` | `${{ github.repository }}/api` | Full image name for API container |
| `IMAGE_NAME_WEB` | `${{ github.repository }}/web` | Full image name for Web container |

### Test Environment Variables

Used in `test-backend` job in `ci.yml`:

| Variable | Value | Purpose |
|----------|-------|---------|
| `DATABASE_URL` | `postgresql+asyncpg://test_user:test_password@localhost:5432/test_db` | PostgreSQL connection string |
| `REDIS_URL` | `redis://localhost:6379` | Redis connection string |
| `SECRET_KEY` | `test-secret-key-minimum-32-characters-long-for-testing` | Application secret key |
| `FERNET_KEY` | `test-fernet-key-32-bytes-base64==` | Encryption key |
| `ENVIRONMENT` | `test` | Application environment |

---

## GitHub Actions Versions

**Last updated:** 2025-11-22

| Action | Version | Purpose |
|--------|---------|---------|
| `actions/checkout` | `v4` | Checkout repository code |
| `actions/setup-python` | `v5` | Set up Python environment |
| `actions/setup-node` | `v4` | Set up Node.js environment |
| `actions/upload-artifact` | `v4` | Upload workflow artifacts |
| `pnpm/action-setup` | `v4` | Install pnpm package manager |
| `docker/setup-qemu-action` | `v3` | Set up QEMU for multi-arch builds |
| `docker/setup-buildx-action` | `v3` | Set up Docker Buildx |
| `docker/login-action` | `v3` | Log in to container registry |
| `docker/metadata-action` | `v5` | Extract Docker metadata |
| `docker/build-push-action` | `v6` | Build and push Docker images |
| `codecov/codecov-action` | `v4` | Upload coverage to Codecov |
| `aquasecurity/trivy-action` | `0.29.0` | Trivy security scanner |
| `github/codeql-action/init` | `v3` | Initialize CodeQL |
| `github/codeql-action/autobuild` | `v3` | CodeQL autobuild |
| `github/codeql-action/analyze` | `v3` | CodeQL analysis |
| `github/codeql-action/upload-sarif` | `v3` | Upload SARIF results |

**Note:** Dependabot automatically monitors and updates these action versions weekly.

---

## Local Testing

### Prerequisites
- Python 3.12
- Node.js 20
- pnpm
- Docker (for Docker builds and services)
- PostgreSQL (for integration tests)
- Redis (for integration tests)

### Backend Linting
```bash
cd apps/api

# Ruff linting
ruff check .

# Ruff formatting
ruff format --check .

# Black formatting (legacy)
black --check .

# MyPy type checking
mypy src --config-file=pyproject.toml

# Vulture dead code detection
vulture src/ --min-confidence 80 --sort-by-size
```

### Backend Testing

#### All tests
```bash
cd apps/api
pytest --cov=src --cov-report=term-missing
```

#### Unit tests only
```bash
cd apps/api
pytest tests/core/ tests/domains/agents/api/mixins/ -v \
  --cov=src/core --cov=src/domains/agents/api/mixins \
  --cov-report=term-missing
```

#### Integration tests
```bash
cd apps/api
pytest tests/integration/ -v -m integration \
  --cov=src --cov-report=term-missing
```

#### E2E tests
```bash
cd apps/api
pytest tests/e2e/ tests/agents/ -v -m e2e \
  --cov=src --cov-report=term-missing
```

#### Mixin tests (all)
```bash
cd apps/api

# Unit tests
pytest tests/domains/agents/api/mixins/test_hitl_management.py -v
pytest tests/domains/agents/api/mixins/test_graph_management.py -v
pytest tests/domains/agents/api/mixins/test_streaming.py -v

# Integration tests
pytest tests/integration/test_mixins_integration.py -v -m integration

# E2E tests
pytest tests/e2e/test_hitl_flows_e2e.py -v -m e2e
```

#### With coverage requirements
```bash
cd apps/api
pytest --cov=src --cov-report=term-missing
coverage report --fail-under=30
```

### Frontend Linting
```bash
cd apps/web

# ESLint
pnpm run lint

# TypeScript type checking
pnpm run type-check

# Prettier format checking
pnpm prettier --check "src/**/*.{ts,tsx,json,css}"

# Depcheck (unused dependencies)
npx depcheck --ignores="@types/*,eslint-*,prettier"
```

### Frontend Testing
```bash
cd apps/web

# Vitest tests (when implemented)
pnpm run test
```

### Security Scanning

#### Backend security tools
```bash
cd apps/api

# Install security tools
pip install pip-audit safety bandit[toml]

# pip-audit
pip-audit --desc

# Safety check
safety check

# Bandit
bandit -r src/ -f screen
```

#### Trivy filesystem scan
```bash
# Install Trivy first: https://aquasecurity.github.io/trivy/latest/getting-started/installation/

# Scan entire repository
trivy fs --severity CRITICAL,HIGH .

# Generate SARIF output
trivy fs --format sarif --output trivy-results.sarif .
```

### Docker Builds

#### Backend (API)
```bash
docker build -f apps/api/Dockerfile.prod -t lia-api:test apps/api
```

#### Frontend (Web)
```bash
docker build -f apps/web/Dockerfile.prod -t lia-web:test apps/web
```

#### Multi-architecture builds (requires buildx)
```bash
# API
docker buildx build --platform linux/amd64,linux/arm64 \
  -f apps/api/Dockerfile.prod -t lia-api:test apps/api

# Web
docker buildx build --platform linux/amd64,linux/arm64 \
  -f apps/web/Dockerfile.prod -t lia-web:test apps/web
```

### SBOM Generation
```bash
cd apps/api

# Install cyclonedx-bom
pip install cyclonedx-bom

# Generate SBOM
pip install -e .
cyclonedx-py requirements -o sbom-backend.json

# View SBOM
cat sbom-backend.json | jq
```

### CodeQL Analysis (Local)
```bash
# Install CodeQL CLI: https://github.com/github/codeql-cli-binaries/releases

# Create CodeQL database (Python)
codeql database create codeql-db-python --language=python \
  --source-root=apps/api/src

# Run analysis
codeql database analyze codeql-db-python \
  --format=sarif-latest --output=results-python.sarif \
  -- codeql/python-queries:codeql-suites/python-security-and-quality.qls

# View results
cat results-python.sarif | jq
```

---

## Troubleshooting

### Workflow Failures

#### Lint Failures

**Symptoms:**
- Ruff, Black, or MyPy errors
- ESLint or TypeScript errors

**Solutions:**
1. **Check the specific linter output** in the job logs
2. **Run linters locally** to see detailed errors:
   ```bash
   # Backend
   cd apps/api
   ruff check .
   black --check .
   mypy src --config-file=pyproject.toml

   # Frontend
   cd apps/web
   pnpm run lint
   pnpm run type-check
   ```
3. **Auto-fix common issues:**
   ```bash
   # Backend
   ruff check --fix .
   black .

   # Frontend
   pnpm run lint --fix
   pnpm prettier --write "src/**/*.{ts,tsx,json,css}"
   ```
4. **Check for new Ruff rules** (Ruff is frequently updated)
5. **Review MyPy configuration** in `pyproject.toml` if type errors persist

---

#### Test Failures

**Symptoms:**
- Pytest failures
- Coverage below threshold
- Database/Redis connection errors

**Solutions:**
1. **Check test output** in job logs for specific failures
2. **Ensure services are healthy:**
   - PostgreSQL: `pg_isready` should return 0
   - Redis: `redis-cli ping` should return PONG
3. **Run tests locally** with same environment:
   ```bash
   export DATABASE_URL="postgresql+asyncpg://test_user:test_password@localhost:5432/test_db"
   export REDIS_URL="redis://localhost:6379"
   export SECRET_KEY="test-secret-key-minimum-32-characters-long-for-testing"
   export FERNET_KEY="test-fernet-key-32-bytes-base64=="
   export ENVIRONMENT="test"

   cd apps/api
   pytest -v
   ```
4. **Check coverage report** for missing tests:
   ```bash
   pytest --cov=src --cov-report=html
   open htmlcov/index.html
   ```
5. **Increase verbosity** for debugging:
   ```bash
   pytest -vv -s --tb=long
   ```
6. **Run specific test categories:**
   ```bash
   pytest tests/core/ -v  # Unit tests only
   pytest -m integration -v  # Integration tests only
   pytest -m e2e -v  # E2E tests only
   ```

---

#### Security Scan Failures

**Symptoms:**
- pip-audit finds vulnerabilities
- Trivy reports CRITICAL/HIGH severity issues
- Bandit flags security issues

**Solutions:**
1. **Review vulnerability details** in job logs
2. **Update dependencies:**
   ```bash
   # Check for updates
   pip list --outdated

   # Update specific package
   pip install --upgrade <package-name>
   ```
3. **For pip-audit vulnerabilities:**
   - Check if update available: `pip-audit --desc`
   - Review CVE details on https://nvd.nist.gov/
   - If no fix available, consider suppressing (document in comments)
4. **For Trivy issues:**
   - Review SARIF output in GitHub Security tab
   - Update base Docker images
   - Use Trivy's ignore file (`.trivyignore`) for false positives
5. **For Bandit issues:**
   - Review code flagged for security issues
   - Use `# nosec` comment if false positive (with justification)
   - Fix actual security issues (SQL injection, hardcoded secrets, etc.)

---

## Security Best Practices

### Secrets Management
1. **Never commit secrets** to the repository
2. **Rotate secrets regularly** (SSH keys: 90 days, API tokens: 90 days, Passwords: 60 days)
3. **Use GitHub Encrypted Secrets** and never echo them in logs
4. **Limit secret scope** with environment-specific secrets

### Dependency Management
1. **Review Dependabot PRs** before merging
2. **Monitor security advisories** via GitHub Security tab
3. **Pin dependency versions** in production
4. **Audit dependencies regularly** with `pip-audit`, `safety`, `npm audit`

---

## Badges

Add these badges to your main `README.md`:

```markdown
[![CI/CD Pipeline](https://github.com/jgouviergmail/LIA-Assistant/actions/workflows/ci.yml/badge.svg)](https://github.com/jgouviergmail/LIA-Assistant/actions/workflows/ci.yml)
[![Code Quality](https://github.com/jgouviergmail/LIA-Assistant/actions/workflows/code-quality.yml/badge.svg)](https://github.com/jgouviergmail/LIA-Assistant/actions/workflows/code-quality.yml)
[![Tests](https://github.com/jgouviergmail/LIA-Assistant/actions/workflows/tests.yml/badge.svg)](https://github.com/jgouviergmail/LIA-Assistant/actions/workflows/tests.yml)
[![CodeQL](https://github.com/jgouviergmail/LIA-Assistant/actions/workflows/codeql.yml/badge.svg)](https://github.com/jgouviergmail/LIA-Assistant/actions/workflows/codeql.yml)
[![codecov](https://codecov.io/gh/jgouviergmail/LIA-Assistant/branch/main/graph/badge.svg)](https://codecov.io/gh/jgouviergmail/LIA-Assistant)
```

---

**Last Updated:** 2025-11-22
**Maintained by:** LIA Team
