# Post-3.14 Follow-ups Implementation Plan (v1.31.1)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (inline — subagents excluded by project rule). Checkbox steps.

**Goal:** Close the five debts surfaced by the ADR-241 migration: runtime provenance neutralized by the prod `.env`, 16 container-hostile repo guards, 3 zombie-skipped multiprocess tests, the 3.16-horizon asyncio deprecations, and the dead dependencies (passlib/slowapi).

**Evidence base (all verified 2026-08-21, this session):**
- **A — Provenance:** the F030 build chain WORKS end to end (compose `build.args` at [docker-compose.prod.yml:141-143](../../docker-compose.prod.yml), `provenance.env` written by prepare-prod.ps1:568-571, sourced by the generated deploy.sh:11; the built image carries `APP_VERSION=1.31.0` + real SHA — probed on the Pi). The runtime values are then **overwritten at `up` by `env_file: .env`**: the real `.env.prod` pins `APP_VERSION=0.0.0-dev`, `GIT_COMMIT_SHA=unknown`, `BUILD_DATE=unknown` (copied from the example). Same failure class as the v1.25.25 sandbox path.
- **B — parents[4] guards:** `tests/_repo_paths.py` exists precisely for this (its docstring names the flat `/app` mount); ~12 files still compute `REPO_ROOT = Path(__file__).resolve().parents[4]` at module level (16 collection errors measured in-container), plus 4 inline recomputations in `test_demo_instance_edge_allowlist.py`. `conftest.py:51`'s second `parents[3]` is a **verified false positive** (guarded by `not os.path.exists("/.dockerenv")`) — leave it.
- **C — Multiprocess zombies:** `pytest._redis_available` is read by 3 skipifs and set **nowhere** — permanently skipped since 2025-11, invisible to the permanent-skip guard (not in `permanent_skips_allowlist.json`) because the skip looks conditional. Proven green on 3.14 forkserver when force-enabled (×2 container runs).
- **D — asyncio deprecations:** (d1) `asyncio.iscoroutinefunction` ×3 (observability profiling.py:48, decorators.py:147/368) — `inspect.iscoroutinefunction` proven equivalent incl. `functools.partial` (True/True probe). (d2) `asyncio.get_event_loop()` in `sherpa_stt.py:296` (async context ✓) and `oauth_lock.py:82/110/124` (verify async at implementation). (d3) the `set_event_loop_policy(WindowsSelectorEventLoopPolicy())` block in main.py is **proven redundant**: uvicorn 0.48 `Server.run → asyncio_run(loop_factory=config.get_loop_factory())` and `uvicorn/loops/asyncio.py` returns `asyncio.SelectorEventLoop` on win32 — no policy involved. bootstrap.py:219 `get_event_loop_policy()` is logging-only.
- **E — Dead deps:** zero `passlib`/`slowapi` imports anywhere in apps/api (grep). **bcrypt reaches the lock ONLY `# via passlib`** — it is imported directly by `src/core/security/utils.py`, so removing passlib without declaring bcrypt would break auth at install. `limits==5.8.0` is slowapi-only. `types-passlib` is dev-only.
- **F (optional) — pydantic shadow warnings:** `MCPToolInput` is a **dynamic `create_model`** ([tool_adapter.py:138](../../apps/api/src/infrastructure/mcp/tool_adapter.py)) over field names declared by the REMOTE MCP server — `json`/`schema` are third-party wire names, never renameable; the fix is automatic aliasing for BaseModel-reserved names.

**Global constraints:** clean tree at start (post-v1.31.0); ADR-112 for Lot 5 (one lock regen); ratchets shrink-only; no git actions without explicit consent; release = **v1.31.1** (CHANGELOG + FAQ key ×6 + version surfaces per reference_release_surfaces); every lot ends with its own oracle green, `task ci:fast` before handing back.

---

### Lot 1 — Runtime provenance: the generated deploy.sh upserts the three keys into `.env`

**Files:** Modify `scripts/deploy/prepare-prod.ps1` (generated deploy.sh here-string, after the `provenance.env` sourcing line); Modify `scripts/deploy/deploy-prod.Tests.ps1` (Pester); untracked `.env.prod`: delete the three dead lines (belt) — the upsert is the braces.

- [x] **Step 1 (TDD):** Add a Pester test: the generated deploy.sh contains an upsert block for the three keys, and running it against a fixture `.env` containing `APP_VERSION=0.0.0-dev` leaves the file with the provenance values (and appends when a key is absent; idempotent on re-run).
- [x] **Step 2:** In the generated deploy.sh, right after `[ -f "provenance.env" ] && . ./provenance.env`, emit:

```sh
# F030: env_file:.env would override the image's provenance ENV at `up` —
# make .env agree with the build instead of silently losing (v1.31.0 shipped
# as 0.0.0-dev because of exactly this).
if [ -f "provenance.env" ] && [ -f ".env" ]; then
    for kv in "APP_VERSION=$APP_VERSION" "GIT_COMMIT_SHA=$GIT_COMMIT_SHA" "BUILD_DATE=$BUILD_DATE"; do
        k="${kv%%=*}"
        if grep -q "^${k}=" .env; then
            sed -i "s|^${k}=.*|${kv}|" .env
        else
            printf '%s\n' "${kv}" >> .env
        fi
    done
fi
```

Edge cases covered: key present (replace, `|` delimiter — SHA contains no `|`), key absent (append with trailing newline), file without final newline (`printf`), idempotence, `.env` absent (no-op).
- [x] **Step 3:** Run the Pester suite (`task test:deploy`) → green (61 + new). Delete the three dead lines from the local `.env.prod`.
- [x] **Step 4:** Oracle at next deploy: `docker exec lia-api-prod env | grep APP_VERSION` shows the release version. Checkpoint commit `fix(deploy): stop env_file from erasing the image's build provenance (F030)`.

### Lot 2 — Repo-level guards use `repo_root_or_skip()`

**Files:** the ~12 modules computing `parents[4]` at module level (exact list from `git grep -n "parents\[4\]" apps/api/tests`) + the 4 inline recomputations in `test_demo_instance_edge_allowlist.py` (hoist to the module constant). No behavior change on host/CI: `repo_root_or_skip()` returns the same root there.

- [x] **Step 1 (TDD/oracle first):** record the current failure: `docker exec lia-api-dev pytest tests/ --collect-only -q -p no:cacheprovider` → 16 collection errors.
- [x] **Step 2:** In each file, replace `REPO_ROOT = Path(__file__).resolve().parents[4]` (and variants like `CADDYFILE = ...parents[4] / ...`) with `from tests._repo_paths import repo_root_or_skip` + `REPO_ROOT = repo_root_or_skip()` (derive sub-paths from it). Hoist the 4 inline `parents[4]` in `test_demo_instance_edge_allowlist.py` to the module constant.
- [x] **Step 3:** Host proof: the same guards still RUN (`pytest <the 12 files> -q --no-cov` → same test count as before, all green — no new silent skips on deep layouts). Container proof: collect-only errors 16 → 0 (the modules now skip cleanly like the other 29).
- [x] **Step 4:** `task test:backend:unit:fast` green. Checkpoint `test(guards): repo-level guards go through repo_root_or_skip (in-container collection clean)`.

### Lot 3 — De-zombify the multiprocess tests

**Files:** `tests/integration/test_redis_limiter_multiprocess.py`.

- [x] **Step 1:** Remove the three `@pytest.mark.skipif(not hasattr(pytest, "_redis_available")...)` decorators (the attribute is set nowhere — the tests have been green-by-absence since 2025-11). Update the class docstring: services are the `integration` contract (preflight guarantees them); the suite runs via explicit `pytest -m multiprocess` and stays out of PR CI by the F006 allowlist (unchanged).
- [x] **Step 2:** Oracles: dev container `pytest tests/integration/test_redis_limiter_multiprocess.py -q --no-cov` → 3 passed (forkserver, already proven); Windows host with dev Redis up → 3 passed (spawn). `task test:markers` green; `git status` shows **no change** to `marker_coverage_allowlist.json` (the v1.25.20 hook-append trap).
- [x] **Step 3:** Checkpoint `test(integration): multiprocess suite runs again — the _redis_available gate was never set by anyone`.

### Lot 4 — asyncio deprecations (removal horizon 3.16)

**Files:** `src/infrastructure/observability/profiling.py`, `.../decorators.py` (×2 sites); `src/domains/voice/stt/sherpa_stt.py`; `src/infrastructure/locks/oauth_lock.py`; `src/main.py` (delete the policy block); `src/core/bootstrap.py` (log without policy API).

- [x] **Step 1:** Count the baseline: `task test:backend:unit:fast` output currently carries ~180 `asyncio.iscoroutinefunction` DeprecationWarnings — record the number.
- [x] **Step 2:** d1: swap the 3 sites to `inspect.iscoroutinefunction` (equivalence proven incl. partials). d2: `sherpa_stt.py:296` → `asyncio.get_running_loop()`; `oauth_lock.py` — first verify each of the 3 sites is inside `async def` (read the file); if yes → `get_running_loop()`; a monotonic-time need without a loop uses `time.monotonic()` instead. d3: delete main.py's `if sys.platform == "win32": set_event_loop_policy(...)` block, replacing it with a comment citing the uvicorn 0.48 proof (loop="asyncio" → `asyncio_loop_factory` → `SelectorEventLoop` on win32 — the psycopg constraint stays honored, without the deprecated API); bootstrap `log_event_loop_configuration`: drop `get_event_loop_policy()`, log the running-loop class only.
- [x] **Step 3:** Oracles: full fast suite green with the deprecation count collapsed (~180 → ~0 for our code; third-party ones remain); observability decorator tests green (`tests/unit/infrastructure/observability/`); dev container restart → healthy, SSE alive; **Windows host boot proof** for d3: `task dev:api` (host) starts and serves /health with psycopg working (SelectorEventLoop via uvicorn), then stop it.
- [x] **Step 4:** Checkpoint `chore(asyncio): retire 3.16-horizon APIs (inspect.iscoroutinefunction, get_running_loop, uvicorn-native selector loop)`.

### Lot 5 — Dead dependencies out; bcrypt declared direct (ADR-112)

**Files:** `apps/api/requirements.txt` (− `passlib[bcrypt]==1.7.4`, − `slowapi==0.1.9`, + `bcrypt==5.0.0  # direct import in core/security/utils.py — was transitive via passlib`), `requirements-dev.txt` (− `types-passlib`), both locks via `task deps:lock`, `pyproject.toml` (drop the now-obsolete slowapi NOTE in the mypy overrides comment).

- [x] **Step 1:** Re-prove the premise on the current tree: `git grep -nE "import (passlib|slowapi)|from (passlib|slowapi)" apps/api` → zero.
- [x] **Step 2:** Edit manifests; `task deps:lock`. Expected package-level delta, verified exactly: **− passlib, − slowapi, − limits, − types-passlib; bcrypt stays at 5.0.0** (now direct); nothing else moves. `scripts/check_requirements_lock.py` green.
- [x] **Step 3:** Reinstall venv from the new dev lock; oracles: `pytest tests/unit/test_security.py -q` (19 tests, bcrypt auth), `pytest tests/unit/test_native_dependency_smoke.py` (bcrypt import pinned there), full fast suite, `pip-audit` task unaffected. Rebuild dev image (lock changed) → healthy.
- [x] **Step 4:** Checkpoint `build(deps): drop dead passlib/slowapi, declare bcrypt direct (ADR-112)`.

### Lot 6 (OPTIONAL — engage only on explicit choice) — MCP reserved-name aliasing

`create_model("MCPToolInput", ...)` receives remote-server field names; when one collides with a BaseModel attribute (`json`, `schema`, `copy`, `dict`…), build the field as `<name>_` with `Field(alias=name)` + `populate_by_name`, so the wire contract is untouched and the warning disappears. Needs its own tests on the converter (round-trip arg binding by alias) and a check that tool-call kwargs bind by alias in the MCP adapter path. Low value (cosmetic warnings), non-zero contract risk — priced separately.

### Release (after lots 1–5)

- [ ] v1.31.1: version surfaces (package.json ×2, pyproject, sw CACHE_VERSION, version.ts LAST_UPDATED), CHANGELOG entry, FAQ `v1_31_1` ×6 + `CHANGELOG_VERSION_KEYS`, landing `releases` 221→222 (tests recount — Lot 3 un-skips 3, count moves by +3 collected), README block, GETTING_STARTED Compatibility. `task ci:fast` full green. No ADR (no architectural decision — ADR-241 already records the debts; update its "follow-up" lines as closed).

**Out of scope (named):** prometheus multi-process warning (upstream), pydub 0.25.1 SyntaxWarnings (upstream), google.genai deprecation (upstream), host RAM instability (memtest — hardware), the two user-only prod proofs (Telegram voice note, script skill).
