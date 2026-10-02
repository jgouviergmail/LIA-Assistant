# Dependency lifecycle: what is pinned, what is watched, what is refused — design

**Date:** 2026-09-30, updated 2026-10-02
**Status:** adversarial review of the first dependency audit of 2026-09-30, every claim
re-measured. D1 and D2 decided by the owner on 2026-10-02 (§3). Lot 1 is the urgent lot, planned
in `docs/superpowers/plans/2026-10-02-dependency-urgent-lot.md`; the other lots get their plan
after the owner's review of this spec. Lots 1 and 2 landed in `9923b414`, lot 3 in `5c05e329`,
lot 4 with ADR-331. D5, D6 and D8 decided; D3, D4 and D7 hold their stated defaults (§3).
**Scope:** every third-party input of the repository — the three Python lockfiles of the API
(runtime, dev, skill sandbox), the pnpm lockfile and the e2e npm lockfile, the wake-word toolbox's
lockfiles, every container image and build-time download, the CI toolchain, the native shells —
and the process that keeps them current.
**Baseline:** `main` at `3a6b7f33` on 2026-09-30 (the probes ran at `ad61235b` and on the
JavaScript manifests of `21b05bfa`); lot 1 re-measured on `13dfc167` (v2.3.0) on 2026-10-02.

## Update of 2026-10-02

What moved between the review and the owner's decisions, each read from the commit or re-measured:

- **Delivered by the owner.** The broken lockfile (fact 3) was repaired by `610e6dc5`, one line.
  `b963e4af` (`urllib3` 2.8.0), `ca88a27f` (`next` 16.3.6, `@grpc/grpc-js` 1.14.5) and `f27f9ef6`
  (`dompurify` 3.4.16) answered the Security workflow once GitHub's global database had caught up
  with those four advisories. What is left of lot 0 is the pnpm version, which lot 1 carries.
- **Fact 1 holds.** A fresh scan of the current lockfiles (1 293 packages) finds 15
  repository-level advisories over 12 packages that the global database still does not carry, the
  Capacitor one 32 days after its publication (three of them — KaTeX, `postcss-selector-parser`,
  `powershell-utils` — only once the listings that failed during the scan were read again: a scan
  that loses a listing must say so, which the watch of lot 4 does).
- **Two releases changed the surface.** v2.2.0 (ADR-327) moved the sandbox's libraries into their
  own image with a third lockfile, `requirements-sandbox.lock.txt`, compiled against the dev lock:
  every Python change now regenerates three files. `pytz` left the sandbox promise of
  `requirements.txt` with it, so the line `requirements.txt:147` has no reader left — no module of
  `src/` imports it, `vobject` keeps it installed. v2.3.0 (ADR-328 to ADR-330) added the browser
  wake word: `onnxruntime-web` 1.30.0 (current) and a training toolbox, `scripts/wake-word/`, with
  its own pinned lockfiles. ADR numbers are taken through 330.
- **New since the review.** `mcp` 2.0.0 carries two more high advisories, both on the SDK's HTTP
  server (session retention, request bodies): LIA uses the client alone, so neither applies, and
  2.2.0 closes them anyway. Next.js 16.3.8 is a security release; its high advisory needs
  `images.remotePatterns`, which `next.config.ts` does not set, and the others need the Pages
  Router, `use cache`, a root catch-all or metadata image routes, none of which LIA has — the bump
  costs nothing and stays in lot 1. KaTeX 0.18.11 is deprecated on npm (« accidentally published
  with breaking changes ») and 0.19.0 is one day old: a caret on 0.18 would resolve the deprecated
  release, so lot 1 pins 0.18.9 exactly. `multidict` 7.0.0 is a new major: lot 1 stops at 6.9.1.
  `@bufbuild/protobuf` 1.10.1, reached through `@elevenlabs/client` → `livekit-client`, carries two
  medium advisories fixed only in its 2.x line; its input is the voice vendor's server, so it
  joins the deferred list (§6).
- **The dev images are older than their lockfiles.** `lia-api-dev` was built on 2026-09-18
  (`mcp`, `urllib3` and `pyjwt` behind the lock); `lia-web-dev` on 2026-09-03 and updated in place
  since. Every runtime proof of lot 1 starts with a rebuild.
- **A correction found while planning lot 1.** Chrome now ships a stable every two weeks, and the
  Chromium of the newest Playwright (153) is already out of support: a Playwright bump shortens
  the engine's lag, it does not end it. D7's first sentence was wrong and is corrected; D8 is new
  (§3) and decided: lot 1 runs Debian's own Chromium.
- **Owner decisions:** D1, D2 and D8 (§3).

## Problem, measured on 2026-09-30

1. **The gates read a database the fixes are not in.** A scan of the repository-level security
   advisories of every locked package (1 291 packages, 50 raw matches, 28 discarded as open-ended
   ranges) leaves **20 advisories whose range contains a locked version (22 package-version
   matches), none of them present in GitHub's global advisory database** — so `pip-audit`,
   `pnpm audit`, Trivy and Dependabot all answer « no known vulnerability ». Seven were known from
   the first pass, all on the JavaScript side; the thirteen others, every Python one among them,
   are in §2.
2. **The update pipeline has been stalled since 2026-07-20.** Last Dependabot version-update merge
   before this review: #209 (actions, 2026-07-20); last manual replay of the npm group: `7d1c7cf4`
   the same day. Of the 107 pull requests Dependabot opened from July to September, 101 were closed
   unmerged (52, 26, 23), two were merged in July and four during this review. The two causes are
   documented in `docs/technical/CI_CD.md` § « Limites connues » and still hold: the pip ecosystem
   rewrites the `uv` universal lockfiles into something uninstallable (#283, #285: Lint Backend,
   Dependency Audit, Code Hygiene, Docker Build red), and the npm group collides with the exact
   `vite` override (`package.json:38`, #280). Only advisories GitHub's database shows are fixed by
   hand — which is fact 1. The Capacitor fix sat in three closed group pull requests (#270, #273,
   #280).
3. **`main` broke during the review.** #264 (jsdom 30) and #266 (jest-dom 7) were merged five
   minutes apart; each had regenerated the lockfile alone, git merged the two texts, and
   `pnpm-lock.yaml:6973` names `vitest@4.1.11(…)(jsdom@29.1.1)(…)`, an entry that no longer
   exists. `pnpm install --frozen-lockfile` fails (`ERR_PNPM_LOCKFILE_MISSING_DEPENDENCY`: Security
   run 36697424368 on `21b05bfa`; Security and Mobile Shell red again on `3a6b7f33`). `main` has
   no branch protection (`GET …/branches/main/protection` → 404). Repair measured:
   `pnpm install --no-frozen-lockfile`; `--lockfile-only` alone changes nothing.
4. **The production observability stack runs end-of-life lines.** endoflife.date: Grafana 11.3
   (EOL 2025-07-22), Prometheus 3.0 (2024-12-26), Loki 3.2 (2025-02-12); Promtail is « end of life
   as of March 2, 2026 » (Grafana's documentation); Tempo 2.6.1 predates four patched 2.x lines;
   cAdvisor's registry stopped at v0.55.1 (the project moved to `ghcr.io` at v0.56.0). Dependabot
   watches two Dockerfile directories and no compose file.
5. **A floating tag is a different image per environment.** The dev database, under the same
   `pgvector/pgvector:pg16` as production, runs PostgreSQL 16.11 and pgvector 0.8.1 from a
   ten-month-old pull; the registry's `pg16` is 16.15 with 0.8.6. On the production host only
   `iron-proxy` is digest-pinned.
6. **One screen regressed and nobody saw it.** `7d1c7cf4` moved the direct `katex` to `^0.18.1`;
   `rehype-katex` keeps rendering with 0.16.45 while `layout.tsx:33` serves the 0.18 stylesheet,
   whose layout classes were renamed. Measured: 9 of 60 emitted classes lose their rule (`base`,
   `strut`, `sizing`, `overline`, `underline`, `accent`, `stretchy`, `tag`, `overlay`); seen in a
   browser: overline and underline gone, `\Huge`/`\tiny` ignored, sub- and superscripts at full
   size, the vector arrow below its letter (`.playwright-mcp/depaudit-katex-*.png`).

## 1. What the first pass got wrong

| First-pass claim | Verdict | Evidence |
|---|---|---|
| `python-jose` is an active flaw | **Not exploitable.** Hygiene only. | In the API image `jose.backends` resolves RSA, EC and HMAC to `cryptography_backend`; `JwtAlgorithm` is a Literal of HMAC names (`core/constants.py:1411`); `security.yml:81-87` already argues it. `ecdsa` and `rsa` are installed and never executed. |
| `pytz` is abandoned — remove it | **Wrong action on 2026-09-30, right line since v2.2.0.** | It was a sandbox promise pinned directly on purpose (ADR-298). PyPI: « Deprecated … Updates continue to be made for legacy systems ». ADR-327 moved the promise to `requirements-sandbox.txt`, where it stays; the `requirements.txt` line has no reader left and leaves with lot 1, the data moving to 2026.4. |
| postgres-exporter 0.20 breaks the metric names LIA reads | **False.** | Dashboards and the two LOADED rule files read `pg_up` and `pg_stat_database_numbackends`; both exist in v0.20.1 (scraped against a throwaway PostgreSQL). The other names live in `alerts.yml`, which `prometheus.yml:29` disables. |
| Move the database to `0.8.6-pg16-trixie` now (small) | **A trap.** | The database's collation is libc `en_US.utf8`, `datcollversion = 2.36` (measured on dev). Debian 13 carries glibc 2.41: a collation-version mismatch, hence an index rebuild. Pin the **bookworm** digest; change the base only with a dump and restore. |
| Redis 7.4 → 8.2 to plan | **No need.** | Redis 7.4 is supported until 2029-12-01; 8.2 until 2030-09-01 and adds a licence question. |
| Promtail → Alloy: medium, two guards to rewrite | **Smaller, in two steps.** | Alloy v1.19.2 runs the repository's Promtail YAML unchanged (`--config.format=promtail`); on four lines covering both redaction stages, Promtail 3.2.1 and Alloy deliver identical (timestamp, line, labels) sets to Loki 3.7.8. Grafana calls that mode « a temporary transition step »: the native file is a second step. |
| Migrate 63 modules from `httpx` to `httpx2` | **Neither needed nor possible now.** | langchain-core 1.6.6, google-genai, firebase-admin (`httpx[http2]==0.28.1`), langfuse, ollama and langgraph-sdk require `httpx`; the sandbox promises it to models. The real defect is narrower and worse (§2, F2). |
| Capacitor: a critical flaw in the mobile app | **True in the code, no build is distributed.** | 8.5.0 serves the proxy path for any host whatever `CapacitorHttp` says (`WebViewLocalServer.java:187`), and the shell's `appUrl` is the person's server (`MainActivity.java:79`), so a relative link suffices. But no release carries an APK or IPA and both guides say « the app itself is planned ». A blocker before any distribution, not an incident. |
| The installer's Python 3.10 floor must be decided | **Already decided** (ADR-215). | Standard library only, tested under exactly 3.10 (`ci.yml:593-611`); Ubuntu 22.04 ships 3.10 until 2027-06-01. Keep, with a dated acceptance. |
| pnpm 10.34.6 | **Right target, one more constraint.** | 10.34.6 installs the current lockfile frozen (1 023 packages, lockfile unchanged) and keeps the `libc:` fields Dependabot writes, which 10.18.3 drops. Dependabot documents pnpm v7–v10 only: no move to 11 or 12. |

Confirmed as stated: the `next/og` advisory (no use in the tree), the pnpm advisories, the four
end-of-life lines of fact 4, cloudflared 2025.1.0 outside Cloudflare's one-year window,
`ubuntu/squid:6.1-23.10_beta` on an end-of-life base, `minio/minio` gone from Docker Hub (404),
Langfuse `latest` (v4) beside worker `:3`, `alpine:latest` and the unversioned Claude Code CLI in
production Dockerfiles, ESLint 9 end of life with ESLint 10 still refused by three plugins
`eslint-config-next@16.3.7` depends on, TypeScript 7 refused by typescript-eslint 8.71.0, the
stale `--ignore-vuln CVE-2026-4539` (OSV: pygments ≤ 2.19.2; the lock holds 2.20.0, dev only), and
the four imports with no manifest line — the AST census of `src/` finds exactly four:
`google-genai`, `pyjwt`, `starlette`, `typing-extensions`.

## 2. What the first pass missed

| # | Finding | Evidence | Severity here |
|---|---|---|---|
| F1 | **MCP SDK 2.0.0 opens server-chosen URLs.** GHSA-rwrf-2pqf-9j8j: a tool's `outputSchema` `$ref` is fetched by the client, synchronously on the event loop, with no timeout. GHSA-qx49-fqc8-xw99 (OAuth providers) does not apply: LIA attaches its own tokens. | The fetch is reproduced with the SDK's own validator in the API image: one request received by a loopback server on 2.0.0, none on 2.2.0 (`Unresolvable`); the stall is the advisory's statement. `user_pool.py:108` also follows redirects. Production: `MCP_USER_ENABLED=true`. The pin `mcp>=2.0.0,<2.1.0` (`requirements.txt:139`) refuses the fix. | **High**: a server any account adds can make the API request internal addresses and hold a worker's event loop. |
| F2 | **An untrusted body is decompressed without a bound.** `httpx` 0.28.1 inflates whatever a chunk holds; the maintained fork fixed it in httpx2 2.12.0 (CVE-2026-84382) and `httpx` has had no release since 2024-12. `web_fetch_tools.py:358` reads with `aread()`. | In the API image: a 6 419-byte zstd body passes the 2 MB header check and becomes 209 715 200 bytes in memory. Under the existing `read_bounded`, one decoded chunk weighs 209 MiB (zstd) or 67 MiB (gzip) before the bound fires. | **High** for web fetch; the radio newsroom reads sites listeners add. |
| F3 | **The browser is Chromium 148, without its sandbox, in the container that holds the secrets.** `playwright==1.60.0` (2026-05-18) bundles 148.0.7778.96; Chrome 148 is end of life since 2026-06-02, stable is 154. `pool.py:117` passes `--no-sandbox`; `browser_enabled` defaults to True and `.env.prod` does not set it. **Chrome now ships a stable every two weeks** (endoflife.date: 153 from 2026-09-08 to 09-22, 154 to 10-06), so the newest Playwright, 1.63 (2026-09-15), bundles 153 — itself ten days out of support on 2026-10-02 (D8). | `python -m playwright --version`, `browsers.json` and a real launch in the image. With 1.63.0: Chromium 153.0.8010.12 launches with the same arguments, the CDP accessibility call returns the same tree, 80 browser tests pass. Debian trixie-security ships Chromium 154.0.8037.92 for amd64 and arm64 (the arm64 build had trailed at .57 when first read); Playwright 1.63 launches it through `executable_path` with the pool's arguments, reads the tree, clicks and fills — on amd64 and on the production Raspberry Pi. | **High**: a page the assistant opens is the attack surface. |
| F4 | **Eleven more invisible advisories.** `urllib3` 2.7.0 (two high, one medium → 2.8.0), `icalendar` 7.2.0 (→ 7.2.2), `maxminddb` 3.1.1, `multidict` 6.7.1, `mako` 1.3.12, `langgraph-sdk` 0.4.2, `postcss-selector-parser`, `@asamuzakjp/css-color`, `powershell-utils`. | The advisory probe of §11, over both ecosystems. None is reached by LIA's own code paths (no `icalendar` alarm expansion, no `requests` stream in `src/`, `mako` is the migration template engine, the three npm ones are build and test tools); the sandbox runs model-written scripts on the Python versions. | Low to medium; floors and a lock refresh. |
| F5 | **Loki ≥ 3.5.8 has no shell.** The ADR-317 purge procedure is `docker exec lia-loki-prod wget …` (`PII_LOGGING_SECURITY.md:434-437`). | Loki upgrade notes, 3.5.8. | The procedure dies with the upgrade. |
| F6 | **Nothing holds the self-host catalogue equal to the compose images.** Tests compare service NAMES (`test_compose.py:194`, `test_self_host_manifest.py:261`). | Read. | A compose bump alone makes PREBUILT installs pin the old images. |
| F7 | **A cooldown can downgrade a security fix.** `uv pip compile --upgrade --exclude-newer` with a 14-day window moves 76 packages and takes `pyjwt` from 2.15.1 back to 2.14.0: the floor of `01b374f5` lives in the lock only. | Dry run in scratch. | Blocks any automated refresh until floors are in the manifest. |
| F8 | **The security workflow implements its own audit.** `security.yml:88` ignores two CVEs, `Taskfile.yml:1485` one; `lint:ci-parity` reads `ci.yml` only; the dev lockfile is audited nowhere; `uv` is unpinned (`Taskfile.yml`, `UV: uv`). | Read. | ADR-151 pointing at the security job. |
| F9 | **A scheduled job nobody reads is not a gate.** `a11y-matrix` has failed on every weekly run since 2026-07-20 (eleven in a row). | `gh run list`. | Shapes §5: the watch must surface where the owner already looks. |
| F10 | **Upgrade side effects, measured.** Grafana 12.4.12 idles at 124 MiB against 83 for 11.3.0 under a 256 MiB limit; cAdvisor v0.60.6 exposes 4 900 series where v0.49.1 exposed 3 096 on the same host; Tempo 3.0.3 refuses `tempo.yml` (six removed fields) while 2.10.8 accepts it unchanged; FastAPI ≥ 0.137 turns `router.routes` into a tree and 28 test modules read it. | Throwaway containers; FastAPI release notes. | Sizes the lots. |
| F11 | Dead configuration: `prometheus.yml:26-30` loads two rule files; the other tracked rule files are not loaded, and `alerts/langgraph_framework_alerts.yml:325` does not parse on either version. | `promtool check rules`. | Out of scope; recorded. |

## 3. Owner decisions

Decided on 2026-10-02:

- **D1 — production while lot 1 is not deployed. Decided: lot 1 becomes a dedicated urgent lot,
  delivered first; nothing is switched off meanwhile.** F1 and F3 are live (F2 too: §5, lot 2,
  which D1 did not cover).
- **D2 — the dev Langfuse profile. Decided: Langfuse is stopped for now and may resume in the
  medium term.** The profile is left untouched and out of this programme; the day Langfuse
  resumes, its first step is the repair measured here (Langfuse 4 for web and worker, ClickHouse
  26.8 LTS, an object store that still publishes an image).
- **D8 — which Chromium the browser tool runs. Decided (delegated by the owner): Debian's
  `chromium` package, in lot 1.** Playwright's bundled build trails Chrome stable by up to about
  six weeks (Chrome ships every two, Playwright every five to seven; 1.63 brings 153, out of
  support since 2026-09-22). Debian's package (trixie-security, 154.0.8037.92 on both
  architectures on 2026-10-02) is signed, declares its own libraries, and is re-resolved by every
  production build because its layer follows the per-build provenance ARGs. Playwright 1.63
  drives it through `executable_path` (`BROWSER_CHROMIUM_EXECUTABLE`), measured before deciding
  with the pool's arguments on amd64 and on the production Raspberry Pi: launch, CDP
  accessibility tree, click, fill, screenshot. ADR-059 amendment 2026-10-02.
- **D5 — Dependabot for pip. Decided (2026-10-02): keep the alerts, stop the version-update pull
  requests**; Python moves through `task deps:refresh` (lot 4).
- **D6 — merge discipline on `main`. Decided and applied (2026-10-02)**: ruleset
  « main: merge only green and up to date » (id 24349332) — a pull request merges only with its
  18 CI and Security checks green on an up-to-date branch; the repository admin bypasses it, so
  the owner's direct pushes are unchanged. `mobile-shell` is not required: it only runs when
  `apps/mobile` changes, and a required check that never reports blocks the merge.

Not blocking, defaults stated:

- **D3 — `iat` when PyJWT replaces python-jose.** python-jose accepts a token issued « in the
  future », PyJWT refuses it at zero leeway: a provider clock one second ahead would fail a
  connector link. Default: parity (`verify_iat: False`), the swap changes the library, not the
  contract. Alternative: a named leeway, which also accepts a token up to that long after `exp`.
- **D4 — cooldown values.** Default: patch 5 days, minor 14, major 60, never applied to a security
  fix.
- **D7 — a browser outside the API container.** D8 gives the browser a supported engine; the
  sandbox stays off, in the container that holds the secrets. Moving the browser to an isolated
  container (the skills sandbox's shape) is a separate design with its own ADR. Default: propose
  it after this programme.

## 4. Doctrine

1. **A version is a claim with an owner: one declaration, every other place reads it.** The pnpm
   version is written in three files, the promtool version in three, an image reference in up to
   five (production compose, dev compose, demonstrator compose, the self-host catalogue, CI). Each
   copy gets a reader or a guard holding it equal.
2. **What a gate cannot see is not safe, it is unseen.** An advisory database is one source; the
   repository-level advisories, the vendors' end-of-life dates and the registries are three more.
   They are read on a schedule and at every release, never inside a pull-request gate: `ci:fast`
   stays offline and deterministic (ADR-112).
3. **A lockfile has one writer at a time.** Two pull requests that each regenerate it are merged
   one after the other with a rebase between, or not at all.
4. **A production input names a version and a digest.** No `latest`, no tag that moves, no global
   install without a version, no download without a checksum. The debt that exists is a shrink-only
   baseline; what is accepted carries a reason, an owner and a review date, and a finding whose date
   has passed is a failure.
5. **A cooldown never moves a version backwards**, and a security floor lives in the manifest,
   where the next resolution reads it.
6. **The longest-supported proven line, not the newest.** A major younger than the cooldown is not
   a target unless the line in use is end of life; when no supported line can be reached (ESLint 9),
   the acceptance is written down with the condition that lifts it.
7. **An upgrade is rehearsed where it will run.** Dev first, on the real configuration, with the
   data path exercised (a pushed log line, a pushed span, a provisioned dashboard, a fired alert).
8. **A body sized by someone else is read under a bound that holds during decompression.**

## 5. Lots

Each lot is one reviewable change, ends with the cold adversarial review of every file of its diff,
and is proven at runtime in Docker dev. « Tests first » names the tests written and seen red before
the change.

### Lot 0 — a base that installs (delivered)

The lockfile was repaired by the owner (`610e6dc5`). The pnpm version (10.18.3 in
`package.json:31`, `apps/web/Dockerfile.prod:5`, `apps/web/Dockerfile.dev:11` and
`docs/guides/GUIDE_DEPLOYMENT.md:747`), which drops the `libc:` fields Dependabot writes, moves to
10.34.6 with lot 1.

### Lot 1 — the fixes that are a version away (urgent, D1)

The task-by-task plan is `docs/superpowers/plans/2026-10-02-dependency-urgent-lot.md`. In short:

- Python: `mcp>=2.2.0,<2.3.0`, `playwright==1.63.0`, `tzdata==2026.4`, the orphan `pytz` line
  removed; then `task deps:upgrade -- icalendar maxminddb multidict==6.9.1 langgraph-sdk mako
  pytz`, the repository's way for transitive security bumps (`b963e4af`). Floors in the manifest
  (F7) belong to lot 4, which introduces the only command that could move a version backwards.
  Both MCP clients stop asking httpx2 to follow redirects (`user_pool.py:108`,
  `client_manager.py:228`): since 2.2 the SDK follows them itself, within the endpoint's origin,
  and never reads that setting — the line states the policy, the SDK enforces it (measured: the
  four tests pass on 2.2 with either value).
- JavaScript: `next` 16.3.8, the four `@capacitor/*` at 8.5.2, `katex` 0.18.9 exactly as the
  dependency and as an override, `@ungap/structured-clone ^1.3.1` (1.3.0 deprecated upstream,
  « Potential CWE-502 », in production code), the dead `esbuild` and `minimatch@9` overrides
  removed, pnpm 10.34.6. `eslint-config-next` stays 16.2.10: 16.3.8 adds
  `@next/next/no-location-assign-relative-destination`, one warning at `lib/api/chat.ts:546` — a
  rule decision for lot 8, not an urgent fix (§6). The Capacitor version the mobile probe scaffolds
  (`scripts/mobile-probe/scaffold.mjs:24`) moves with the shell, then both platforms are re-probed.
- The browser's engine (D8): both API images install Debian's `chromium` without its recommends
  and set `BROWSER_CHROMIUM_EXECUTABLE=/usr/bin/chromium`, which `BrowserPool.initialize` hands to
  Playwright as `executable_path` (blank reads as unset; unset, a host run starts the bundled
  build). The production image drops `playwright install chromium` and its hand-written library
  list. A failed launch is counted (`browser_errors_total{error_type="launch_failed"}`, dashboard
  20) and stops the driver it started; the engine that runs is logged at launch.
- Tests first, prototyped red then green: four MCP boundary tests against real loopback servers
  through the pool's own call and discovery paths (a remote `$ref` makes no request, an
  in-document `$defs` reference still validates, a cross-origin redirect is not followed, a
  same-origin trailing-slash redirect still is — on 2.0.0 the first and third fail, on 2.2.0 all
  pass); a vitest guard rendering six display formulas through `MarkdownContent` and checking every
  emitted layout class against the stylesheet the layout imports (red today on exactly the nine
  classes of fact 6, green on the candidate); a Playwright spec streaming a formula into the real
  chat page of a production build and reading its computed layout (red today: the formula's first
  box `static`, its strut `inline`; green on the candidate).
- Measured in advance on `13dfc167`: the three Python lockfiles move 10, 10 and 4 packages, none
  across a major; the fast backend unit suite gives identical verdicts on the current and the
  candidate locks (35 460 and 35 462 passed, with the same seven failures, each a test calling
  `git` in a copy with no `.git`); `mypy src` is clean on the candidate packages;
  `check_requirements_lock.py` passes; the pnpm lockfile changes the same 17 package names however
  it is regenerated (a command may also fold an existing duplicate), holds one `katex@0.18.9`, and
  `pnpm audit` finds nothing; lint, the three ratchets and `tsc` are identical
  on both sides; the frontend suite passes with the CI thresholds (10 480 tests) and the whole e2e
  suite in the CI image (369 tests); a 1.28.1 server is served identically on SDK 2.0 and 2.2; the
  Alembic template renders byte for byte on Mako 1.4.3; the Capacitor 8.5.2 native templates are
  byte-identical to 8.5.0's, so the drift baseline holds.
- What lot 1 does NOT do: close F2 — the unbounded decompression of web fetch is live in
  production too and is lot 2.

### Lot 2 — a bounded read that is bounded (ADR-326 amendment)

- `infrastructure/utils/bounded_read.py` reads `aiter_raw()` and decodes the raw bytes itself,
  never asking a decoder for more than what is left of the ceiling plus one byte: gzip and deflate
  through `zlib.decompressobj().decompress(data, max_length)` over `unconsumed_tail` (deflate
  zlib-wrapped or raw, the first stream only, as httpx), zstd through the standard library's
  `compression.zstd`, every frame. It decodes exactly what httpx advertises in the image
  (`ACCEPTED_ENCODINGS`; a test holds the two equal, so installing brotli is a decision) and
  refuses any other or stacked `Content-Encoding` before a byte is decoded
  (`UnsupportedEncodingError`, an `httpx.DecodingError`); a corrupt body and a compressed stream
  cut before its end are `httpx.DecodingError` too, which all seven callers already handled. A
  response read already (a test transport's `content=`) answers to the ceiling alone. Its module
  docstring claimed every server-side download went through it, which was not true and still
  is not: it now names who does — every `pinned_stream` caller (held by a guard) and the vendor
  downloads that adopted it; the Google media and Drive thumbnail proxies are deferred (§6).
- `pinned_stream` (`web_fetch/url_validator.py`) sends `ACCEPT_ENCODING_HEADER` unless the caller
  set one, so an honest server never answers in an encoding the reader refuses.
- `web_fetch_tools.py`: `read_bounded(response, WEB_FETCH_MAX_CONTENT_LENGTH)`, the text decoded
  with `response.encoding or "utf-8"` and `errors="replace"`, which is what `response.text` did. A
  refused encoding and a corrupt or cut body map to `INVALID_RESPONSE_FORMAT`, each with its own
  message, an overflow to the existing `CONSTRAINT_VIOLATION`. A header value the server chose
  reaches those messages only as a short token (a media type, a list of codings) — a failure
  message is not wrapped as external content; the `content-type` quote had the same gap.
- Tests first: `tests/unit/infrastructure/utils/test_bounded_read.py` (new) — 200 MiB bombs in
  gzip and in zstd refused under a 1 MiB ceiling with the allocation measured (`tracemalloc`: 141.8
  and 400.0 MiB before, 2.2 and 2.0 after), the exact ceiling, an identity stream with no length,
  every accepted encoding round-tripped (loosely spelled, raw deflate, several zstd frames),
  trailing bytes ignored and never held (found by the cold review: 32 MiB held for 16 MiB of
  trailing bytes before), `x-gzip` read as gzip (RFC 9110), `br`, `compress`, `x-zstd`,
  `gzip, gzip` and `gzip, zstd` refused, a
  truncated or corrupt stream an error; the tool's own tests over a body still on the wire (a bomb
  refused with its peak bounded, `br` refused by name, a cut page refused, the offered header,
  hostile header values kept out of the messages), red on the former tool; the avatar proxy's
  tests moved from a mocked response to httpx's own. The AST guard
  `test_pinned_stream_bounded_read_guard.py`: every `pinned_stream` call is entered by
  `async with … as <name>` and nothing reads `<name>` through an httpx reader inside the block —
  red on the former tool (`aread`, `content`, `text`).
- No new setting: the ceilings exist.

### Lot 3 — guards that need no network (implemented 2026-10-02)

- `tests/unit/test_imports_are_declared_guard.py`: every third-party module `src/` imports belongs
  to a distribution `requirements.txt` declares; a namespace package (`google`) is resolved by the
  distribution whose files hold the sub-package — `from google import genai` read as the whole
  namespace would have named nine distributions. Red on exactly `google-genai`, `PyJWT`,
  `starlette` and `typing-extensions`, now declared as floors at their locked versions (PyJWT's
  is also its security floor, CVE-2026-102274): the locks moved no version.
- `tests/unit/test_build_inputs_pinned_guard.py`: in the production compose chain (read from
  `deploy_readiness_gate.sh`, where the deploy declares it), the demonstrator compose and the three
  Dockerfiles the release builds, every image carries a version and a digest, every global install
  a version, every download a checksum and no moving URL (`latest`, a Hugging Face `resolve/main`);
  `apt-get` is out of scope (signed repositories, updates wanted). Shrink-only baseline of 32
  entries (`build_inputs_baseline.json`): 23 compose images, the two base images, the Claude Code
  CLI, the Whisper `resolve/main`, the `latest-v24` Node URL, the Silero VAD archive, the DB-IP
  file and the Docker key; lots 6 and 7 empty it. Proven to fail both ways (a new entry, a fixed
  one still listed). The sandbox Dockerfile was already clean.
- `test_self_host_compose_contract.py`: the catalogue pins what production runs (Caddy: the
  default `scripts/install/compose.py` renders); one third-party image, one reference across every
  compose file (the root ones discovered) and every workflow's services and containers — red on
  the CI's `redis:7-alpine` against production's `redis:7.4-alpine`, aligned; the Playwright
  container of `ci.yml` and `a11y-matrix.yml` is held equal the same way (lot 9 moves both). The
  Langfuse profile's own Redis is exempt in writing (D2), and an exemption that no longer diverges
  fails.
- `test_one_value_one_owner_guard.py`: pnpm (`packageManager` against the two web Dockerfiles),
  promtool (`ci.yml` and `Taskfile.yml` against the production Prometheus image), uv (the
  workflows' install against `UV_VERSION`). Proven red on divergent copies.
- `scripts/audit/doc_facts.py`: facts for the Prometheus, Grafana, Loki and Tempo image tags (eight
  quotations in three living documents, all exact today); the PostgreSQL resolver accepts the
  digest-pinned `X.Y.Z-pg16-bookworm@sha256:…` (tested).
- Supply chain (F8): `security.yml` calls `task security:scan:backend` (the three locks, runtime,
  dev and sandbox: 233 distinct packages read), `task security:scan:frontend` and
  `task security:sbom:backend`; `CVE-2026-4539` is no longer ignored; `lint:ci-parity` reads
  `security.yml` too. pip-audit 2.10.1 and cyclonedx-bom 7.4.0 run isolated through `uv tool run`
  at the versions the Taskfile pins — they cannot share the app's venv: cyclonedx-bom 7.4 requires
  `chardet<6` where the app locks 7.1 (7.5.0 is inside the minor cooldown). uv itself is pinned
  (`UV_VERSION` 0.12.18, which reproduces the locks byte for byte): `deps:lock`, `deps:upgrade*`
  and `wake:deps:lock` refuse any other.
- Found on the way: a test leaked its git identity into the real `.git/config` through the
  variables a git hook exports (every commit from `354484ed` to `13dfc167` authored « guard »);
  fixed separately (`a0b7d85a`).

### Lot 4 — the watch, and a pipeline that moves (implemented 2026-10-02, ADR-331)

Measured on landing — the design below held, with these findings on the way:

- **The first real run reported 94 findings; 21 were real.** The rest were ranges read
  literally: `*`, `8+`, `11.0.x`, `||`, `14.3.0-canary.77`, one fix per release line
  (`v16.0.7, v15.5.7, v15.4.8` — the line is major and minor, else major), a fix not
  released (`16.3.?`), a local build (`torch 2.14.1+cpu`). Each shape is a recorded fixture of
  `test_dependency_watch.py`, seen red before the reader moved. One run: about 80 seconds,
  2,500 requests, 389 PyPI and 1,121 npm releases, 969 repositories, 17 product lines, 36 images.
- **What it found**: `sharp` 0.35.4 under GHSA-wq5f-xc86-pv6w (librsvg, high), fixed by its
  override's floor; `fsspec` 2025.3.0 under GHSA-27vj-qcqg-25rc in the wake-word GPU toolbox (the
  wake-word locks were audited by nothing), held by `voxcpm` → `datasets` 3.6.0 and accepted;
  five Next.js advisories whose fix is announced as `16.3.?`, each verified not to apply in the
  code. Twenty acceptances, each dated to the lot that lifts it.
- **The refresh needs the upload of what it holds.** uv's window filters ARTIFACTS (measured: a
  cutoff between a release's two uploads keeps the version with one of its files), and a
  per-package date overrides the global one in both directions (measured). So the window of a
  locked package never ends before the last artifact of the version it holds, and a final plain
  `deps:lock` restores every artifact. On the real locks: 75 changes in two passes, 17 seconds,
  no version lower than before, `lint:lockfiles` green; the result was restored, lot 8 applies it.
- `deps:upgrade:all` is removed (a second door for the same move, with no cooldown);
  `deps:lock` takes the refresh's arguments through `UV_EXTRA` and writes byte for byte what it
  wrote before. `task lint:deps` gates the three tools. The ten floors moved no version.
- Not verified: Dependabot's next run (cooldowns, `docker-compose` with `group-by`, the `vite`
  floor) and the workflow's first issue.

The design, as specified:

- `scripts/audit/dependency_watch.py` (proposed; standard library, network) and `task deps:watch`:
  repository-level advisories against every locked version; end-of-life dates of the product lines
  the repository pins, the line derived from the file that pins it; registry facts (an image that
  no longer exists, a missing arm64 variant, a deprecated npm version, a yanked PyPI version); the
  age of the browser engine (the Chromium major of the pinned Playwright against Chrome's supported
  majors). Every finding is accepted in `dependency_watch_accepted.json` — reason, owner,
  `review_by` — or fails; an acceptance past its date or matching nothing fails too. The report
  states how many packages it read of how many; a partial scan is named, never silent.
- Unit tests on recorded answers, no network: the range reader (the 28 open-ended false positives
  of this review are its fixtures), the lock parsers, the acceptance rules.
- Where it is read: a weekly workflow that opens or updates ONE issue (F9), and a step of the
  release procedure (`lia-release`), because a release is where the owner already looks.
- First acceptances, written: ESLint 9 (lifted when `eslint-config-next` depends on plugins whose
  peer range accepts ESLint 10), the installer's Python 3.10 (until 2027-06-01), openai 2.x (§6).
- `task deps:refresh`: `uv pip compile --upgrade --exclude-newer <today − cooldown>`, then a check
  that refuses any version lower than the lock it started from (F7).
- `.github/dependabot.yml`: the `docker-compose` ecosystem on `/`, `/infrastructure/docker` and
  `/scripts/install/tests/runtime`; npm on `/apps/web/e2e`; `cooldown` on every ecosystem (D4);
  pip version updates per D5. `package.json`: the `vite` override becomes a floor, the form
  `CI_CD.md` already calls preferable — to be confirmed by the first Dependabot run after it.
- Before the first `task deps:refresh`, the security bumps that live in a lockfile alone become
  floors in their manifest, each with its advisory in the comment as `requirements.txt:69-82`
  already do (`PyJWT>=2.15.1`, `anyio>=4.14.2`, `soupsieve>=2.9.2`, `click>=8.4.2`, `urllib3>=2.8.0`
  and the transitive bumps of lot 1) — F7: the refresh is the only command that could move a
  version backwards.
- One ADR, numbered when the lot lands (ADR-327 to ADR-330 are taken: 331 or later), the
  six-language map entries, `task docs:maps`, `task release:sync-counts`, and at most four lines in
  `CLAUDE.md` pointing at the ADR, then `task docs:sync-agents`.

### Lot 5 — python-jose leaves (implemented 2026-10-02, ADR-331 amendment)

Measured on landing: the seventeen-row table ran red on python-jose on exactly one row (« aud
absent »), then green on PyJWT 2.15.1, on the host and in the Linux dev container. A token minted
by python-jose 3.5.0 is recorded in `tests/unit/core/security/test_jwt_tokens.py` and read by
today's `verify_token`. D3 held its default. The resolution dropped exactly `python-jose`,
`ecdsa`, `rsa`, `types-python-jose` and `types-pyasn1`, moved nothing else; pip-audit reads the
three locks with no exemption left; the watch's ecdsa acceptance went with them. Proven on the
dev API: a garbage token answers 401, a well-signed token for an unknown account reaches the
account lookup (404), with `jose` absent from the host venv.

The design, as specified:


- Tests first: the seventeen cases of the JWT parity probe (§11) as a parametrised
  characterisation of `verify_provider_identity`, green on python-jose; the same table must hold
  after the swap, with one row changed on purpose (a token with no `aud` is now refused).
- `oauth_identity.py`: `jwt.PyJWK(key).key`, `jwt.decode(…, options per D3)`, a private
  `_verify_at_hash` — left half of SHA-256, base64url without padding, `hmac.compare_digest`,
  absent claim skipped, which is what python-jose does and PyJWT does not. `core/security/utils.py`:
  `jwt.encode` / `jwt.decode`, `except PyJWTError`.
- Measured: tokens issued by either library are read by the other, so a reset link sent before the
  deploy still works after it; `decode(None)` becomes a refusal instead of an `AttributeError`.
- Remove `python-jose`, `types-python-jose`, both `--ignore-vuln CVE-2024-23342`, the stale comment
  at `Taskfile.yml:1481`; rewrite the description at `core/config/security.py:163`. The resolution
  drops `python-jose`, `ecdsa`, `rsa` and two type packages and moves nothing else.

### Lot 6 — production observability, one service at a time (6a-6h rehearsed on dev 2026-10-02)

Rehearsed on dev, every image pinned by version and digest in the compose files and the self-host
catalogue; production is the owner's step, each service's volume snapshotted first. The newest
patch of three lines was younger than the five-day cooldown and was not taken (Prometheus 3.13.4,
redis_exporter 1.92.1, Grafana 12.4.12): 3.13.3, 1.92.0 and 12.4.11 instead.

- **6a Prometheus 3.13.3.** promtool 3.13.3 passes both rule files (116 rules), the alert unit tests
  and the configuration; on dev 116 rules evaluate `ok`, 11 targets `up`, no error line. The CI's
  promtool archive is now checked against the release's `sha256sums.txt` (a tampered archive is
  refused, measured).
- **6b Alertmanager 0.34.1.** Six receiver combinations ({no SMTP, e-mail only, e-mail + Slack and
  PagerDuty} × {LIA webhook off, on}) start through the real entrypoint, pass `amtool check-config`
  and route a critical alert to the same receivers as 0.27.0; Prometheus sees it on dev.
- **6c exporters and cAdvisor (now `ghcr.io/google/cadvisor`).** Of the metrics a dashboard or a
  loaded rule reads, none lost and none gained, exporter by exporter. cAdvisor exposes 2 411 series
  on the dev host: watch Prometheus's memory after the production step (F10).
- **6d Grafana 12.4.11**, in place over the 11.3.0 database (snapshotted): 31 dashboards, four
  datasources each answering its health check, no error line, 123.6 MiB — the production limit
  goes from 256M to 384M. The dev compose's `GF_INSTALL_PLUGINS` (an unpinned clock panel no
  dashboard uses, there since v1.0.0) is removed rather than migrated.
- **6e Loki 3.7.8.** The configuration verifies (a broken copy is refused), ready in 19 s where 3.2.1
  never answered `/ready` with 200, 39.7 MiB; a line pushed with structured metadata is read back by
  it, and Promtail 3.2.1 keeps shipping. The purge procedure moves to the Prometheus container
  (Loki has no shell since 3.5.8, F5), proven on dev: 204, then `received`.
- **6f Tempo 2.10.8**, same configuration: an OTLP span pushed and read back, the API's traces
  found, the metrics generator still writing span metrics (195 series) and the service graph to
  Prometheus. Its two configuration warnings (unscoped overrides, an unused v2 index setting) are
  left to the Tempo 3 move (§6), which removes those fields.
- **6h Portainer 2.39.8**: 2.39.0's data upgraded on a throwaway volume, same instance, no error.
- **6g Promtail → Alloy v1.19.2, step one**: the same Promtail-format file through
  `--config.format=promtail`. The service keeps its name: the deploy removes no orphan, so a renamed
  service would leave Promtail shipping beside Alloy. On dev, the redaction guard's corpus, written
  by a throwaway container, is stored exactly as `sanitize_url_query` renders it, credentials then
  content (5 lines of 5); the streams carry the same label keys before and after; Loki discarded
  nothing. The first start re-ships what the engine still holds of each container (2 973 duplicate
  lines on dev, whose containers were not recreated; production's deploy recreates them all); a
  restart re-ships nothing. **Found on the way:** the converter imports Promtail's legacy positions
  file into the file job of `/var/log/promtail.log` — a path that never existed and never shipped a
  line — and Alloy rewrote its 30 944 stale entries on every save: 3.1 GB allocated in two minutes,
  255 MiB held, the production limit to the MiB. That job goes, with every block Alloy ignores
  (`server`, `positions`, a line-rate limit never enabled, a file-discovery period): 106-111 MiB held,
  44 MB allocated in five minutes, and Alloy sets `GOMEMLIMIT` to 90 % of its container's limit by
  itself (measured), so 256M stays. Alloy also reports usage to Grafana Labs by default:
  `--disable-reporting`, and `test_observability_reports_no_usage_guard.py` holds Loki, Tempo,
  Grafana and Alloy to it. Production step: through the deploy, which recreates every container
  (Alloy started alone over old ones re-ships what the engine holds of each); then delete
  Promtail's files from the positions volume (`rm -f /tmp/positions.yaml /tmp/.positions.yaml*`
  in the container), which nothing reads now.

The design, as specified:


Every step updates the production and dev compose files, the catalogue, the documents, and pins by
digest; is rehearsed on dev; snapshots the service's volume before the production change, because
neither Grafana's database migration nor a newer TSDB goes backwards.

| Step | From → to | Measured before writing this |
|---|---|---|
| 6a | Prometheus 3.0.0 → 3.13 LTS (supported to 2027-07-31), with promtool in `Taskfile.yml` and `ci.yml` | Starts with the production flags and entrypoint; `promtool test rules` passes; both rule files load. |
| 6b | Alertmanager 0.27.0 → 0.34.1 | The five receiver combinations render, start and pass `amtool check-config`. |
| 6c | blackbox 0.25.0 → 0.28.0, node-exporter 1.8.2 → 1.12.1, postgres-exporter 0.15.0 → 0.20.1, redis_exporter 1.62.0 → 1.92.1, cAdvisor → `ghcr.io/google/cadvisor:v0.60.6` | No metric name read by a dashboard or a loaded rule disappears; image users unchanged. Watch Prometheus memory after cAdvisor (F10). |
| 6d | Grafana 11.3.0 → 12.4 (to 2027-05-24) | In-place upgrade of a 11.3.0 database: healthy, 31 dashboards, four datasources, no error line. Raise the limit from 256M to 384M. |
| 6e | Loki 3.2.1 → 3.7 | Configuration valid, ready in 16 s, a push with structured metadata accepted, 44 MiB. Rewrite the purge procedure to call Loki from the Prometheus container, which keeps a shell (F5). |
| 6f | Tempo 2.6.1 → 2.10.8 | Same configuration, a span pushed over OTLP and read back. Tempo 3 is §6. |
| 6g | Promtail 3.2.1 → Alloy, step one: the same YAML through `--config.format=promtail`; service renamed | Parity above; 39 MiB. Rehearse the first start on dev: Alloy keeps no Promtail position for Docker targets, so count what Loki rejects and what it duplicates. |
| 6h | Portainer 2.39.0 → 2.39.8 now, 2.45 LTS before November 2026 | Portainer's lifecycle table. |

After 6g the two Promtail guards still read the file Alloy runs. Step two — a native
`config.alloy`, both guards reading it, the infrastructure module renamed on the maps in six
languages — is a lot of its own.

### Lot 7 — the demonstrator, the build inputs, the dev profile

- Demonstrator: cloudflared 2026.9.x; `ubuntu/squid:6.6-24.04_edge` (it carries Squid 6.14 on a
  base supported to 2029; `squid -k parse` accepts `squid.conf`; the 26.04 image has no shell to
  check with); postfix 5 and the collector 0.161 each with a demonstrator rehearsal
  (`task demo:prod:verify`). The four demonstrator `.env` files are untouched: no setting changes.
- Builds: `alpine`, `python:3.14-slim-trixie` and `node:24-alpine` by digest; the Claude Code CLI
  at the version its `stable` tag names; the Node tarball at an exact version; a checksum on the
  sherpa-onnx archive and a pinned revision for the Whisper model.
- Database and cache: `pgvector/pgvector:0.8.6-pg16-bookworm@sha256:…` and `redis:7.4.x-alpine@…`
  — a pin, not a migration; read the PostgreSQL 16.12 to 16.15 release notes first;
  `ALTER EXTENSION vector UPDATE` is a separate, deliberate act.
- The dev Langfuse profile is out of scope (D2).

### Lot 8 — the catch-up, once the pipeline is sound

Two changes, never one: the npm minor-and-patch group, then `task deps:refresh` for Python. The
first Python refresh moves about 76 packages under a 14-day cooldown, four across a major
(`websockets` 15 → 16 among them); it is read line by line before it is run.

### Lot 9 — migrations with their own plan

FastAPI ≥ 0.137 (one route walker for the 28 modules that read `router.routes`, then the bump);
`webauthn` 3.0.1 with `cbor2` 6 (22 tests pass on it) and SQLAlchemy 2.0.54 (in the measured
overlay); the e2e package on Playwright 1.63 and the `noble` image with the accessibility matrix
repaired; `pydub` replaced by a direct ffmpeg call, which also drops `audioop-lts`; the asyncpg
allowlist whose `review_by` is 2026-10-01 (`pyproject.toml:291`).

## 6. Deferred, with the condition that reopens each

| Subject | Stays on | Reopened when |
|---|---|---|
| openai 3, anthropic 1 | 2.54.0, 0.125.0 (langchain-openai 1.6.6 accepts `>=2.45,<4`) | an advisory on the 2.x line, or the LangChain packages refusing it |
| LIA's own calls on httpx2 | httpx 0.28.1 behind the bounded reader | httpx 1.0 stable, or the last dependency leaving httpx |
| SQLAlchemy 2.1, vitest 5, mermaid 12 | 2.0, 4.1, 11 (all maintained) | the major is older than the cooldown |
| TypeScript 7, ESLint 10 | 6.0.3, 9.39.5 (accepted) | typescript-eslint and `eslint-config-next` accept them |
| pnpm 11 or 12 | 10.34.x (to 2027-04-30) | Dependabot documents the version |
| Capacitor 9, Tempo 3, Node 26 | 8.5.x, 2.10.x, 24 LTS (to 2028-04-30) | a stable release; for Tempo, no more 2.10 patches |
| PostgreSQL 18 | 16 (to 2028-11-09) | a planned dump and restore, in 2027 |
| KaTeX 0.19 | 0.18.9 (0.18.11 deprecated upstream) | 0.19 older than the cooldown, and `rehype-katex`, `mermaid` and the guard of lot 1 green on it |
| `multidict` 7 | 6.9.1 | the major older than the cooldown, `aiohttp` declaring it |
| `@bufbuild/protobuf` 2, through `@elevenlabs/client` | 1.10.1 (two medium advisories, input from the voice vendor's server) | an `@elevenlabs/client` release whose `livekit-client` moves to it; the client is pinned exactly because its protocol was measured |
| `postcss-selector-parser` 7, `powershell-utils` 0.2 | 6.0.10, 0.1.0 (build and code-generation tools only) | lot 8, with the parents that pull them |
| `eslint-config-next` 16.3.x | 16.2.10 beside `next` 16.3.8 | lot 8, with a decision on `@next/next/no-location-assign-relative-destination` at `lib/api/chat.ts:546` (a full reload to the login page from a module with no router) |
| The Google media proxies (`connectors/media_proxy_router.py`) and the Drive thumbnail proxy (`connectors/router.py`) | whole-body reads of Google's own images, `follow_redirects=True` | a proxy that serves a host somebody else chose, or an image measured past what a page can show; then `read_bounded` with a ceiling of its own |

## 7. Impact map and risks

| Lot | Touches | Can break | Kept from breaking by |
|---|---|---|---|
| 0 | every job that installs | nothing: it restores them | a fresh frozen install |
| 1 (mcp) | user and admin MCP tools, ReAct and pipeline | a server reached through a cross-origin redirect now fails; a tool with an external reference fails at call time; a legacy (2025) server no longer connects | the first two are tested and fail with a message naming the cause; a trailing-slash redirect and an in-document reference are tested to keep working; a 1.28.1 server measured on 2.2; the dev servers re-discovered against a baseline; production failures counted for 24 h after the deploy |
| 1 (browser) | browser tool, image size | a CDP shape change; an engine release ahead of what the driver was released with; an arm64 package trailing amd64 | a real launch, accessibility tree, click and fill on Debian's 154 in the dev image, in a production image built from the candidate, and on the Pi; a failed launch counted on dashboard 20 and the engine logged at launch; `task sandbox:libraries:check` |
| 1 (JS) | chat rendering, mobile shells, every build | formula markup read by `rehype-table-labels`, search highlight, the sanitise schema; a stale dev `node_modules` | the existing math test modules, the stylesheet guard, the browser spec, the whole e2e suite (369), the dev web container rebuilt on fresh volumes and its versions read inside |
| 2 | web fetch, radio newsroom, skill import and library, image download, avatar proxy, the typed-choice client | a site answering in a coding nobody offered (brotli); a compressed body cut short, which httpx used to hand over shortened | refused before any decode as a transport failure each caller already handles, the web fetch tool naming it (`INVALID_RESPONSE_FORMAT`); the request header makes the first rare; zstd is decoded |
| 3 | CI only | a pull request that was green turns red on a debt | baselines hold today's state |
| 4 | CI schedule, release procedure | a vendor API that is down | a failed source is named, never read as « nothing to report » |
| 5 | e-mail verification, password reset, connector linking | a provider token refused for a clock second | D3; the characterisation table; tokens cross-read both ways |
| 6 | dashboards, alerts, the logs' redaction, the self-host installer | a panel with no data, an alert that cannot fire, a line that reaches Loki unredacted | metric-name diff, rule unit tests on the new promtool, pipeline parity probe, a test alert fired end to end |
| 7 | demonstrator egress and mail, every image build | the account-activation e-mail, the tunnel | `task demo:prod:verify`, a no-cache production build |
| 8 | everything | the usual | two separate changes, the full gates, the no-downgrade check |

Transverse: a deploy ships the working tree, so every lot is deployed from a clean worktree of its
commit; the dev images are rebuilt after any lock change; the Pi is arm64 and every image and wheel
above was checked for it; nothing here adds a setting, a migration or a translated string.

Shared files: the skill-library work landed with v2.2.0 (ADR-327), so a Python change of this
programme regenerates three lockfiles and rebuilds the sandbox image (`task sandbox:image:build`,
`task sandbox:libraries:check`). Other sessions write in the same tree: a lot starts from the
current `main`, and two changes that regenerate one lockfile are sequenced by the owner, never
interleaved — fact 3.

## 8. Test plan

| Level | What |
|---|---|
| Unit, backend | the four MCP reference and redirect cases; `test_bounded_read.py`; the JWT characterisation table; the import, build-input, catalogue and single-value guards; the watch's parsers on recorded answers |
| Unit, frontend | the KaTeX stylesheet guard; the existing math, sanitise and table-label suites |
| Integration | PyJWT-issued and jose-issued tokens through the real routes; webauthn ceremonies on recorded vectors |
| Flow, in containers | the log pipeline probe (four lines, both shippers); a span through Tempo; an in-place Grafana upgrade; the five Alertmanager combinations; exporter scrapes diffed against what dashboards and rules read |
| Browser | the formula spec in the e2e suite (computed layout in a real engine); a formula seen in the dev chat; the mobile probes after Capacitor |
| Production, read-only, after each deploy | the running image digests, a control query in Loki on a period known to hold lines, dashboards 01 and 03, one alert fired and delivered |

Edge cases to exercise, by name: a redirect to another origin; a schema reference to `file://`;
a compressed bomb in each encoding; a stream with no length; a truncated stream; a token with no
audience, a wrong `at_hash`, a clock one minute ahead, a malformed token, a token issued by the
other library; a first Alloy start over containers with weeks of logs; a Grafana restart at its
memory limit; a lockfile merged from two regenerations; a refresh that would downgrade; a vendor
source that does not answer.

## 9. Rejected

- **A `uv.lock` project** so that Dependabot can update Python: ADR-112 already weighed it; the
  replay task and the watch close the gap without moving the declarations.
- **Renovate in place of Dependabot:** a second writer of the same files, and a decision about a
  third-party application with repository access that nothing here requires.
- **ESLint 10 through the workaround of vercel/next.js#89764:** three shrink-only ratchets read
  plugins whose peer range refuses it.
- **The watch inside `ci:fast`:** a network answer must never turn a pull request red (ADR-112).
- **Redis 8, PostgreSQL 18, the trixie base, Tempo 3 now:** §1 and §6.
- **One lot for the whole observability stack:** eight services, eight rollbacks.

## 10. What was not verified

- **The production host.** Docker Engine's version (28 is end of life since 2026-05-13), the
  digests actually running, the host `cloudflared`, the extension versions in the production
  database. Each infrastructure lot opens with those reads.
- **Dependabot's behaviour after the changes of lot 4** (the floor override, digest-pinned compose
  references): observable only on its next run.
- **A formula seen in the running application.** The defect is proven by measurement, on a static
  page built from the application's own packages, and on the real chat page of a production build
  driven by Playwright with a mocked API — not yet on the dev or production chat with a real
  answer (plan, Task 3 and Task 5).
- **The production image on arm64.** Debian's Chromium was driven by Playwright 1.63 on the Pi in
  a throwaway container, but the release image itself is built for arm64 by the release workflow,
  which does not launch the browser; this host has no arm64 emulation. The first launch of the
  released image is the production check of the plan's Task 5.
- **Every external API version** the backend calls was listed and none looked retired; that list
  was not checked against each vendor's deprecation page.
- **Exploitation of F1 to F3 end to end against a running LIA.** Each is proven at the level of the
  component and of the exact call LIA makes.

## 11. Probes written for this review

Session files, outside the repository; each is a few dozen lines and is rebuilt from its line here.
None of them writes to the repository, and every container they start is disposable and on a
network of its own.

| Probe | What it measures |
|---|---|
| `repo_advisories.py` | For each package of the four lockfiles: its repository (registry metadata), that repository's published advisories (`gh api repos/…/security-advisories`), the ranges containing the locked version, and whether GitHub's global database knows the advisory. An open-ended range is kept only when the locked version is below the patched one. |
| `undeclared_imports.py` | AST walk of `src/`, `importlib.metadata.packages_distributions()`, against the names `requirements.txt` declares. |
| `mcp_ref_probe.py` | The SDK's own `ClientSession._output_schema_validator` on a schema whose `$ref` is a loopback URL; counts the requests received. |
| `bomb_probe.py` | `httpx.MockTransport` serving 200 MiB of zeros as gzip and as zstd, read the way `web_fetch_tools.py:345-361` reads and the way `read_bounded` reads. |
| `jwt_parity_probe.py` | Seventeen provider-token cases through python-jose and through a PyJWT candidate; HS256 tokens read across both libraries. |
| `browser_smoke.py` | Chromium launched by `BrowserPool.initialize()` itself (the arguments of `pool.py:112-121`), the tree read by `AccessibilityTreeExtractor` through CDP on a page set in place. |
| `log_pipeline_probe.sh` | The repository's Promtail configuration (discovery label changed, nothing else) run by Promtail 3.2.1 and by Alloy, each into its own Loki 3.7.8, on four lines; compares what arrives. |
| `grafana_probe.sh`, `tempo_probe.sh`, `alertmanager_probe.sh`, `exporters_probe.sh` | The repository's configuration started on the version in use and on the target, with the data path exercised; exporter metric names diffed against `referenced_metrics.py`. |
| `py_scenarios.sh`, `lock_diff.py` | `uv pip compile` with the Taskfile's flags on scratch copies of the manifests; package-level diff. `uv` 0.12.18 reproduces the current lockfile byte for byte. |
| `full_unit_suite.sh` | The pre-commit selection of the backend unit suite in a container of the dev API image, as built and with the candidate versions overlaid. |
| `legacy_mcp_server.py`, `legacy_mcp_probe.py` | A FastMCP server on SDK 1.28.1 in a throwaway container; the pool's discovery and call paths against it, on `/mcp` and on `/mcp/` (a same-origin 307), from SDK 2.0 and 2.2. |
| `mcp_dev_servers_probe.py` | The pool's discovery path over every enabled dev server without OAuth; prints an id prefix and a verdict, never a URL. |
| `run_frontend_gates_v2.sh`, `run_vitest_full.sh` | Lint, the three ratchets, `tsc` and vitest in `node:24.21.0-alpine`; then `pnpm test:coverage` on a faithful `git archive` workspace (public assets, the API files and the wake-word toolbox the web tests read). |
| `run_e2e_math.sh`, `run_e2e_full.sh` | `task test:e2e` reproduced in the CI image (`playwright:v1.60.0-jammy`): e2e typecheck, managed production build, the math spec and its control, then the whole default suite. |
| `debian_chromium_probe.py`, `pw_native_deps.js` | Playwright 1.63 driving Debian trixie's Chromium through `executable_path`; the Debian 13 library list each Playwright driver declares. |
| `render_alembic_template.py` | The repository's Alembic revision template rendered through `alembic.util.template_to_file` on two Mako versions, compared byte for byte. |

