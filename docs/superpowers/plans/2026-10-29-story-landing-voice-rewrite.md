# Story and landing voice rewrite — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite the form of `/story` and of every home-page string in a clear, human voice (the new `/why` / `/how` voice), French first and owner-approved, then the five other languages — with every fact, caveat and figure kept.

**Architecture:** Drafts and ledgers live outside the app in `.tmp/story-landing-rewrite/`; small Python tools derive the landing key set from the code, check drafts mechanically, and swap values into the shared locale files without touching anything else. Two owner gates: a voice sample, then the full French on the running page.

**Tech Stack:** Markdown guides (`apps/web/src/data/guides/`), i18next JSON locales (`apps/web/locales/*/translation.json`), Python 3 stdlib tools run with `python -I`, vitest (`task test:frontend`), the release-surface checks (`task release:check`), Docker dev (`https://localhost:3000`).

**Spec:** `docs/superpowers/specs/2026-10-29-story-landing-voice-rewrite-design.md` — read it before any task.

## Global Constraints

- Values only: no key added, removed, renamed or reordered; no component touched (except the budget test, Task 7).
- Every fact, guarantee, limitation, figure and caveat of the current text survives; a statement the repository contradicts is kept as is and written to `flags.md` with its evidence.
- Voice: the why/how spec § Voice rules; landing in « tu »; `/story` in « je » with no direct address to the reader.
- Headlines and taglines are kept verbatim; a better one is only *proposed* beside the original in the ledger, the owner picks.
- UI strings (titles, chips, badges, buttons, tab labels, aria labels) stay ≤ 110 % of the current length of the same key in the same language; body text is free.
- Interpolations (`{{…}}`), embedded markup and array lengths identical to the current value.
- French vocabulary: `e-mail` / `e-mails` (never `email`, `Emails`); no-break space before `; : ? !` as the current French files use it.
- `/story` release fragments kept verbatim per language (patterns in `scripts/release/version_surfaces.py`): the two table rows `| Décisions d'architecture documentées (ADR) | **N** |`, `| Versions livrées à rythme régulier | **N** |`, the prose fragment « parmi les N documentées », and the `story.meta.description` fragment « tests, N ADRs, un audit technique ».
- No new exact count; existing figures keep their precision.
- `Date` header of the guides unchanged; `/story` `Version` 2.6 → 3.0 in the six files.
- Forbidden words (marketing guard): turnkey, one key, one endpoint, zero friction, and their translations.
- Registers: German « du », Spanish « tú », Italian « tu », Chinese « 你 ».
- Locale edits follow the `lia-i18n` skill: scripts in files (never heredocs), German/Chinese quotes from explicit OPEN/CLOSE constants, round-trip byte check before writing, integrity pass after.
- No git action of any kind (owner rule). Every « commit » step of the template is replaced by « leave the change in the working tree ».

## Review Focus

1. A rewritten UI string that wraps or overflows at 390 px in a long language (de, es, it) inside an opened disclosure — the reader sees a broken card. Pinned by the overflow probe in Task 8.
2. A sentence composed from several keys (`*_before` / `*_highlight` / `*_after`, `*_prefix`, a label followed by a value) that no longer reads once one fragment changes. Pinned by the fragment-group check in Task 4.
3. Another agent writes the same `translation.json` between the tool's read and its write — the swap would erase their work. Pinned by the stale-read refusal test in Task 5.
4. A caveat that a translation condenses away. Pinned by the per-language caveat back-check in Task 6.
5. An SEO description that grows past what a search result shows. Pinned by the length rule in Task 4 (`meta.description`, `home_meta.description`, `story.meta.description` ≤ max(current length, 160 characters); zh ≤ current length).

---

### Task 1: Landing inventory from the code

**Files:**
- Create: `.tmp/story-landing-rewrite/tools/landing_inventory.py`
- Create: `.tmp/story-landing-rewrite/tools/test_landing_inventory.py`
- Output: `.tmp/story-landing-rewrite/inventory/in-scope.txt`, `.tmp/story-landing-rewrite/inventory/orphans.txt`

**Interfaces:**
- Produces: `in-scope.txt` — one dotted leaf key per line (`landing.hero.title_line1`), sorted; array items as `key[i]`. `orphans.txt` — `key<TAB>reader` where reader is the page that reaches it (`/demo`, `/faq`…) or `none`.
- Produces: `python -I landing_inventory.py` → exit 0 and both files; exit 1 with the unresolved template on stderr.

- [ ] **Step 1: Write the tests** (`pytest`, plain functions):
  - `test_known_static_keys`: `landing.hero.title_line1`, `landing.context.center_body`, `landing.home_cta.title`, `landing.transparency.honest` are in scope.
  - `test_every_required_feature_card`: for every key of `REQUIRED_FEATURE_KEYS` (parsed from `apps/web/src/components/landing/editorial/chapters-data.ts`), `landing.features.<k>.title` and `.description` are in scope.
  - `test_dynamic_families`: `landing.catalog_explorer.feature_examples.<k>.request` for one required key, `landing.product_demo.scenes.decision.title`, `landing.home_product_demo.approval_hint` are in scope.
  - `test_shared_strings_included`: every leaf under `landing.cta.` and `landing.meta.` is in scope.
  - `test_demo_only_excluded`: `landing.product_demo.meta_description` is NOT in scope (if the walk reaches it, investigate the reachable file; never edit the assertion away).
  - `test_partition`: in-scope ∪ orphans = every leaf of `landing` in `apps/web/locales/fr/translation.json`, and they are disjoint.
- [ ] **Step 2: Run them** — `cd .tmp/story-landing-rewrite/tools && python -I -m pytest test_landing_inventory.py -q` → FAIL (module missing).
- [ ] **Step 3: Implement `landing_inventory.py`.** Walk the import graph from `apps/web/src/app/[lng]/page.tsx` (resolve `@/` to `apps/web/src/`, relative imports, `.ts`/`.tsx`/`index.*`; ignore `__tests__`). In each reachable file: a string literal `landing.a.b` is an exact key (if it names a subtree rather than a leaf, take every leaf below it); a template literal is resolved by substituting string constants defined `const X = 'landing.…'` in any reachable file, then its static prefix before the first `${` selects every leaf below that prefix. A prefix shorter than `landing.<namespace>.` is unresolved → exit 1. Add `landing.cta.*` and `landing.meta.*` (spec: shared strings). Orphans are labelled by the same scan run from every other `apps/web/src/app/[lng]/**/page.tsx`.
- [ ] **Step 4: Run the tests** → PASS. Record in `progress.md`: in-scope count, orphan count, French words in scope.
- [ ] **Step 5: Leave in the working tree** (no git).

### Task 2: `/story` ledger and accuracy check

**Files:**
- Create: `.tmp/story-landing-rewrite/source/story.{fr,en,de,es,it,zh}.md` (copies of the current files) and `source/blobs.txt` (`git hash-object` of each current guide and locale file)
- Create: `.tmp/story-landing-rewrite/ledger-story.md`
- Create: `.tmp/story-landing-rewrite/tools/ledger_check.py` (copy of `.tmp/why-how-rewrite/tools/ledger_check.py`, adapted)
- Create: `.tmp/story-landing-rewrite/flags.md`

**Interfaces:**
- Produces: ledger rows `| id | source § | category | fact | verified | destination |` — categories as in the why/how ledger; `verified` = a repository path, a command and its output, or `FLAG-n`; `destination` filled in Task 4 (the new section key and a quoted fragment), or `DROPPED duplicate of #id`.
- Produces: `flags.md` entries `FLAG-n · § · statement · evidence · proposed wording` — starts with the three of the spec (July audit date, « six niveaux », « trente-deux tableaux de bord »).

- [ ] **Step 1: Adapt `ledger_check.py`**: fates are only `KEPT` (any category) or `DROPPED duplicate of #id` (the referenced row must exist and be `KEPT`); add `--require-destination` (every row has one) and `--require-verified` (every row has a non-empty `verified`).
- [ ] **Step 2: Write the ledger** for every section and sub-section of `source/story.fr.md` (including the table, the italic stack line and the closing note); one row per fact a reader could repeat.
- [ ] **Step 3: Verify every row** against the repository (code, `CLAUDE.md`, ADRs, `docs/audit/README.md`, `version_surfaces.py` derived counts); a contradiction becomes a `FLAG-n` in `flags.md`.
- [ ] **Step 4: Run** `python -I ledger_check.py source/story.fr.md ledger-story.md --require-verified` → exit 0.
- [ ] **Step 5: Leave in the working tree.**

### Task 3: Voice sample → owner gate

**Files:**
- Create: `.tmp/story-landing-rewrite/draft/story.fr.md` (sections 1 and 4 rewritten, others unchanged)
- Create: `.tmp/story-landing-rewrite/draft/fr.landing.json` (`{ "landing.hero.…": "new value", … }` for every in-scope key of `hero`, `promise`, `context`)
- Create: `.tmp/story-landing-rewrite/tools/voice_check.py` (copy of `.tmp/why-how-rewrite/tools/voice_check.py`, `HEADER_LINES` adjusted to the story header)

**Interfaces:**
- Consumes: `in-scope.txt` (Task 1), `ledger-story.md` (Task 2).
- Produces: the draft formats used by every later task.

- [ ] **Step 1: Write** §1 and §4 of `/story` per the spec § The `/story` subtext (folding §1's three appended paragraphs into §1's body; splitting §4's long paragraph by subject), and the three landing blocks per § Voice (headlines verbatim; any better headline goes into `ledger-landing.md` as a proposal, not into the draft).
- [ ] **Step 2: Run** `python -I tools/voice_check.py draft/story.fr.md` → exit 0, and `python -I tools/ledger_check.py source/story.fr.md ledger-story.md --only 1-1` and `--only 4-4` with destinations filled for those sections → exit 0.
- [ ] **Step 3: Present to the owner**: old and new side by side for §1, §4 and the three landing blocks, plus the flags found so far. **Stop until the owner approves the voice**; record their corrections in `progress.md` as rules applied to every later task.

### Task 4: Full French draft and its checks

**Files:**
- Modify: `.tmp/story-landing-rewrite/draft/story.fr.md` (all sections; header `Version` → `3.0`)
- Modify: `.tmp/story-landing-rewrite/draft/fr.landing.json` (every in-scope key whose value changes; unchanged keys omitted)
- Create: `.tmp/story-landing-rewrite/draft/fr.story-keys.json` (`story.meta.*`, `story.hero.*`, `story.breadcrumb`, `story.toc.*` if reworded)
- Create: `.tmp/story-landing-rewrite/ledger-landing.md`
- Create: `.tmp/story-landing-rewrite/tools/landing_check.py`, `tools/test_landing_check.py`

**Interfaces:**
- Consumes: Task 1 files, Task 2 ledger, Task 3 rules.
- Produces: `python -I landing_check.py <lang> draft/<lang>.landing.json` → exit 0 or one line per failure `key: rule: detail`.
- Produces: `ledger-landing.md` rows `| key | old | new | facts and caveats (each ticked ✓ when present in new) | headline proposal |`.

- [ ] **Step 1: Write `test_landing_check.py`** with synthetic inputs: a changed `{{count}}` fails (`placeholder`); a dropped `<strong>` fails (`markup`); a 3-item array becoming 2 fails (`array`); a button label at 115 % of its old length fails (`ui-size`), a body text at 200 % passes; `Emails` in a fr value fails (`vocabulary`); « turnkey » fails (`claim`); a `home_meta.description` growing past max(old, 160) fails (`seo-length`); changing `hero.title_line2_after` without listing `hero.title_line2_before` and `hero.title_line2_highlight` in the same draft fails (`fragment-group`); a key absent from `in-scope.txt` fails (`scope`).
- [ ] **Step 2: Run** `python -I -m pytest tools/test_landing_check.py -q` → FAIL.
- [ ] **Step 3: Implement `landing_check.py`.** UI-string class = key leaf named `title`, `label`, `*_label`, `badge*`, `chip_*`, `button`, `cta*`, `aria*`, `tab*`, `eyebrow`, `hint`, or any current value ≤ 40 characters; size in characters (zh included). Fragment groups = sibling keys sharing a stem with suffixes `_before`, `_highlight`, `_after`, `_prefix`, `_suffix`. Old values are read from the current locale file; the check also writes `composed.md` (every fragment group rendered whole, old and new) for the reviewer.
- [ ] **Step 4: Run the tests** → PASS.
- [ ] **Step 5: Write the rest of the French**: `/story` §2, 3, 5, 6, 7 and the closing note (folding §3's three `###` sub-sections and §5's appended paragraphs into their subjects; the §3 blockquote becomes a sentence); every in-scope landing block. Fill `ledger-landing.md` for every changed key and every `destination` of `ledger-story.md`. Check every landing figure and every claim about what LIA does or guarantees; contradictions go to `flags.md`.
- [ ] **Step 6: Run** `voice_check.py draft/story.fr.md` → exit 0; `ledger_check.py source/story.fr.md ledger-story.md --require-verified --require-destination` → exit 0; `landing_check.py fr draft/fr.landing.json` → exit 0; every row of `ledger-landing.md` has all its facts ticked. Record the French size of `/story` and of the landing in `progress.md`.

### Task 5: Swap the French in → owner review on the running page

**Files:**
- Create: `.tmp/story-landing-rewrite/tools/apply_values.py`, `tools/test_apply_values.py`
- Modify: `apps/web/src/data/guides/story.fr.md` (copied from the draft)
- Modify: `apps/web/locales/fr/translation.json` (values only)
- Modify: any component test that asserts a French literal that changed (`apps/web/src/components/landing/**/__tests__/`, `apps/web/src/app/[lng]/__tests__/`) — expected literal updated, assertion kept

**Interfaces:**
- Produces: `python -I apply_values.py <lang> <draft.json> [<draft.json>…]` → writes the locale file or exits 1 without writing.

- [ ] **Step 1: Write `test_apply_values.py`** on a temp copy of a small locale-shaped file: only the targeted leaves differ after apply (every other leaf and the key order byte-identical); a key missing from the file fails; a file whose bytes no LF/CRLF candidate reproduces fails without writing; **a file modified between read and write fails without writing** (hash taken at read, compared just before write — Review Focus 3); the integrity pass rejects an empty quote pair (`„“`, `“”`, `«  »`) and a value under 20 characters whose old value was ≥ 40 (answers/body only).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** (round-trip candidates as in the `lia-i18n` skill; values set by dotted path; dump with the matched line ending). **Step 4: Run** → PASS.
- [ ] **Step 5: Re-check the sources**: compare `source/blobs.txt` with the current files; any change made meanwhile is merged into the draft and ledgers first.
- [ ] **Step 6: Apply** `apply_values.py fr draft/fr.landing.json draft/fr.story-keys.json`; copy `draft/story.fr.md` to `apps/web/src/data/guides/story.fr.md`.
- [ ] **Step 7: Verify**: `task lint:i18n` exit 0; `task test:frontend` all green (update pinned French literals only); `task release:check` reports no `/story` surface drift; `python scripts/audit/doc_facts.py` 0 drifted.
- [ ] **Step 8: Runtime proof** on Docker dev, French: home page with every disclosure opened and `/story`, light and dark, 390 px and desktop; no raw key, no broken composed sentence (`composed.md`), no overflow.
- [ ] **Step 9: Owner review**: send the owner the two French URLs, `flags.md`, the headline proposals, `orphans.txt` with readers, and the sizes. **Stop until approval.** Apply their rulings (flags, headlines, wording) to the French drafts, re-run Steps 6–8, record rulings in `progress.md`.

### Task 6: Translations (en, de, es, it, zh)

**Files:**
- Create: `.tmp/story-landing-rewrite/TRANSLATION_BRIEF.md`
- Create per language: `draft/story.<lang>.md`, `draft/<lang>.landing.json`, `draft/<lang>.story-keys.json`, `backcheck/<lang>.md`
- Modify: `apps/web/src/data/guides/story.<lang>.md`, `apps/web/locales/<lang>/translation.json`

**Interfaces:**
- Consumes: approved French drafts and ledgers (Task 5), tools of Tasks 3–5.
- Produces: `backcheck/<lang>.md` rows `| key or ledger id | caveats and facts of the French row | ✓ each, with the target-language fragment |`.

- [ ] **Step 1: Write the brief**: the approved French is the source; the voice rules restated for the language; the register; headlines adapted to sound like headlines, not literal; the per-language release fragments copied from `version_surfaces.py` (en « among the N documented », de « unter den N dokumentierten », es « entre las N documentadas », it « tra le N documentate », zh « 在 N 个已记录的决策中 », the two table labels and the meta-description fragment of that language); UI size compared to the current value **in that language**; zh punctuation full-width.
- [ ] **Step 2: Translate** each language from the approved French (one independent worker per language is fine; each reads only the brief, the French drafts and its own current locale values).
- [ ] **Step 3: Back-check each language**: a reader other than its translator fills `backcheck/<lang>.md` for every `ledger-landing.md` key with a caveat and every `ledger-story.md` row; a missing item is fixed in the draft (Review Focus 4).
- [ ] **Step 4: Run per language**: `landing_check.py <lang> draft/<lang>.landing.json` exit 0; `voice_check.py draft/story.<lang>.md --lang <lang>` exit 0; every back-check row ticked.
- [ ] **Step 5: Apply per language** (`apply_values.py`, copy the story draft), then `task lint:i18n`, `task test:frontend`, `task release:check` — all green before the next language.

### Task 7: No relapse

**Files:**
- Modify: `apps/web/src/components/guides/__tests__/guides-structure.test.ts` (`GUIDE_BUDGETS` and its `it.each`)
- Modify: `.claude/skills/lia-release/SKILL.md` (Showcase surfaces bullet)

- [ ] **Step 1: Extend the test first**: type `Record<'why' | 'how' | 'story', …>` and `it.each` over the three families; run `task test:frontend` → the `story` cases FAIL (no budget).
- [ ] **Step 2: Add `story` budgets** = `ceil(guideSize(story.<lang>.md) × 1.10)` measured on the final files (the why/how rule), with the comment stating the measurement date; run → PASS.
- [ ] **Step 3: Extend the release rule**: `why`, `how` **and `story`** are summaries under the tested budget; a release changes at most one sentence of an existing section and never appends a paragraph. (The skill is git-ignored: the tracked carrier is the test comment.)

### Task 8: Final verification and cold review

- [ ] **Step 1: Gates**: `task lint` (if a pre-existing failure unrelated to this lot blocks it, run and report each sub-gate: `task lint:i18n`, `task lint:frontend`, `task lint:docs`), `task test:frontend`, `task release:check`, `apps/api/.venv/Scripts/pytest scripts/release/tests -q` (from the repository root, as the Taskfile runs it) — exact commands, exit codes and counts recorded in `progress.md`.
- [ ] **Step 2: Overflow probe** (Review Focus 1): on Docker dev, for fr, en, de, es, it, zh, home page with every disclosure opened at 390 px, evaluate in the page every element under `main` with `scrollWidth > clientWidth + 1` or a text node clipped by `overflow: hidden`; expected: none attributable to a rewritten string. Same for `/story` in fr, en, zh, light and dark.
- [ ] **Step 3: Cold adversarial review** by a fresh reviewer given the spec, the ledgers and the diff of the six locale files and six story files: every changed value read in full, every caveat and figure found, every voice rule applied; fixes carried into all six languages.
- [ ] **Step 4: Report** to the owner: what changed, sizes, flags and rulings, gates with their outputs, what was not verified. Update the memory entry for this lot. No git action.
