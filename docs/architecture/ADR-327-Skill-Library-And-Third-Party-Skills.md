# ADR-327 — Skills from a public library, and what a skill written elsewhere may do

**Status:** Accepted — 2026-09-30, owner request: let a person search, install, update and
remove skills published on a public library (skills.sh, the `vercel-labs/skills` portal), with
other portals possible later, and make them fully functional without critical or important
security risk. Delivered in lots; the network lot (lot 3) was approved at its checkpoint on
2026-09-30, the vendor keys (lot 4) are deferred.

**Amends:** ADR-118 (the import pipeline: S2 name collisions), ADR-225 (plugin provenance),
ADR-149 / SEC-001 (the throwaway sandbox), ADR-249 (the sandbox image), ADR-075 (rich outputs),
ADR-279 (generated files), ADR-298 (the image the sandbox starts from), ADR-215 (the release
and the installer carry a third app image).

## Context

Measured before deciding (2026-09-30):

- The portal's search is anonymous (`GET https://skills.sh/api/search?q=&limit=`); its file and
  audit API needs a Vercel-issued token no self-hosted instance holds, so the content comes from
  GitHub (60 REST calls per hour and per IP without a token, 5 000 with one) and the audits from
  the CLI's anonymous audit endpoint.
- Across 500 surveyed skills (the portal's three leaderboards plus thirty topical searches):
  41 % are instructions only, 41 % are instructions that make the agent run commands (mostly an
  `npx` vendor CLI), 18 % ship scripts — 62 % of them not in Python, and **1 in 91** follows
  LIA's stdin-only script contract. 38 % need the network, 13 % name a vendor key, 4 % exceed
  LIA's import budget, 99 % have a name LIA accepts.
- In LIA a skill name was unique for the **whole instance**: a second person could never keep a
  skill the first had installed under the same name.
- A skill's instructions reached a model holding every tool (ReAct) or, in the pipeline, the
  response prompt at the highest priority. Nothing distinguished a skill the person wrote from
  one fetched from a third party.

## Decision — lot 0: a skill name is unique per account

- The instance-wide unique index on `skills.name` becomes two partial unique indexes — system
  names unique among system skills (`owner_id IS NULL`), a person's names unique among their own
  — and a CHECK pins `is_system ⇔ owner_id IS NULL`, which both indexes rely on. The owner
  foreign key cascades the whole row, so no foreign-key action can leave a row between the two
  states. Migration `61b299a42af9`; its downgrade refuses, with the count, while two scopes
  share a name.
- **Every lookup names its scope.** The any-scope `SkillsCache.get_by_name` (first match,
  whoever owned it) is gone: with per-account names it hands one person another person's
  skill. The cache offers `get_system_by_name`, `get_exact(name, owner)` and
  `get_by_name_for_user` (own, else system); the repository `get_system`, `get_owned`,
  `resolve_for_user`; deletes go by id. The cache key carries the owner
  (`user:<owner>:<name>`) — keyed on `user:<name>`, the second person's `pdf` overwrote the
  first's in memory.
- A person's own skill shadows a system skill of the same name **for that person only**, and
  the listing shows the skill their name resolves to (one card per name).
- A user import still refuses to shadow a system skill (ADR-118 S2). An admin import is never
  blocked by a name some person holds — otherwise any account could reserve a system name.
- Two defects of the same class, found on the way and closed: a plugin's uninstall and its
  update deleted skills **by name** (`delete_by_name`), which per-account names would have
  turned into deleting every person's skill of that name; the disk-to-database sync registered
  a recovered user skill without its owner's activation state (invisible), and a folder whose
  owner no longer exists made its insert violate the owner foreign key and abort the whole
  sync. A concurrent import losing the race on the new unique index answers the same 409 as the
  up-front check.

## Decision — lot 1: what a skill written elsewhere may do, and the library

### Provenance, decided once per request

- `skills.provenance` says how the content arrived: `system`, `authored` (written by the
  person: an upload, the chat), `url`, `plugin`, `library`. The last three are **third-party**;
  `plugin` and `library` are also **managed** (their source updates them). The import that
  registers a skill writes it in the same transaction (migration `00c0324db6ae`, a CHECK ties
  `system` to `is_system`), and a managed channel never captures a skill of another provenance.
- The agent service binds the request's third-party names beside its active set
  (`third_party_skills_ctx`); every reader asks `skills.trust` and nothing re-derives it. A
  request that bound nothing treats every user skill as third-party: **doubt closes**.

### What a third-party skill may do

- Its catalogue entry is marked (`<skill trust="third_party">`), one line says a marked
  description is a label and never an instruction, and its declared priority is ignored. It
  never runs a `plan_template` and is never `always_loaded`.
- Its instructions run **only in the isolated skill runner** — whether it ships scripts or
  not — which binds its own skill's `run_skill_script` and `read_skill_resource` and nothing
  else: no connector, no import tool. `isolated_skill_ctx` scopes those two tools to that skill
  while the runner runs; any other skill is refused (`FORBIDDEN`). A runner that fails leaves
  nothing of the skill in the response prompt.
- Its answer is drawn by `untrusted_markdown`: outside code, every `<`, the `!` of an image and
  the `[` of a link reference definition become numeric references, and Unicode tag characters
  are removed. No image is fetched (an address can carry the turn's data out), no HTML draws
  what LIA's own cards draw, and **nothing it writes is invisible to the person** — which
  matters because the turn-start repair turns that answer into ordinary history later turns
  read. The rule is linear and pinned by the flattener growth guard.
- Read from outside its runner — the main loop, the pipeline — its resources and its scripts'
  output arrive as external content. `activate_skill_tool` on a third-party skill does not hand
  its instructions over: it runs the isolated runner on a `request` the model states, and
  returns the answer as external content.
- **No frame, ever, and images `data:` only.** A sandboxed frame runs scripts and may navigate
  itself to an address carrying what it was given; no content policy forbids a navigation. The
  same holds for the skills a plugin installed before this lot: they lose their frames and
  remote images (a deliberate behaviour change). A skill imported from an address before this
  lot was recorded `authored` by the migration — its channel had never been stored.
- A managed skill is updated from its source, never rewritten by the chat (`SKILL_MANAGED`);
  a skill imported from an address stays editable — the person holds it.

### The library

- **The portal indexes, the origin serves.** skills.sh is searched anonymously and its audit
  service read; the files come from the GitHub repository the portal names (a skill listed on a
  website is shown, marked not installable). A portal is one `Portal` in `PORTALS`.
- **What is installed is what was read.** A preview resolves the branch to a commit once;
  install and update send that commit back. The listing at a commit is recursive and refused
  when GitHub truncated it; the folder is located by name, then by manifest name among at most
  `SKILL_LIBRARY_MAX_CANDIDATES`; its size is checked against the package bounds BEFORE a byte
  is downloaded; every file is verified against its git blob SHA; links and submodules are
  never followed, only reported.
- **An update is a moved folder.** The folder's git tree SHA is stored; a different one at the
  ref's head is an update, reviewed file by file before it installs, and a version carrying
  another name is refused (`skill_library_renamed`) — it is another skill.
- **One pipeline.** The files go through `SkillImportService.import_directory` with the
  `library` provenance — the same S1-S5 checks, conflicts and quota — and the provenance row
  (`skill_library_sources`) is written in the registration's own transaction. A library skill
  never takes a system skill's name (a stranger's text would answer a request meant for LIA's
  own) and never captures another folder's skill. Removing it is the gallery's ordinary delete;
  the row cascades.
- **Audits are read under every name** the skill may be audited under — the portal's id, its
  manifest name, its folder — and pooled, so a folder named otherwise is no way around a
  refusal. At or above `SKILL_LIBRARY_AUDIT_BLOCK_LEVEL` (`high` by default, `none` refuses
  nothing) the install is refused (`skill_library_audit_blocked`). An audit service that
  cannot be read refuses nothing: the audits are advice, the isolation is the protection.
- **Every request is checked at every hop** (ADR-326): validated, pinned, a redirect validated
  before it is contacted, one total deadline, a byte ceiling. An optional
  `SKILL_LIBRARY_GITHUB_TOKEN` lifts GitHub's anonymous 60 requests per hour and reaches
  `api.github.com` alone — a redirect elsewhere drops it. Public answers are shared across
  accounts in the `skill_library` family (GLOBAL, ADR-260): a head for a few minutes, a listing
  at a commit for the day.
- **No session across a wait** (ADR-304): the routes authenticate on a session of their own
  and every read of the account opens a short one; the import's session opens once every file
  is local. The routes carry a per-account rate limit.
- `PlatformCapability.SKILL_LIBRARY` guards the router, under the skills switch; the
  demonstrator switches it off. Every refusal is a stable `detail.code` with a sentence in six
  languages (pinned both ways) and `skill_library_operations_total{operation,outcome}` counts
  them (dashboard 19).

### Stated limits

- A third-party answer stays in the conversation like any answer; later turns read it as LIA's
  earlier words. It can hide nothing from the person, but what it says openly is there.
- The chat's import tool could create an `authored` skill from content the model read (a web
  page, a mail, a third-party resource) without a confirmation. Closed by the owner's
  arbitration of 2026-09-30: see « A skill written in the chat is proposed » below.
- GitHub's anonymous allowance is the instance's, not the person's: without a token, a busy
  instance meets `skill_library_rate_limited`.
- What the turn already fetched (the plan's results) reaches the isolated runner, so a
  third-party skill sees it; its answer can carry it out only through a link the person clicks.

## Decision — lot 2: a skill runs its own commands, offline

41 % of the surveyed skills make the agent RUN something and 62 % of the scripts are not
Python: a runner that can only call `run_skill_script` (stdin JSON, stdout JSON) turns them into
instructions nobody can follow.

### `run_skill_command`

- One shell command, run with bash in a **copy** of the skill's folder, in the SEC-001 throwaway
  container: no network, read-only root, uid 65534, every capability dropped, memory, processes,
  CPU and file size bounded — `executor.isolation_flags`, the scripts' own declaration, shared
  so a later edit cannot harden one kind of run and forget the other.
- **Nothing is mounted.** The skill folder and the files the person attached to this turn
  travel in as one tar on stdin (`skills/command_bundle.py`); the command's standard output and
  error, its exit status and the files it wrote under `out/` come back as one tar on stdout. No
  host path, no named volume, no dependency on the Docker version.
- **The command is an argument, never part of the script**: the container's bootstrap is a
  constant and receives the command as `$1`, so no quoting escapes it. Inside, `timeout -k`
  stops the command at its budget and the bootstrap still hands back what it wrote (exit 124).
- **What comes back is read under a ceiling and trusted for nothing**
  (`skills/command_sandbox.py`): a run writing past the ceiling is stopped and its container
  removed by name, as is a run past every grace period; the reader keeps regular files under
  `out/` only, bounds their count, each size and their total, and NAMES every file it leaves
  out with its reason. Text is cut inside the sandbox and the cut is stated.
- **The files become the person's generated files** (ADR-279, `skills/command_outputs.py`):
  one `attachments` row each, the gallery, the usual lifetime, the chat's own cards. What a file
  IS is decided by its name AND its first bytes, never by the command: a PDF, an office file,
  a CSV or an image keeps its type once its signature matches; a page a skill wrote (Markdown,
  HTML, SVG, XML, sources) comes back as TEXT (`notes.md.txt`) — the document viewer renders
  Markdown with remote images, and HTML or SVG served inline would run in LIA's origin;
  anything else is named and left out.
- The turn's files reach the tool through the request (`skill_turn_files_ctx`, a list bound
  fresh by `bind_skill_context` and filled by the attachment injection), never past it: a
  scheduler may run several people's turns in one task.
- Gates: the scripts' own switch, plus the container sandbox — the legacy in-process mode is
  refused, as for model-written code. A third-party skill's command answers as external content
  outside its isolated runner. The tool is registered (the effect gate, `sandboxed`), bound with
  the other skill tools, and every bound it enforces is a setting (`SKILL_COMMAND_*`) or a
  published constant (the command's length). `skill_commands_total{outcome}` counts the runs
  (dashboard 19). A skill whose `scripts/` holds anything, Python or not, goes through the
  runner.

### A sandbox image of its own

Every sandbox run — a skill's script, a skill's command, the agent's ephemeral Python — used to
start from the API's own image, which carries the Docker client and the application's code. It
now starts from `apps/api/Dockerfile.sandbox`:

- Python on a base pinned by its multi-arch index digest, Node, bash, jq, zip/unzip and poppler,
  and the libraries a run is promised, installed system-wide from a hash-verified lock
  (`requirements-sandbox.txt` compiled **under** the dev lock, which includes its manifest, so
  the image runs exactly the versions the unit suite imported; `task lint:lockfiles` holds
  it). No Docker client, no code, no credential; 874 MB against 6 GB for the API image,
  measured on the dev host.
- ONE declaration of what it holds (`skills/sandbox_toolbox.py`) feeds the runner's prompt and
  is held to both build inputs by unit tests; `task sandbox:libraries:check` starts the built
  image as a run starts it (no network, uid 65534, read-only) and proves every library, every
  command and both absences. Measured: the dedicated image passes, the API image fails eight.
- It is built where the API is built: the dev tasks (`task sandbox:image:build`), the host
  deployment script, the installer's local mode; published by the release as a third app image
  with its SBOM and pulled by digest in prebuilt mode. It is no Compose service: a one-shot
  container fails `up --wait` (measured).
- `SKILLS_SCRIPT_SANDBOX_PYTHONPATH` defaults to empty: the libraries need none.

### Measured on Docker dev (2026-09-30, no model called)

The tool, for the proof account, on its installed library skill with a real PDF attached: Node,
`pdftotext` on the input, pandas; three files filed (a PDF, a PNG, `notes.md.txt`) and a page
wearing a `.png` name left out; a network call refused, no Docker client, no `/app`, uid 65534,
a read-only root; a 3 s budget stopped at exit 124 in 3.3 s; stdout cut at 32 KB; ten files
of fourteen handed back and four named; an environment carrying no secret; no container left
behind. The system QR and skill-generator scripts and the ephemeral Python ran on the new image,
and the egress probe passed 11/11 on it.

### Stated limits (lot 2)

- Which files survive the count bound follows the archive's order, not the person's intent.
- A rollback of the API image keeps the sandbox image last built or pulled.
- No per-account disk quota bounds generated files; a run is bounded, and the calls are
  rate-limited.
- The API no longer pins the libraries only the sandbox uses: pandas, phonenumbers,
  pycountry, segno, unidecode and xmltodict left its image (owner decision 2026-09-30). The
  unit suite still imports every promise through `requirements-dev.txt`, which includes the
  sandbox manifest, and the sandbox lock is compiled under the dev lock. The legacy
  in-process `subprocess` mode runs on the API's interpreter and therefore lacks them.

## Decision — a skill written in the chat is proposed, the person's click installs it

Owner arbitration, 2026-09-30. The chat's import tool registered a skill the moment the model
called it: a skill the model wrote from a page, a mail or a third party's resource entered the
person's skills with the assistant's trust, unconfirmed. `mutation_policy="confirm"` could not
close it — the skill generator runs in the response node's isolated runner, whose drafts never
reach the graph, so the card would never have been shown and the generator would have lost its
main path.

- **The tool proposes** (`mutation_policy="draft"`: the card IS the confirmation; an unattended
  run is refused, and so is a run that draws no card — a ticket run, whose rows stay out of
  the chat, or a messaging channel (`run_origin.chat_cards_reach_the_person`): the model is
  told to send the person to the chat rather than announce a card nobody will see).
  `SkillImportService.validate_files` runs every check the import runs and writes nothing —
  the S4/S5/S2 checks moved into one `_validated` both paths call, so a proposal and its
  install can never disagree on what is accepted. A card past its deadline asks the API
  nothing: it says the proposal is closed.
- **The proposal is kept, bounded** (`skills/proposals.py`): the validated files in Redis under
  the conversation family (a reset forgets it with the card) for `SKILL_PROPOSAL_TTL_SECONDS`,
  at most `SKILL_PROPOSALS_MAX_PER_USER` live per account — the oldest makes room, expired
  members never count, in one atomic script proven on a real Redis. A replacement records the
  fingerprint of the installed text files and what it adds, changes and removes.
- **The card installs** (`POST /skill-proposals/{id}/install`): one install in flight per
  proposal (an owner-token claim), refused as `skill_proposal_stale` when the skill it
  replaces changed since the card described it, idempotent — a proposal whose record could not
  be marked is recognised by its installed files, never reported stale. The install is an
  ACTION of the person's (`skill_proposal_install`, ADR-263 amendment 2026-09-27), claimed
  after every refusal. Every refusal is a stable `detail.code` with a sentence in six languages
  (pinned both ways); `skill_proposals_total{operation,outcome}` counts propose, read and
  install (dashboard 19).
- **The card** (`components/chat/SkillProposalCards.tsx`) travels as the answer's metadata
  (`skill_proposals`) like the generated files, through ONE card door in the streaming layer
  (`agents/api/card_delivery.py`, which the image and document cards now share, over one
  pending-card store, `shared/pending_cards.py`). It shows the name, the description, what a
  replacement changes, each file on demand, the deadline and a notice; the focus lands on the
  result once installed; the chat's skill shortcuts read the list again (`revisionStore`).
- The two-call replacement token of ADR-165 is gone with it: the person's agreement was the
  model's word.

## Decision — lot 3: a skill's command reaches the network it declares

Owner approval, 2026-09-30. 38 % of the surveyed skills need the network, most of them to
install a package or fetch a repository before they run. Lot 3 gives a command ADR-298's
network — the Python sandbox's decision, never a second one.

- **`hosts` on `run_skill_command`**: the bare hostnames the command reaches over HTTPS, read
  by the manifest and the `@tool` schema from ONE constant (`command_bundle.HOSTS_DESCRIPTION`)
  with the bound the egress path enforces (`PYTHON_SANDBOX_MAX_HOSTS_PER_RUN`, ADR-184).
  Without it the run stays offline, exactly as in lot 2.
- **One decision for both kinds of run** (`egress/tool_path.authorize_network`, extracted from
  the Python sandbox's path): every host is `connector`, `operator`, `grant` or `unknown`, the
  run is published to the proxy (`egress/run.serving`) and the network act is an ACTION of its
  own, `skill_command_network`, labelled in six languages (ADR-263).
  `skill_command_egress_total{outcome}` counts `allowed`, `asked`, `refused` and
  `proxy_unavailable` (dashboard 19).
- **A skill written elsewhere never reaches the person's connectors**: its run is decided
  as a third party's (`authorize_network(third_party_skill=True)`), so no connector host is
  permitted, no token is minted, and such a host is reachable only as the operator's or the
  person's grant. The runner's prompt says the same thing
  (`command_network.runner_network_line`): offline, or the hosts a command reaches without a
  question — never a connector for a third-party skill. **And the card says who asks**: the
  question carries `third_party_skill`, drawn as a warning above the answers on the chat card
  and as a line of the server preview, in six languages — allowing a host WITH the turn's
  data hands that skill's command the files the person attached.
- **An unknown host is asked only where the answer can be settled.** The ReAct loop re-invokes
  the same call under the person's answer (`nodes/react_egress_question.py`, now for any
  sandbox tool — for a command, the card's purpose is the skill and its command). Anywhere else — the skill runner inside
  the response node, a pipeline step, a routine — nothing could answer the card, so
  `egress/tool_path.question_settleable()` is false and the tool refuses, naming the setting
  where the person allows the host.
- **Allowed from the settings**: `POST /sandbox/egress-grants` stores a host under the
  normalisation the tool applies and under the card's cap (`EgressGrantService.grant`; ONE
  `_has_room` serves the card and the settings), each refusal a stable `detail.code`
  (`egress_grant_host_invalid`, `egress_grant_limit_reached`, `egress_grant_asking_disabled`)
  with its sentence in six languages, pinned both ways; *Settings › Sandbox network* gained
  its « Allow a host » form. **The operator's `ask` switch closes both doors**: where an
  unknown host is never asked (`PYTHON_SANDBOX_EGRESS_ASK_ENABLED=false`) the route refuses
  and the form is not drawn — before lot 3 no grant could exist on such an instance, and a
  form that wrote one would have widened what the operator closed.
  The grants router is mounted with the skills as well as with the Python sandbox, since both
  read the grants.
- **The data scope is ADR-298's**: allowed « without the turn's data », the files the person
  attached never enter the container, and the report says so.
- **The image holds the clients** (`SANDBOX_COMMANDS`): git and curl join pip and Python from
  Debian (git 104 MB with perl, curl 2 MB measured on the base), and **Node comes from the
  official image, pinned by version and digest in a stage of its own** (`FROM node:24.x.y
  … AS node`, the binary and npm's tree copied out of it, npm and npx re-created as the
  symlinks the official image ships — `COPY` dereferences a symlink, and the two files it left
  the first time failed `require('../lib/cli.js')` on every call): Debian trixie ships Node 20,
  past its upstream end of life, and its `npm` package weighed 140 MB of `node-*` packages;
  the image measures 1.05 GB against 874 MB before the lot. Every client is pointed at the
  proxy's CA (`executor.egress_args`); measured, git refuses the proxy without
  `GIT_SSL_CAINFO` (its TLS library ignores `SSL_CERT_FILE`), and Node's own `fetch` follows
  `HTTPS_PROXY` only under `NODE_USE_ENV_PROXY=1`, which the same arguments set (measured on
  Node 24: 200 with it, no route without). Offline, npm is told so
  (`npm_config_offline=true`): it retried an unreachable registry until the 60 s budget ran
  out, and now fails in 0.25 s naming its cache mode. **The image check RUNS every command**
  with its declared probe flag (`SandboxCommand.probe`): found is not working, and the
  presence check had passed the broken npm.
- `SKILL_COMMAND_NETWORK_ENABLED` (on) withdraws the network from commands alone; the sandbox
  egress capability (ADR-280) and `PYTHON_SANDBOX_EGRESS_ENABLED` still gate every network
  run, read at the act.
- **What the tool can do reaches every caller through its SCHEMA** (ADR-184, reviewed
  2026-09-30): the ReAct loop and the planner never read the skill runner's prompt, so the
  `command` description — ONE constant read by the manifest and the `@tool` schema — names
  the commands the image holds (from the declaration the image is proven against) and the
  fresh-copy rule (« chain dependent steps in ONE command »), which only `<Sandbox>` and the
  runner's rules used to say; and the skill generator, which runs in that runner, is told
  that a generated skill may use only what `<Sandbox>` lists and must write the `hosts` its
  commands need into its instructions.

### Measured on Docker dev (2026-09-30, no model called)

`task sandbox:egress:probe` passed 21/21: npm view and install (`docx@9`, 22 packages in
0.9 s), npx, a git clone, a pip download and curl through the proxy; an undeclared host refused
(403); git refused without its CA variable; a plain Node `fetch` finding no route. Through the
tool, for a throwaway account: the settings route refused `https://pypi.org` by name and stored
` Registry.NPMJS.org. ` as `registry.npmjs.org`; an unknown host was refused naming the
setting; the allowed host answered (`7.0.0`), the report naming the network and the scope, and
the grant was stamped as used; an offline `npm view` failed at once. The account was deleted
through the audited path with nothing left.

### Measured in use (2026-09-30 evening, the owner's tests on Docker dev)

The API log of one evening of real use held six things, each now closed by a test:

- **A skill written in the chat was proposed TWICE** (« convert Celsius to Fahrenheit »): in
  ReAct the loop activated the skill-generator, ran its validation script and proposed the
  skill; the response node then found the same skill detected, saw that it ships scripts and
  ran the skill runner AGAIN — 27 s of model calls and a second card of the same name, which
  the person could only meet as `skill_proposal_stale` once the first was installed (the
  guard did its job). In ReAct the loop IS the runner: `react_execute_tools_node` records
  what the loop activated (`react_activated_skills`, from the activation tool's own answer,
  reset per turn like every accumulator) and the response node reads it before running the
  runner (`_loop_already_activated`), as it reads the plan's own widget (B1).
- **A third-party skill activated from the loop was killed at 30 s, three times**:
  `activate_skill_tool` runs such a skill in its ISOLATED runner — a nested loop — under the
  generic tool budget, so the runner died mid-command and the loop retried. The tool now
  belongs to the sub-agent family of `compute_step_timeout` (its floor and ceiling).
- **A command of 4 000 characters was refused four times in one turn** (`web-artifacts-builder`
  writes a page through a heredoc — the only way a file gets in): `SKILL_COMMAND_MAX_CHARS`
  is 16 000, still one argument far below `ARG_MAX`.
- **The command rate limit refused a legitimate multi-step skill** at 5 per minute: it is a
  setting read at every call (`SKILL_COMMAND_RATE_LIMIT_CALLS`, 12 by default, and its
  window), the tool doctrine.
- **`companion_activity_unavailable` four times per turn**: the response node's skill runner
  publishes no effect scope, so every tool it called built an activity with an empty run id
  the model refused. No run, no activity — and no warning.
- **`skill_name_dir_mismatch` on every library preview and install**: the loader's
  installed-folder convention applied to a manifest staged in a random temporary folder.
  `parse_skill_file(check_dir_name=False)` where the library reads one.

Two graceful-shutdown `CancelledError`s in the same log were the API container being
recreated during an open stream (the operator's own restart), not a defect.

### Stated limits (lot 3)

- **Dependencies are fetched on every run.** Caching them when the skill is installed was
  approved in principle and is not built: measured, a per-run `npm install` of a 22-package
  dependency costs under a second, while a cache means running a third party's install
  scripts at install time and keeping a tree per skill — left to the owner's arbitration.
- **Dependabot moves the Node stage as it moves the Python base** (the docker ecosystem of
  `/apps/api`); a Node major change is reviewed like any base change and the declaration
  names the major the image ships (a test holds them equal).
- **A permitted host receives whatever the command sends it**: the skill's folder, what the
  command computed and — when the scope allows — the files the person attached. The operator's
  list and a grant given « with the turn's data » are therefore trust in the HOST for every
  skill, third-party included; the settings form defaults to « without », and the card names a
  third-party skill. Package registries accept no anonymous upload, which is what makes them
  reasonable operator hosts — the `.env` templates list `registry.npmjs.org`, `pypi.org`,
  `files.pythonhosted.org` and `github.com` in `PYTHON_SANDBOX_EGRESS_HOSTS` (owner decision
  2026-09-30), so an install or a clone needs no question and carries the attached files.
- A permission covers the whole command: npm's own install scripts run in the same container
  and reach the same hosts.
- ADR-298's union limit now includes commands: the proxy has one allowlist for every live
  run, so while a third-party skill's command overlaps another run it may CONNECT to that
  run's hosts — never with its token.
- Allowed « without the turn's data », a command receives no attached file at all: a skill
  that must install a package AND read the person's file needs its hosts allowed with the data
  (or by the operator).
- The register row of a network act is filed under the turn's run, as every in-turn effect: a
  tool called outside any graph has no run to file it under.
- A third-party skill cannot use the person's API keys at all (lot 4, deferred).

## Consequences

- Chat editing no longer answers « name unavailable » for another person's skill: for this
  person the name is simply free.
- The FAQ (six languages) and the knowledge page state the per-account rule.
- Third-party skills are marked in the gallery and their detail says what they may do here;
  « Find skills » opens the library in the skills section.
- A skill that ships commands works here: its files come back as the person's generated files.
- Every sandbox run starts from an image with no Docker client and no application code.
- A skill written in the chat is installed by the person's click, never by the model.
- A skill's command reaches the hosts it declares, through the proxy, once the operator or the
  person allows them; a third-party skill never reaches the person's connectors.
