# Model lifecycle read from the vendors — design

**Date:** 2026-09-26
**Status:** designed with the owner section by section (2026-09-26); written spec awaiting the
owner's review. Plan: written after approval, in `docs/superpowers/plans/`.
**Scope:** every model of the LLM catalogue, for every provider. A daily job reads what each
vendor announces about its models' lifecycle and whether its API still serves them, writes the
shutdown dates, retires a model when every source agrees it is gone — performing exactly what an
administrator's manual deactivation performs — and informs administrator accounts only. Lot 0
also closes four defects found in the uncommitted Gemini catalogue lot of the same day.

## Problem, measured on 2026-09-26

1. **Nothing reads a lifecycle date on a schedule.** The only flow is manual:
   `task llm:catalogue:fetch` vendors two public registries (LiteLLM, models.dev) into
   `infrastructure/llm/catalogue/snapshot.json`; `task llm:catalogue:sync`, `task
   llm:catalogue:preflight` and `GET /admin/llm/catalogue-status` read that snapshot. No scheduler
   job reads a date, so a catalogue is as current as the last time someone ran the fetch.
2. **The registries contradict the vendor.** LiteLLM dates Gemini 2.5 Pro, Flash and Flash-Lite
   2026-10-20 and the two Gemini 3.5 models in 2027; Google's deprecations page announces no
   shutdown for any of them (the 2.5 models « will continue to be served until further notice »).
3. **A date is not proof.** Google calls its dates the « earliest possible » shutdown, and its API
   still served three models whose date had passed: `gemini-3.1-flash-lite-preview` (2026-05-25),
   `gemini-3-pro-image-preview` (2026-06-25), `gemini-embedding-2-preview` (2026-08-10).
4. **A model list is not proof either.** Compared with the active catalogue, each vendor's list
   omits models that work: Anthropic lists dated snapshots, not the aliases `claude-sonnet-4-5`,
   `claude-opus-4-5`, `claude-haiku-4-5`; DeepSeek no longer lists `deepseek-v4-flash`, a retired
   name its API still accepts; ElevenLabs' `/v1/models` covers speech synthesis only, so
   `scribe_v1` and `scribe_v2` are absent. Perplexity has no list at all (404).
5. **The vendor table written by hand the same day covers Gemini only and ages**
   (`infrastructure/llm/catalogue/vendor_announcements.py`).
6. **What the vendors publish** (read the same day): Google — a deprecations page of tables
   (model, release, shutdown, replacement); Anthropic — a deprecations table (model, state,
   deprecated, retired); OpenAI — one table per announcement (« Shutdown date | Model / system |
   Recommended replacement »), naming dated snapshots, not aliases; DeepSeek — a prose change log
   (« deepseek-chat and deepseek-reasoner will be discontinued … (2026-07-24) »); Perplexity — a
   prose changelog (« sonar-reasoning … removed as of December 15, 2025 »); Qwen — a model page
   rendered by JavaScript (empty as HTML); ElevenLabs — a models page with no dates.
7. **What a manual deactivation does** (`DELETE /admin/llm/pricing/{pricing_id}`):
   `LLMModelService.deactivate` switches the model and its active tariff off (the tariff row is
   kept, so past costs stay exact); an `AdminAuditLog` row is added; the transaction commits;
   `_invalidate_caches` reloads `ModelCapabilitiesCache` and republishes the pricing cache to every
   worker; a structured log line is written. It checks no reference. `admin_audit_log.admin_user_id`
   is a NOT NULL foreign key, which is why the automatic account deletion skips its audit row.

## Owner decisions (2026-09-26)

1. **Coverage:** every model present in the catalogue, every provider — never a partial table.
2. **Automatic:** a scheduled job, not a manual flow.
3. **Retirement:** when every source agrees a model has expired, deactivate it and perform every
   action a manual deactivation performs.
4. **Evidence rule:** the vendor's own API says the model is no longer served (asked model by
   model, with the instance's key) AND an announced shutdown date has passed (the vendor's page,
   else a registry) AND no source says it is still active. A provider with no way to ask its API
   is informed about, never retired automatically.
5. **A model still in use is retired anyway** — « it will not work anyway » — and the
   administrators are told which slots to re-target.
6. **Anthropic:** its free model endpoint (list and retrieve) is the one Anthropic call allowed;
   no other call to the Anthropic API (the account's credit is zero, 2026-09-23 directive).
7. **Approach:** a lifecycle package and a daily job; the registries stay vendored and manual and
   only supply a fallback date.
8. **Audience:** only administrator accounts are notified and informed.

## 1. Components

- `infrastructure/llm/catalogue/lifecycle/` — small units, each testable alone:
  - `sources.py` — the declaration, per `LLMProviderEnum` member, of its announcement source
    (page URL and parser) and its served probe, or `None` with a written reason. A boot assert
    refuses a provider with no declaration (ADR-085); adding a provider without deciding its
    lifecycle fails the boot.
  - `parsers/` — one pure function per page shape: `google_tables`, `anthropic_table`,
    `openai_tables`, `dated_prose` (DeepSeek, Perplexity). Input: page HTML. Output: a mapping
    `model id -> ShutdownAnnouncement(date | None)`, or a `SourceReadError`.
  - `probes.py` — asks the vendor about one model, with the instance's key and configured base
    URL: `SERVED` (an answer naming the model, an alias included), `GONE` (the vendor's explicit
    « model not found »), `UNKNOWN` (anything else).
  - `verdict.py` — the rule of section 3, a pure function.
- `domains/llm/retirement.py` — `retire_model(...)`, the ONE retirement operation. The admin
  route calls it and so does the job, so a job retirement and a manual one are the same act by
  construction (section 5).
- `infrastructure/scheduler/model_lifecycle.py` — the run (section 6), registered by
  `infrastructure/startup/scheduler_catalogue.py` behind the leader election, a `SchedulerLock`
  with an owner token, and `jitter_seconds_for`.
- `task llm:catalogue:lifecycle` — the same run from the command line, dry-run by default,
  printing the verdict table.
- `vendor_announcements.py` is deleted: the dates live in the database, written by the job.

## 2. Sources per provider

| Provider | Announcements | Served probe | Automatic retirement |
|---|---|---|---|
| gemini | deprecations page tables | `GET /v1beta/models/{name}` | yes |
| anthropic | model-deprecations table | `GET /v1/models/{id}` (resolves aliases) | yes |
| openai | deprecations tables — exact snapshot names only, never a prefix | `GET /v1/models/{id}` | yes |
| deepseek | change log, dated statements naming a catalogue model | none authoritative: the list omits names the API accepts | no — informed only |
| perplexity | changelog, dated statements naming a catalogue model | none (no list) | no — informed only |
| qwen | established in lot 2; `None` with its reason if no official page exists | the configured compatible endpoint's retrieve, if lot 2 measures one; else `None` | only with a probe |
| elevenlabs | `None` unless lot 2 finds an official dated source | `GET /v1/models`, for `kind = tts` rows only (the list covers synthesis only) | tts only, with a date |
| ollama | `None` — a local server has no vendor lifecycle | the server's tags (already discovered) | no — no date ever |
| edge | `None` — a local bridge | `None` | no |

A registry date (LiteLLM, uncontradicted by models.dev) is the fallback announcement for a model
the vendor's page does not list. The vendor always wins: a model the vendor lists with no
shutdown announced has no date, whatever a registry says.

## 3. The rule

For each active model, once per run:

- **announced** = the vendor's date when the vendor lists the model (source `vendor`); else a
  registry date (source `registry`); else none. « Listed, no shutdown announced » is none.
- **served** = the probe's answer: `SERVED`, `GONE` or `UNKNOWN`. Only the vendor's explicit
  not-found is `GONE` — classified by HTTP status and the vendor's error code, never by message
  text (the codes are measured with free calls in lot 2). A timeout, a 5xx, 401, 403 or 429 is
  `UNKNOWN`. A provider without a probe always yields `UNKNOWN`.

Every combination falls in exactly one row:

| announced | served | verdict | action |
|---|---|---|---|
| ≤ today (UTC) | `GONE`, confirmed | `RETIRE` | retire (section 5), notify |
| ≤ today | `GONE`, first sighting | `RETIRE_PENDING` | nothing yet; the next run confirms or clears it |
| ≤ today | `SERVED` | `ANNOUNCED_STILL_SERVED` | nothing (Google's « earliest possible ») |
| ≤ today | `UNKNOWN` | `ANNOUNCED_PAST_UNVERIFIED` | notify when in use (a provider without a probe, or a probe that failed) |
| > today | any | `ANNOUNCED` | notify when in use and within `RETIREMENT_NOTICE` (30 days, the existing constant) |
| none | `GONE` | `NOT_SERVED_UNANNOUNCED` | notify (an alias, a key restriction, an unannounced removal) |
| none | `SERVED` or `UNKNOWN` | `KEEP` | nothing |

Two safeguards sit on top of the table:

- **Confirmed means seen twice.** `GONE` must hold on two runs at least
  `LLM_CATALOGUE_LIFECYCLE_CONFIRM_HOURS` (20) apart, the first sighting kept in
  `vendor_gone_since`; any other answer in between clears it. A vendor's transient « not found »
  (an outage, a rolling deployment) therefore retires nothing.
- **A human reactivation stands.** A model the job retired carries `lifecycle_retired_at`. If an
  administrator switches it back on (the pricing sheet import is today's path), the job never
  retires it again and notifies instead: the administrator decided with information the job does
  not have. A manual reactivation writes no per-model audit row, so the decision is read from the
  row's own state (`is_active` with `lifecycle_retired_at` set), never reconstructed from the log.

The job never reactivates a model and never writes a price or a capability.

## 4. Data

- `llm_models.deprecation_date` — written on every row the sources know, whatever its
  provenance (ADR-244 already treats this field as the provider's announcement); a model the
  vendor lists with no shutdown announced gets `NULL`, clearing a registry's date. A row no
  source knows is left as it is. New `deprecation_source` (`vendor` | `registry`, nullable).
- New `llm_models.vendor_served` (`served` | `gone` | `unknown`, nullable = never asked),
  `vendor_checked_at` and `vendor_gone_since` (timestamptz), and `lifecycle_retired_at`
  (timestamptz, set by an automatic retirement).
- New table `llm_lifecycle_sources` — one row per (provider, source kind): last attempt, last
  success, last error code, entries read. It is what tells a failing source from a silent one
  across runs and restarts. Declared `GLOBAL` in the user data map.
- `admin_audit_log.admin_user_id` becomes nullable and a new `actor` column (`admin` |
  `system:model_lifecycle`, NOT NULL, default `admin`) says who acted, with a CHECK that an
  `admin` row carries an administrator. The CHECK is safe with the foreign key: its action is
  `CASCADE`, which deletes the row rather than nulling the column. A retirement row carries its
  evidence in `details`: announced date and source, the probe's answer and time, the slots that
  still used the model.

## 5. Retirement — the same act as an administrator's

`retire_model(db, model_name, *, actor, evidence, request=None) -> RetirementResult`:

1. `LLMModelService.deactivate(model_name)` — the model and its active tariff (history kept);
2. an `AdminAuditLog` row — `actor` and `admin_user_id` for a person, `system:model_lifecycle`
   and the evidence for the job;
3. commit;
4. `ModelCapabilitiesCache.invalidate_and_reload` and `refresh_and_publish_pricing_cache` — every
   worker;
5. the structured log line;
6. returns the slots (`llm_config_overrides`) and code defaults (`LLM_DEFAULTS`) that still name
   the model.

The admin route `DELETE /admin/llm/pricing/{pricing_id}` is rewritten to call it, so the two
paths cannot drift.

## 6. The job

- Registered in `startup/scheduler_catalogue.py`: interval `LLM_CATALOGUE_LIFECYCLE_INTERVAL_HOURS`
  (24), jitter, leader only, `SchedulerLock` with an owner token; switched by
  `LLM_CATALOGUE_LIFECYCLE_ENABLED` (on, off in the demonstrator's env files);
  `LLM_CATALOGUE_LIFECYCLE_DRY_RUN` (off); `LLM_CATALOGUE_LIFECYCLE_MAX_RETIREMENTS` (5);
  `LLM_CATALOGUE_LIFECYCLE_CONFIRM_HOURS` (20); `LLM_CATALOGUE_LIFECYCLE_STALE_DAYS` (3).
- One run: read the catalogue on a short session, closed → read each announcement source once
  (bounded concurrency, per-source timeout, each source isolated) → probe every active model of
  the providers that have a probe (bounded concurrency) → compute the verdicts → write dates,
  served states and source health on a short session → **circuit breaker**: more `RETIRE`
  verdicts than the maximum retires none and notifies the administrators → otherwise
  `retire_model` for each → notifications → metrics. No database session is held across a
  network call (ADR-304).
- `task llm:catalogue:lifecycle [--apply] [--max-retirements N]` runs the same code; without
  `--apply` it only prints what it would do. It is how an administrator confirms a first run that
  the breaker stopped.

## 7. Notifications — administrator accounts only

The existing path is reused: `domains/diagnostics/notifications.py` already notifies active
superusers only, in-app and by push (and their bound channels), in each administrator's
language, behind an atomic per-key cooldown, with no e-mail (Alertmanager e-mails). Its loop is
extracted into a shared `notify_superusers(...)` that diagnostics and the lifecycle both call.

| Message | When | Cooldown key |
|---|---|---|
| model retired | after a `RETIRE`, listing the slots to re-target | model |
| shutdown announced for a model in use | `ANNOUNCED` within 30 days, or `ANNOUNCED_PAST_UNVERIFIED`, on a model a slot or a code default names — with the date and whether it could be verified | model + date |
| model no longer served, unannounced | `NOT_SERVED_UNANNOUNCED` | model |
| reactivated model still reported gone | a model an administrator reactivated, still `GONE` | model |
| source unreadable | no successful read for `LLM_CATALOGUE_LIFECYCLE_STALE_DAYS` (3) | provider + source |
| breaker tripped | more retirements than the maximum | run date |

The six messages are a translated table in six languages under the i18n completeness guards.

## 8. Failure handling

- A source that errors, times out, or returns zero entries where it last returned some is a
  **failed read**: counted, recorded in `llm_lifecycle_sources`, never read as « no date ».
- A probe that is not an explicit not-found is `UNKNOWN`, never `GONE`.
- One failing provider never stops another; a failing run retires nothing it has not proved.
- Every failure log carries codes and counts, no page content (ADR-317).

## 9. Observability

- `llm_catalogue_lifecycle_source_reads_total{provider, source, outcome}`
- `llm_catalogue_lifecycle_probes_total{provider, outcome}`
- `llm_catalogue_lifecycle_retirements_total{provider}`
- `llm_catalogue_lifecycle_breaker_trips_total`
- `llm_catalogue_lifecycle_source_last_success_timestamp_seconds{provider, source}`
- `llm_catalogue_lifecycle_last_run_timestamp_seconds` (written only by a run that reached its end)

Each on a Grafana panel (metric coverage ratchet). The administrators are informed in-app
(section 7), so ONE Prometheus alert suffices: `LLMCatalogueLifecycleStalled`, no completed run
for 48 hours — the one failure the job cannot report about itself — with its runbook under
`docs/runbooks/alerts/` and its ADR-266 evidence recipe.

## 10. Admin screen

The existing catalogue status panel (`CatalogueStatusPanel`) keeps its shape: its retiring list
reads the dates the job wrote (so it can no longer contradict the vendor) and gains two columns,
the date's source and the vendor's last answer. Failing sources are notified (section 7), not
drawn. The new labels in the six locales.

## 11. Tests

- Parsers on copies of the real pages captured on 2026-09-26, plus a page whose layout changed
  (it must fail, not return an empty mapping).
- Probes on the measured response shapes: an alias answering, each vendor's not-found, a 401, a
  429, a timeout.
- The rule: every row of the table of section 3, table-driven.
- Retirement on PostgreSQL: the job and the admin route produce the same rows (model, tariff,
  audit); a model in use is retired and its slots reported; a first `GONE` retires nothing and a
  second one 20 hours later does; an answer in between clears it; a model an administrator
  reactivated is never retired again; the breaker retires nothing; a second run changes nothing;
  nothing is ever reactivated.
- Cross-cutting guards: provider completeness, scheduler jitter, metric coverage, evidence
  recipes, i18n parity, no session across a network call.
- Runtime proof on dev: a dry run, then a real run, then the notification read by a superuser.

## 12. Doctrine

A new ADR amends ADR-244:

- the vendor's announcement outranks the registries' copy for shutdown dates;
- a model is retired automatically on concordant evidence — including a model still in use, the
  administrators being told what to re-target;
- a date alone never proves a retirement, nor does an absence from a list;
- capabilities stay vendored and reviewed, no price is ever imported, nothing is reactivated.

ADR-245 is amended in lot 0 (section 13, item 5).

## 13. Lot 0 — the Gemini lot's four defects

1. **An inserted model has no price.** Migration `70fd39bf9e8d` inserts a missing model without
   its tariff, so an instance lacking one gets an active model the pricing cache bills at zero
   (`get_cached_cost_usd_eur` returns `(0.0, 0.0)` for a model without a price). It inserts the
   seed's active tariff with the row, like `f6c2a8e4b0d7` and `7b3e9d1f5c2a`; a guard holds the
   two equal.
2. **The 2.5 ladders were narrowed to the wrong vocabulary.** The thinking guide's levels are for
   `thinking_level`; LIA drives Gemini 2.5 through `thinking_budget`, where any budget in the
   measured range is valid. The narrowing sent a slot configured on `minimal` to `low`
   (6 553 → 13 107 tokens of budget, measured). The 2.5 rows go back to the family ladder; the
   2.5 Pro rule (no off switch, 128–32 768) and the clamp stay.
3. **A vendor date was read as proof.** `is_retired` must not treat a vendor-sourced date as a
   retirement (the page's dates are « earliest possible »); lot 2 then deletes the hand table.
4. **A seed comment claims every inactive Gemini row is unserved** — the image rows are inactive
   by design; the comment says which rows it means.
5. **The ADR-245 amendment** for the derived budget clamped to the profile's range and the 2.5 Pro
   rule, both measured on 2026-09-26.

The one-off migration keeps its reference check when it deactivates the models Google no longer
serves: a migration cannot notify anyone. The job's first run retires what the migration spared
and tells the administrators which slots to re-target (decision 5).

The Gemini 2.5 budget keeps the clamp: `medium` and `high` then give the same budget
(24 576 on Flash, 32 768 on Pro), as OpenRouter's published mapping does. Taking the ratio of the
model's budget range instead would keep four distinct depths but lowers every existing slot's
budget; it is not done without the owner's decision.

## 14. Delivery lots

| Lot | Content |
|---|---|
| 0 | section 13 |
| 1 | `retire_model` shared with the admin route; `admin_audit_log.actor` (migration); `notify_superusers` extracted |
| 2 | `lifecycle/`: sources, parsers, probes, rule; `llm_models` columns and `llm_lifecycle_sources` (migration); the hand table deleted |
| 3 | job, task, settings (four env files, demonstrator off), two-run confirmation, human-reactivation rule, breaker, metrics, dashboard, the one alert, its runbook and evidence recipe |
| 4 | the status panel's two columns and dates read from the job, six locales |
| 5 | ADR, technical documentation, CLAUDE.md and AGENTS.md, living maps in six languages, release counts |

Each lot ends with an exhaustive cold review.

## 15. Why a wrong retirement is unlikely, and cheap if it happens

- **The decisive signal is the vendor's own « not found » for that exact model, twice, 20 hours
  apart**, asked with the instance's key. A parser can only bring a date: a misread page cannot
  retire a model the vendor still serves.
- **The date must also have passed**, and a vendor that lists the model with no shutdown clears
  any registry date.
- **The breaker** caps a run at five retirements; a vendor answering « not found » for everything
  retires nothing.
- **Nothing is ever lost**: a retirement keeps the tariff row and the history, an administrator
  reactivates in one step, and the job then leaves that model alone.
- **Residual risk, stated:** a model the vendor stops serving for the instance's key while it
  still works under another key the instance also uses — LIA keeps one key per provider, so
  there is none today.

## 16. Rejected

- **Re-targeting a slot automatically** (owner, 2026-09-26): it changes a slot's price,
  capabilities and reasoning without a human decision.
- **Vendoring the vendor pages in the manual fetch:** faithful to ADR-244, but as stale as the
  last manual run.
- **Automating the registries alone:** they contradict the vendor (problem 2).
- **Reading a list absence as a retirement:** problem 4.
- **E-mailing administrators:** Alertmanager already e-mails; the diagnostics doctrine holds.
