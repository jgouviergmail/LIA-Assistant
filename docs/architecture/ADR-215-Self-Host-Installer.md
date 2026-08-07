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
