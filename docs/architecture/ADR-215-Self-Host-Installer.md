# ADR-215: Self-Host Installer — local-first, digest-gated prebuilt, stdin-only secrets

**Status:** Accepted (2026-08-06)
**Context documents:**
`docs/superpowers/specs/2026-07-29-self-host-installer-design.md` (product intent, historical),
`docs/superpowers/specs/2026-08-05-self-host-installer-audit-addendum.md` (binding corrections, blockers B01-B15 + B10-bis, gates G0-G6),
`docs/superpowers/plans/2026-08-05-self-host-installer-activation.md` (governing execution plan).

## Context

The public-web-showroom program converts visitors toward self-hosting, but the audited
repository had no installer surface at all (B01) and a dozen structural blockers between
"clone" and "working instance": host-specific Web images, tag-addressed artifacts, opt-in
seeds without atomicity, an admin bootstrap that bypassed the password authority and leaked
secrets through argv, readiness that proves infrastructure but not installation, and a July 29
plan whose Compose wiring was invalid as written (B15). Every claim below was verified
statically against the audited snapshots (`1c1c5d66`, re-verified on `c5955b73`).

## Decision

1. **Local build is the v1 default.** `./install.sh` builds `lia-api:local` / `lia-web:local`
   from the checked-out source. Prebuilt mode exists but stays locked until Gate G5.
2. **Prebuilt is digest-only and manifest-gated.** It consumes a release bundle plus
   `repository@sha256:...` references from a validated manifest with
   `qualification="passed"`; mutable tags are never an installer input; Compose runs with
   `--no-build`. Publishing the passed manifest next to the already-qualified bundle is the
   only activation switch — no artifact is rebuilt for promotion.
3. **The release Web artifact is same-origin and host-neutral** (B03): built with
   `NEXT_PUBLIC_API_URL=""`, no baked deployment hostname; the canonical origin comes from
   validated server-only `APP_URL_SERVER` at request time.
4. **Fresh-install seeds are explicit, atomic, and marked** (B08/B09): one `psql` process,
   `ON_ERROR_STOP=1`, one transaction over the five seed files plus a blocking verification
   file, and a `SELF_HOST_SEED_BUNDLE` marker written in the same transaction. Seed intent is
   armed only for the first API start and cleared right after the first `/ready`.
5. **Bootstrap secrets enter through stdin only** (B11): one JSON document creates/promotes the
   admin (through `validate_password_strict`) and upserts the encrypted provider keys in one
   transaction. No default password, no secret argv, no secret in installer state.
6. **The current-core provider baseline is OpenAI + DeepSeek** (B10/B10-bis, owner
   arbitration 2026-08-06): the reference `llm_config_overrides` seed is the proven production
   configuration and is kept verbatim — the baseline is therefore derived from the POST-SEED
   effective configuration (DB override, else code default), the questionnaire collects one key
   per derived provider, and the verifier checks coverage on that same effective view.
   Optional seeded capabilities (Gemini vision, ElevenLabs voice, Anthropic MCP-App widgets)
   degrade without their key and are named in the final report.
7. **`/ready` is necessary, never sufficient** (B12): installation completes only after the
   non-secret backend verifier (single Alembic head, exact seed marker, reference-data
   postconditions, active admin, decryptable provider rows, effective provider coverage) and,
   in disposable qualification, a public-path login plus one hermetic fake-provider chat.
8. **The Docker socket is opt-in** (B15): script-skill sandboxing moves to a dedicated
   `docker-compose.skill-sandbox.yml` overlay; generic installs run with script skills off.
   Maintainer-only Claude-CLI mounts move to `docker-compose.devops.yml`.
9. **Resume is fail-closed and secret-free** (B13/B14): versioned state stores only non-secret
   facts plus SHA-256 fingerprints; a mismatch stops before any Compose mutation; incomplete
   bootstrap re-prompts exactly the three ephemeral secrets (admin password, OpenAI and
   DeepSeek keys). Upgrades, database downgrades, and destructive reinstalls are outside v1.
   *Amended 2026-10-18: the ephemeral secrets re-prompted also include the optional Google
   Gemini key the questionnaire now asks, which may be skipped again (amendment below).*
10. **Disposable qualification is mandatory before any prebuilt claim** (G3/G4): clean amd64
    and native arm64 rows, migration replay, atomic seed proof, login/chat through a hermetic
    OpenAI-compatible fake serving all three provider base URLs, resume/rollback injections,
    and label-scoped cleanup. Public "turnkey/one-key/zero-friction" copy additionally
    requires Gate G6 (a named mono-provider profile), which this ADR does not grant.

## Consequences

- A release can always ship the local-build path even when prebuilt qualification fails;
  GHCR never becomes the default silently.
- The maintainer's production deploy keeps `COMPOSE_FILE` with the devops overlay and gains
  `COMPOSE_PROFILES=observability`; the release note must call out both migration lines.
- CI gains hermetic installer gates (unit, Compose matrix, Python 3.10 contract) on every
  branch and a manual-dispatch-only disposable smoke behind a reviewer-protected environment.

## Amendment 2026-10-15 — concurrent provider-key writes

The shared uncommitted provider-key helper now performs one PostgreSQL UPSERT.
Concurrent first inserts serialize on the provider's unique key instead of
turning the second write into an integrity failure. `RETURNING` refreshes an
already-loaded ORM row; the caller still owns audit, commit and cache reload.
The bootstrap remains one transaction with secrets supplied through stdin.

Administrative key changes additionally lock the provider row before the active
administrator row, rechecking current authority through commit. Disposable
PostgreSQL tests cover revocation, first-insert concurrency, read-your-write,
audit and invalidation. This does not qualify a live provider or change an
adapter's existing environment fallback policy.

## Amendment 2026-10-18 — `--reconfigure` is wired, an optional Gemini key, the degraded list reaches the report

`--reconfigure` checked its flag exclusivity, then fell through to a FRESH
install over the running one: every question asked again, secrets included;
the `.env` re-rendered from the template, dropping the operator's own lines;
the seeds re-armed; the images rebuilt (pulled in prebuilt mode); the bootstrap
re-run, the typed provider keys replacing the stored ones — while
`deploy.reconfigure_existing`, the non-destructive swap this ADR describes, had
no caller. It now has its own path, on a recorded and bootstrapped installation
only: the routing and capability questions, each prompt SHOWING the answer in
force that Enter keeps (`build_reconfiguration_questions`, never a secret);
candidate files staged in a private directory — the `.env` UPDATED from the
installed file (`render_reconfigured_env` rewrites only `ANSWER_DERIVED_KEYS`,
held complete by a test that varies every answer, so operator lines, values
tuned in place and the diagnostics webhook secret in force survive), the
override with seeds disarmed under the recorded seed identity; validation with
the candidate `.env` (`--env-file`); then `swap_in` — one atomic replace per
file, each previous file copied beside itself private from its first byte,
put back if the swap stops halfway; `up --no-build`; Caddy restarted when its
routes changed under it (it reads its bind-mounted file once, and Compose
hashes no file content); the services of a profile turned off removed by name
(Compose never counts a disabled profile's containers as orphans); `/ready`.
Any failure or interrupt after the swap restores the previous files and stack
and waits for THEM to be ready (`restore_reconfiguration`); a restore that
cannot is `reconfigure_restore_failed`, naming the copies. A file the swap
writes is not required to exist before it — moving from LAN to Caddy used to
stop on the missing Caddyfile. Turning the sandbox on obtains its image
(`acquire_sandbox`, extracted from `acquire`). The state takes the new answers
and file fingerprints, so a later `--resume` does not stop on a mismatch.
`--dry-run`, `--check-only` and `--manifest` join the flags it refuses, and a
recorded manifest gone missing is `manifest_unreadable`, not a traceback.

The questionnaire asks one OPTIONAL provider key, Google Gemini
(`OPTIONAL_INSTALL_PROVIDER_IDS`, mirrored by the wizard and pinned by the
alignment test): memory recall and every search by meaning run on it, and the
embeddings now read the key the bootstrap stores (ADR-069 amendment). An empty
answer, or a key left out of an answers file, skips it (`Question.optional`);
the bootstrap accepts it when given and never stores a blank one.

The final report was handed a hard-coded empty list. The bootstrap computes
what stays degraded from the keys it stored (`unkeyed_capabilities`: every
seeded slot outside the core whose provider needs a key — held EQUAL to the
post-seed derivation by an anti-drift test, which found `voice_transcription`
missing from the audited trio — plus `semantic_search`). The installer reads
that result line out of the bootstrap's output (the line carrying `status` and
`optional_unkeyed`, never merely the last JSON line: the API logs JSON on the
same stream), records it in the state (`degraded_capabilities`) for a later
resume, and prints it. A reconfiguration touches no key, and a resume that
re-ran nothing would only replay a list the Admin UI may have outdated: both
reports point at the Admin UI instead of claiming one.

A review of these paths reproduced each of the following defects before it was
fixed. The reconfiguration's questions default to the RECORDED answers
while the answer-derived values are rewritten from them, so pressing Enter
everywhere reset a value edited by hand (a second origin in `CORS_ORIGINS`) in
silence: every such value that would differ from the `.env` in force is now
listed (a secret as `(hidden)`) and applied only on an explicit `yes` — Enter
declines, `reconfigure_declined`, nothing changed. Whether Caddy must reread
its routes was decided by reading the files after the swap, outside the
restore's reach, and the swap recorded a target only once its replace had
returned: a failed read or an interrupt in either gap left the new files in
place under a line saying the previous ones were. The decision now reads the
staged and current bytes before the swap, and a target is recorded, its copy
taken, before it is replaced. A hang-up (a closed SSH session) or a `SIGTERM`
ended the process where it stood: while the questions are asked and the
candidate is applied, both are an interrupt, as Ctrl-C is — before the swap
nothing changed (an interrupt at a question no longer advises `--resume`),
after it the restore runs. What stopped the candidate is logged before the
restore starts (it survived only as the context of a restore that failed too),
and a restore that fails prints the commands that bring the previous stack
back, from the builder the restore itself runs (`bring_up_commands`): the
previous Compose selection exactly, which the guide's `liac` alias is not on a
prebuilt or sandboxed install. Turning the sandbox on writes `DOCKER_GID` from
the host's Docker socket where `.env` holds none — not answer-derived, so later
runs keep it. And the bootstrap reads the providers `provider_api_keys` holds,
in its transaction, to compute the degraded list: computed from the run's own
payload, a resume that skipped the optional key again reported its
capabilities degraded while an earlier run's row was stored.
