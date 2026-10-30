# Why / How Readable Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `/why` and `/how` guides (6 languages) with short, human-voiced summaries that keep every important piece of information, and stop releases from re-inflating them.

**Architecture:** The work is editorial. Each page goes through inventory (a ledger of claims with a fate each), then a French draft, reviewed by the owner, then five translations. Drafts are staged in `/.tmp/why-how-rewrite/` (git-ignored) and swapped into `apps/web/src/data/guides/` in one step, together with the TOC arrays, i18n labels and release-surface declarations. Two vitest guards land in the same step: on-site links resolve, and a shrink-only length budget per page and locale.

**Tech Stack:** Markdown rendered by `react-markdown` + `MermaidDiagram.tsx` (Next.js 16), vitest, Python release-surface declarations (`scripts/release/version_surfaces.py`), i18n JSON in `apps/web/locales/{lang}/translation.json`.

**Spec:** `docs/superpowers/specs/2026-10-28-why-how-readable-rewrite-design.md` (read it first; its Ledger, Voice and Constraints sections are normative).

## Global Constraints

- French is the source; `en`, `de`, `es`, `it`, `zh` are translated only after the owner approves the French.
- Targets: `why` ≈ 2,500 French words, 8–10 sections; `how` ≈ 5,000 French words, 12–14 sections, 3–5 Mermaid diagrams. Information beats the count; a French draft > 20 % over target is reported to the owner with the reason.
- `why` addresses the reader as « tu ». `how` uses « tu » for the reader and the author's « je » for choices (owner decision 2026-10-28); every « je » reason must be supported by an ADR or doc the ledger names.
- Ledger rule: `capability`, `guarantee`, `design-choice`, `limitation` rows are never `DROPPED`; a row whose content exists nowhere else is never `DROPPED`.
- No exact counts the code owns (ADR count, FAQ questions, metrics, dashboards). Versions at generation precision (`Next.js 16`, `LangGraph 1.x`, `Python 3.14`).
- Keep the header block of every file: `**Version**`, `**Date**`, `**Application**`, `**Licence**` (localized labels). New doc versions: `why` → `7.0`, `how` → `6.0`. **Do not change the `Date`** — the 18 guides (story included) must share one header date.
- Links: `why` → on-site pages (`/faq#faq-<section>`, `/how`, `/how#<id>`, `/story`, `/maps`); `how` → those plus `https://github.com/jgouviergmail/LIA-Assistant/blob/main/<stable doc>`. Never code lines, never relative `../docs` paths.
- Never leave `apps/web/` with red structure or parity tests: nothing under `apps/web/` changes before Task 9.
- **No git actions** (owner rule): every "commit" step below is "leave the change in the working tree". The owner handles git.
- New repository documents are in English; drafts and ledgers in `.tmp/` are not repository documents.

## Review Focus

1. **Release lands mid-work** — a release edits the old guides after the snapshot; expected: its new claims reach the ledger before the swap (Task 8 re-diff).
2. **A link to an anchor that does not exist** (`/faq#faq-x`, `/how#y`) — expected: the structure test fails naming the file and the link (Task 1).
3. **A translation that drifts in length or loses a section** — expected: section count, TOC and budget tests fail per locale (Task 9).
4. **A Mermaid diagram that fails to parse in one locale** (a translated label with `:` or quotes) — expected: caught at runtime proof, diagram renders in fr, en, zh, light and dark (Task 11).
5. **A removed sentence still declared as a release surface** — expected: `release:check` and the version-surface tests fail until the declaration is removed or re-counted (Task 9).

---

### Task 0: Staging area and source snapshot

**Files:**
- Create: `.tmp/why-how-rewrite/source/{why,how}.{fr,en,de,es,it,zh}.md` (copies)
- Create: `.tmp/why-how-rewrite/source/BLOBS.txt`

- [ ] **Step 1:** Copy the 12 current files from `apps/web/src/data/guides/` into `.tmp/why-how-rewrite/source/`.
- [ ] **Step 2:** Record `git hash-object apps/web/src/data/guides/<file>` (the WORKING-TREE content, which carries uncommitted release edits) for each of the 12 files into `BLOBS.txt`, one `<hash>  <file>` line each.
- [ ] **Step 3:** Verify: `git check-ignore .tmp/why-how-rewrite/source/BLOBS.txt` prints the path (the folder is ignored).

### Task 1: Guard — every on-site link in a guide resolves

**Files:**
- Modify: `apps/web/src/components/guides/__tests__/guides-structure.test.ts`

**Interfaces:**
- Produces: `onSiteLinks(text: string): string[]` (every markdown link target starting with `/`) and `unresolvedLink(target: string): string | null` (reason or `null`), local to the test file.
- Resolution rules: `/how#<id>` → `<id>` ∈ `HOW_TOC_SECTIONS` ids; `/why#<id>` → ∈ `WHY_TOC_SECTIONS`; `/story#<id>` → ∈ `STORY_TOC_SECTIONS`; `/faq#faq-<s>` → `<s>` ∈ `PUBLIC_FAQ_SECTIONS` (`components/faq/faq-sections.ts`); bare `/how`, `/why`, `/story`, `/faq`, `/maps`, `/privacy`, `/terms` resolve; anything else is unresolved.

- [ ] **Step 1: Write the failing test** `describe('guide on-site links')`:
  - `it('resolves known targets')`: `unresolvedLink('/how#ddd')` → `null` (`ddd` exists today), `unresolvedLink('/faq#faq-' + PUBLIC_FAQ_SECTIONS[0])` → `null`, `unresolvedLink('/maps')` → `null`.
  - `it('rejects unknown targets')`: `unresolvedLink('/how#nope')`, `unresolvedLink('/faq#faq-nope')`, `unresolvedLink('/nowhere')` are all non-null.
  - `it('extracts on-site links only')`: `onSiteLinks('[a](/story) [b](https://x.y/z) [c](#local)')` → `['/story']`.
  - `it.each(FAMILIES × LANGS)('every on-site link of {name}.{lang} resolves')`: `onSiteLinks(read(name, lang)).map(unresolvedLink).filter(Boolean)` → `[]`.
- [ ] **Step 2:** Run `cd apps/web && NEXT_PUBLIC_API_URL= pnpm vitest run src/components/guides/__tests__/guides-structure.test.ts` → FAIL (helpers undefined).
- [ ] **Step 3:** Implement both helpers in the test file (regex `\]\((\/[^)\s]*)\)`; split on `#`).
- [ ] **Step 4:** Re-run the same command → PASS (current guides only link `/story`).

### Task 2: Ledger of `why` (French)

**Files:**
- Create: `.tmp/why-how-rewrite/ledger-why.md`
- Create: `.tmp/why-how-rewrite/tools/ledger_check.py`

**Interfaces:**
- Produces: a markdown table, one row per claim: `| id | source § | claim | category | fate | where |`. `id` = `W-<n>`; `source §` = the `###` (or `##`) heading number it came from; `category` ∈ `capability, guarantee, design-choice, limitation, figure, detail`; `fate` ∈ `KEPT, LINKED, DROPPED`; `where` = link target for `LINKED`, the doc/ADR/code path for `DROPPED`, empty for `KEPT`.
- Produces: `ledger_check.py <source.md> <ledger.md>` exiting non-zero on: a source heading with no row; a `DROPPED` row whose category is not `figure`/`detail`; a `DROPPED` or `LINKED` row with empty `where`; a `LINKED` target that is a bare index (`ADR_INDEX`, `docs/INDEX.md`).

- [ ] **Step 1:** Write `ledger_check.py` (stdlib only, run with `python -I`).
- [ ] **Step 2:** Fill the ledger from `.tmp/why-how-rewrite/source/why.fr.md`, one fact a reader could repeat per row (spec, "Precisions"). For every `LINKED`/`DROPPED` row, open the `where` target and confirm it says the claim.
- [ ] **Step 3:** Run `python -I .tmp/why-how-rewrite/tools/ledger_check.py .tmp/why-how-rewrite/source/why.fr.md .tmp/why-how-rewrite/ledger-why.md` → exit 0.

### Task 3: French draft of `why` → owner review

**Files:**
- Create: `.tmp/why-how-rewrite/draft/why.fr.md`
- Create: `.tmp/why-how-rewrite/tools/voice_check.py`

**Interfaces:**
- Consumes: `ledger-why.md` (Task 2).
- Produces: the section id list for `why` (written at the top of the ledger as `ids: [...]`), consumed by Task 9; outline per spec ("Proposed outlines").
- Produces: `voice_check.py <draft.md>` reporting: word count; paragraphs opening on a bold sentence (`^\*\*[^*]+[.!?]\*\*`) — must be 0; `ADR-\d+` outside a « Pour aller plus loin » line — 0; ISO dates outside the header — 0; « jamais » and em dashes per 1,000 words — each ≤ 3.

- [ ] **Step 1:** Write `voice_check.py`.
- [ ] **Step 2:** Write the draft: header block (Version `7.0`, Date unchanged, Application unchanged, Licence), `# ` title, `## Table des matières` with `N. [Title](#anchor)` lines, then `## 1.` … sections. Every `KEPT` row is said; every `LINKED` row has its link.
- [ ] **Step 3:** Run `python -I .tmp/why-how-rewrite/tools/voice_check.py .tmp/why-how-rewrite/draft/why.fr.md` → all checks pass; word count reported (flag > 3,000).
- [ ] **Step 4 (checkpoint, STOP):** Send the owner the draft path, its reading time, and the `LINKED`/`DROPPED` rows grouped by section. Apply the owner's corrections (promoted rows become `KEPT`). Do not start Task 4 before the owner approves.

### Task 4: Sample section of `how` in the « je » voice → owner check

**Files:**
- Create: `.tmp/why-how-rewrite/draft/how.sample.fr.md`

- [ ] **Step 1:** Write the « Le parcours d'un message » section (spec outline §3): router, pipeline vs ReAct with one Mermaid diagram, « je » reasons taken from ADR-070 and the ADRs it cites (name them at the end of the section).
- [ ] **Step 2:** Run `voice_check.py` on it → pass.
- [ ] **Step 3 (checkpoint, STOP):** Send it to the owner; adjust the voice from the feedback before Task 6.

### Task 5: Ledger of `how` (French)

**Files:**
- Create: `.tmp/why-how-rewrite/ledger-how.md` (ids `H-<n>`)

- [ ] **Step 1:** Inventory `.tmp/why-how-rewrite/source/how.fr.md` exactly as Task 2. The file is ~366 KB: split by `##` sections into batches (e.g. 1–12, 13–24, 25–36, 37–47) and merge. The `design-choice` vs `detail` boundary is the spec's (one-page architecture summary test).
- [ ] **Step 2:** Run `ledger_check.py` on source + ledger → exit 0.

### Task 6: French draft of `how` → owner review

**Files:**
- Create: `.tmp/why-how-rewrite/draft/how.fr.md`

- [ ] **Step 1:** Write the draft (Version `6.0`, Date unchanged), outline per spec, the Task 4 section in place, 3–5 Mermaid diagrams; record its `ids: [...]` at the top of `ledger-how.md`.
- [ ] **Step 2:** `voice_check.py` → pass; report the word count (flag > 6,000).
- [ ] **Step 3 (checkpoint, STOP):** Owner review exactly as Task 3 Step 4.

### Task 7: Translations (en, de, es, it, zh)

**Files:**
- Create: `.tmp/why-how-rewrite/draft/{why,how}.{en,de,es,it,zh}.md`

- [ ] **Step 1:** Load the `lia-i18n` skill. Translate both approved French drafts; keep each locale's existing header labels (copy them from `source/`), the same section count, anchors and links; translate Mermaid labels (quote any label containing `:` or parentheses).
- [ ] **Step 2:** Run `voice_check.py` on the ten files (the « jamais » check applies to French only; skip it elsewhere).
- [ ] **Step 3:** Check each file has the same number of `## N.` headings and TOC lines as its French source.

### Task 8: Re-diff the sources before the swap

- [ ] **Step 1:** For each of the 12 files, compare `git hash-object apps/web/src/data/guides/<file>` with `BLOBS.txt`.
- [ ] **Step 2:** For every changed file, `diff` it against `.tmp/why-how-rewrite/source/<file>`, add each new claim to the ledger with a fate, and apply `KEPT`/`LINKED` rows to the drafts in all six languages. Re-run `ledger_check.py` → exit 0. If nothing changed, note it.

### Task 9: Swap, navigation, labels, release surfaces, length budget

**Files:**
- Modify: `apps/web/src/data/guides/{why,how}.{fr,en,de,es,it,zh}.md` (replaced by the drafts)
- Modify: `apps/web/src/components/guides/guides-toc.ts` (`WHY_TOC_SECTIONS`, `HOW_TOC_SECTIONS`; drop unused icon imports)
- Modify: `apps/web/locales/{en,fr,de,es,it,zh}/translation.json` (`why.toc`, `how.toc`, `why.meta.description`, `why.hero.subtitle` — today « Sept qualités… »/« 7 piliers » —, `how.meta.*`, `how.hero.subtitle`)
- Modify: `scripts/release/version_surfaces.py` (every `FIXED_SURFACES`/`COUNT_SURFACES` entry whose path is a `why`/`how` guide)
- Modify: `apps/web/src/components/guides/__tests__/guides-structure.test.ts`

**Interfaces:**
- Consumes: the `ids: [...]` lists of Tasks 3 and 6.
- Produces: `GUIDE_BUDGETS: Record<'why' | 'how', Record<Lang, number>>` and `guideSize(text: string, lang: Lang): number` (zh: non-whitespace characters; others: whitespace-separated words).

- [ ] **Step 1: Write the failing test** `it.each(['why','how'] × LANGS)('stays within its length budget')`: `guideSize(read(name, lang), lang)` ≤ `GUIDE_BUDGETS[name][lang]`. Values: `ceil(measured size of the draft × 1.10)`, measured with `guideSize` on `.tmp/why-how-rewrite/draft/`. Comment above the constant: shrink-only, lower it when a page shrinks, never raise it to absorb a release.
- [ ] **Step 2:** Run the structure test → FAIL (old guides exceed the budget).
- [ ] **Step 3:** Copy the 12 drafts into `apps/web/src/data/guides/`; rewrite the two TOC arrays from the `ids` lists (one lucide icon each); replace `why.toc` / `how.toc` keys in the six locales (old keys removed) and update the meta/hero copy to match the new pages.
- [ ] **Step 4:** In `version_surfaces.py`, remove each guide surface whose sentence no longer exists (the `how` provenance note, the ADR/metric/dashboard counts, the `why` FAQ question count); re-declare `expected` for any that survive. Leave `STAMPED_GUIDE_STEMS`, `MIN_EXPECTED_GUIDE_STAMPS` unchanged.
- [ ] **Step 5:** `grep -rnE '/(why|how)#' apps/web/src apps/web/locales docs README.md` → no link to a removed id (outside the spec).
- [ ] **Step 6:** Run, all PASS:
  - `cd apps/web && NEXT_PUBLIC_API_URL= pnpm vitest run src/components/guides/__tests__/guides-structure.test.ts`
  - `task lint:i18n`
  - `apps/api/.venv/Scripts/pytest scripts/release/tests -q`
  - `cd apps/api && .venv/Scripts/pytest tests/unit/test_version_surface_consistency_guard.py tests/unit/test_doc_facts_guard.py -q`
  - `task release:check` (no drift reported)

### Task 10: The release rule

**Files:**
- Modify: `.claude/skills/lia-release/SKILL.md` (bullet « Showcase surfaces », lines ~89–95)

- [ ] **Step 1:** Add to that bullet: `why` and `how` are summaries under a tested length budget (`guides-structure.test.ts`, `GUIDE_BUDGETS`): a feature changes at most one sentence of an existing section; what does not fit goes to the FAQ or `docs/`; a new section is a deliberate decision (TOC array + six labels), never a release reflex; no exact counts.
- [ ] **Step 2:** `task lint:docs` → PASS.

### Task 11: Verification and runtime proof

- [ ] **Step 1:** Run `task lint` and `task test:frontend` → PASS; record command, exit status and test counts.
- [ ] **Step 2:** On the Docker dev stack (`task dev:detach`, web on `http://localhost:3000`), open `/fr/why`, `/fr/how`, `/en/why`, `/en/how`, `/zh/why`, `/zh/how`: light and dark, desktop and 390 px width; every TOC entry lands on its section, every Mermaid diagram renders, no console error. Screenshots kept in `.tmp/why-how-rewrite/proof/`.
- [ ] **Step 3:** Report to the owner: final reading times per page, the files changed, the command results, and that nothing was committed.
