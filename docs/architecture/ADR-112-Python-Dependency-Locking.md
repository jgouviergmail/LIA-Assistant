# ADR-112: Python Dependency Locking — Universal Lockfiles via uv

**Status**: ✅ IMPLEMENTED (2026-07-08)
**Author**: Claude Code (Fable 5)
**Related**: `apps/api/requirements.lock.txt`, `apps/api/requirements-dev.lock.txt`, `scripts/check_requirements_lock.py`, [GUIDE_DEVELOPPEMENT.md](../guides/GUIDE_DEVELOPPEMENT.md) (bump process)

## Context

`apps/api/requirements.txt` mixed ~54 exact pins (`==`) with ~20 loose pins
(`>=`: pyyaml, sherpa-onnx, mcp, python-telegram-bot, caldav, Pillow,
PyMuPDF, …), and none of the ~120 transitive dependencies were constrained at
all (74 declared packages → 194 actually installed). `Dockerfile.prod` ran
`pip install -r requirements.txt`, so **two builds of the same commit could
ship different dependency versions**. Measured on 2026-07-08: the Windows dev
venv and the Linux dev container — both installed from the same manifest —
diverged on **88 packages**, including majors (starlette 0.50.0 vs 1.3.1,
google-genai 1.67.0 vs 2.10.0). The frontend has been locked all along
(`pnpm-lock.yaml`); the backend had no equivalent.

Constraints on any solution:

- Production images are **multi-arch** (linux/amd64 + linux/arm64, `release.yml`),
  and the Pi deploy path rebuilds the image locally from `PROD/`.
- Development spans a **Windows venv (Python 3.13)** and **Linux containers
  (Python 3.12)** — one lock must serve all four platform/Python combinations.
- The final image must install with **vanilla pip** (no uv runtime dependency).

## Decision

**`uv pip compile --universal` generates two committed lockfiles; every
environment installs from them; requirements files become intent manifests.**

| File | Role |
|------|------|
| `requirements.txt` / `requirements-dev.txt` | Intent manifests (loose pins allowed) |
| `requirements.lock.txt` | Compiled universal lock (195 pins) — installed by `Dockerfile.prod` via `pip install --require-hashes` |
| `requirements-dev.lock.txt` | Compiled with `-c requirements.lock.txt` (layering: runtime pins bit-identical) — installed by `Dockerfile.dev`, CI jobs, and the local venv |

Key properties, each verified before adoption:

1. **pip-tools was disqualified** by the decisive criterion: it resolves for
   the platform it runs on. This repo has both Linux-only (`uvloop`) and
   Windows-only (`pywin32`) resolution branches, so a single pip-tools lock is
   impossible without maintaining an OS×arch matrix. `--universal` emits one
   file with environment markers (`pywin32==311 ; sys_platform == 'win32'`),
   valid for linux/amd64, linux/arm64, Windows, Python ≥ 3.12
   (`--python-version 3.12`), and the output is standard requirements format —
   pip installs it unmodified. uv is a **compile-time tool only** (dev
   machine + already present in `Dockerfile.dev`); the prod image never sees it.
2. **Hashes are included** (`--generate-hashes`): uv embeds the SHA256 of
   *every* published file (all wheels + sdist), so one hashed lock serves all
   architectures. A PyPI audit of all pinned versions confirmed
   aarch64+x86_64 cp312 wheel coverage except `odfpy` (pure-Python sdist,
   trivial build — unchanged from before) and `pywin32` (win32 marker, never
   installed on Linux). Residual risk accepted: a wheel *added* to an existing
   PyPI release after lock generation can break installs until `task deps:lock`
   is re-run; the CI `docker-build` job surfaces this early.
3. **No silent bumps at adoption**: the initial locks were compiled with the
   dev venv's `pip freeze` as constraints — **zero version drift** against the
   tested venv; the only addition is `uvloop==0.22.1` (Linux-only, identical to
   the dev container's version). Consequence: on rebuild, the dev container
   converges back to the venv's (tested) versions.
4. **Stable regeneration**: `uv pip compile` treats the existing output file as
   version preferences, so `task deps:lock` only applies manifest changes
   (verified: recompilation is a byte-identical no-op). Upgrades are explicit:
   `task deps:upgrade -- <pkg>` or `task deps:upgrade:all`.
5. **Universal-resolution forks** (same package, several versions under
   disjoint markers) would be pip-compatible but are absent from both locks
   today (checked); the clean-venv install validation would catch one.
6. **Inconsistent wheel metadata pitfall** (found by the clean-venv
   validation): uv reads ONE distribution's metadata per version and assumes
   consistency, but `sherpa-onnx` wheels disagree — the armv7l wheel declares
   no dependencies while the manylinux/win wheels require
   `sherpa-onnx-core==<same version>`. uv therefore omitted the core package
   and `pip --require-hashes` (which refuses any unpinned requirement)
   failed. Fix: `sherpa-onnx-core` is now **declared explicitly in
   `requirements.txt`** with a comment mandating that both packages are
   upgraded together. A future mismatch fails loudly at install time (pip
   hash mode rejects the unpinned/conflicting requirement), never silently.

Rollout across consumers: `Dockerfile.prod` and `Dockerfile.dev` install from
the locks (`--require-hashes`); CI `lint-backend`/`test-backend` install
`requirements-dev.lock.txt` (cache keyed on it); `task setup:backend` does the
same for the venv; `prepare-prod.ps1` ships `requirements.lock.txt` to `PROD/`;
`pip-audit` (`task security:scan:backend`) and the release SBOM
(`cyclonedx-bom`) now read the lock — transitive dependencies are finally
audited and inventoried.

## Enforcement

CI job `code-hygiene` runs `scripts/check_requirements_lock.py` (offline,
deterministic — new upstream releases can never make it flaky). It fails when:

- a manifest requirement is missing from its lockfile;
- a manifest specifier is not satisfied by the pinned version (pin bumped
  without `task deps:lock`);
- a runtime pin is absent or diverges in the dev lock (stale layering).

## Alternatives considered

- **pip-tools** — rejected: single-platform resolution (see Decision #1).
- **uv.lock / PEP 751 project workflow** — rejected for now: would move
  dependency declarations into `pyproject.toml` and require uv at install
  time (or an export step anyway); the pip-compile interface is the minimal
  change that keeps `pip install -r` everywhere.
- **Lock without hashes** — viable fallback (same version reproducibility,
  no supply-chain integrity); revisit if post-release wheel additions ever
  break builds in practice.

## Consequences

- Reproducible API images: same commit → same 195 dependency versions on both
  architectures, hash-verified.
- Version changes become **visible in diffs** (manifest + lock committed
  together) instead of happening silently at build time.
- New workflow obligation: after editing a manifest, run `task deps:lock`
  (enforced by CI); direct `pip install <pkg>` into the venv no longer
  reflects what ships.
- The dev container, CI, the venv, and prod now install the exact same
  resolution — "works in dev, breaks in prod" version drift is closed.
- Auditing the lock immediately surfaced 17 vulnerable pinned packages
  (starlette, pyjwt, pillow, python-multipart, pydantic-settings, langsmith,
  mako, pyasn1, idna, urllib3, langchain, langgraph-sdk, aiohttp — 21 CVEs
  alone —, msgpack, cryptography, ecdsa, requests) that had been invisible:
  the CI dependency-audit job ran `pip install -e .` against a pyproject with
  no dependencies and therefore audited an empty environment. All 17 were
  explicitly upgraded to fix versions in the same change (`task deps:upgrade`
  + manifest pin bumps), the CI job now audits `requirements.lock.txt`, and
  the final audit reports zero known vulnerabilities (one deliberate ignore:
  ecdsa CVE-2024-23342, signing-only). The langchain GHSA fix (1.3.2 → 1.3.9)
  forced a metadata-driven cascade, each step verified against the resolver's
  own error messages and PyPI metadata: langgraph 1.2.2 → 1.2.4 and
  langchain-core 1.4.0 → 1.4.6 (langchain 1.3.9 minimums), langgraph-sdk
  0.3.11 → 0.4.2 (langgraph 1.2.4 requires >=0.4.2), and websockets
  16.0 → 15.0.1 (langgraph-sdk 0.4.2 caps websockets <16; langsmith 0.9.8
  floors it >=15). The full pin diff is exactly those 20 packages.
