# Story and landing — a human voice, the same substance

Date: 2026-10-29. Status: design, awaiting owner approval. Nothing is rewritten yet.

## Intent

`/why` and `/how` were rewritten on 2026-10-28/29 into short, concrete pages in a
human voice (spec: `2026-10-28-why-how-readable-rewrite-design.md`). The owner now
wants the same treatment for the **form** of two other showcase surfaces: the
`/story` page and the landing (the home page).

Owner's words (2026-10-29):

- « en français je trouve les formulations non naturelles, très impersonnelles et
  peu claires. Le fond du contenu est très bien et il faut le conserver, c'est
  vraiment une question de forme »;
- « t'inspirer des formulations /why et /how qui sont très bien, mais toujours sans
  dénaturer le fond. Il faut rendre les textes clairs et humains et se défaire de
  formulations impersonnelles ou typées IA »;
- on `/story`: « mettre en avant, mais en filigrane, entre les lignes, ma démarche de
  directeur qui sait se confronter à de la réalisation opérationnelle afin
  d'améliorer ses capacités de décision. C'est un peu démontrer mes capacités de
  dirigeant avec un pied dans la maîtrise et la compréhension fine. »

The owner judges French well and the other five languages poorly, so French is the
source: it is rewritten and approved first, then the five other languages are
rewritten from it.

What the current French looks like (examples, not an exhaustive list):

- `/story` §1: « Les décisions natives facultatives prolongent cette méthode sans
  transformer une confiance de modèle en permission. » — abstract nominal phrasing;
  three closing paragraphs of §1, three `###` sub-sections of §3 and the last three
  paragraphs of §5 were appended release after release, each in that register and
  each loosely attached to its section.
- `/story` §4: one paragraph of ~600 words chaining « Et … », « Enfin … ».
- `/story` §3: the blockquote aphorism « La vitesse vient de l'IA. La qualité vient
  du cadre. Et le cadre est un travail de direction. »
- landing `context.center_body`: « Relations rassemble l'échange récent et
  l'engagement ouvert. En conversation, prépare le rendez-vous à partir des sources
  accessibles ; ta préférence de réponse concise aide à aller à l'essentiel. »
- landing everywhere: stacked legal hedges (« selon les fonctions activées et les
  sources autorisées », « quand le parcours le prévoit », « selon ta
  configuration »), sometimes two in one sentence.

## Scope

### `/story`

- `apps/web/src/data/guides/story.{fr,en,de,es,it,zh}.md`.
- The `story.*` locale keys: `meta.title`, `meta.description`, `breadcrumb`,
  `hero.title`, `hero.subtitle`, `toc.*` (labels may be reworded; section ids may
  not, see Constraints).

### The landing

Every string the **home page** (`apps/web/src/app/[lng]/page.tsx`) can show,
including what opens on a click (feature cards behind « Le détail … », catalog
explorers, chapter scenes, the product-demo scenes rendered inside the chapters, the
screenshot captions, the gallery, the video section, the presentation dialog), its
SEO strings (`home_meta.*`, the `how_it_works.*` JSON-LD steps) and the footer and
header labels.

The set is **derived from the code**, not guessed: walk the component tree from
`page.tsx`, collect every `t('landing.…')` and every dynamic key built from data
files (`chapters-data.ts`, `FeatureScenes.ts`, `demo/scenes.ts`…), resolve them to
leaf keys. Measured while scoping: the `landing`
namespace holds ~1,300 French leaves, ~19,900 words; the largest blocks are
`features` (~6,900 words), `catalog_explorer` (~2,700), `tech` (~1,900) and
`chapters` (~1,800).

`landing.cta.*`, `landing.meta.*` (the home page renders `home_cta` and `home_meta`
instead; these are shown on `/faq`, `/blog`, `/changelog`, `/more`) are in scope
anyway, as the landing's own copy reused elsewhere (designer's call).

SEO strings (`home_meta.*`, `landing.meta.*`, the `how_it_works.*` JSON-LD steps)
follow the voice, but keep the nouns a person types in a search engine (assistant
IA personnel, open source, auto-hébergé, e-mails, agenda, six langues). Internal
jargon nobody searches for (« HITL ») goes (designer's call).

Out of scope:

- `/more` (its own page and `more.*` namespace, with its own content tests);
- strings the home page borrows from other surfaces: the changelog items
  (`faq.changelog.*`) behind the changelog disclosure and the blog titles and
  excerpts (`blog.*`, rewritten on 2026-10-29) in the blog preview;
- strings only the `/demo` page renders (`landing.product_demo.*` where the home
  page does not reach them);
- `landing.*` keys no page renders (orphans): listed in the inventory and reported
  to the owner, not rewritten, not deleted;
- the giant one-word labels (`cosmos.ghost.*`, planet names): in scope, but expected
  to stay as they are;
- the FAQ, the blog, `docs/knowledge/`, the README, `/why`, `/how`.

## Goals

1. A French text that reads as written by a person: clear on first reading, in the
   voice of the new `/why` and `/how`.
2. **The same substance.** Every fact, guarantee, limitation, figure and caveat of
   the current text is still in the new text (see « The substance ledger »).
3. On `/story`, the owner's posture shows between the lines (see « The `/story`
   subtext »).
4. Five translations rewritten from the approved French, each natural in its own
   language.
5. No relapse on `/story`: a length ceiling like `/why` and `/how`.

## Non-goals

- No redesign: no component, layout, section, card, chapter or key is added,
  removed, renamed or reordered. Only string **values** change.
- No new claims, no new capability, no new figure.
- No shortening for its own sake. Pages may get shorter as padding and repetition
  go, but no target length is imposed and nothing is cut to reach one.
- No change to the `/story` audience (people evaluating a leader and a method, not
  product buyers) or to its seven-section structure.

## Anti-goals (failure even if it "works")

- A caveat that disappears. « Les conclusions de LIA restent à vérifier », « la
  facture des services externes reste celle de leur fournisseur », « ce rapport ne
  constitue pas une certification », « LIA est en bêta » — each one survives,
  said once where it matters, in plain words.
- Marketing fluff: adjectives in place of facts, superlatives, exclamation marks.
- On `/story`: self-praise. No « en tant que dirigeant exigeant… », no adjective
  about the author, no LinkedIn-style punchline. The reader must conclude it; the
  text never says it.
- Swapping one tic for another (rhetorical questions everywhere, « Résultat : »
  openers, bullet lists replacing every paragraph, emoji).
- A UI string that no longer fits its place (button, chip, badge, card title) or a
  broken interpolation.

## Voice

The rules of the why/how spec (§ Voice) apply unchanged. In short:

- short sentences, concrete verbs, one everyday example where it helps
  (« Tu demandes à LIA de décaler ton rendez-vous de jeudi : elle prépare la
  modification et te la montre avant de l'envoyer. »);
- the landing speaks to its reader with « tu » (existing convention); `/story` is
  written in the author's « je » and does **not** address its reader: its reader
  is a leader assessing the author, and the few « tu » sentences it holds today are
  product sentences appended by releases, rewritten in the third person
  (« la personne », « l'utilisateur ») as they are folded in (designer's call; the
  §1/§4 voice sample is where the owner sees it first);
- bold marks a key term, never a sentence; no paragraph opens on an aphorism; no
  blockquote maxims;
- « X, jamais Y » / « pas X, mais Y » at most occasionally; no chiasms, no chains of
  em dashes, no reflex triplets, no « Et … » chains;
- no abstract nominal phrasing where a subject and a verb will do: say who does
  what (« LIA te montre le brouillon avant de l'envoyer », not « la validation
  humaine des actions sensibles »);
- consistent French vocabulary across both surfaces (`e-mail`, never `email` /
  `Emails`; the same name for the same feature as the app and `/why` use).

Landing-specific:

- **The headlines are the owner's and stay** (owner decision 2026-10-29): the short
  parallel taglines and section titles (« Ton quotidien. LIA garde le fil. Tu gardes
  la main. », « Reprends le fil. Prépare la suite. », « LIA n'a rien à cacher. »,
  « Et tout le reste, évidemment. »…) are kept as they are, « sauf si tu trouves de
  meilleures formulations ». A better one is never swapped in silently: it is
  proposed beside the original in the ledger and the review, and the owner picks.
  The anti-aphorism rules apply to body text, not to these headlines. In the five
  translations a headline is adapted to sound like a headline in that language, not
  translated word for word.
- **A caveat is a fact, said concretely.** « selon les sources autorisées »
  becomes what it means (« à partir de ce que tu as connecté »). Where a whole
  block depends on the same condition, it is stated once for the block (the
  existing `context.control` / `transparency.honest` lines are the natural place),
  not repeated in every card — but only inside the same visible block, never moved
  to a place the reader of that card would not see.
- **Jargon a visitor does not know is explained or replaced** (« HITL » outside a
  dashboard name → « confirmations »), unless the string is a technical card whose
  audience is an operator (`tech.*`, `platform.monitoring.*`), where the technical
  name stays.
- **UI strings keep their size class.** Titles, chips, badges, buttons, tab labels
  and aria labels stay within about +10 % of their current length; body text may
  grow or shrink freely. Interpolations (`{{count}}`…), embedded markup and array
  lengths are preserved exactly.

## The `/story` subtext

The page already argues that AI-assisted development is a management practice. The
rewrite makes the **author** visible as the person who chose to do the operational
work in order to decide better, without ever saying so:

- **Decisions told as decisions.** Each section shows choices a leader makes —
  scope, budget, risk, make-or-buy, what to accept as debt — and their reasons, in
  « je » (« J'ai voulu… », « J'ai choisi… parce que… », « J'ai appris à mes dépens
  que… »). Every reason is one the current text or the ADRs already state.
- **The fine detail is the evidence.** Keep one or two precise operational facts
  per section (the 4-to-8 cost gap, the confirmation that survives a restart, the
  wake word shipped as beta because it missed its own thresholds, a green test
  suite that proves nothing about a feature). Precision carried calmly is what
  shows command of the subject; no comment on it.
- **What was learned, and what changes in a decision.** The link from « I built
  it » to « this is how I decide now » stays where it already is (§7 Convictions,
  the closing lines of §3 and §6) and is written plainly.
- **Readable by a non-engineer leader.** A technical term gets a few words of
  explanation the first time, or is replaced.

Structure stays: seven `##` sections with their ids. The three `###` sub-sections of
§3 and the release-appended paragraphs of §1 and §5 are **folded** into the section
where their subject belongs (the World, Simli, the radio, SMS relay, proactive
discussions, peer sharing…): their facts stay, their headings may go. The long §4
paragraph is split by subject.

## The substance ledger

French first, before any rewriting:

- **`/story`**: one row per fact a reader could repeat (same definition as the
  why/how ledger), with the source section; after the draft, each row points to the
  sentence that now carries it. No row may end without a destination. A row may
  only be dropped as an exact duplicate of another row, recorded as such.
- **Landing**: one row per in-scope key: old French value, new French value, and
  the list of facts and caveats in the old value, each ticked in the new one. A fact
  may move to a sibling key only if both render in the same visible block.

The ledger is a working file under `.tmp/story-landing-rewrite/`, not a repository
document. It is what the owner checks a doubt against, and what the translations are
checked against.

**Accuracy is not silently changed.** The rewrite is form-only; where the builder
finds a statement the repository contradicts, the text keeps the statement and the
ledger flags it for the owner, with the evidence.

How far the check goes (designer's call): **every `/story` row is checked against
the repository** (a bounded step, ~150 rows, on the page whose argument is « measured,
not proclaimed »); on the landing, **every figure and every claim about what LIA
does or guarantees** is checked, the rest of the copy only as it is read. The flags
are presented with the French review (step 3); the owner's rulings are applied to
the French **before** the translations start, so the five languages are written
once. Three found while scoping:

- `/story` closing note: « Évaluation technique issue de l'audit de juillet 2026 »
  while §6 dates the latest evaluation (7,9/10) to 2026-10-25.
- `/story` §4: « Six niveaux de contrôle humain … jusqu'à la confirmation des
  opérations destructives » while `CLAUDE.md` (Key Patterns, HITL) states that the
  plan-approval level is auto-approved and the destructive-confirm level is emitted
  by no node.
- `/story` §5: « trente-deux tableaux de bord », written in words so no release
  guard reads it, while the Grafana count derived in `version_surfaces.py` is 33.

## Constraints

- **Values only.** No key added or removed; `editorial-content-coverage.test.ts`
  (exact partition of `REQUIRED_FEATURE_KEYS`) and the i18n parity gate stay green
  untouched.
- **The locale files are shared with uncommitted work in progress** (the why/how
  TOC labels, the blog, other lots). Edits are targeted text replacements of
  values, following the `lia-i18n` skill: never a load/dump rewrite of a whole file,
  scripts written to files (never heredocs), German/Chinese quotes from explicit
  constants, an integrity pass at the end (no empty quote pairs, array lengths,
  suspiciously short answers).
- **Release surfaces in `/story` keep their exact patterns**
  (`scripts/release/version_surfaces.py`): the two table rows
  `| Décisions d'architecture documentées (ADR) | **N** |` and
  `| Versions livrées à rythme régulier | **N** |` and the prose fragment
  « parmi les N documentées » in each language, and the `story.meta.description`
  fragment « tests, N ADRs, un audit technique » (per-language patterns in the
  same file). If a sentence carrying one is rewritten, the fragment stays verbatim;
  re-declaring a surface is a last resort and goes through the release tests.
- **No new exact counts.** Figures keep their current precision; counters on the
  landing come from `components/landing/constants.ts` and are not retyped in prose.
  `doc_facts` scans `apps/web/src/data/guides/*.md`.
- **`guides-structure.test.ts`**: `STORY_TOC_SECTIONS` ids unchanged; on-site links
  carry their locale prefix; GitHub links point at files that exist on `main`; the
  `Date` header stays equal across the 18 guide files (do not change it); the
  `/story` document `Version` goes from 2.6 to 3.0 in the six files.
- **Marketing-claim guard** (`test_self_host_marketing_claim_guard.py`): no
  « turnkey / one key / one endpoint / zero friction » or their translations.
- **Registers**: German « du », Spanish « tú », Italian « tu », Chinese « 你 », as in
  the app (ADR-323); French typography (no-break space before `; : ? !`) as the
  current French files already use it.
- **Drafts are staged outside the app** (`.tmp/story-landing-rewrite/`) and swapped
  in per language in one step, so the working tree never sits with red structure or
  parity tests.
- **Tests that pin literal copy**: if a component test asserts a French or English
  string that changes, its expected literal is updated to the new string; no
  assertion is removed or loosened.
- **No git actions** (owner rule).

## No relapse

- `/story` gains a length ceiling in `GUIDE_BUDGETS` (`guides-structure.test.ts`)
  at its measured rewritten size per language plus a small margin, shrink-only like
  the others.
- `.claude/skills/lia-release/SKILL.md` (Showcase surfaces): the rule written for
  `/why` and `/how` is extended to `/story`: a release changes at most a sentence
  of an existing section, never appends a paragraph.
- The landing has no length ceiling (its size is bound by its keys).

## Order of work

1. Inventory: the in-scope landing key set (from the code) and the orphan list; the
   `/story` ledger.
2. **Voice sample** → owner check: `/story` §1 and §4, and one landing block
   (hero + promise + context), in French.
3. Full French draft of `/story` and the landing, with the ledger; swapped into the
   French files only (keys unchanged, so every gate stays green) → owner review
   **on the running page** on Docker dev (`https://localhost:3000`), plus the ledger
   flags and the orphan list.
4. Translations into en, de, es, it, zh from the approved French, each checked
   against the ledger.
5. `/story` length ceiling, release-skill rule, verification.

## Verification

- `task lint:i18n`, `task lint:frontend`, `task lint:docs` (including `doc_facts`),
  `task test:frontend`, `task release:check` and the release-surface tests.
- Runtime proof on Docker dev: the home page with every disclosure opened and
  `/story`, in French, English and Chinese, light and dark, at phone width — no
  overflowing UI string, no raw key, no broken interpolation.

## Left to the builder

The exact wording; the ledger's file format; how the inventory is computed; how
the translation work is split; the budget margin.

Calls made by the designer (not decided by the owner): the scope boundary above
(orphans, `/more`, borrowed changelog and blog strings and `/demo`-only strings
excluded, shared `landing.cta.*` / `landing.meta.*` included); SEO strings in the
voice but keeping searched nouns; `/story` in « je » without addressing its reader;
the depth of the accuracy check and the rulings applied before translation; the
+10 % size rule for UI strings; folding the appended `/story` paragraphs and
removing the `###` sub-sections of §3; replacing the §3 blockquote maxim by a
sentence; the `/story` length ceiling and release rule; the review on the running
page; the document version 3.0.
