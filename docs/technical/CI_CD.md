# CI/CD Pipeline

> Continuous Integration et automatisation qualite pour le projet LIA.

**Fichiers sources** :
- `.github/workflows/ci.yml` — Pipeline CI principale
- `.github/workflows/security.yml` — Scans de securite (CodeQL, Trivy, SBOM)
- `.github/workflows/release.yml` — Build Docker + GitHub Release
- `.github/workflows/a11y-matrix.yml` — Matrice navigateurs hebdomadaire (AC-002) : rejoue la suite E2E/axe sur Chromium, Firefox et WebKit (`E2E_ALL_BROWSERS=1`), rapports archives 30 jours
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
             ├─> test-backend-integration
             └─> migration-replay
lint-frontend ─> test-frontend
code-hygiene (independant)
docker-build (independant)
secret-scan (independant)
```

`test-backend` et `test-frontend` attendent que leur lint respectif passe avant de s'executer. Les autres jobs sont independants et tournent en parallele.

**`migration-replay`** (F007) rejoue toute la chaine Alembic (`alembic upgrade head`) sur une base PostgreSQL **vide** (service `pgvector`, extensions `vector`/`uuid-ossp`/`pg_trgm` creees), verifie qu'elle atteint le head unique, puis fait un cycle downgrade/upgrade de la derniere revision. Le job unitaire construit son schema via `create_all()` et ne rejoue jamais les migrations : seule une execution from-scratch attrape une migration non rejouable (disaster recovery, nouvelle region). En local : `task db:migrate:replay-check` (base jetable dans le PostgreSQL dev). Le script partage : `scripts/db/check_migrations_replay.sh`.

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

Step 1 — tests unitaires :
```bash
pytest tests/unit/ -v --tb=short \
  -m "not integration and not slow and not e2e and not benchmark and not multiprocess" \
  --cov=src --cov-report=xml --cov-fail-under=45
```

Step 2 — suite agents (cablee en 2026-07 apres l'audit — elle avait pourri
en silence faute de gate) :
```bash
pytest tests/agents/ -v --tb=short \
  -m "not slow and not e2e and not benchmark and not multiprocess" --no-cov
```

Seuil de couverture : **45%** minimum (doctrine ratchet +2 points par
release, jamais de baisse — voir [GUIDE_TESTING](../guides/GUIDE_TESTING.md)
et ADR-113). Coverage uploade sur [Codecov](https://codecov.io).

Il n'y a **plus de liste `--ignore`** : les tests exigeant une vraie base
portent le marker `integration` et vivent dans `tests/integration/`
(reclasses en 2026-07 — la quarantaine par `--ignore` etait redondante avec
le filtre `-m` et masquait le pourrissement de la suite).

#### Test Backend Integration

Memes services PostgreSQL + Redis, mais la base est consommee directement :

```bash
pytest tests/integration/ -v --tb=short \
  -m "not e2e and not benchmark and not multiprocess" --no-cov
```

Le job pose `TEST_DATABASE_URL=postgresql+asyncpg://test:test@localhost:5432/test_db` —
seule variable DB qui survit au `load_dotenv(.env.test, override=True)` du
conftest ; elle route les fixtures vers le service PostgreSQL au lieu de
Testcontainers (`tests/conftest.py::_detect_environment`). Les credentials du
service reproduisent volontairement `.env.test` pour que les tests lisant
`settings.database_url` en direct (checkpointer LangGraph) atteignent la
meme base. `--no-cov` : le gate de couverture appartient au job unit.

En local : `TEST_DATABASE_URL=...lia_test task test:backend:integration`
(base JETABLE obligatoire — les fixtures droppent toutes les tables), ou
fallback Testcontainers sans variable.

#### Test Frontend

```bash
pnpm test:coverage
```

Le script dédié est obligatoire : `pnpm test -- --coverage` transmet le `--`
littéral à vitest, qui ignore silencieusement le flag — aucun rapport n'est
produit (piège corrigé en v1.21.26, ADR-116). Le job applique les **seuils de
couverture ratchet** de `apps/web/vitest.config.ts` (reducers/sse-handlers/
stores verrouillés à 100 %, hooks aux valeurs mesurées, plancher global) et
uploade `coverage/coverage-final.json` vers Codecov. Le test de symétrie SSE
(`sse-symmetry.test.ts`) reparse le Literal backend depuis `apps/api/` — un
nouveau type d'événement SSE backend fait échouer ce job tant que le frontend
n'a pas pris de décision explicite (handler ou non-gestion documentée).

#### Code Hygiene

| Check | Severite | Description |
|-------|----------|-------------|
| `.bak` files | Error | Detecte les fichiers backup oublies |
| Sync Store calls | Error | `runtime.store.put()` au lieu de `store.aput()` = deadlock |
| Redis setex | Warning | `setex()` sans `json.dumps()` = crash serialisation |
| Raw HTTPException raises | Warning | `raise HTTPException` hors de la taxonomie centralisee `src/core/exceptions.py` (regle #18, ADR-124) — 0 site tolere ; bascule en Error prevue a la release suivante |
| Python lockfiles sync | Error | `scripts/check_requirements_lock.py` — manifeste `requirements*.txt` modifie sans regenerer les lockfiles (`task deps:lock`), ou lock dev desynchronise du lock runtime (ADR-112) |
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

**Declencheurs** : `push` sur `main`, `pull_request`, schedule hebdomadaire (lundi 9h UTC), `workflow_dispatch` — avec groupe `concurrency` (annulation des runs obsoletes). Le trigger `push` garantit que la baseline d'alertes code-scanning de `main` se rafraichit a chaque merge, pas seulement une fois par semaine.

**Permissions** : `contents: read`, `security-events: write`, `actions: read`. La derniere est requise par `codeql-action`/`upload-sarif` (lecture des metadonnees de workflow run) : sans elle, les runs echouent avec "Resource not accessible by integration" et la baseline d'alertes reste figee (incident corrige en v1.21.24 apres deux mois de baseline gelee).

| Job | Description |
|-----|-------------|
| CodeQL | Analyse statique Python + JavaScript (queries `security-and-quality`) |
| Dependency Audit | `pip-audit -r requirements.lock.txt` (Python, transitifs inclus — ADR-112) + `pnpm audit` (Node) |
| Trivy | Scan filesystem (severite CRITICAL/HIGH), resultats SARIF |
| SBOM | Generation CycloneDX depuis `requirements.lock.txt` (versions exactes embarquees, artifact conserve 90 jours) |

---

## Release Workflow (`release.yml`)

**Declencheur** : push de tag `v*`

| Job | Description |
|-----|-------------|
| **Require green CI** | **Gate (F008)** : bloque la release si `ci.yml` n'a pas conclu `success` pour le SHA taggue. `build-and-push` et `generate-sbom` en dependent. |
| Build & Push | Images Docker multi-arch (`amd64` + `arm64`) vers `ghcr.io` |
| Generate SBOM | CycloneDX pour le backend, depuis `requirements.lock.txt` (transitifs inclus) |
| Create Release | GitHub Release avec changelog + images Docker + SBOM |

Tags semver : `v1.2.3` genere les tags Docker `1.2.3`, `1.2`, `1`, `latest`.

**Deploiement (F008)** — strategie choisie = **build local sur le Pi avec provenance equivalente** (pas d'images GHCR par digest ; le pipeline Windows→Pi build localement). Elle est rendue tracable + reversible :

- **Provenance injectee** : `prepare-prod.ps1` capture `APP_VERSION` (package.json), `GIT_COMMIT_SHA` (`git rev-parse HEAD`) et `BUILD_DATE` au moment du prepare, les ecrit dans `provenance.env` (embarque au bundle) ; `docker-compose.prod.yml` les passe en **build args** (api) → `Dockerfile.prod` les fige en ENV → exposes a `/api/v1/health` et dans la resource OTel/Langfuse (F030).
- **Manifeste de release** : a la reussite readiness, `release-manifest.json` est ecrit (version, commit, build date, IDs d'images api/web, timestamp), l'ancien rotant en `.previous` — l'artefact effectivement execute est prouvable.
- **Rollback operationnel** (plus seulement textuel) : les services `api`/`web` ont un **tag d'image explicite** (`lia-api:local` / `lia-web:local`) ; avant le build, `capture_rollback_point` sauve l'image courante en `:__rollback` ; si `/ready` echoue apres deploiement, `run_readiness_gate` **restaure automatiquement l'image precedente** (`up --force-recreate --no-build`) et **revalide `/ready`**, puis sort non-zero (deploiement echoue mais service restaure), ou signale une intervention manuelle si le rollback echoue aussi.
- **Logique testee** : `scripts/deploy/lib/deploy_readiness_gate.sh` (source par le `deploy.sh` genere) + tests hermetiques `scripts/deploy/lib/test_deploy_readiness_gate.sh` (succes / readiness rouge → rollback → revalide / rollback impossible). **A valider par un smoke deploiement reel sur le Pi** (le rollback docker ne peut etre exerce que la).

Garde statique : `apps/api/tests/unit/test_release_workflow_gate_guard.py` (le gate ne peut pas etre retire silencieusement).

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

### Dependency Vulnerability Remediation (pnpm Overrides)

When a transitive dependency has a known CVE but the direct dependency hasn't released a fix, use **pnpm overrides** in the root `package.json` to force a safe version:

```json
{
  "pnpm": {
    "overrides": {
      "brace-expansion": "2.0.2"
    }
  }
}
```

**Rules:**
- Always pin to an **exact version** (no `>=` or `^`) — we control versions strictly.
- Run `pnpm install` to regenerate the lockfile, then verify with `pnpm ls <package> --recursive`.
- Document the CVE in the commit message and CHANGELOG.
- Dismiss the Dependabot alert with reason `fix_started` and a reference to the commit.
- Remove the override once the direct dependency updates its own dependency.

**Current overrides** (see `package.json`):
| Package | Pinned Version | Reason |
|---------|---------------|--------|
| `flatted` | 3.4.2 | Prototype pollution fix |
| `picomatch` | 4.0.4 | ReDoS fix |
| `brace-expansion` | 2.0.2 | CVE-2024-4068 (DoS) + CVE-2025-5889 (ReDoS) |

---

## Supply Chain Security

Toutes les GitHub Actions sont **pinnees par SHA** (pas par tag) pour se proteger des attaques supply-chain :

```yaml
# Exemple
- uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5 # v4
```

Le commentaire `# v4` sert de reference humaine. Le SHA garantit l'immutabilite.

### Lockfiles Python (ADR-112)

Les dependances backend sont installees partout (Dockerfile.prod, Dockerfile.dev, CI,
venv local) depuis des **lockfiles compiles** avec hashes SHA256 :

- `apps/api/requirements.txt` / `requirements-dev.txt` — **manifestes d'intention**
  (pins souples autorises) ;
- `apps/api/requirements.lock.txt` / `requirements-dev.lock.txt` — lockfiles
  universels compiles par `uv pip compile --universal` (un seul fichier pour
  linux/amd64, linux/arm64, Windows, Python >= 3.12), installes par pip vanilla
  avec `--require-hashes`.

Deux builds du meme commit embarquent donc exactement les memes versions, verifiees
par empreinte. Workflow : editer le manifeste → `task deps:lock` → committer manifeste
et lockfiles ensemble (le check *Python lockfiles sync* du job code-hygiene echoue
sinon). Bumps explicites : `task deps:upgrade -- <pkg>` ou `task deps:upgrade:all`.
Details et pieges (metadonnees de wheels incoherentes, hashes multi-arch) :
[ADR-112](../architecture/ADR-112-Python-Dependency-Locking.md).

---

## Alignement Pre-commit / CI

Le pre-commit est le filet local rapide, la CI est le filet distant qui doit couvrir **au minimum** tout ce que fait le pre-commit. Si quelqu'un bypass le hook (`--no-verify`) ou clone sans installer les hooks, la CI rattrape.

| Check | Pre-commit | CI | Notes |
|-------|:----------:|:--:|-------|
| Ruff (`src/ tests/`) | ✓ | ✓ | Aligne |
| Black (`src/ tests/`) | ✓ | ✓ | Aligne |
| MyPy (`src/`) | ✓ | ✓ | Aligne |
| Unit tests | ✓ (fast, no cov) | ✓ (fast + cov 45%) | CI ajoute coverage |
| Agents tests | — | ✓ (`tests/agents/`) | CI only (~1 min, hors hook pour garder les commits rapides) |
| Integration tests | — | ✓ (`tests/integration/`) | CI only (necessitent PostgreSQL + Redis) |
| ESLint | ✓ | ✓ | Aligne |
| TypeScript | ✓ | ✓ | Aligne |
| `.bak` files | ✓ | ✓ | Aligne |
| Critical patterns | ✓ | ✓ | Aligne |
| i18n keys sync | ✓ (si stages) | ✓ (toujours) | CI couvre tout |
| Alembic conflicts | ✓ (date prefix) | ✓ (revision chain) | CI plus precis |
| `.env.example` | ✓ (os.environ) | ✓ (config Pydantic) | CI couvre plus large |
| Secrets | grep basique | Gitleaks | CI superieur |
| Docker build | — | ✓ | CI only (trop lent en local) |
| Python lockfiles sync | — | ✓ | CI only (`scripts/check_requirements_lock.py`, offline et deterministe) |

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

# Dependances Python (lockfiles — ADR-112)
task deps:lock              # Regenere les lockfiles apres edition d'un manifeste
task deps:upgrade -- <pkg>  # Bump cible d'un ou plusieurs paquets
task deps:upgrade:all       # Bump global (mises a jour planifiees)
task security:scan:backend  # pip-audit sur requirements.lock.txt (transitifs inclus)
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
