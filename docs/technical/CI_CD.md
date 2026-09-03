# CI/CD Pipeline

> Continuous Integration et automatisation qualite pour le projet LIA.

**Fichiers sources** :
- `.github/workflows/ci.yml` — Pipeline CI principale
- `Taskfile.yml` — **l'implementation reelle de tous les gates** (voir ci-dessous)
- `.github/workflows/security.yml` — Scans de securite (CodeQL, Trivy, SBOM)
- `.github/workflows/release.yml` — Build Docker + GitHub Release
- `.github/workflows/a11y-matrix.yml` — Matrice navigateurs hebdomadaire (AC-002) : rejoue la suite E2E/axe sur Chromium, Firefox et WebKit (`E2E_ALL_BROWSERS=1`), rapports archives 30 jours
- `.github/hooks/pre-commit` — Hook Git pre-commit local
- `scripts/audit/check_ci_parity.py` — Garde : le workflow orchestre, il n'implemente pas
- `.github/dependabot.yml` — Mises a jour automatiques des dependances

---

## Principe : le workflow orchestre, le Taskfile implemente (ADR-151)

Chaque etape `run:` de `ci.yml` est un appel `task <nom>`. La logique vit dans
`Taskfile.yml`, jamais dans le YAML du workflow. **La CI execute donc
litteralement la commande que le developpeur lance.**

Ce n'est pas une convention de style : c'est ce qui rend un gate exécutable
avant le push. Un gate ecrit inline dans le workflow est un gate que personne ne
peut jouer en local, et qui se decouvre par un build rouge apres un local vert —
ce qui est arrive au gate de couverture par markers, au ratchet de complexite
frontend, aux seuils de couverture par fichier et a tout le bloc code-hygiene.

Trois exceptions seulement, chacune motivee par ecrit dans le dictionnaire
`CI_ONLY` de `scripts/audit/check_ci_parity.py` :

| Etape CI-only | Raison | Equivalent local |
|---|---|---|
| `promtool` (binaire natif) | promtool n'est pas installe sur une machine de dev | `task test:alerts` — **meme version v3.0.0**, via conteneur |
| Replay des migrations (bash, dans le conteneur) | le wrapper bash ne tourne pas sur l'hote Windows | `task db:migrate:replay-check` (portage Python, F048) |
| Gate 3.10 de l'installateur (`tests_py310.py`, ADR-215) | doit tourner sous l'interpreteur 3.10 nu de setup-python, hors venv du repo | n'importe quel python >= 3.10 execute le meme fichier |

Le reste des `run:` est du provisionnement de runner (checkout, venv, `pnpm
install`). `task lint:ci-parity` echoue sur toute etape qui n'est ni un appel de
tache, ni un provisionnement declare, ni une exception motivee.

---

## Architecture

```
Poste de developpement                   GitHub Actions
========================                 ========================

git commit                               push to main / PR
    |                                        |
    v                                        v
hook pre-commit (~5 min)                 ci.yml — 12 jobs, 15 appels `task`
    |                                        |
    +-- .bak, secrets, infra reelle          +-- Lint Backend .......... task lint:backend lint:mypy-debt
    +-- Ruff / Black / MyPy                  +-- Lint Frontend ......... task lint:frontend
    +-- tests unitaires rapides              +-- Test Backend .......... task test:backend:unit:coverage
    +-- patterns critiques                   |                          task test:backend:agents
    +-- parite des cles i18n                 |                          task test:markers
    +-- conflits de migration                +-- Test Backend Integr. .. task test:backend:integration
    +-- completude .env.example              +-- Migration Replay ...... (CI-only, cf. tableau)
    +-- ESLint / TypeScript                  +-- Test Frontend ......... task test:frontend:coverage
                                             +-- E2E + a11y (Playwright) task test:e2e
    task ci:fast (~10 min, sans service)     +-- Code Hygiene .......... task lint:hygiene / lint:i18n
    task ci       (+ PG, Redis, Docker,      |                          task test:deploy / lint:docs
                   navigateur)               |                          task lint:cycles / lint:cc
                                             |                          task lint:lockfiles / lint:ci-parity
                                             +-- Observability Config .. task lint:observability + promtool
                                             +-- Docker Build .......... images API + Web (smoke)
                                             +-- Installateur 3.10 (ADR-215) (CI-only)
                                             +-- Secret Scan ........... Gitleaks
```

**`task ci:fast`** est le gate d'avant-push : tout ce que la CI verifie sans
service externe (~10 min mesure). Le hook pre-commit est volontairement plus
etroit — il tient dans ~5 min et saute les ratchets, le gate de markers, les
tests de deploiement et les seuils de couverture frontend.

---

## Pre-commit Hook

**Fichier** : `.github/hooks/pre-commit`

Installe via `task setup:hooks` (configure `git config core.hooksPath .github/hooks/`).

Le hook ne s'execute que sur les fichiers stages et s'adapte au type de fichier modifie :

| # | Check | Declencheur | Bloquant |
|---|-------|------------|----------|
| 0 | `.bak` files | Toujours | Oui |
| 1 | Secrets (grep) | Toujours | Oui |
| 1.5 | Infos d'infrastructure/personnelles reelles (denylist locale git-ignoree) | Toujours | Oui |
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
e2e-frontend   (independant)
code-hygiene   (independant)
observability  (independant)
docker-build   (independant)
secret-scan    (independant)
```

Les jobs de test attendent que leur lint respectif passe avant de s'executer. Les autres sont independants et tournent en parallele. `e2e-frontend` ne depend pas de `lint-frontend` : il tourne dans l'image Playwright officielle (glibc) et construit l'application lui-meme, donc rien ne serait gagne a le serialiser.

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

Chaque ligne « Commande » est **litteralement** ce que contient le workflow.
Pour savoir ce que fait un gate, lire la tache dans `Taskfile.yml`.

#### Lint Backend

| Step | Commande |
|------|----------|
| Lint backend | `task lint:backend lint:mypy-debt` |

`lint:backend` = Ruff + Black + MyPy sur `src/` et `tests/`. `lint:mypy-debt`
est le ratchet F020 : il fige la surface `disable_error_code` en paires
(module, code) et echoue sur toute **nouvelle** exemption — simple lecture de
`pyproject.toml`, sans relancer MyPy.

#### Lint Frontend

| Step | Commande |
|------|----------|
| Lint frontend | `task lint:frontend` |

ESLint, puis trois ratchets shrink-only, puis `tsc --noEmit --incremental
false`. Les ratchets figent la dette existante pour qu'elle ne grossisse pas :
violations `jsx-a11y` (F012/F013/F021), `react-hooks`/immutabilite (F021), et
les fonctions a CC >= 15 avec empreinte par fichier (F011) — une nouvelle
fonction complexe echoue meme sous le plafond global d'ESLint. Le typecheck est
**non incremental** volontairement : `tsconfig.json` pose `"incremental": true`
et `*.tsbuildinfo` est git-ignore, donc un run local sur cache pourrait passer
la ou le runner, a froid, echoue.

#### Test Backend

Services containers : PostgreSQL (`pgvector/pgvector:pg16`) + Redis (`redis:7-alpine`).

| Step | Commande |
|------|----------|
| Tests unitaires + couverture | `task test:backend:unit:coverage` |
| Suite agents | `task test:backend:agents` |
| Gate de couverture par markers (F006) | `task test:markers` |

Le seuil de couverture est **69 %** (`--cov-fail-under`), et il a **une seule
source de verite** : `apps/api/pyproject.toml`, dont le `Taskfile.yml` reprend
la valeur pour la commande que la CI appelle. Deux gardes la tiennent, chacune
sur son versant :

- `test_task_ci_pytest_parity_guard.py::test_coverage_threshold_has_a_single_source_of_truth`
  compare les fichiers de **configuration** entre eux ;
- `scripts/audit/doc_facts.py` (`task lint:docs`) compare ce que la
  **documentation** annonce a cette source.

La seconde a ete ecrite le 2026-08-27 apres avoir mesure six documents citant
six valeurs fausses differentes — dont ce paragraphe, qui annoncait 60 % tout en
certifiant l'unicite de la source.

Doctrine ratchet (jamais de baisse, >= 2 points de marge avant de monter) :
voir [GUIDE_TESTING](../guides/GUIDE_TESTING.md) et ADR-113. Rapport uploade sur
[Codecov](https://codecov.io).

`task test:markers` (F006) ferme un angle mort du garde-fou par chemins : un
fichier de test peut vivre sous une racine executee en CI et rester
**entierement deselectionne** par l'expression de markers du job. Le gate
collecte chaque nodeid avec ses markers et echoue si un test ne tourne dans
**aucun** job sans figurer dans l'allowlist justifiee et shrink-only
(`apps/api/tests/marker_coverage_allowlist.json`).

La suite agents a ete cablee en 2026-07 apres l'audit : elle avait pourri en
silence (83 echecs) faute de gate. Il n'y a **plus de liste `--ignore`** — les
tests exigeant une vraie base portent le marker `integration`.

#### Test Backend Integration

| Step | Commande |
|------|----------|
| Tests d'integration | `task test:backend:integration` |

Memes services PostgreSQL + Redis, mais la base est consommee directement. La
tache enchaine le preflight AC-001 (classification de la strategie DB, echec
immediat et actionnable si aucune n'est disponible) puis **deux collections** :
`tests/integration/`, et les tests marques `integration` qui vivent
physiquement sous `tests/unit` ou `tests/agents` (F006) — ce job equipe de
services est leur seul foyer.

Le job pose `TEST_DATABASE_URL=postgresql+asyncpg://test:test@localhost:5432/test_db` —
seule variable DB qui survit au `load_dotenv(.env.test, override=True)` du
conftest ; elle route les fixtures vers le service PostgreSQL au lieu de
Testcontainers (`tests/conftest.py::_detect_environment`). Les credentials du
service reproduisent volontairement `.env.test` pour que les tests lisant
`settings.database_url` en direct (checkpointer LangGraph) atteignent la
meme base. `--no-cov` : le gate de couverture appartient au job unit.

**`LIA_REQUIRE_DB=1`** (pose par la tache et par le job, F019) : ce job
*promet* une base, donc une base injoignable doit faire **echouer** le job, pas
skipper silencieusement des groupes entiers de tests. Un vert obtenu par skips
massifs est le pire des resultats.

En local : `TEST_DATABASE_URL=...lia_test task test:backend:integration`
(base JETABLE obligatoire — les fixtures droppent toutes les tables), ou
fallback Testcontainers sans variable.

#### E2E + a11y smoke (Playwright)

| Step | Commande |
|------|----------|
| Suite E2E + axe | `task test:e2e` |

F031. Tourne dans l'image Playwright officielle (glibc) : le conteneur de dev
Alpine ne peut pas executer les navigateurs embarques de Playwright, d'ou une
suite en **package isole** (`apps/web/e2e`, hors du workspace pnpm, dependances
figees par `package-lock.json` et installees avec `npm ci`).

Chaque spec intercepte `/api/v1/**` et sert des payloads fixes : aucun backend,
aucun LLM, aucun fournisseur payant n'est contacte. Playwright construit et sert
l'application lui-meme. Smoke Chromium sur PR pour la vitesse ; la **meme**
suite rejoue chaque semaine sur Firefox/WebKit via `a11y-matrix.yml` (AC-002),
et la campagne manuelle NVDA/VoiceOver est dans `docs/a11y/AT_CAMPAIGN.md`.

L'environnement (serveur gere, IPv4, URLs d'API relatives) vit **dans la
tache** : ce ne sont pas des reglages CI mais la facon dont la suite fonctionne,
et les garder dans le workflow faisait diverger le run local du job.

#### Test Frontend

| Step | Commande |
|------|----------|
| Vitest + couverture | `task test:frontend:coverage` |

La tache appelle le script dedie `pnpm test:coverage`, jamais
`pnpm test -- --coverage` : pnpm transmet le `--` litteral a vitest, qui ignore
silencieusement le flag — aucun rapport n'est produit (piege corrige en
v1.21.26, ADR-116). Elle applique les **seuils de couverture ratchet** de
`apps/web/vitest.config.ts` (reducers/sse-handlers/stores verrouilles a 100 %,
hooks aux valeurs mesurees, plancher global) et uploade
`coverage/coverage-final.json` vers Codecov.

La tache **vide `NEXT_PUBLIC_API_URL`**. Ce Taskfile declare `dotenv: - .env`
globalement, donc chaque tache herite de l'environnement du developpeur, que le
runner n'a pas. L'ecart n'est pas cosmetique : mesure le 2026-07-25,
`voice-input-service.ts` tombe a 80 % de couverture de branches contre un
plancher de 83 % **uniquement** parce que cette variable est posee — le code lit
`process.env.NEXT_PUBLIC_API_URL || ''` et la branche vide cesse d'etre
exercee.

Le test de symetrie SSE (`sse-symmetry.test.ts`) reparse le Literal backend
depuis `apps/api/` — un nouveau type d'evenement SSE backend fait echouer ce job
tant que le frontend n'a pas pris de decision explicite (handler ou non-gestion
documentee).

#### Code Hygiene

| Step | Commande |
|------|----------|
| Hygiene de code | `task lint:hygiene -- --github` |
| Parite des cles i18n (F027) | `task lint:i18n` |
| Tests des chemins de deploiement (F008) | `task test:deploy` |
| Derive doc, cycles, complexite | `task lint:docs lint:cycles lint:cc` |
| Lockfiles Python (ADR-112) | `task lint:lockfiles` |
| Parite CI/local (ADR-151) | `task lint:ci-parity` |

Les six controles de `task lint:hygiene` vivent dans
`scripts/audit/check_code_hygiene.py` — en Python et non en bash parce que la
machine de dev est sous Windows et le runner sous Linux : un controle bash-only
est un controle qu'un seul des deux peut jouer. `--github` (drapeau explicite,
et non lecture de `GITHUB_ACTIONS`) bascule la sortie en annotations
`::error::`/`::warning::`.

| Check | Severite | Description |
|-------|----------|-------------|
| `.bak` files | Error | Detecte les fichiers backup oublies |
| Sync Store calls | Error | `runtime.store.put()` au lieu de `store.aput()` = deadlock |
| Alembic heads | Error | Detecte les heads multiples (parsing statique des revisions) |
| Redis setex | Warning | `setex()` sans `json.dumps()` = crash serialisation |
| Raw HTTPException raises | Warning | `raise HTTPException` hors de la taxonomie centralisee `src/core/exceptions.py` (regle #18, ADR-124) — 0 site tolere ; bascule en Error prevue a la release suivante |
| `.env.example` | Warning | Variables dans `src/core/config/` absentes de `.env.example` |

Les severites sont **inchangees par le portage** depuis le bash inline : les
trois controles consultatifs le restent. En promouvoir un est une decision
deliberee (un booleen dans le script), pas un effet de bord.

#### Observability Config

| Step | Commande |
|------|----------|
| Validation structurelle (F025) | `task lint:observability` |
| promtool check/test rules | binaire natif — **CI-only declare** |

Validation deterministe et sans serveur : JSON/YAML valides, cles de dashboard
requises, uids uniques, requetes de panels non vides, crochets PromQL
equilibres. Les deux etapes promtool utilisent la **meme version v3.0.0** que
`task test:alerts` sur les **memes fichiers** — binaire natif ici, conteneur en
local. Le mecanisme differe, l'artefact verifie non.

> **Le pin promtool doit suivre l'image Prometheus** de `docker-compose.{dev,prod}.yml`.
> Le moteur PromQL a change entre les majeures : mesure du 2026-07-28, memes regles,
> memes donnees, `SUCCESS` sur 2.53.2 et `FAILED` sur 3.0.0. Valider sur un autre
> moteur que celui de la production n'est pas valider — une regle pouvait franchir
> la CI et se comporter autrement sur le Raspberry Pi.

#### Installer Python 3.10 floor (ADR-215)

CI-only declare : import de chaque module du wizard d'installation self-host
sous l'interpreteur 3.10 **nu** (`python -B scripts/install/tests_py310.py`),
hors venv du repo — toute syntaxe ou API 3.11+ echoue ici plutot que sur la
machine d'un operateur.

> Le job `python-compat` (F041, sous-ensemble unitaire sur Python 3.13) a ete
> retire par l'ADR-241 : sous le contrat mono-version (`>=3.14,<3.15`), il ne
> reste aucun second interpreteur a prouver — `test-backend` execute la meme
> selection sur 3.14. La garde
> `tests/unit/test_python_runtime_surfaces_guard.py` verrouille depuis toutes
> les surfaces de version (pyproject, Dockerfiles, flags uv, sandbox skills,
> workflows).

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
| CodeQL | Analyse statique Python + JavaScript (queries `security-and-quality` + `security-extended`), config `.github/codeql/codeql-config.yml` |
| Dependency Audit | `pip-audit -r requirements.lock.txt` (Python, transitifs inclus — ADR-112) + `pnpm audit --audit-level=high` (Node). **Les deux etapes sont bloquantes.** |
| Trivy | Scan filesystem (severite CRITICAL/HIGH), resultats SARIF |
| SBOM | Generation CycloneDX depuis `requirements.lock.txt` (versions exactes embarquees, artifact conserve 90 jours) |

**`pnpm audit` a longtemps tourne avec `continue-on-error: true`** : l'etape signalait les
advisories et le job passait quand meme. C'est ainsi qu'une advisory **critique**
(`websocket-driver`, GHSA-xv26-6w52-cph6) a vecu des mois sur `main` sous un pipeline vert.
Le flag a ete retire — corriger l'advisory ou epingler un override (voir plus bas), jamais
restaurer le flag.

### Perimetre analyse par CodeQL

`paths` restreint l'analyse a `apps/api/src/**` et `apps/web/src/**` ; `paths-ignore` en
retire les tests, artefacts de build, migrations, scripts et documentation.

Piege a connaitre : **`**/tests/**` ne matche pas `__tests__`**. Les 31 repertoires de tests
frontend etaient donc analyses malgre l'intention affichee, ce qui produisait des alertes sur
du code de test (cookies sans `Secure` dans un test jsdom, stubs de navigateur). Le motif
`**/__tests__/**` est desormais liste explicitement. Cote backend l'exclusion fonctionne par
construction : les tests vivent hors de `apps/api/src`, donc `paths` les ecarte deja.

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

**Etat reel au 2026-07-25 : `main` n'est protegee par aucune regle.** Verifie
par `gh api repos/{owner}/{repo}/branches/main/protection` (404 « Branch not
protected ») et `gh api repos/{owner}/{repo}/rulesets` (liste vide). Ce
paragraphe decrivait auparavant un jeu de regles — reviews obligatoires, status
checks requis, force-push interdit — qui n'a jamais existe cote GitHub.

Ce qui bloque reellement aujourd'hui :

| Point d'application | Ce qu'il garantit |
|---|---|
| Hook pre-commit local | Rien pour qui clone sans `task setup:hooks` ou passe `--no-verify` |
| `ci.yml` sur push/PR vers `main` | Signale un echec, mais **n'empeche pas** le push |
| Gate « Require green CI » de `release.yml` (F008) | **Bloque la release** si `ci.yml` n'a pas conclu `success` pour le SHA taggue — garde statique : `test_release_workflow_gate_guard.py` |

Autrement dit : une CI rouge n'empeche pas un commit d'atterrir sur `main`, mais
elle empeche ce commit d'etre publie en release. Pour un depot a un seul
mainteneur qui pousse directement, c'est un choix tenable ; il devient
insuffisant des la premiere contribution externe. Activer la protection
demanderait d'exiger au minimum les 12 jobs de `ci.yml` comme status checks —
**decision du proprietaire du depot**, non prise a ce jour.

### Merge settings

Verifie par `gh api repos/{owner}/{repo}` le 2026-07-25 :

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
| npm | `/` (racine du workspace) | Hebdomadaire (lundi) | minor + patch groupes |
| Docker | `/apps/api`, `/apps/web` | Mensuelle | — |
| GitHub Actions | `/` | Hebdomadaire | Toutes les actions groupees |

Les updates mineures/patch sont groupees en une seule PR pour reduire le bruit.

L'ecosysteme npm cible la **racine** et non `/apps/web` : `pnpm-lock.yaml` vit a la racine
du workspace, donc une PR scopee sur `/apps/web` bumperait `package.json` sans le lockfile
et ne pourrait jamais passer `pnpm install --frozen-lockfile`.

### Limites connues des PR Dependabot

Deux classes de PR Dependabot ne sont **pas rattrapables par un rebase** dans ce depot.
Les reconnaitre evite de rejouer indefiniment `@dependabot rebase`.

**1. Ecosysteme pip — lockfiles non reproductibles.** Dependabot regenere
`requirements*.lock.txt` avec son propre resolveur, alors que le depot les compile avec
`uv pip compile --universal --generate-hashes` (ADR-112). Les lockfiles produits sont
insolubles : la CI echoue des l'installation sur `ResolutionImpossible`, avant le moindre
test. Constate sur 9 PR consecutives (#197-#204, #211). **Conduite a tenir** : fermer la PR
et rejouer le bump localement via `task deps:upgrade -- <paquet>` puis `task deps:lock`,
une majeure a la fois.

**2. Ecosysteme npm — collision override / version workspace.** Tout paquet a la fois
epingle dans `pnpm.overrides` (racine) **et** declare dans `apps/web/package.json` produit
un blocage : Dependabot ne lit pas les overrides de la racine quand il bumpe un membre du
workspace, les deux valeurs divergent, et chaque job faisant
`pnpm install --frozen-lockfile` echoue sur `ERR_PNPM_LOCKFILE_CONFIG_MISMATCH`.
Constate sur #195 puis #210 (`vite` 8.1.5 cote workspace contre 8.1.3 cote override) — un
rebase resout le conflit git sans corriger la contradiction. **Conduite a tenir** : rejouer
le lot en alignant l'override sur la nouvelle version et en **regenerant** le lockfile
(jamais en le fusionnant). Paquets concernes aujourd'hui : `vite`, `postcss`, `dompurify`.

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
- Prefer an **exact version**; a caret range (`^x.y.z`) is acceptable — and preferable —
  when the advisory names a minimum patched version rather than a single fixed release.
  An exact pin becomes a liability once upstream patches again: `brace-expansion` was
  frozen at `2.0.2` by this very table while the fix shipped in `2.0.3`, so **our own
  override was pinning a vulnerable version**. Re-read the pins when auditing.
- Scope the key when only one major line is affected: `"minimatch@9": "^9.0.7"` patches the
  vulnerable 9.x without touching the `3.1.5` that ESLint depends on. An unscoped
  `"minimatch"` key would force ESLint onto v9 and break it.
- Never override a package that `apps/web/package.json` also declares without aligning both
  — see *Limites connues des PR Dependabot* above (`ERR_PNPM_LOCKFILE_CONFIG_MISMATCH`).
- Run `pnpm install --lockfile-only` to regenerate the lockfile, then verify with
  `pnpm why <package>` (use `--prod` from `apps/web/` to tell a runtime dependency from a
  dev-only one — the distinction drives the real severity).
- Weigh the blast radius: an override that removes a package and its platform binaries from
  the graph for a *low* advisory on an unused tool is not worth it (tried and reverted for
  `esbuild`, which Vite 8/rolldown does not execute).
- Document the CVE in the commit message and CHANGELOG.
- Remove the override once the direct dependency updates its own dependency.

**Current overrides** (see `package.json` — 14 entries):
| Package | Pinned Version | Reason |
|---------|---------------|--------|
| `flatted` | 3.4.2 | Prototype pollution fix |
| `picomatch` | 4.0.4 | ReDoS fix |
| `brace-expansion` | ^2.0.3 | CVE-2024-4068 (DoS) + CVE-2025-5889 (ReDoS) + zero-step sequence DoS (patched in 2.0.3) |
| `vite` | 8.1.5 | Aligned with `apps/web/package.json` — divergence breaks `--frozen-lockfile` |
| `defu` | 6.1.5 | Prototype pollution |
| `protobufjs` | ^7.6.3 | Prototype pollution |
| `uuid` | ^11.1.1 | Consolidation |
| `postcss` | ^8.5.10 | Parsing advisory |
| `dompurify` | ^3.4.11 | XSS bypass |
| `@grpc/grpc-js` | ^1.9.16 | Memory exhaustion |
| `@babel/core` | ^7.29.6 | RegExp complexity |
| `websocket-driver` | ^0.7.5 | GHSA-xv26-6w52-cph6 (critical, message corruption) + GHSA-mp7j-qc5w-4988 (resource limit bypass). Transitive via `firebase` → `@firebase/database` → `faye-websocket`; unreachable at runtime (only `firebase/app` and `firebase/messaging` are imported) but present in the image |
| `minimatch@9` | ^9.0.7 | 3 ReDoS advisories on the 9.x line; scoped so ESLint's `3.1.5` is untouched |
| `js-yaml` | ^4.2.0 | Quadratic-complexity DoS in merge keys (dev-only, via ESLint) |

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
  linux/amd64, linux/arm64, Windows, Python >= 3.14), installes par pip vanilla
  avec `--require-hashes`.

Deux builds du meme commit embarquent donc exactement les memes versions, verifiees
par empreinte. Workflow : editer le manifeste → `task deps:lock` → committer manifeste
et lockfiles ensemble (le check *Python lockfiles sync* du job code-hygiene echoue
sinon). Bumps explicites : `task deps:upgrade -- <pkg>` ou `task deps:upgrade:all`.
Details et pieges (metadonnees de wheels incoherentes, hashes multi-arch) :
[ADR-112](../architecture/ADR-112-Python-Dependency-Locking.md).

---

## Alignement hook / `task ci:fast` / CI

Trois filets, du plus rapide au plus complet. Le hook pre-commit garde les
commits rapides ; **`task ci:fast` est le gate d'avant-push** ; la CI ajoute ce
qui exige des services ou un environnement particulier. Si quelqu'un bypass le
hook (`--no-verify`) ou clone sans installer les hooks, la CI rattrape.

| Check | Hook | `task ci:fast` | CI | Notes |
|-------|:----:|:--------------:|:--:|-------|
| Ruff / Black / MyPy (`src/ tests/`) | ✓ | ✓ | ✓ | Aligne |
| Ratchet MyPy-debt (F020) | — | ✓ | ✓ | Meme tache |
| Tests unitaires | ✓ (rapides, xdist, sans cov) | ✓ (+ cov, plancher 60 %) | ✓ | Le hook troque la couverture contre le parallelisme |
| Gate de markers (F006) | — | ✓ | ✓ | Meme tache |
| ESLint | ✓ | ✓ | ✓ | Aligne |
| TypeScript | ✓ | ✓ | ✓ | Non incremental des le script `type-check` |
| Ratchets a11y / react-hooks / complexite | — | ✓ | ✓ | Inclus dans `lint:frontend` |
| Couverture frontend (seuils par fichier) | — | ✓ | ✓ | Meme tache, `NEXT_PUBLIC_API_URL` vide des deux cotes |
| `.bak`, Store sync, setex, HTTPException, heads alembic, `.env.example` | ✓ (partiel) | ✓ | ✓ | Le hook n'en fait qu'une partie, sur les fichiers stages |
| Parite des cles i18n | ✓ (si stages) | ✓ (toujours) | ✓ | La CI couvre tout |
| Derive doc / cycles / complexite backend | — | ✓ | ✓ | Memes taches |
| Lockfiles Python (ADR-112) | — | ✓ | ✓ | Meme tache |
| Parite CI/local (ADR-151) | — | ✓ | ✓ | Meme tache |
| Tests de deploiement (F008) | — | ✓ | ✓ | Hermetiques, sans Docker ni reseau |
| Secrets | grep + denylist infra | — | Gitleaks | La CI est superieure |
| Suite agents | — | — (dans `task ci`) | ✓ | Necessite ~1 min |
| Tests d'integration | — | — (dans `task ci`) | ✓ | Necessitent PostgreSQL + Redis |
| Replay des migrations | — | — (dans `task ci`) | ✓ | Necessite PostgreSQL |
| E2E + a11y (Playwright) | — | — (dans `task ci`) | ✓ | Necessite un navigateur |
| Regles Prometheus (promtool) | — | — (dans `task ci`) | ✓ | Conteneur en local, binaire natif en CI |
| Build Docker | — | — | ✓ | CI-only (trop lent en local) |
| Installateur 3.10 (ADR-215) | — | — | ✓ | CI-only (interpreteur 3.10 nu) |

**Limite assumee** : cette iso porte sur les **commandes**, pas sur
l'**environnement**. Le hote de dev est Windows, le runner est Linux ; une
divergence de shell, de casse de systeme de fichiers ou de permissions ne sera
toujours pas attrapee en local. Corriger cela demanderait d'executer les gates
sensibles a la plateforme dans un conteneur Linux.

---

## Secrets GitHub

| Secret | Usage |
|--------|-------|
| `TEST_FERNET_KEY` | Encryption key pour les tests backend |
| `CODECOV_TOKEN` | Upload coverage vers Codecov |
| `GITHUB_TOKEN` | Auto-genere, utilise par Gitleaks et releases |

---

## Commandes locales equivalentes

Elles ne sont pas « equivalentes » : ce sont **les memes commandes**. La CI les
appelle (ADR-151).

```bash
# Equivalent du pre-commit hook (~5 min)
task pre-commit

# Gate d'avant-push : tous les gates CI sans service externe (~10 min mesure)
task ci:fast

# CI complete en local (PostgreSQL + Redis + Docker + navigateur)
# TEST_DATABASE_URL doit pointer vers une base JETABLE
task ci

# Linters seuls
task lint                   # tout : backend, frontend, i18n, docs, ratchets, hygiene, lockfiles, parite CI
task lint:backend           # Ruff + Black + MyPy
task lint:frontend          # ESLint + ratchets a11y/hooks/CC + tsc non incremental
task lint:hygiene           # les 6 controles d'hygiene de code
task lint:ci-parity         # le workflow orchestre, il n'implemente pas

# Tests seuls
task test:backend:unit:fast     # rapide, xdist, sans couverture (perimetre du hook)
task test:backend:unit:coverage # la commande CI a l'identique, plancher 60 % inclus
task test:markers               # gate F006 : aucun test ne tourne dans zero job
task test:frontend              # Vitest
task test:frontend:coverage     # + les seuils de couverture par fichier
task test:e2e                   # Playwright + axe (hermetique)
task test:alerts                # promtool sur les regles Prometheus vivantes

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

### CI echoue sur un gate quelconque

Rejouer **la meme commande** que le job : ouvrir `.github/workflows/ci.yml`,
lire l'appel `task ...` de l'etape rouge, le lancer en local. C'est tout
l'interet de ADR-151 — il n'y a pas de traduction a faire.

### CI echoue sur i18n

Les cles i18n sont desynchronisees entre `en` et une autre langue :

```bash
task lint:i18n
```

Le script signale, par langue, les cles manquantes et les cles en trop. Rappel :
`zh` n'a pas de pluriel selon CLDR — dupliquer quand meme la valeur en `_one`
pour que la parite passe.

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
