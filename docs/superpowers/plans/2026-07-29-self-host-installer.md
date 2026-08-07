# Self-Host Installer Implementation Plan

> **Implementation amendment (2026-08-05):**
> `docs/superpowers/specs/2026-08-05-self-host-installer-audit-addendum.md`
> governs every conflict. The July document remains historical context.
> Execution goes through `docs/superpowers/plans/2026-08-05-self-host-installer-activation.md`;
> do not execute this baseline plan independently.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One-command guided production install for self-hosters: `./install.sh` asks the indispensable questions, generates `.env` + compose override, builds, validates, starts, bootstraps, and reports a working LIA instance.

**Architecture:** A stdlib-only Python wizard package (`scripts/install/`) bootstrapped by a minimal POSIX `install.sh`. Fine-grained validation is delegated to the real Pydantic `Settings` executed inside the freshly built API image. `docker-compose.prod.yml` stays the single reference compose; the wizard layers a generated override. Migrations and first-run SQL seeds already run in the API entrypoint (`apps/api/docker-entrypoint.sh:16-39`) — the wizard orchestrates around them, never duplicates them.

**Tech Stack:** Python 3.10+ stdlib only (wizard), POSIX sh (bootstrap), Docker Compose v2.24+ (needed for `!override` list semantics), pytest (via `apps/api/.venv`), Caddy 2 (optional TLS scenario).

**Spec:** `docs/superpowers/specs/2026-07-29-self-host-installer-design.md` — read it before starting any task.

## Global Constraints

- Wizard code: **Python stdlib only** — no third-party import anywhere under `scripts/install/` (the target server has no venv).
- MyPy strict + Ruff + Black (line-length 100) apply to `scripts/install/` like backend code; comments/docstrings in English.
- **No secret** may be written to `install.log`, `.install-state.json`, or test fixtures. `.env` is written with mode `0o600`.
- Never overwrite an existing `.env` silently — timestamped backup first.
- **Git rule (project)**: commit steps below are *proposals* — present the diff and suggested message to the user and wait for their green light; never run git yourself.
- All wizard user-facing strings go through `i18n.tr()` (en + fr). No hardcoded user-facing literals.
- Docker Compose is always invoked as `docker compose -f docker-compose.prod.yml [-f <override>]` — never a bare `docker compose` (implicit file resolution could pick dev files).
- Run `task test:install` after every wizard task; run `task ci:fast` before proposing the final commit.

## File Structure

```
install.sh                                     # POSIX bootstrap (new)
scripts/install/__init__.py                    # package marker (new)
scripts/install/__main__.py                    # entry point, arg parsing, step loop (new)
scripts/install/i18n.py                        # en/fr message catalog (new)
scripts/install/questions.py                   # declarative sections/questions + validators (new)
scripts/install/answers.py                     # interactive & file-based collection (new)
scripts/install/envgen.py                      # .env generation + secrets (new)
scripts/install/compose.py                     # override + Caddyfile generation (new)
scripts/install/preflight.py                   # system checks (new)
scripts/install/verify.py                      # LLM key verification (new)
scripts/install/state.py                       # resume state machine (new)
scripts/install/deploy.py                      # build/validate/up/wait/create_admin (new)
scripts/install/report.py                      # final summary (new)
scripts/install/tests/                         # hermetic unit suite (new)
apps/api/scripts/validate_settings.py          # real-Settings validation entry (new)
infrastructure/caddy/Caddyfile.template        # Caddy vhost template (new)
docker-compose.devops.yml                      # maintainer-only overlay (new)
docker-compose.prod.yml                        # profiles + mount extraction (modified)
scripts/deploy/prepare-prod.ps1                # ship the devops overlay (modified)
scripts/deploy/lib/deploy_readiness_gate.sh    # COMPOSE_FILE gains the overlay (modified)
Taskfile.yml                                   # test:install + lint:install (modified)
.github/workflows/ci.yml                       # task test:install step (modified)
.gitignore                                     # install artifacts (modified)
.env.prod.example / .env.min.prod              # COMPOSE_PROFILES documentation (modified)
docs/architecture/ADR-179-Self-Host-Installer.md  # decisions + release directive (new)
docs/GETTING_STARTED.md / README.md / docs/INDEX.md / docs/architecture/ADR_INDEX.md (modified)
```

---

### Task 1: `validate_settings` script (API side)

**Files:**
- Create: `apps/api/scripts/validate_settings.py`
- Test: `apps/api/tests/unit/test_validate_settings_script.py`

**Interfaces:**
- Produces: `main() -> int` — returns 0 and prints `OK: settings are valid` when the real `Settings` boots; returns 1 and prints one `  - <loc>: <msg>` line per validation error otherwise. Invoked in-container as `python -m scripts.validate_settings` (Task 11 consumes this exact command).

- [ ] **Step 1: Write the failing test**

```python
"""Tests for scripts/validate_settings.py (installer support script)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # apps/api on sys.path

from scripts.validate_settings import main


def test_main_returns_zero_in_valid_test_env(capsys: pytest.CaptureFixture[str]) -> None:
    assert main() == 0
    assert "OK: settings are valid" in capsys.readouterr().out


def test_main_reports_invalid_setting(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # DEBUG is a plain bool field: "banana" cannot coerce -> ValidationError.
    # If a before-validator ever coerces DEBUG, switch to another plain bool
    # field without a validator (grep "bool = Field" in src/core/config/).
    monkeypatch.setenv("DEBUG", "banana")
    assert main() == 1
    out = capsys.readouterr().out
    assert "INVALID" in out
    assert "debug" in out.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/test_validate_settings_script.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.validate_settings'`

- [ ] **Step 3: Write the implementation**

```python
"""Boot the real Settings and report every validation error, then exit.

Installer support script (ADR-179). Runs inside the API image with the
entrypoint bypassed — Settings validation is pure Pydantic and needs neither
PostgreSQL nor Redis (the entrypoint would otherwise wait on pg_isready):

    docker compose -f docker-compose.prod.yml run --rm --no-deps \
        --entrypoint "" api python -m scripts.validate_settings
"""

import importlib
import sys


def main() -> int:
    """Validate the environment against the composed Settings class.

    Returns:
        0 when Settings boots, 1 with one line per error otherwise.
    """
    try:
        if "src.core.config" in sys.modules:
            # Re-read the current environment (tests call main() repeatedly).
            importlib.reload(sys.modules["src.core.config"])
        else:
            importlib.import_module("src.core.config")
    except Exception as exc:
        try:
            from pydantic import ValidationError

            if isinstance(exc, ValidationError):
                print(f"INVALID: {exc.error_count()} setting error(s)")
                for err in exc.errors():
                    loc = ".".join(str(part) for part in err["loc"])
                    print(f"  - {loc}: {err['msg']}")
                return 1
        except ImportError:
            pass
        print(f"INVALID: {type(exc).__name__}: {exc}")
        return 1
    print("OK: settings are valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/test_validate_settings_script.py -v`
Expected: 2 PASS

- [ ] **Step 5: Checkpoint — propose commit** `feat(installer): add validate_settings script (real-Settings env validation)`

---

### Task 2: Observability compose profiles

**Files:**
- Modify: `docker-compose.prod.yml` (12 services)
- Modify: `.env.prod.example` (~line 15, environment block) and `.env.min.prod` (section [11] area)
- Test: `apps/api/tests/unit/test_compose_observability_profiles_guard.py`

**Interfaces:**
- Produces: profile name literal `"observability"`; core services set `{postgres, postgres-backup, redis, api, web}` (Task 8 and the ADR consume these).

- [ ] **Step 1: Write the failing guard test**

```python
"""Guard: observability/management services carry the 'observability' profile.

The self-host installer (ADR-179) offers "core only" installs by NOT setting
COMPOSE_PROFILES. Core services must stay profile-less; every monitoring or
management service must belong to exactly the 'observability' profile, so the
split can never silently drift.
"""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
COMPOSE_PROD = REPO_ROOT / "docker-compose.prod.yml"

CORE_SERVICES = {"postgres", "postgres-backup", "redis", "api", "web"}
OBSERVABILITY_SERVICES = {
    "tempo", "prometheus", "alertmanager", "blackbox-exporter", "grafana",
    "loki", "promtail", "node-exporter", "cadvisor", "postgres-exporter",
    "redis-exporter", "portainer",
}


def test_profile_split_is_exact() -> None:
    services = yaml.safe_load(COMPOSE_PROD.read_text(encoding="utf-8"))["services"]
    assert set(services) == CORE_SERVICES | OBSERVABILITY_SERVICES
    for name, svc in services.items():
        if name in CORE_SERVICES:
            assert "profiles" not in svc, f"core service {name} must not carry a profile"
        else:
            assert svc.get("profiles") == ["observability"], (
                f"service {name} must carry exactly ['observability']"
            )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/test_compose_observability_profiles_guard.py -v`
Expected: FAIL — no service has a `profiles` key yet.

- [ ] **Step 3: Add `profiles: ["observability"]`** to each of the 12 services listed in `OBSERVABILITY_SERVICES` in `docker-compose.prod.yml` (directly under each service's `container_name:` line, e.g.):

```yaml
  grafana:
    image: grafana/grafana:11.3.0
    container_name: lia-grafana-prod
    profiles: ["observability"]
```

(`portainer` joins the profile: it is host management, not needed for a working instance.)

- [ ] **Step 4: Document the profile in both env templates**

`.env.prod.example` — add under the `[01] ENVIRONMENT`-equivalent header block:

```bash
# Compose profiles: the full observability stack (Grafana, Prometheus, Loki,
# Tempo, exporters, Portainer) only starts when this is set (ADR-179).
# Core-only installs (small hosts) simply omit the line.
COMPOSE_PROFILES=observability
```

`.env.min.prod` — same block but with the assignment commented out (`# COMPOSE_PROFILES=observability`), since minimal installs default to core-only.

- [ ] **Step 5: Run the guard + hygiene**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/test_compose_observability_profiles_guard.py -v` → PASS
Run: `task lint:hygiene` → exit 0 (the `.env.example` checks must still pass)

- [ ] **Step 6: Sanity-check merged config with and without the profile**

Run: `docker compose -f docker-compose.prod.yml config --services` → exactly the 5 core services.
Run: `COMPOSE_PROFILES=observability docker compose -f docker-compose.prod.yml config --services` → all 17.

- [ ] **Step 7: Checkpoint — propose commit** `feat(compose): gate the observability stack behind a compose profile (ADR-179)` — release note MUST state: *the maintainer's production `.env` needs `COMPOSE_PROFILES=observability` added before the next deploy.*

---

### Task 3: Extract maintainer-only DevOps mounts

**Files:**
- Create: `docker-compose.devops.yml`
- Modify: `docker-compose.prod.yml` (api service: remove 3 volume lines + `group_add`)
- Modify: `scripts/deploy/lib/deploy_readiness_gate.sh` (COMPOSE_FILE) and `scripts/deploy/prepare-prod.ps1` (`$rootPaths`)

**Interfaces:**
- Produces: overlay filename literal `docker-compose.devops.yml` (deploy driver + ADR consume it).

- [ ] **Step 1: Investigate the skills sandbox dependency (decision gate)**

Run: `grep -rn "docker" apps/api/src/domains/skills/executor.py | head -20` and `grep -rn "SKILLS_SCRIPT_SANDBOX_IMAGE" apps/api/src -l`
Decision rule: **if** the skills script sandbox spawns containers through `/var/run/docker.sock`, the socket mount and `group_add` STAY in `docker-compose.prod.yml` (removing them would silently break script skills for every self-hoster) and only the two Claude-CLI mounts move; **otherwise** all three mounts and `group_add` move. Record the outcome in the ADR (Task 15).

- [ ] **Step 2: Create the overlay**

```yaml
# Maintainer-only overlay for the reference production host (ADR-179).
# NOT part of a standard self-hosted install: it wires the in-container
# DevOps Claude CLI (infrastructure/claude-cli/). Deployed by the driver via
# COMPOSE_FILE=docker-compose.prod.yml:docker-compose.devops.yml.
services:
  api:
    volumes:
      - ~/.claude:/home/appuser/.claude
      - ./infrastructure/claude-cli/CLAUDE.server.md:/opt/claude-workspace/CLAUDE.md:ro
```

(Include `- /var/run/docker.sock:/var/run/docker.sock` and the `group_add` block here **only** if Step 1 concluded they can move.)

- [ ] **Step 3: Remove the moved lines from `docker-compose.prod.yml`** (api service volumes; compose overlays *append* volumes, so the base must not keep duplicates).

- [ ] **Step 4: Point the deploy driver at both files**

In `scripts/deploy/lib/deploy_readiness_gate.sh`, locate where `COMPOSE_FILE` is assigned (the `_dc()` helper at line 31 reads it) and set it to the colon-separated pair:

```bash
COMPOSE_FILE="docker-compose.prod.yml:docker-compose.devops.yml"
```

Then grep the rest of the deploy chain for single-file invocations: `grep -rn "docker-compose.prod.yml" scripts/deploy/ | grep -v devops` — every runtime invocation (not comments/log hints) must include both files. In `scripts/deploy/prepare-prod.ps1`, add to `$rootPaths`:

```powershell
@{ Path = "docker-compose.devops.yml";  Required = $true;  Recurse = $false },
```

- [ ] **Step 5: Run the deploy test suite**

Run: `task test:deploy`
Expected: PASS (if a Pester expectation pins the old single-file COMPOSE_FILE, update the expectation — the *behavior* under test is unchanged).

- [ ] **Step 6: Verify merged config equals the previous one for the maintainer path**

Run: `COMPOSE_FILE="docker-compose.prod.yml:docker-compose.devops.yml" docker compose config > after.yml` and compare the api service's volumes/group_add against `git show HEAD:docker-compose.prod.yml` — the merged set must be identical to the pre-extraction set. Delete `after.yml` afterwards.

- [ ] **Step 7: Checkpoint — propose commit** `refactor(compose): move maintainer DevOps mounts to a devops overlay (ADR-179)`

---

### Task 4: Wizard package skeleton — i18n

**Files:**
- Create: `scripts/install/__init__.py`, `scripts/install/i18n.py`
- Test: `scripts/install/tests/__init__.py`, `scripts/install/tests/conftest.py`, `scripts/install/tests/test_i18n.py`

**Interfaces:**
- Produces: `set_language(lang: str) -> None`, `tr(msg_id: str, **kwargs: object) -> str`, `MESSAGES: dict[str, dict[str, str]]`. Every later module imports `tr`.

- [ ] **Step 1: conftest + failing test**

`scripts/install/tests/conftest.py`:

```python
"""Make the repo root importable so `from scripts.install import ...` works."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
```

`scripts/install/tests/test_i18n.py`:

```python
"""i18n catalog tests: bilingual completeness and formatting."""

import pytest

from scripts.install import i18n


def test_every_message_has_en_and_fr() -> None:
    for msg_id, translations in i18n.MESSAGES.items():
        assert set(translations) == {"en", "fr"}, f"{msg_id} missing a language"


def test_tr_switches_language() -> None:
    i18n.set_language("fr")
    fr = i18n.tr("welcome")
    i18n.set_language("en")
    en = i18n.tr("welcome")
    assert fr != en


def test_tr_unknown_id_raises() -> None:
    with pytest.raises(KeyError):
        i18n.tr("no_such_message_id")
```

- [ ] **Step 2: Run to verify it fails** — `apps/api/.venv/Scripts/pytest scripts/install/tests/test_i18n.py -v` → FAIL (module missing)

- [ ] **Step 3: Implement `i18n.py`**

```python
"""Bilingual (en/fr) message catalog for the installer wizard.

Deliberately outside the frontend 6-locale i18n scope: this is a server-side
operator tool (see ADR-179).
"""

_current_language = "en"

MESSAGES: dict[str, dict[str, str]] = {
    "welcome": {
        "en": "LIA self-host installer — a few questions, then a working instance.",
        "fr": "Installateur LIA — quelques questions, puis une instance fonctionnelle.",
    },
    "build_warning": {
        "en": "Building images from source now. This takes 10-30 minutes (longer on ARM).",
        "fr": "Construction des images depuis les sources. Comptez 10 à 30 minutes (plus sur ARM).",
    },
    # Every module adds its ids here as it is implemented (Tasks 5-12).
}


def set_language(lang: str) -> None:
    """Switch the wizard language ('en' or 'fr')."""
    global _current_language
    if lang not in ("en", "fr"):
        raise ValueError(f"unsupported wizard language: {lang}")
    _current_language = lang


def tr(msg_id: str, **kwargs: object) -> str:
    """Translate a message id in the current language, formatting kwargs."""
    return MESSAGES[msg_id][_current_language].format(**kwargs)
```

- [ ] **Step 4: Run to verify it passes** — same command → 3 PASS
- [ ] **Step 5: Checkpoint — propose commit** `feat(installer): wizard package skeleton with en/fr i18n`

---

### Task 5: Question catalog + validators + anti-drift guard #1

**Files:**
- Create: `scripts/install/questions.py`
- Test: `scripts/install/tests/test_questions.py`, `scripts/install/tests/test_env_keys_guard.py`

**Interfaces:**
- Produces:

```python
Answers = dict[str, str]                     # key -> raw string answer

@dataclass(frozen=True)
class Question:
    key: str                                 # env key, or "_"-prefixed wizard-internal key
    prompt_id: str                           # i18n message id
    kind: str = "text"                       # "text" | "secret" | "choice" | "bool"
    choices: tuple[str, ...] = ()
    default: str | None = None
    required: bool = False
    validate: Callable[[str], str | None] | None = None   # -> error msg id or None
    condition: Callable[[Answers], bool] | None = None    # ask only when True

@dataclass(frozen=True)
class Section:
    section_id: str
    title_id: str
    optional: bool                           # gated by "Configure X? [y/N]"
    questions: tuple[Question, ...]

SECTIONS: tuple[Section, ...]
PROVIDER_ENV_KEYS: dict[str, str]            # provider -> env key (mirrors adapter.py)
GENERATED_SECRET_KEYS: tuple[str, ...]
def iter_questions(section: Section, answers: Answers) -> Iterator[Question]
def validate_email(v: str) -> str | None
def validate_domain(v: str) -> str | None
def validate_password(v: str) -> str | None  # UX mirror of the backend policy
```

- Consumes: `i18n.tr` (Task 4).

Key content decisions (all evidence-backed, encode them exactly):

- `PROVIDER_ENV_KEYS` mirrors `apps/api/src/infrastructure/llm/providers/adapter.py:43-51`: `{"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY", "deepseek": "DEEPSEEK_API_KEY", "perplexity": "PERPLEXITY_API_KEY", "gemini": "GOOGLE_GEMINI_API_KEY", "ollama": "OLLAMA_BASE_URL", "qwen": "QWEN_API_KEY"}`.
- Mandatory sections: `core` (in order: `_wizard_lang` choice en/fr; `_exposure` choice `lan`/`proxy`/`caddy`; `_server_host` text, condition exposure==lan; `_domain_web` + `_domain_api` domain-validated, condition exposure!=lan; `_caddy_email` email-validated, condition exposure==caddy; `_admin_email` email; `_admin_password` secret + password policy; `_admin_name` default "Admin"; `DEFAULT_LANGUAGE` choice `fr,en,es,de,it,zh-CN` default `fr`; `_primary_provider` choice of the 7; one provider-key secret question per chosen provider using `PROVIDER_ENV_KEYS` — for `ollama` a text URL, default `http://host.docker.internal:11434/v1`).
- Optional sections: `google` (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` secret, `GOOGLE_API_KEY` secret non-required); `microsoft` (`MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET` secret); `telegram` (`TELEGRAM_BOT_TOKEN` secret); `observability` (`_observability_full` bool default no).
- `GENERATED_SECRET_KEYS = ("SECRET_KEY", "FERNET_KEY", "POSTGRES_PASSWORD", "REDIS_PASSWORD", "GRAFANA_ADMIN_PASSWORD", "GRAFANA_PRODUCT_DB_PASSWORD")`.
- Password mirror: ≥10 chars, ≥2 uppercase, ≥2 digits, ≥2 specials — mirrors `apps/api/src/core/security/password_validation.py` (UX only; the backend stays the authority at `create_admin` time).

- [ ] **Step 1: Write failing tests** — `test_questions.py` (conditions: LAN answers hide domain questions and show `_server_host`; caddy shows `_caddy_email`; provider choice yields exactly one key question; password validator accepts `Xx12!!abcdA` shape and rejects `short1!`), plus the guard:

```python
"""Anti-drift guard #1: every env key the wizard writes exists in .env.prod.example."""

import re
from pathlib import Path

from scripts.install import questions

REPO_ROOT = Path(__file__).resolve().parents[3]
TEMPLATE = (REPO_ROOT / ".env.prod.example").read_text(encoding="utf-8")


def _template_keys() -> set[str]:
    return set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]+)=", TEMPLATE, flags=re.MULTILINE))


def test_all_question_env_keys_exist_in_template() -> None:
    keys = _template_keys()
    for section in questions.SECTIONS:
        for q in section.questions:
            if not q.key.startswith("_"):
                assert q.key in keys, f"question key {q.key} missing from .env.prod.example"


def test_all_generated_secret_keys_exist_in_template() -> None:
    keys = _template_keys()
    for key in questions.GENERATED_SECRET_KEYS:
        assert key in keys, f"generated secret {key} missing from .env.prod.example"
```

- [ ] **Step 2: Run to verify failure** → module missing.
- [ ] **Step 3: Implement `questions.py`** per the interface block above (declarative data + the three validators; email regex `^[^@\s]+@[^@\s]+\.[^@\s]+$`, domain regex `^(?!-)[a-z0-9-]{1,63}(\.[a-z0-9-]{1,63})+$` case-insensitive).
- [ ] **Step 4: Run tests** → PASS. If the guard reveals a key absent from `.env.prod.example` (e.g. `ANTHROPIC_API_KEY` — likely, only OpenAI/Gemini keys exist today at lines 395/344): **add the missing keys to `.env.prod.example`** in the `[LLM]` block as documented empty entries (e.g. `# ANTHROPIC_API_KEY=` with a one-line comment referencing the adapter fallback). The template gains truth; the guard then passes both ways.
- [ ] **Step 5: Checkpoint — propose commit** `feat(installer): declarative question catalog with env-template drift guard`

---

### Task 6: Answer collection

**Files:**
- Create: `scripts/install/answers.py`
- Test: `scripts/install/tests/test_answers.py`

**Interfaces:**
- Produces:

```python
@dataclass
class IOAdapter:                      # injectable for tests
    input_fn: Callable[[str], str] = input
    getpass_fn: Callable[[str], str] = getpass.getpass
    print_fn: Callable[[str], None] = print

def collect_interactive(sections: Sequence[Section], io: IOAdapter) -> Answers
def load_answers_file(path: Path) -> Answers     # KEY=value lines, "#" comments
def collect(sections, *, io, answers_file: Path | None) -> Answers
```

- Consumes: `Section`, `Question`, `iter_questions`, validators (Task 5); `tr` (Task 4).

Behavior to implement and test: optional sections asked as `[y/N]` and skipped by default; empty input takes `default`; `required` questions loop until non-empty; a `validate` failure prints the translated error and re-asks; `secret` questions use `getpass_fn`; answers-file mode fills answers then falls back to interactive **only** for missing required keys (and raises `MissingAnswerError` listing them when `io is None`, i.e. `--non-interactive`).

- [ ] **Step 1: Failing tests** — scripted `IOAdapter` with a queue of canned inputs; cover: full LAN happy path produces expected `Answers` dict; invalid email re-asks; optional section skipped on Enter; answers-file + missing required raises listing `_admin_password`.
- [ ] **Step 2: Verify failure** → module missing.
- [ ] **Step 3: Implement** (~120 lines).
- [ ] **Step 4: Verify pass** — `apps/api/.venv/Scripts/pytest scripts/install/tests -q` all green.
- [ ] **Step 5: Checkpoint — propose commit** `feat(installer): interactive and file-based answer collection`

---

### Task 7: `.env` generation

**Files:**
- Create: `scripts/install/envgen.py`
- Test: `scripts/install/tests/test_envgen.py`

**Interfaces:**
- Produces:

```python
def generate_secrets() -> dict[str, str]
    # SECRET_KEY: secrets.token_urlsafe(48); FERNET_KEY:
    # base64.urlsafe_b64encode(os.urandom(32)).decode(); passwords: token_urlsafe(24)
def derive_env(answers: Answers, secrets_map: dict[str, str]) -> dict[str, str]
    # answers + scenario-derived URL/cookie/CORS keys + COMPOSE_PROFILES
def render_env(base_template: str, env: dict[str, str]) -> str
    # replace matching KEY= lines in .env.min.prod content; append a
    # "# --- Added by installer ---" block for keys absent from the base;
    # comment out any surviving CHANGE_ME line (rule: no CHANGE_ME survives)
def write_env(path: Path, content: str) -> Path | None
    # timestamped .env.backup.YYYYmmdd_HHMMSS first if path exists; chmod 0o600
```

- Consumes: `Answers`, `GENERATED_SECRET_KEYS` (Task 5).

Scenario derivations (exact — `.env.min.prod` keys, verified):

| Key | lan | proxy / caddy |
|---|---|---|
| `FRONTEND_URL`, `NEXT_PUBLIC_APP_URL` | `http://{_server_host}:3000` | `https://{_domain_web}` |
| `API_URL`, `NEXT_PUBLIC_API_URL`, `API_URL_SERVER` | `http://{_server_host}:8000` | `https://{_domain_api}` |
| `CORS_ORIGINS` | `http://{_server_host}:3000` | `https://{_domain_web}` |
| `SESSION_COOKIE_SECURE` | `false` (explicit value is honored in production — `config/__init__.py:215-233`) | `true` |
| `SESSION_COOKIE_DOMAIN` | *omit line* (host-only cookie) | longest common dot-suffix of the two domains prefixed with `.`; omit if none |
| `COMPOSE_PROFILES` | only when `_observability_full == "yes"`: `observability` | idem |
| `NEXT_PUBLIC_GOOGLE_CLIENT_ID` | copy of `GOOGLE_CLIENT_ID` when the google section was filled | idem |

- [ ] **Step 1: Failing tests** — `generate_secrets` returns all `GENERATED_SECRET_KEYS`, FERNET value is 44-char urlsafe base64, two calls differ; `derive_env` LAN vs caddy tables above (assert exact values); `render_env` golden test on a 15-line mini-base fixture (inline string in the test, NOT a copy of `.env.min.prod`) asserting replacement, appended block, and zero `CHANGE_ME` outside comments; `write_env` creates `0o600` (skip mode assert on Windows: `sys.platform != "win32"`) and backs up an existing file without data loss.
- [ ] **Step 2: Verify failure.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Verify pass.**
- [ ] **Step 5: Checkpoint — propose commit** `feat(installer): env generation with auto-secrets and scenario-derived URLs`

---

### Task 8: Compose override + Caddyfile

**Files:**
- Create: `scripts/install/compose.py`, `infrastructure/caddy/Caddyfile.template`
- Test: `scripts/install/tests/test_compose.py`

**Interfaces:**
- Produces:

```python
OVERRIDE_FILENAME = "docker-compose.install.yml"
CADDYFILE_PATH = Path("infrastructure/caddy/Caddyfile")   # generated, gitignored
def build_override(answers: Answers) -> str | None   # None for "proxy" (loopback base is already right)
def build_caddyfile(answers: Answers, template: str) -> str
def compose_file_args(answers: Answers) -> list[str]
    # ["-f", "docker-compose.prod.yml"] + (["-f", OVERRIDE_FILENAME] if override)
```

- Consumes: `Answers` (Task 5). Task 11 consumes `compose_file_args`.

Override content (exact):

- `lan` — republish on all interfaces using the compose v2.24 `!override` list tag (appending would clash with the loopback binds in the base):

```yaml
services:
  web:
    ports: !override ["3000:3000"]
  api:
    ports: !override ["8000:8000", "127.0.0.1:9091:9091"]
```

- `caddy` — add the proxy on the compose network (web/api keep their loopback binds; Caddy reaches them via service DNS):

```yaml
services:
  caddy:
    image: caddy:2-alpine
    container_name: lia-caddy
    restart: unless-stopped
    ports: ["80:80", "443:443"]
    volumes:
      - ./infrastructure/caddy/Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    networks: [lia-network]
volumes:
  caddy_data:
  caddy_config:
```

`Caddyfile.template` (placeholders `{domain_web}`, `{domain_api}`, `{acme_email}`):

```
{
    email {acme_email}
}
{domain_web} {
    reverse_proxy web:3000
}
{domain_api} {
    reverse_proxy api:8000
}
```

- [ ] **Step 1: Failing tests** — proxy → `build_override` returns `None` and `compose_file_args` has one `-f`; lan → YAML parses (note: `yaml.safe_load` rejects the `!override` tag — assert on the rendered *string* containing `ports: !override` instead) ; caddy → override parses, Caddyfile contains both domains and the email.
- [ ] **Step 2: Verify failure.** **Step 3: Implement.** **Step 4: Verify pass.**
- [ ] **Step 5: Checkpoint — propose commit** `feat(installer): exposure-scenario compose override and Caddy provisioning`

---

### Task 9: Preflight checks

**Files:**
- Create: `scripts/install/preflight.py`
- Test: `scripts/install/tests/test_preflight.py`

**Interfaces:**
- Produces:

```python
@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str

Runner = Callable[[list[str]], "subprocess.CompletedProcess[str]"]   # injectable
def run_base_checks(runner: Runner) -> list[CheckResult]
    # docker present + daemon reachable (`docker info`), compose >= 2.24
    # (parse `docker compose version --short`), disk >= 10 GiB free on cwd
def run_scenario_checks(answers: Answers, runner: Runner) -> list[CheckResult]
    # lan: ports 3000/8000 free; caddy: ports 80/443 free (socket bind probe)
def all_ok(results: list[CheckResult]) -> bool
```

- [ ] **Step 1: Failing tests** — fake runner returning canned outputs: compose `2.23.0` → not ok with detail mentioning `2.24`; compose `2.32.1` → ok; docker daemon down (returncode 1) → not ok; port probe against a socket the test binds itself → not ok.
- [ ] **Step 2-4: red → implement → green.**
- [ ] **Step 5: Checkpoint — propose commit** `feat(installer): preflight system checks`

---

### Task 10: LLM key verification

**Files:**
- Create: `scripts/install/verify.py`
- Test: `scripts/install/tests/test_verify.py`

**Interfaces:**
- Produces:

```python
class VerifyOutcome(Enum): OK; INVALID; UNSUPPORTED; NETWORK_ERROR
def verify_provider_key(provider: str, key_or_url: str, *,
                        opener: Callable[..., Any] = urllib.request.urlopen,
                        timeout: float = 10.0) -> VerifyOutcome
```

Endpoints (GET, cheap, list-models — no token spend):

| provider | request |
|---|---|
| openai | `https://api.openai.com/v1/models`, header `Authorization: Bearer <key>` |
| anthropic | `https://api.anthropic.com/v1/models`, headers `x-api-key: <key>`, `anthropic-version: 2023-06-01` |
| gemini | `https://generativelanguage.googleapis.com/v1beta/models?key=<key>` |
| deepseek | `https://api.deepseek.com/models`, Bearer |
| qwen | `https://dashscope-us.aliyuncs.com/compatible-mode/v1/models`, Bearer |
| ollama | `<url>/models` (OpenAI-compatible base URL, no auth) |
| perplexity | **UNSUPPORTED** (no free listing endpoint — wizard prints "cannot verify, continuing") |

HTTP 200 → OK; 401/403 → INVALID; URLError/timeout → NETWORK_ERROR (wizard warns but continues — a firewalled build host must not block installation).

- [ ] **Step 1: Failing tests** — fake opener asserting the exact URL + headers per provider, returning 200/401 stubs; perplexity → UNSUPPORTED without any call; URLError → NETWORK_ERROR.
- [ ] **Step 2-4: red → implement → green.**
- [ ] **Step 5: Checkpoint — propose commit** `feat(installer): optional pre-build LLM key verification`

---

### Task 11: State machine + deploy orchestration

**Files:**
- Create: `scripts/install/state.py`, `scripts/install/deploy.py`
- Test: `scripts/install/tests/test_state.py`, `scripts/install/tests/test_deploy.py`

**Interfaces:**
- Produces (`state.py`):

```python
STEPS = ("preflight", "questions", "generate", "build", "validate", "start", "bootstrap", "report")
@dataclass
class InstallState:
    completed: list[str]
    exposure: str | None = None
    admin_email: str | None = None          # NOT secret; password is never stored
    observability: bool = False
def load_state(path: Path) -> InstallState   # missing file -> fresh state
def save_state(path: Path, state: InstallState) -> None
def next_step(state: InstallState) -> str | None
```

- Produces (`deploy.py`) — every function takes `runner: Runner` (Task 9's type) and `compose_args: list[str]` (Task 8):

```python
def run_build(compose_args, runner, *, env: dict[str, str]) -> None
    # docker compose <args> build ; env carries APP_VERSION/GIT_COMMIT_SHA/BUILD_DATE
    # derived from `git describe --tags --always` + `git rev-parse HEAD` + UTC now,
    # each falling back to "unknown" when git is absent (ZIP download install)
def run_validate(compose_args, runner) -> None
    # docker compose <args> run --rm --no-deps --entrypoint "" api
    #   python -m scripts.validate_settings          <- Task 1's contract
def run_up(compose_args, runner) -> None             # up -d
def wait_ready(url: str, *, opener=urllib.request.urlopen,
               timeout_s: int = 300, interval_s: int = 5) -> bool
    # poll http://127.0.0.1:8000/ready (apps/api/src/api/health.py:119)
def run_create_admin(compose_args, runner, *, email: str, password: str, name: str) -> None
    # docker compose <args> exec -T api python -m scripts.data.create_admin
    #   --email <email> --password <password> --name <name>
class StepFailed(RuntimeError):  # message = translated, actionable, includes resume hint
```

- [ ] **Step 1: Failing tests** — state round-trip via tmp_path; `next_step` ordering and completion; a canned `runner` recording argv: `run_validate` argv contains `--no-deps` **and** `--entrypoint` `""`; `run_create_admin` argv passes the three flags and uses `exec -T`; `wait_ready` with a fake opener flipping 503→200 returns True, all-503 returns False after simulated timeout (inject a fake clock via `interval_s=0`); non-zero returncode raises `StepFailed` whose message contains `--resume`; **no secret in saved state**: `save_state` output for a state built from answers must not contain a canary password string.
- [ ] **Step 2-4: red → implement → green.**
- [ ] **Step 5: Checkpoint — propose commit** `feat(installer): resumable state machine and deploy orchestration`

---

### Task 12: Entry point, report, bootstrap script, gitignore

**Files:**
- Create: `scripts/install/__main__.py`, `scripts/install/report.py`, `install.sh`
- Modify: `.gitignore`
- Test: `scripts/install/tests/test_main_flow.py`, `scripts/install/tests/test_install_sh.py`

**Interfaces:**
- Produces: CLI `python3 -m scripts.install [--lang fr|en] [--non-interactive --answers FILE] [--resume] [--dry-run]`. `--dry-run` stops after `generate` (guard #2 and CI use it). `report.render(answers, secrets_map, state) -> str` returns the final summary (URLs, one-time credentials, post-install checklist: Google redirect URIs, DNS, non-OpenAI LLM slot warning, voice/image pointers).
- Consumes: everything from Tasks 4-11.

`__main__.py` flow (the only place steps chain):

```python
def run(argv: list[str]) -> int:
    args = parse_args(argv)
    i18n.set_language(args.lang)
    state = load_state(STATE_PATH) if args.resume else InstallState(completed=[])
    # menu on existing .env without --resume: resume / reconfigure / reinstall / abort
    for step in STEPS:
        if step in state.completed:
            continue
        _run_step(step, args, state)          # dispatch table, saves state after each
        if args.dry_run and step == "generate":
            return 0
    return 0
```

`install.sh` (complete):

```sh
#!/bin/sh
# LIA self-host installer bootstrap. Checks prerequisites, then hands over to
# the stdlib-only Python wizard (scripts/install). See ADR-179.
set -eu
cd "$(dirname "$0")"

fail() { printf 'ERROR: %s\n' "$1" >&2; exit 1; }

command -v docker >/dev/null 2>&1 || fail "docker is required (https://docs.docker.com/engine/install/)"
docker compose version >/dev/null 2>&1 || fail "docker compose v2 plugin is required"
command -v python3 >/dev/null 2>&1 || fail "python3 (>= 3.10) is required"
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' \
    || fail "python3 >= 3.10 is required"

[ "${1:-}" = "--check-only" ] && { echo "prerequisites OK"; exit 0; }
exec python3 -m scripts.install "$@"
```

`.gitignore` additions:

```
# Self-host installer artifacts (ADR-179)
.install-state.json
install.log
docker-compose.install.yml
infrastructure/caddy/Caddyfile
```

- [ ] **Step 1: Failing tests** — `test_main_flow.py`: end-to-end `--non-interactive --answers <tmp file> --dry-run` in a tmp repo-root fixture (copies `.env.min.prod` into tmp, monkeypatches the module's path constants) produces a `.env` containing the admin's DEFAULT_LANGUAGE and generated SECRET_KEY, exits 0, and state file contains `"generate"`; second run with `--resume` skips straight past `generate` (assert via injected recording step-dispatch). `test_install_sh.py` (skip on Windows: `@pytest.mark.skipif(sys.platform == "win32", ...)`): run `sh install.sh --check-only` with a PATH-stubbed fake `docker`/`python3` → exit 0; without `docker` on PATH → exit 1 and "docker is required" on stderr.
- [ ] **Step 2-4: red → implement → green.** Run the whole suite: `apps/api/.venv/Scripts/pytest scripts/install/tests -q`.
- [ ] **Step 5: Checkpoint — propose commit** `feat(installer): CLI entry point, final report, install.sh bootstrap`

---

### Task 13: Anti-drift guard #2 — default answers boot the real Settings

**Files:**
- Test: `apps/api/tests/unit/test_installer_default_env_guard.py`

**Interfaces:**
- Consumes: `envgen.derive_env`, `envgen.generate_secrets`, `questions.SECTIONS` (defaults), `render_env`, and the real `.env.min.prod`.

- [ ] **Step 1: Write the test** (this one is red only if the pipeline is broken — write it, watch it pass, then mutate a required key locally to prove it can fail, revert):

```python
"""Anti-drift guard #2 (ADR-179): the installer's default output boots Settings.

A release adding a mandatory setting without a default turns this red,
forcing the wizard/template update in the same change. Runs in ci:fast:
Pydantic validation needs no service.
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from scripts.install import envgen, questions  # noqa: E402


def _default_answers() -> dict[str, str]:
    answers: dict[str, str] = {
        "_wizard_lang": "en", "_exposure": "lan", "_server_host": "192.168.1.50",
        "_admin_email": "admin@example.com", "_admin_password": "Xx12!!abcdA",
        "_admin_name": "Admin", "DEFAULT_LANGUAGE": "fr",
        "_primary_provider": "openai", "OPENAI_API_KEY": "sk-guard-not-a-real-key",
    }
    return answers


def test_default_env_boots_settings(tmp_path: Path) -> None:
    env_map = envgen.derive_env(_default_answers(), envgen.generate_secrets())
    content = envgen.render_env(
        (REPO_ROOT / ".env.min.prod").read_text(encoding="utf-8"), env_map
    )
    env_file = tmp_path / ".env"
    env_file.write_text(content, encoding="utf-8")
    # Isolated interpreter: only the generated file, no inherited env leakage.
    result = subprocess.run(
        [sys.executable, "-c",
         "import os, sys; sys.path.insert(0, 'apps/api'); "
         f"os.environ.setdefault('ENV_FILE', r'{env_file}'); "
         "import src.core.config"],
        cwd=REPO_ROOT, capture_output=True, text=True,
        env={"PATH": "", "ENV_FILE": str(env_file)},
        timeout=120,
    )
    assert result.returncode == 0, f"Settings rejected the generated env:\n{result.stderr}"
```

  **Implementation note (resolve while writing):** check how `src.core.config` locates its env file (`model_config`/`SettingsConfigDict(env_file=...)`). If it hardcodes `.env` relative to cwd, run the subprocess with `cwd=tmp_path` and copy the minimal `sys.path` bootstrap accordingly; if an `ENV_FILE` override doesn't exist, pass the parsed key/values directly in the subprocess `env=` dict instead. The assertion contract (generated env ⇒ Settings boots in an isolated process) is what matters, not the injection mechanism.

- [ ] **Step 2: Prove both directions** — run green; then temporarily set `"DEFAULT_LANGUAGE": "xx"` (invalid literal) and confirm red; revert.
- [ ] **Step 3: Checkpoint — propose commit** `test(installer): guard — default wizard output must boot the real Settings`

---

### Task 14: Taskfile + CI wiring

**Files:**
- Modify: `Taskfile.yml`, `.github/workflows/ci.yml`

- [ ] **Step 1: Add tasks** (imitating `test:deploy` at Taskfile.yml:493 — platform-split venv commands):

```yaml
  test:install:
    desc: Self-host installer wizard suite (hermetic, stdlib module — ADR-179)
    cmds:
      - cmd: apps/api/.venv/Scripts/pytest scripts/install/tests -q
        platforms: [windows]
      - cmd: apps/api/.venv/bin/pytest scripts/install/tests -q
        platforms: [linux, darwin]

  lint:install:
    desc: MyPy strict + Ruff over the installer wizard (stdlib-only module)
    cmds:
      - cmd: apps/api/.venv/Scripts/python -m mypy --strict scripts/install --exclude scripts/install/tests
        platforms: [windows]
      - cmd: apps/api/.venv/bin/python -m mypy --strict scripts/install --exclude scripts/install/tests
        platforms: [linux, darwin]
      - cmd: apps/api/.venv/Scripts/python -m ruff check scripts/install
        platforms: [windows]
      - cmd: apps/api/.venv/bin/python -m ruff check scripts/install
        platforms: [linux, darwin]
```

- [ ] **Step 2: Wire them** — add `- task: test:install` and `- task: lint:install` to the `ci:fast` cmds list (Taskfile.yml:1353-1364); add a CI step next to the `task test:deploy` step (ci.yml:505):

```yaml
      - name: Installer wizard suite
        run: task test:install
      - name: Installer wizard lint
        run: task lint:install
```

- [ ] **Step 3: Verify gates** — `task test:install`, `task lint:install`, `task lint:ci-parity` (new steps are task calls — must pass), `task test:markers` (scripts/install/tests are outside the apps/api marker scan; confirm it still passes untouched).
- [ ] **Step 4: Checkpoint — propose commit** `ci(installer): wire test:install and lint:install into ci:fast and the workflow`

---

### Task 15: Documentation + ADR-179

**Files:**
- Create: `docs/architecture/ADR-179-Self-Host-Installer.md`
- Modify: `docs/GETTING_STARTED.md`, `README.md`, `docs/INDEX.md`, `docs/architecture/ADR_INDEX.md`

- [ ] **Step 1: Write ADR-179** — sections: Context (manual 740-setting journey), Decision (CLI wizard, stdlib, build-local, guided exposure, delegated validation), the compose-profiles change (with the maintainer migration note from Task 2), the DevOps-overlay extraction (with Task 3's socket decision recorded), out-of-scope v1 list, and the **release directive** verbatim:

```markdown
## Release directive (installability)

At every release, verify the release remains installable from scratch:
1. A new mandatory setting or changed default -> update `scripts/install/envgen.py` and `.env.min.prod`.
2. A new optional integration relevant to self-hosters -> add a section in `scripts/install/questions.py`.
3. A new compose service -> decide core vs `observability` profile; update `scripts/install/compose.py` and the profile guard.
4. A new seed or bootstrap step -> update `scripts/install/deploy.py`.
5. A boot-path change (migrations, `/ready`, entrypoint) -> update `scripts/install/deploy.py` and the GETTING_STARTED install section.
Finish with `task test:install` and the default-env Settings guard: both green before tagging.
```

- [ ] **Step 2: GETTING_STARTED** — insert a "One-command production install" subsection at the top of *Step-by-Step Installation* (clone → `./install.sh` → what the wizard asks → where the manual path still applies). README: 4-line quickstart block in the installation section. `docs/INDEX.md` + `ADR_INDEX.md`: one line each for ADR-179.
- [ ] **Step 3: Run** `task lint:docs` → 0 broken links.
- [ ] **Step 4: Checkpoint — propose commit** `docs(installer): ADR-179, one-command install guide, release directive`

---

### Task 16: Full gates + runtime proof

- [ ] **Step 1:** `task lint` → exit 0 (includes lint:install via ci:fast wiring? No — `lint` and `ci:fast` are distinct: verify `lint:install` is reachable from the gate the team actually runs; if `task lint` does not include it, add `- task: lint:install` to the `lint` task's cmds as well).
- [ ] **Step 2:** `task test:backend:unit:fast` → green (Tasks 1, 2, 13 tests included).
- [ ] **Step 3:** `task ci:fast` → green, full output captured.
- [ ] **Step 4 (runtime proof, per project rule "never 'done' without runtime evidence"):** on the dev machine, run `sh install.sh --check-only` (Git Bash) → "prerequisites OK"; then `python3 -m scripts.install --non-interactive --answers <sample file> --dry-run` from a scratch copy → inspect the generated `.env` and override by hand. Full end-to-end (build + up) is validated on a disposable Linux host or VM — **not** on the production Pi.
- [ ] **Step 5: Checkpoint — propose the release-readiness summary to the user** (gates output + generated-artifact samples), then the final commit series on their green light.

---

## Self-Review (performed while writing)

- **Spec coverage:** every spec section maps to a task — architecture/modules (4-12), validation delegation (1, 11), profiles (2), DevOps overlay (3), questionnaire incl. turnkey-OpenAI nuance (5, 12-report), exposure scenarios (7, 8), idempotence/resume (11, 12), security posture (7 chmod/backup, 11 no-secret state), guards (5, 13), tests/CI (14), docs+directive (15), out-of-scope stated in ADR (15).
- **Placeholder scan:** the two deliberate decision gates (Task 3 Step 1 socket investigation; Task 13 env-injection mechanism) carry explicit decision rules and both possible outcomes — they are contingencies, not placeholders.
- **Type consistency:** `Runner` defined once (Task 9) and consumed by Task 11; `compose_file_args` (Task 8) consumed by Task 11; `Answers` (Task 5) used everywhere; `main() -> int` contract of Task 1 consumed verbatim by `run_validate`.
