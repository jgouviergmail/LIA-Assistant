# Why / How guides — a readable rewrite

Date: 2026-10-28. Status: design, awaiting owner approval. Nothing is rewritten yet.

## Intent

`/why` and `/how` (`apps/web/src/data/guides/{why,how}.{lang}.md`, rendered by
`components/guides/`) are showcase pages. A visitor must come away understanding
LIA **in broad strokes** — why it exists, what it does, how it is built. The
detail lives in the code, the ADRs and `docs/`; the pages point there instead of
restating it.

Owner's words (2026-10-28): *« trop verbeux, trop détaillé, style d'écriture trop
impersonnel et typé "IA". Il faut comprendre dans les grandes lignes, le code est
là pour comprendre en détail. »* And: *« Attention cependant à ne pas perdre
d'information importante. »*

Measured today (French): `why` ≈ 15,000 words / 11 sections (~1 h of reading),
`how` ≈ 53,000 words / 47 sections (~4 h). The growth comes from releases
appending one paragraph per feature: sections 26–46 of `how` are mostly single
features (tickets board, settings palette, meeting minutes…).

The "AI" register the owner objects to, as found in the text:

- every paragraph opens on a bold aphorism (`**Une extraction est complète, ou ce
  n'est pas une extraction.**`);
- antitheses and chiasms as the default sentence shape (« X, jamais Y »,
  « ce qui est rare, c'est la mémoire ; ce qu'on bornerait, c'est la vérité »);
- abstract nominal phrasing (« sans transformer une confiance de modèle en
  permission »);
- incident forensics and measurements in the body (« mesuré le 2026-09-… »,
  counts of rows, milliseconds), ADR numbers mid-sentence, internal identifiers;
- nobody behind the text.

## Goals

1. **`why`: about 10 minutes** (≈ 2,500 French words), 8–10 sections.
2. **`how`: about 25 minutes** (≈ 5,000 French words), 12–14 sections, with
   3–5 Mermaid diagrams replacing prose where a picture explains faster.
3. **A human voice** (rules below).
4. **No important information lost** — defined and enforced by the ledger below.
5. **No relapse**: the next releases cannot silently re-inflate the pages.
6. Six languages, French as the source.

## Non-goals

- No redesign of the guide renderer, layout or TOC component. Only the data it
  needs changes (TOC arrays, labels).
- `story`, `privacy`, `terms` are untouched.
- No new claims: the rewrite only says what is true today.
- FAQ, `docs/knowledge/`, landing, README are out of scope (they keep their own
  detail and are where a visitor goes for more).

## Anti-goals (failure even if it "works")

- Marketing fluff: shorter but emptier, adjectives instead of facts.
- Swapping one tic set for another (bullets everywhere, emoji headings,
  « En bref : » boxes on every section).
- A capability a visitor would care about that disappears without being
  reachable anywhere else.
- Deep links into code paths or line numbers that rot.

## Not losing important information — the ledger

The rewrite starts with an inventory, not with writing.

1. **Inventory.** Walk the current French `why` and `how` section by section and
   record every distinct claim in a ledger (one row: source section, the claim in
   a short sentence, category).
   Categories: `capability` (something a user can do), `guarantee` (privacy,
   self-hosting, cost transparency, confirmation before acting, no lock-in,
   AGPL), `design-choice` (a founding architecture decision and its reason),
   `limitation` (what LIA does not claim to be or do), `figure` (a number),
   `detail` (mechanism, edge case, incident, measurement).
2. **Fate.** Each row gets exactly one fate:
   - `KEPT` — said in the new page, condensed;
   - `LINKED` — named in a phrase, with a link to a document that already
     explains it (the target is opened and checked to actually say it);
   - `DROPPED` — not on the page; the row records where it still lives
     (ADR, technical doc, FAQ, code).
3. **Rules.**
   - `capability`, `guarantee`, `design-choice` and `limitation` rows are never
     `DROPPED`: they are `KEPT` or `LINKED`.
   - A row whose content exists nowhere else cannot be `DROPPED`: it is `KEPT`,
     or flagged to the owner.
   - `figure` rows: kept only when the figure matters to a visitor, at a
     precision the code cannot contradict tomorrow (CLAUDE.md rules 1–2:
     « 350+ ADRs », not an exact count), else dropped.
   - `detail` rows are dropped by default — that is the point of the rewrite —
     provided rule 2 holds.
4. **Review.** The owner receives the `LINKED` and `DROPPED` rows (grouped by
   section) alongside the French draft, and can promote any row back to `KEPT`.
   The ledger is a working file for that review, not a repository document.

Precisions (my calls, from the builder check):

- **A row is one fact a reader could repeat** (« LIA lit et envoie tes e-mails
  chez Google, Apple ou Microsoft »), not a sentence of the source.
- **`KEPT` may be grouped.** One phrase can carry several rows (« mail, agenda,
  contacts, tâches et fichiers »); the everyday example is one per *group* of
  capabilities, not per capability.
- **`LINKED` may be grouped too**, but only to a target that covers *each* row of
  the group — a link to the ADR index covers nothing. If no single target covers
  them, the rows stay `KEPT`.
- **`design-choice` vs `detail`.** A design choice is a decision that shapes the
  system as a whole and would appear on a one-page architecture summary
  (DDD, LangGraph, pipeline vs ReAct, one connector abstraction, confirmation
  before acting, multi-provider models, self-hosting). An engineering rule that
  applies inside a part (never mutate a JSONB in place, one session per task,
  jittered schedulers) is `detail`: it lives in `CLAUDE.md` and the ADRs.
- **Information beats the word count.** The targets are targets: when the
  ledger forces more, the page grows. A French draft more than 20 % over target
  is reported to the owner with the reason, not cut silently.
- **The source moves while the work runs.** The ledger records the git blob of
  each source file it read. Before the swap, the builder diffs the current files
  against those blobs and adds every new claim to the ledger, so nothing a
  release added in the meantime is lost.

## Voice

Checkable rules, applied to both pages:

- Short sentences, concrete verbs. One everyday example per capability
  (« Tu demandes à LIA de décaler ton rendez-vous de jeudi : elle prépare la
  modification et te la montre avant de l'envoyer. »).
- `why` speaks to the reader with **« tu »** (existing convention). `how` keeps
  « tu » for the reader and uses the author's **« je »** where a choice is
  explained (« J'ai choisi LangGraph parce que… »), as `story` already does —
  **owner decision 2026-10-28**. The reasons are taken from the ADRs and the
  owner reviews them in the sample section and the French draft: nothing is put
  in the author's mouth that the ADRs do not support.
- Bold marks a key term, never a sentence. No paragraph opens on an aphorism.
- « X, jamais Y » / « pas X, mais Y » at most occasionally, never as a pattern;
  no chiasms, no chains of em dashes, no reflex triplets.
- No incident stories, dates of measurements, row counts or milliseconds in the
  body. No ADR numbers mid-sentence: a section may end with one « Pour aller plus
  loin » line of links.
- `why` names no internal identifier. `how` names only the major ones a reader
  will meet in the code (LangGraph, `MessagesState`, the ExecutionPlan DSL…).
- Explain the *why* of a choice in one sentence; the mechanism belongs to the
  linked doc.

## Proposed outlines

Starting points, adjusted once the inventory shows where the weight is.

**`why`**

1. Pourquoi LIA — the context, what makes it different
2. Ce que LIA fait pour toi — connected services, voice and Live, creation,
   initiative, calls and meetings, people you know
3. Chez toi, pour tes proches — self-hosting, one server for a family, the World
4. Simple à administrer — guided install, then everything from the web UI
5. Rien de caché — debug panel, cost to the cent, the registers, self-knowledge
6. Une assistante qui te connaît — memory, personality and Psyche, journals,
   emotional safety
7. Elle agit, tu décides — confirmation before acting, nothing behind your back,
   standards and compliance
8. Ouverte — no lock-in, extensibility, channels
9. Ce que LIA n'est pas, et où elle va — limits and vision

**`how`**

1. Vue d'ensemble — founding choices, stack, one architecture diagram
2. Un backend découpé par domaines — DDD, monorepo
3. Le parcours d'un message — router, pipeline vs ReAct (diagram), planning,
   semantic routing, smart services
4. Agir avec prudence — HITL, drafts, the execution authority chain, the three
   registers
5. Mémoire et contexte — state and windowing, long-term memory, psychological
   profile, journals, Psyche engine, habits
6. Les modèles — multi-provider factory, reasoning configuration, cost and
   prompt cache
7. Connecteurs et outils — connector abstraction, MCP, skills and sandbox,
   browser, knowledge spaces (RAG)
8. Voix, mode Live et téléphone (diagram of the two wires if useful)
9. L'initiative — heartbeat, scheduled actions, moments, proactive discussions
10. Sécurité et vie privée — defence in depth, PII-free logs
11. Observer et mesurer — observability stack, cost accounting, self-diagnosis,
    running on a Raspberry Pi
12. Les interfaces — web app, native shells, expressive eyes, cards, the World
13. Comment ce code est tenu — CI/CD, shrink-only ratchets, ADRs, tests (links
    to `story` for the method)
14. Pour aller plus loin — where to read next in the repository

## Constraints the builder must honour

- **Positional TOC.** `guides-toc.ts` (`WHY_TOC_SECTIONS`, `HOW_TOC_SECTIONS`),
  the `why.toc.*` / `how.toc.*` labels in the six locales (remove the old keys,
  parity is enforced) and the markdown TOC inside each file must match the new
  sections — `components/guides/__tests__/guides-structure.test.ts` checks all of
  it, including setext headings and unnumbered `##`.
- **Release stamps stay**: the `Version` / `Date` / `Application` header block of
  every file (written by `task release:bump`, checked by the same test). Bump the
  document `Version` of the twelve files to the next major.
- **Derived counts.** `scripts/release/version_surfaces.py` declares exact counts
  inside these guides (ADR counts in `how`, the FAQ question count in `why`,
  Prometheus metric counts, the provenance note closing `how`). Every declaration
  whose sentence disappears is removed or re-declared with its new `expected`;
  `doc_facts` (`FACT_ONLY_GLOBS`) still scans the guides. Prefer dropping exact
  counts over keeping new surfaces.
- **Links.** `why` links first to on-site, translated pages: the public FAQ
  section anchors (`#faq-<section>`, `PublicFAQContent.tsx`), `/how`, `/story`,
  `/maps`. `how` links to those too and to repository documents through absolute
  GitHub URLs on `main`
  (`https://github.com/jgouviergmail/LIA-Assistant/blob/main/…`), pointing at
  stable documents (technical docs, ADRs, `docs/INDEX.md`), never at code lines.
  `guides-structure.test.ts` checks that every on-site anchor a guide links to
  exists. The current files carry a relative `../docs/…` link and a wrong repo
  name (`jgouviergmail/LIA`): both go.
- **Drafts are staged outside the app.** The French drafts, then the
  translations, are written outside `apps/web/` and swapped in, all twelve
  files with their TOC arrays and labels, in one step. The working tree is
  shared with other work and must never sit with red structure or parity tests.
  The rendered proof on Docker dev happens after the swap.
- **Deep links.** Search the web app and docs for links to old `/why#…` /
  `/how#…` anchors before renaming ids.
- **Mermaid.** Fenced ```` ```mermaid ```` blocks, rendered by
  `MermaidDiagram.tsx` (light and dark). Labels translated per locale.
- **Meta.** `why.meta.*` / `how.meta.*` / breadcrumb labels updated if they claim
  a « complete » guide.
- **Six languages.** French first; the five translations follow only after the
  owner approves the French (load `lia-i18n`). zh keeps its own register and
  punctuation.
- **No git actions** (owner rule): the work stays in the working tree.

## No relapse

- **A length budget, tested.** `guides-structure.test.ts` gains a ceiling per
  family and locale (characters for zh, words elsewhere), set at the measured
  size of the rewrite plus a small margin, shrink-only like the other ratchets.
- **The release rule.** `.claude/skills/lia-release/SKILL.md` (Showcase
  surfaces) states that `why` / `how` are summaries under a budget: a feature
  changes at most a sentence of an existing section; what does not fit belongs
  to the FAQ or `docs/`. A new section means a new TOC entry and labels — a
  visible decision, never a release reflex.

## Order of work

1. Ledger of `why` (French) → French draft of `why` → owner review (draft +
   `LINKED`/`DROPPED` rows).
2. One sample section of `how` in the chosen voice → owner check → ledger and
   French draft of `how` → owner review.
3. Translations of both into en, de, es, it, zh.
4. TOC arrays, labels, version surfaces, links, length budget, release rule.
5. Verification.

`why` goes first because it is smaller and sets the voice the owner validates
before the larger page is written.

## Verification

- `task lint` (frontend, i18n, docs — `doc_audit`, `doc_facts`), `task
  test:frontend` (guides structure + budget), the release-surface tests
  (`scripts/release/tests/`, `task release:check`).
- Runtime proof on the Docker dev stack: both pages in light and dark, at phone
  width, diagrams rendered, every TOC entry landing on its section, in at least
  French, English and Chinese.

## Left to the builder

The exact section titles and their number within the ranges above, which
diagrams to draw, the budget margins, the ledger's file format, and how to split
the translation work.
