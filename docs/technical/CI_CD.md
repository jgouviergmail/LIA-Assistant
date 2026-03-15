# CI/CD Pipeline

> Continuous Integration et automatisation qualite pour le projet LIA.

**Fichiers sources** :
- `.github/workflows/ci.yml` — Pipeline CI principale
- `.github/workflows/security.yml` — Scans de securite (CodeQL, Trivy, SBOM)
- `.github/workflows/release.yml` — Build Docker + GitHub Release
- `.github/hooks/pre-commit` — Hook Git pre-commit local
- `.github/dependabot.yml` — Mises a jour automatiques des dependances

---

## Architecture

```
Developer workstation                    GitHub Actions
========================                 ========================

git commit                               push to main / PR
    |                                        |
    v                                        v
pre-commit hook (local)                  CI workflow (ci.yml)
    |                                        |
    +-- .bak files check                     +-- Lint Backend
    +-- secrets grep                         |     Ruff (src/ tests/)
    +-- Ruff (src/ tests/)                   |     Black (src/ tests/)
    +-- Black (src/ tests/)                  |     MyPy (src/)
    +-- MyPy (src/)                          +-- Lint Frontend
    +-- Fast unit tests                      |     ESLint
    +-- Critical pattern detection           |     TypeScript check
    +-- i18n keys sync                       +-- Test Backend
    +-- Alembic migration conflicts          |     Fast unit tests + coverage
    +-- .env.example completeness            +-- Test Frontend
    +-- ESLint                               |     Vitest + coverage
    +-- TypeScript check                     +-- Code Hygiene
                                             |     .bak files
                                             |     Critical patterns
                                             |     i18n keys sync
                                             |     Alembic migration conflicts
                                             |     .env.example completeness
                                             +-- Docker Build
                                             |     API image (smoke test)
                                             |     Web image (smoke test)
                                             +-- Secret Scan
                                                   Gitleaks
```

---

## Pre-commit Hook

**Fichier** : `.github/hooks/pre-commit`

Installe via `task setup:hooks` (configure `git config core.hooksPath .github/hooks/`).

Le hook ne s'execute que sur les fichiers stages et s'adapte au type de fichier modifie :

| # | Check | Declencheur | Bloquant |
|---|-------|------------|----------|
| 0 | `.bak` files | Toujours | Oui |
| 1 | Secrets (grep) | Toujours | Oui |
| 2.1 | Ruff (`src/ tests/`) | `.py` stages | Oui |
| 2.2 | Black (`src/ tests/`) | `.py` stages | Oui |
| 2.3 | MyPy (`src/`) | `.py` stages | Oui |
| 2.4 | Fast unit tests | `.py` stages | Oui |
| 2.5 | Critical patterns (sync Store, Redis setex) | `.py` stages | Oui |
| 3 | i18n keys sync (EN vs fr/de/es/it/zh) | `locales/` stages | Oui |
| 4 | Alembic migration conflicts (date prefix) | `alembic/versions/` stages | Oui |
| 5 | `.env.example` completeness | `.py` stages | Oui |
| 6.1 | ESLint | `.ts/.tsx` stages | Oui |
| 6.2 | TypeScript check | `.ts/.tsx` stages | Oui |

### Cross-platform

Le hook detecte Windows (Git Bash) et adapte les chemins des binaires :
- Windows : `.venv/Scripts/python.exe`, `python -m ruff`, etc.
- Linux/Mac : `.venv/bin/ruff`, etc.

### Bypass (urgences uniquement)

```bash
git commit --no-verify
```

---

## CI Workflow (`ci.yml`)

**Declencheurs** : `push` sur `main`, `pull_request` vers `main`

### Jobs et dependances

```
lint-backend ──> test-backend
lint-frontend ─> test-frontend
code-hygiene (independant)
docker-build (independant)
secret-scan (independant)
```

`test-backend` et `test-frontend` attendent que leur lint respectif passe avant de s'executer. Les autres jobs sont independants et tournent en parallele.

### Concurrence

```yaml
concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true
```

Un nouveau push annule le run CI en cours sur la meme branche.

### Permissions

```yaml
permissions:
  contents: read
```

Principe du moindre privilege : le `GITHUB_TOKEN` n'a acces qu'en lecture.

### Jobs detail

#### Lint Backend

| Step | Commande |
|------|----------|
| Ruff | `ruff check src/ tests/` |
| Black | `black --check src/ tests/` |
| MyPy | `mypy src/ --config-file=pyproject.toml` |

#### Lint Frontend

| Step | Commande |
|------|----------|
| ESLint | `pnpm lint` |
| TypeScript | `pnpm exec tsc --noEmit` |

#### Test Backend

Services containers : PostgreSQL (`pgvector/pgvector:pg16`) + Redis (`redis:7-alpine`).

Commande :
```bash
pytest tests/unit/ -v --tb=short \
  -m "not integration and not slow and not e2e and not benchmark and not multiprocess" \
  --ignore=tests/unit/test_base_repository.py \
  --ignore=tests/unit/test_auth_service_refactored.py \
  # ... (10 fichiers exclus — tests necessitant des fixtures specifiques)
  --cov=src --cov-report=xml --cov-fail-under=75
```

Seuil de couverture : **75%** minimum.
Coverage uploade sur [Codecov](https://codecov.io).

#### Test Frontend

```bash
pnpm test -- --coverage
```

#### Code Hygiene

| Check | Severite | Description |
|-------|----------|-------------|
| `.bak` files | Error | Detecte les fichiers backup oublies |
| Sync Store calls | Error | `runtime.store.put()` au lieu de `store.aput()` = deadlock |
| Redis setex | Warning | `setex()` sans `json.dumps()` = crash serialisation |
| i18n keys sync | Error | Compare les cles EN vs de/es/fr/it/zh |
| Alembic conflicts | Error | Detecte les heads multiples (parsing statique des revisions) |
| `.env.example` | Warning | Variables dans `src/core/config/` absentes de `.env.example` |

#### Docker Build

Build smoke test (pas de push) avec cache GitHub Actions :

| Image | Context | Dockerfile |
|-------|---------|------------|
| API | `./apps/api` | `Dockerfile.prod` |
| Web | `.` (root) | `apps/web/Dockerfile.prod` |

#### Secret Scan

[Gitleaks](https://github.com/gitleaks/gitleaks) sur l'historique complet (`fetch-depth: 0`).

---

## Security Workflow (`security.yml`)

**Declencheurs** : `pull_request`, schedule hebdomadaire (lundi 9h UTC), `workflow_dispatch`

| Job | Description |
|-----|-------------|
| CodeQL | Analyse statique Python + JavaScript (queries `security-and-quality`) |
| Dependency Audit | `pip-audit` (Python) + `pnpm audit` (Node) |
| Trivy | Scan filesystem (severite CRITICAL/HIGH), resultats SARIF |
| SBOM | Generation CycloneDX (artifact conserve 90 jours) |

---

## Release Workflow (`release.yml`)

**Declencheur** : push de tag `v*`

| Job | Description |
|-----|-------------|
| Build & Push | Images Docker multi-arch (`amd64` + `arm64`) vers `ghcr.io` |
| Generate SBOM | CycloneDX pour le backend |
| Create Release | GitHub Release avec changelog + images Docker + SBOM |

Tags semver : `v1.2.3` genere les tags Docker `1.2.3`, `1.2`, `1`, `latest`.

---

## Branch Protection

La branche `main` est protegee avec les regles suivantes :

| Regle | Valeur |
|-------|--------|
| PR review obligatoire | 1 approbation minimum (contributeurs externes) |
| Stale reviews | Dismisses automatiquement |
| Status checks requis | Lint Backend, Lint Frontend, Test Backend, Test Frontend, Code Hygiene, Docker Build, Secret Scan |
| Branche a jour | Oui (strict mode) |
| Conversations resolues | Oui |
| Force push | Interdit |
| Deletion | Interdit |
| Admins bypass | Oui (owner peut push directement) |

### Merge settings

| Option | Valeur |
|--------|--------|
| Squash merge | Oui |
| Merge commit | Oui |
| Rebase merge | Oui |
| Delete branch on merge | Oui (auto) |
| Allow update branch | Oui |
| Allow auto merge | Oui |

---

## Dependabot

**Fichier** : `.github/dependabot.yml`

| Ecosystem | Directory | Frequence | Groupes |
|-----------|-----------|-----------|---------|
| pip | `/apps/api` | Hebdomadaire (lundi) | minor + patch groupes |
| npm | `/apps/web` | Hebdomadaire (lundi) | minor + patch groupes |
| Docker | `/apps/api`, `/apps/web` | Mensuelle | — |
| GitHub Actions | `/` | Hebdomadaire | Toutes les actions groupees |

Les updates mineures/patch sont groupees en une seule PR pour reduire le bruit.

---

## Supply Chain Security

Toutes les GitHub Actions sont **pinnees par SHA** (pas par tag) pour se proteger des attaques supply-chain :

```yaml
# Exemple
- uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5 # v4
```

Le commentaire `# v4` sert de reference humaine. Le SHA garantit l'immutabilite.

---

## Alignement Pre-commit / CI

Le pre-commit est le filet local rapide, la CI est le filet distant qui doit couvrir **au minimum** tout ce que fait le pre-commit. Si quelqu'un bypass le hook (`--no-verify`) ou clone sans installer les hooks, la CI rattrape.

| Check | Pre-commit | CI | Notes |
|-------|:----------:|:--:|-------|
| Ruff (`src/ tests/`) | ✓ | ✓ | Aligne |
| Black (`src/ tests/`) | ✓ | ✓ | Aligne |
| MyPy (`src/`) | ✓ | ✓ | Aligne |
| Unit tests | ✓ (fast, no cov) | ✓ (fast + cov 75%) | CI ajoute coverage |
| ESLint | ✓ | ✓ | Aligne |
| TypeScript | ✓ | ✓ | Aligne |
| `.bak` files | ✓ | ✓ | Aligne |
| Critical patterns | ✓ | ✓ | Aligne |
| i18n keys sync | ✓ (si stages) | ✓ (toujours) | CI couvre tout |
| Alembic conflicts | ✓ (date prefix) | ✓ (revision chain) | CI plus precis |
| `.env.example` | ✓ (os.environ) | ✓ (config Pydantic) | CI couvre plus large |
| Secrets | grep basique | Gitleaks | CI superieur |
| Docker build | — | ✓ | CI only (trop lent en local) |

---

## Secrets GitHub

| Secret | Usage |
|--------|-------|
| `TEST_FERNET_KEY` | Encryption key pour les tests backend |
| `CODECOV_TOKEN` | Upload coverage vers Codecov |
| `GITHUB_TOKEN` | Auto-genere, utilise par Gitleaks et releases |

---

## Commandes locales equivalentes

```bash
# Equivalent du pre-commit hook
task pre-commit

# Equivalent de la CI complete
task ci

# Linters seuls
task lint                   # backend + frontend
task lint:backend           # Ruff + Black + MyPy
task lint:frontend          # ESLint + Prettier + tsc

# Tests seuls
task test:backend:unit:fast # Fast unit tests (pre-commit)
task test:backend:unit      # All unit tests
task test:frontend          # Vitest

# Format auto
task format                 # Black + Prettier
```

---

## Troubleshooting

### Pre-commit echoue sur Black

```bash
task format              # Auto-fix formatting
git add -p               # Re-stage fixed files
git commit               # Retry
```

### CI echoue sur i18n

Les cles i18n sont desynchronisees entre `en` et une autre langue. Verifier avec :

```bash
python -c "
import json, pathlib
def get_keys(d, prefix=''):
    keys = set()
    for k, v in d.items():
        full = f'{prefix}.{k}' if prefix else k
        if isinstance(v, dict): keys |= get_keys(v, full)
        else: keys.add(full)
    return keys

ref = get_keys(json.loads(pathlib.Path('apps/web/locales/en/translation.json').read_text(encoding='utf-8')))
for lang in ['fr','de','es','it','zh']:
    tgt = get_keys(json.loads(pathlib.Path(f'apps/web/locales/{lang}/translation.json').read_text(encoding='utf-8')))
    missing = ref - tgt
    if missing: print(f'{lang}: MISSING {len(missing)} keys: {sorted(missing)[:5]}')
"
```

### CI echoue sur Alembic

Conflit de migration (heads multiples). Resoudre avec :

```bash
cd apps/api
alembic heads                              # Voir les heads
alembic merge -m "merge heads" head1 head2 # Fusionner
```

### Docker build echoue en CI

Le Dockerfile ne builde plus. Tester localement :

```bash
docker build -f apps/api/Dockerfile.prod apps/api/
docker build -f apps/web/Dockerfile.prod .
```
