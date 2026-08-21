# ADR-241: Python 3.14 / Debian Trixie migration — single-version runtime contract

**Status**: Accepted (2026-08-20)
**Deciders**: LIA core team
**Technical story**: full-surface migration audit 2026-07-29, re-verified 2026-08-20 (v1.31.0)

## Context

The runtime was split across three interpreter versions: Python 3.12 in every
Docker image and CI job, Python 3.13 on developer hosts, and a bounded contract
`requires-python = ">=3.12,<3.14"` proven by a dedicated `python-compat` CI job
(audit F041). The Docker base was `python:3.12-slim-bookworm` (Debian 12).

Python 3.14 (GIL build) and Debian 13 "trixie" are both stable, and every one of
the 229 pinned packages in the universal lockfiles now publishes cp314-compatible
artifacts for the three platforms LIA actually installs on (Windows x64 dev
hosts, manylinux x86_64 dev containers, manylinux aarch64 production on the
Raspberry Pi 5). The audit that established this checked every pin against PyPI
wheel metadata — not classifiers — and dry-ran both lock recompilations.

Two latent defects made the migration urgent rather than cosmetic:

1. **`import pydub` was already broken on developer hosts.** The stdlib
   `audioop` module was removed in Python 3.13; pydub imports it at module load.
   Production only worked because Docker was still on 3.12, and no test imported
   pydub — the Telegram voice-message path would have died **silently at
   runtime** on any 3.13+ interpreter.
2. **The interpreter version is encoded in six independent surfaces** (pyproject
   contract, both API Dockerfiles, the uv compile flags, the skills-sandbox
   PYTHONPATH constant + real `.env` files, and the CI workflows). Nothing tied
   them together: a partial bump would ship a mixed-version system where the
   skills sandbox mounts a dead `site-packages` path (the v1.25.25 `.env`
   failure class).

## Decision

1. **Single-version contract**: `requires-python = ">=3.14,<3.15"`. Host venv,
   Docker dev, Docker prod, the skills sandbox and every CI job run CPython
   3.14. The F041 `python-compat` job is retired: with one supported
   interpreter there is no second version left to prove — `test-backend` runs
   the same selection on 3.14. The bounded-contract guard
   (`test_python_contract_bounded_guard.py`) continues to enforce that every
   minor in the range is exercised by CI.
2. **The ADR-215 installer wizard keeps its independent Python 3.10 floor**
   (`installer-py310` CI job, `scripts/install/tests_py310.py`): it targets bare
   operator hosts, not the application runtime, and is exempted narrowly (and
   itself asserted) by the new surfaces guard.
3. **Base image**: `python:3.14-slim-trixie` in all seven `FROM` lines across
   `Dockerfile.dev`/`Dockerfile.prod`, standard GIL build — the free-threaded
   (`3.14t`) and JIT builds are explicitly **not** adopted (revisit no earlier
   than 3.15). The Docker CE apt repository moves to its `trixie` dist, and the
   five Chromium runtime libraries renamed by Debian's time64 transition become
   `libasound2t64`, `libcups2t64`, `libatk1.0-0t64`, `libatk-bridge2.0-0t64`,
   `libatspi2.0-0t64` (verified: the old names no longer exist in trixie).
4. **`audioop-lts==0.2.2` joins the runtime manifest** (abi3 wheels on all three
   platforms) so pydub keeps working on 3.13+. The universal locks are
   recompiled on the 3.14 floor — the package-level delta is exactly that one
   addition (proven by dry-run before applying: zero versions changed, zero
   removed).
5. **Non-recurrence guards** close the two silent-failure classes the audit
   surfaced:
   - `tests/unit/test_python_runtime_surfaces_guard.py` — every version surface
     (interpreter running the suite, Dockerfile `FROM` tags, uv compile flags,
     sandbox PYTHONPATH constant + `.env` examples, every workflow's
     `python-version`) must track the pyproject floor, the single source of
     truth. Falsified both ways before adoption.
   - `tests/unit/test_native_dependency_smoke.py` — every compiled runtime
     dependency (audioop included) must import on the current interpreter, so a
     missing cpXY wheel fails loudly instead of at first runtime use.
   - `tests/unit/infrastructure/channels/test_telegram_voice_audio_pipeline.py`
     — hermetic behavioral pins of the exact audioop-backed chain
     (`ratecv`/`tomono`/`lin2lin`) used by `_ogg_to_pcm_float`, ffmpeg-free by
     design (an `from_ogg` test would be a silently-skipped test on hosts
     without ffmpeg — the ADR-155 forbidden class).

## Consequences

- Tooling targets move together: black/ruff `py314`, mypy `python_version =
  "3.14"`. Measured fallout was purely mechanical (408 ruff auto-fixes — mostly
  UP037 unquoted annotations now safe under PEP 649 — and 93 black reformats);
  mypy strict reported **zero** issues in 1 177 files under 3.14. Note that
  black's py314 style adopts **PEP 758** (unparenthesized `except ValueError,
  TypeError:` when there is no `as`): this syntax is 3.14-only — one more
  reason the interpreter guard pins the whole toolchain to the same floor.
- The ruff UP037 sweep surfaced one real latent defect: a quoted bare
  `"ToolRuntime"` annotation invisible to the ADR-231 guard (which inspects AST
  names, not strings); it is now parameterized like every other site.
- Deprecations accepted knowingly at migration time (removal horizon 3.16):
  the Windows event-loop-policy call and `asyncio.iscoroutinefunction`.
  **Closed in the same release's hardening pass**: `inspect.iscoroutinefunction` everywhere,
  `get_running_loop()` at the four call sites, and zero policy APIs left — the
  probe work also showed the policy had NO effect under uvicorn 0.48 (its
  runner passes a `loop_factory`, which ignores policies) and that the Windows
  non-reload path had been silently Proactor — hence psycopg-broken — since
  that uvicorn change; `src/main.py` now drives `Server.serve()` under an
  explicit `SelectorEventLoop` factory, pinned by
  `tests/unit/test_main_entrypoint_loop.py`.
- Python 3.14 changes Linux's default multiprocessing start method from fork to
  forkserver: the only multiprocessing consumer (`test_redis_limiter_multiprocess.py`)
  was proven compatible by running it repeatedly in the 3.14 container.
- Deployment: the RPi5 rebuilds images from the same Dockerfiles; every aarch64
  cp314 wheel was verified on PyPI beforehand, so no source compiles are
  expected. The prod `.env` (SOPS source) must carry the new sandbox
  PYTHONPATH (`.../python3.14/site-packages`) before `task deploy:prod` — the
  surfaces guard pins the examples, and the runbook pins the real file.
- The in-container pytest entry path was hardened while proving the migration:
  `tests/conftest.py` no longer assumes a four-level-deep repo layout (it
  crashed with `IndexError` under the flat `/app` mount before reaching its own
  "no root .env" tolerance). The sixteen repo-level guard modules that
  hardcoded deep `parents[n]` indexing were **converted to
  `tests/_repo_paths.repo_root_or_skip()` in the same release's hardening pass**
  (collection errors 16 → 0 in the container; 46 modules skip cleanly there;
  host/CI counts unchanged). Reviving the zombie multiprocess suite in the
  same pass exposed and fixed a real over-admission bug in the Redis
  rate limiter (non-unique sliding-window member).

## Rejected alternatives

- **Keeping a two-version contract (3.13 hosts / 3.14 containers)**: perpetuates
  the class of host-only breakage this migration closes (pydub), and doubles
  the CI surface for no user value.
- **Free-threaded 3.14t**: the ecosystem's cp314t coverage is far from the 100 %
  the GIL build reaches today, and LIA's concurrency is asyncio-bound.
- **Bookworm with a 3.14 base**: official `python:3.14` images target trixie;
  pinning bookworm would mean maintaining a divergent base for no benefit.
