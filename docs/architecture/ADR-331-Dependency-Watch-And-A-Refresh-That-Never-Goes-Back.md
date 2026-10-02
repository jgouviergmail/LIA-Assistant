# ADR-331 — Dependency watch, and a refresh that waits and never goes back

**Status:** Accepted — 2026-10-02. Lot 4 of the dependency programme
(`docs/superpowers/specs/2026-09-30-dependency-lifecycle-design.md`); owner
decisions D4 (cooldowns: patch 5 days, minor 14, major 60, never applied to a
security fix) and D5 (Dependabot for pip: keep the alerts, stop the
version-update pull requests).

**Amends:** ADR-112 (`task deps:upgrade:all` is replaced by `task deps:refresh`;
a security fix lives in its manifest, never in a lockfile alone), ADR-151 (the
watch's own workflow orchestrates and the Taskfile implements, like every gate).

## Context

Measured before anything changed:

1. **The gates read a database the fixes are not in.** A scan of the security
   advisories each dependency's OWN repository publishes, against the exact
   locked versions, found twenty whose range held a locked version on
   2026-09-30 — none of them in GitHub's global advisory database, so
   `pip-audit`, `pnpm audit`, Trivy and Dependabot all answered « no known
   vulnerability ». Fifteen were still invisible on 2026-10-02, the Capacitor one
   32 days after its publication.
2. **The update pipeline had stalled since 2026-07-20.** Of the 107 pull
   requests Dependabot opened from July to September, 101 were closed unmerged:
   the pip ecosystem rewrites the uv universal lockfiles into files nothing can
   install, and only advisories GitHub's database shows were fixed by hand.
3. **A cooldown can move a fix backwards (F7).** `uv pip compile --upgrade
   --exclude-newer` with a 14-day window took `pyjwt` from 2.15.1 back to
   2.14.0: the security bump of `01b374f5` lived in the lockfile alone.
4. **A scheduled job nobody reads is not a gate (F9).** `a11y-matrix` had failed
   on every weekly run since 2026-07-20, eleven in a row.
5. **Production ran end-of-life lines** — Grafana 11.3, Prometheus 3.0, Loki 3.2
   — and nothing said so.

## Decision

### 1. `task deps:watch` reads what the gates cannot see

`scripts/audit/dependency_watch.py`, standard library plus `packaging` and
`pyyaml`, against every version the repository pins: the five Python lockfiles
(the API's three and the wake-word toolbox's two, which no audit read before),
`pnpm-lock.yaml`, the e2e suite's `package-lock.json`, the Dockerfiles'
`npm install -g` (since lot 7: the API image's Claude Code CLI reaches no
lockfile, so no other gate reads it), every image of every compose file,
Dockerfile and workflow, and the product lines the repository
pins — each derived from the file that pins it, through `doc_facts` where it
already reads it. Four sources:

- **the repository's own advisories** (GitHub's API), each range read against
  the locked version;
- **end of life** (endoflife.date);
- **registry facts**: an image that no longer exists, an image without arm64
  where production runs it (a Raspberry Pi), a deprecated npm release, a yanked
  PyPI release;
- **the browser engine**: the Chromium a build installs from Debian (decision
  D8, ADR-059) against the majors Chrome still supports.

Every finding is **fixed or accepted in writing** in
`scripts/audit/dependency_watch_accepted.json` — kind, subject, advisory,
reason, owner, review date. The run fails on an unaccepted finding, on an
acceptance past its date and on one that matches nothing. **A source that does
not answer is named with what it did not read, and fails the run**: a partial
scan is never reported as a clean one.

**Ranges are written by hand, and read the way their authors meant them.** The
first real run reported 94 findings; read the way their authors write them, the
ranges left 21 — one fixed at once (`sharp`), twenty accepted. Measured shapes,
each now a test fixture: an open range
(« every version from X on », `*`, `8+`) is how a maintainer writes « until
the fix » when the fix is in the patched field — a version at or past the fix
of its OWN release line is no hit, the line being its major and minor, else its
major (`v16.0.7, v15.5.7, v15.4.8` lists one fix per line); `||` separates
alternatives, `11.0.x` is a line; an npm prerelease (`14.3.0-canary.77`) is
read by its release; a fix announced but not released (`16.3.?`) patches
nothing on its line; a local build (`torch 2.14.1+cpu`) is its public release.
What still cannot be read is kept, for a person.

It is read **where the owner already looks**: weekly in
`.github/workflows/dependency-watch.yml`, which keeps ONE issue labelled
`dependency-watch` (opened or rewritten while something is left to decide,
closed by the first clean run), and at every release (`lia-release`, the gates
`ci:fast` does not run). **Never inside a pull-request gate** (ADR-112: a
network answer must never turn a pull request red). One run: about 80 seconds,
2,500 requests; GitHub's API needs a token (`GITHUB_TOKEN`, `GH_TOKEN` or
`gh auth token` — anonymously it answers sixty requests an hour).

### 2. `task deps:refresh` moves Python under the cooldown, never backwards

`scripts/refresh_requirements_lock.py` replaces `deps:upgrade:all`, which moved
everything at once with no cooldown. uv's window filters ARTIFACTS by their
upload time, so:

- the window of a locked package never ends before the last artifact of the
  version it holds — a window can hold a version back, never take it back;
- every package is resolved under the patch window; one that moves by a minor
  or a major gets that kind's window and the three locks are resolved again,
  until no move asks for more than it was resolved under;
- a final plain `task deps:lock` keeps those versions and lists every artifact
  of each (the result is what `deps:lock` writes), then the age of every new
  version is checked against its kind from PyPI's own dates;
- any failure, and any version lower than before, restores the three lockfiles
  byte for byte.

Measured on the real locks: 75 changes in two passes, 17 seconds, no version
lower than before, and `lint:lockfiles` green on the result. The compile
commands keep ONE owner: `deps:lock` takes the refresh's arguments through
`UV_EXTRA` (empty, it writes byte for byte what it wrote before). Python versions
now move through three doors and no fourth: `deps:lock` (a manifest change),
`deps:upgrade -- <pkg>` (a fix, at once, with its floor) and `deps:refresh`.

### 3. A security floor lives in its manifest

Ten fixes adopted in a lockfile alone (`anyio`, `click`, `icalendar`,
`langgraph-sdk`, `mako`, `maxminddb`, `multidict`, `pyasn1`, `soupsieve`,
`urllib3`; PyJWT joined with lot 3) became floors in `requirements.txt`, each
naming who pulls the package and the advisory it clears. The locks moved no
version.

### 4. Dependabot follows the same doctrine

`.github/dependabot.yml`: pip keeps its alerts with `open-pull-requests-limit:
0` (D5); npm (the workspace and, new, `apps/web/e2e`) waits 5/14/60 days by kind
of move — held equal to the refresh's constants by a test; Docker images and
the new `docker-compose` ecosystem (`/`, `/infrastructure/docker`,
`/scripts/install/tests/runtime`, one pull request per image across them) wait
5 days, GitHub Actions 14 (a compromised action runs with the repository's
token). The `vite` override becomes a floor (`^8.1.5`), the form
`docs/technical/CI_CD.md` already called preferable.

### 5. The first findings

The first run found what it was built for: `sharp` 0.35.4 under
GHSA-wq5f-xc86-pv6w (librsvg, high), fixed by its override's floor
(`^0.35.5`); `fsspec` 2025.3.0 under GHSA-27vj-qcqg-25rc (high) in the wake-word
GPU toolbox, held by `voxcpm` → `datasets` 3.6.0 and accepted (it never opens a
ReferenceFileSystem and never runs in production); five Next.js advisories whose
fix is announced as `16.3.?`, each verified not to apply (no `remotePatterns`,
no Pages Router, no catch-all route, no metadata image route; one is `next dev`
only). Twenty acceptances, each dated to the lot that lifts it.

### 6. The tools are gated like code

`task lint:deps` — Ruff, Black and strict MyPy over the lock check, the refresh
and the watch — joins `task lint` and the CI's backend lint step.

## Consequences

- A finding no gate could see now reaches an issue within a week, and a release
  waits on « nothing to decide » and « 0 not read ».
- An acceptance is a dated decision, never a silence: past its date, or once it
  matches nothing, the run fails until someone reads it again.
- The first Python refresh (lot 8) moves about 75 packages under the cooldown,
  ten across a major older than 60 days, each read line by line.
- **Stated limits.** A package whose next major is younger than 60 days is held
  entirely — its minors and patches with it — until the major is old enough or
  a manifest caps it. Forty packages publish no GitHub repository: their own
  advisories cannot be read, and the report counts them. Tempo, Alloy and
  cAdvisor are not tracked by endoflife.date. The watch reads what a build
  would install, never what production runs: the deployed engine is as fresh as
  the last image build.

## Amendment 2026-10-02 — python-jose leaves (lot 5)

Every JWT LIA signs or reads goes through PyJWT, which the repository already carried. The
verifier's decisions were written down first, as a seventeen-row table of provider identity
tokens; one row changed on purpose — an identity token with no audience is refused, OpenID Connect
requires `aud` and python-jose skipped the check when it was absent. Decision D3 keeps the rest:
`iat` is not verified (a provider clock ahead of ours never fails a connector link), `nbf` and
`exp` hold at zero leeway, and `at_hash` is checked by LIA itself, as python-jose did and PyJWT
does not. A password-reset link minted by python-jose before the deploy opens after it (a recorded
token is the test). The resolution drops `python-jose`, `ecdsa`, `rsa` and two stub packages and
moves nothing else; the last pip-audit exemption (CVE-2024-23342) and the watch's ecdsa acceptance
go with them. See `docs/technical/AUTHENTICATION.md`.

## Alternatives rejected

- **A `uv.lock` project so that Dependabot can update Python**: ADR-112 weighed
  it; the refresh and the watch close the gap without moving the declarations.
- **Renovate**: a second writer of the same files, and a third-party application
  with repository access nothing here requires.
- **The watch inside `ci:fast`**: a network answer must never turn a pull
  request red.
- **One cooldown for every kind of move**: a 14-day window adopts a major at 14
  days; the iteration costs one pass when a minor or a major moves.
- **Dropping the ranges a parser cannot read**: a silent miss is the defect the
  watch exists to remove; they are kept for a person.

## Not verified

- Dependabot's behaviour after these changes — the cooldown keys, the
  `docker-compose` ecosystem with `group-by`, the `vite` floor — is observable
  only on its next run.
- The weekly workflow's first issue, on its first scheduled or dispatched run.

## Implementation references

- `scripts/audit/dependency_watch.py`, `scripts/audit/dependency_watch_accepted.json`,
  `apps/api/tests/unit/test_dependency_watch.py`
- `scripts/refresh_requirements_lock.py`, `apps/api/tests/unit/test_requirements_refresh.py`
- `Taskfile.yml`: `deps:watch`, `deps:refresh`, `deps:lock` (`UV_EXTRA`), `lint:deps`
- `.github/workflows/dependency-watch.yml`, `.github/dependabot.yml`
- `apps/api/requirements.txt` (the security floors), `package.json` (`vite`, `sharp`)
- the release procedure (`lia-release`): the watch is a gate `ci:fast` does not run
