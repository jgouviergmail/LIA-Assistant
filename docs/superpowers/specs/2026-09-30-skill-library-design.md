# Skill library — design (2026-09-30)

Owner request: let a person search, install, update and remove skills published on the
skills.sh portal (vercel-labs/skills), with other portals possible later, and make the
installed skills fully functional without critical or important security risk.
Owner decisions (2026-09-30): the ten hypotheses of the analysis are accepted; lots 0 to 2
are delivered in this pass, the network lot waits for a checkpoint.

## Facts the design rests on (measured 2026-09-30)

- Portal search is anonymous: `GET https://skills.sh/api/search?q=&limit=` →
  `{skills:[{id, source, skillId, name, installs}]}`; `count` is the page size, never a total.
  A GitHub skill has `source = owner/repo`; a site skill has `source = <host>`.
  The portal's file and audit API (`/api/v1/...`) needs a Vercel OIDC token: content comes
  from GitHub, audits from `https://add-skill.vercel.sh/audit?source=&skills=` (anonymous).
- GitHub: 60 REST calls per hour per IP without a token, 5 000 with one. A recursive tree
  gives every file's path, mode, size and git blob SHA-1 before any download.
- 500 skills surveyed: 41 % instructions only, 41 % instructions that make the agent run
  commands, 18 % ship scripts (62 % of them not Python, 1 in 91 follows LIA's stdin
  contract). 38 % need the network, 13 % name a vendor key, 4 % exceed LIA's import budget,
  99 % have a name LIA accepts.
- Today a skill name is unique for the whole instance; a skill's instructions reach a model
  holding every tool (ReAct) or with the highest priority in the response prompt (pipeline);
  the chat loads any `https:` image, and user-skill frames may load `https:` images.

## Lot 0 — a skill name is unique per account

- DB: `skills.name` loses its global unique index; two partial unique indexes replace it
  (system names unique among system skills, user names unique per owner) and a CHECK pins
  `is_system ⇔ owner_id IS NULL`.
- Every lookup names its scope: `SkillsCache.get_by_name` (first match, any scope) is replaced
  by `get_system_by_name`; per-person code resolves own-then-system (`get_by_name_for_user`),
  never falls back to another scope. The repository offers `get_system`, `get_owned`,
  `resolve_for_user`, and deletes by id.
- A person's own skill shadows a system skill of the same name for that person only (the
  existing override rule); the listing shows the one that resolves.
- An admin import no longer refuses a name some user holds (a user could otherwise block a
  system name); a user import still refuses to shadow a system skill (ADR-118 S2).

## Lot 1 — the library, and the trust of a skill written elsewhere

Backend domain `domains/skill_library/`:
- **Portals** (search) and **origins** (content) are two declared registries, checked at
  boot. v1: portal `skills_sh`, origin `github`. A hit whose origin is not supported is
  returned as not installable, with its reason (never dropped in silence).
- **Preview** reads the repository tree once (cached by commit), locates the skill folder,
  checks the import budgets on the tree metadata BEFORE any download, reads SKILL.md, the
  portal audits and the name/quota verdicts.
- **Install** downloads each file at the pinned commit from `raw.githubusercontent.com`
  through the pinned, SSRF-validated fetch (ADR-326), verifies its git blob SHA-1, stages
  the folder and hands it to the existing import pipeline (`import_directory`, S1-S5).
  Provenance is a 1:1 row `skill_library_sources` (portal, repository, path, commit, folder
  tree SHA).
- **Update**: a verdict derived from the folder tree SHA against the current HEAD (cached),
  an explicit click, a summary of the changed files, the audits read again.
- **Remove**: the existing route (the provenance row cascades).
- Audits are shown; an install whose worst audit reaches the operator's blocking level
  (default `high`) is refused. An unreachable audit service never blocks: it is stated.
- No telemetry is sent to the portal. An optional operator GitHub token raises the quota.
- A capability switch `skill_library` (on by default, off on the demonstrator).

Trust: `skills.provenance` (`system`, `authored`, `url`, `plugin`, `library`) is recorded at
every import; `url`, `plugin` and `library` are **third-party**. The request loads the
third-party names beside the active ones. A third-party skill:
- is marked in the catalogue, whose note says its description is a label, never an order;
- never runs a `plan_template`, is never `always_loaded`;
- always runs in the isolated skill runner, which holds only its own skill's tools (no
  import tool, no other skill), and whose answer is neutralised (no image, no raw HTML)
  before it is shown;
- in ReAct, `activate_skill_tool` runs that runner and hands the loop its answer as external
  content; reading a third-party skill's files from the loop returns external content;
- emits no frame at all, and images as `data:` only — decided during lot 1: a sandboxed frame
  runs scripts and may navigate itself to an address carrying what it was given, which no
  content policy forbids (ADR-327);
- is not editable through chat when a library or a plugin owns it (update instead).

## Lot 2 — a skill runs its own commands, offline

- `run_skill_command`: the skill folder and the turn's input files travel into the throwaway
  container as a tar on stdin, the command runs with bash in a copy of the folder, the output
  (stdout, stderr, exit code, files written under `out/`) comes back as a tar on stdout. No
  mount, so no host path and no Docker-version dependency. Same isolation flags (SEC-001),
  no network.
- Files written under `out/` become generated files of the person (gallery, lifetime).
- A dedicated sandbox image: Python, Node, bash and the command-line tools the portal's skills
  call, the libraries the sandbox promises, and neither the Docker client nor the
  application's code.

## Out of scope (stated)

Network for skills (lot 3), vendor keys swapped by the proxy (lot 4), site origins
(well-known), chat tools to search/install, automatic description translation, promotion of a
third-party skill to trusted, LibreOffice in the sandbox image.
