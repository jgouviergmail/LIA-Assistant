# Reproduction notes for isolated LIA world characterization

These files are disposable characterization fixtures, not application code or a proposed production implementation. Measurements are transcribed from completed tool outputs in [observations.json](observations.json); scope/interpretation lives in the [validation report](../../../2026-10-09-lia-isometric-world-validation.md). They contain no host identity, credentials, participant data or paid provider output. Browser distributions are not vendored here.

## Existing targeted tests

Run from the repository root for the Docker commands:

```powershell
docker exec -e NEXT_PUBLIC_API_URL= lia-web-dev pnpm exec vitest run src/components/eyes/__tests__/useCompanionEnvironment.test.tsx src/components/eyes/__tests__/useCompanionEnvironment.context.test.tsx src/hooks/__tests__/useApplicationStateSync.test.tsx src/lib/__tests__/csp.test.ts src/lib/__tests__/settings-sections.test.ts --reporter=dot
docker exec -e NEXT_PUBLIC_API_URL= lia-web-dev pnpm exec vitest run src/components/settings/__tests__/LanguageSettings.test.tsx src/components/__tests__/LanguageSelector.test.tsx src/lib/__tests__/language-match.test.ts --reporter=dot
```

Run from apps/api using its configured venv:

```powershell
.venv/Scripts/python.exe -m pytest tests/unit/domains/briefing/test_companion_environment.py tests/unit/domains/peers/test_models.py tests/unit/domains/peers/test_service.py tests/unit/domains/peers/test_connection_release.py tests/unit/domains/memories/test_active_set_filters.py tests/unit/domains/usage_limits/test_cost_bearer_declaration.py tests/unit/domains/usage_limits/test_instance_budget_enforcement.py --no-cov -q
.venv/Scripts/python.exe -m pytest tests/unit/domains/radio/test_articles.py tests/unit/core/test_i18n_language_name.py tests/unit/core/test_i18n_declared_language.py --no-cov -q -o log_cli=false
```

The first family totals 201 frontend tests; the second 12. Backend families total 124 and 106. These selections are the observed runs, not substitutions for required implementation CI tasks. The final collection-only check independently counted the latter 106 without rerunning the already-passing suite.

## Admission primitive

Run only against the disposable development boundary named below. The script obtains configured Redis credentials internally, targets database 15, creates four exact UUID-prefixed keys and deletes only those keys. Never use a database flush. The trusted injected clock is a test fixture. Full production ticket/reservation/auth logic is intentionally absent.

```powershell
Get-Content -LiteralPath 'docs/superpowers/specs/assets/2026-10-09-lia-world/evidence/admission_probe.py' -Raw -Encoding UTF8 | docker exec -i lia-api-dev python -
```

## Browser fixtures

Copy probe.html and three-probe.html to an ignored scratch directory. In that directory, obtain the pinned distributions actually characterized: Pixi 8.22.0 dist/pixi.min.js, and Three 0.186.1 build/three.module.js plus build/three.core.js. These are measurement versions, not LIA dependency declarations. The corresponding official package CDN paths are:

- https://cdn.jsdelivr.net/npm/pixi.js@8.22.0/dist/pixi.min.js
- https://cdn.jsdelivr.net/npm/three@0.186.1/build/three.module.js
- https://cdn.jsdelivr.net/npm/three@0.186.1/build/three.core.js

Copy the current apps/web/public/avatars/bip/v1/male/body.webp as scratch/bip.webp. Serve that scratch directory on localhost and open the pages in an isolated browser session. Do not place downloaded scripts in the application public bundle. The probe pages expose measurement/input/camera helpers, not an application protocol. Record GPU/viewport/DPR, baseline and active frame distributions, cold/warm observations and failures. Keep raw failed/degraded results rather than selecting only the smooth run.

The actual observed host used an RTX 4090, a 1280 x 720 viewport and later a 390 x 844 viewport on the same desktop. No physical-phone result exists. The test HTTP server and isolated browser session are closed after review.

The final visual gallery was separately served for a local browser check. All five images decoded, with no horizontal overflow at 390 x 844 and 1280 x 900. This verifies the gallery artifact only; it adds no phone or game-performance evidence. An initial file-protocol navigation was rejected by the automation browser, so the check used a localhost-only server instead.

## Pi observation and CPU-only fixture

Use the owner's configured SSH host without placing its address/credentials in documentation. Read-only host/container snapshots were used for installed/available memory, short vmstat intervals, temperature/throttling and API worker configuration. No application data was queried.

server_tick_probe.py runs a bounded memory-only calculation with no application imports, Redis, database, files or network. The actual run was piped into one subprocess in the existing API container, with a three-second computation bound and under one second observed runtime. It is not a stress test; do not interpret it as full capacity or repeat it broadly on production. For future complete mixed-load qualification, use the separately agreed staging/production protocol and record existing LIA baseline interference.

## Documentation gate

The subsequent [global review](../../../2026-10-09-lia-isometric-world-global-review.md) adds a [fresh source/check manifest](global-review-evidence.json): 140 existing backend tests and 88 existing frontend tests in Docker dev, with referenced source fingerprints. These overlap the previous checks; they are neither new-world certification nor additional unique coverage. No production observation or paid model request was added by that pass.

Run task lint:docs:preview from the repository root. It evaluates the working-tree additions without staging unrelated changes. The refreshed run after adding the validation report, gallery and evidence found zero broken living links, zero stale living paths, zero living orphans and zero quoted-fact drift. The overall task still fails on the same six pre-existing technical-map coverage gaps: account_export_downloads, application_sessions, file_transfer, phone_history, phone_number_preferences and phone_preferences. Historical/roadmap diagnostics are reported separately by the repository tool and are not introduced by these artifacts. No baseline is weakened and no concurrent source changes are repaired by this analysis.

Probe source SHA-256 values at the recorded snapshot:

| Fixture | SHA-256 |
|---|---|
| admission_probe.py | e180c4afaa84a1116d0ebd9e2c3a3db250d87b21742217aed3c4d861a4265b89 |
| server_tick_probe.py | a234ebdad791c80d7a5db93d3fe3695caa8a33ce39f9c208abe50e81f782f258 |
| probe.html | 6f944cfe7ee7f350445ef6d7f54ebd5b6e7e3c50840611cbeecc240d99b671f7 |
| three-probe.html | a0ec5d5042de410b77335def7e21381a163cda5b0f9b340b38358a2d3d3d0607 |
