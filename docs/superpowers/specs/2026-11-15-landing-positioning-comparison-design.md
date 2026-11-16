# Landing: positioning, five arguments and a comparison table

**Date**: 2026-11-15 · **Status**: approved by the owner on 2026-11-15 (decisions below) · **Source**: the owner's
`lia-comparatif-v5-v3.html` and the text of the request.

## Intent

The home page states where LIA stands before it shows how it works: the market is split between developer agent
harnesses (OpenClaw, Hermes Agent) and closed consumer assistants (Meta's Muse); LIA claims the ground between them.
The owner supplied the words; the page gives them the landing's form, in the six languages.

## Owner decisions (2026-11-15)

1. The functional constellation leaves the HOME page only. The living map keeps it (`/maps`, `FunctionalMap`).
2. The supplied text moves to the landing's voice: `tu`, never `vous`.
3. Claims about LIA follow the code, or stay deliberately general: GDPR tooling rather than "strict compliance",
   the two real-time voice modes are Live direct and Live delegated, skills that LIA writes are installed on the
   person's click, SMS are archived (LIA sends none), no "zero latency" (no model wait instead).
4. "60+ bricks" stays written as is, so that 61 or 62 bricks need no edit. A test keeps the floor true.
5. Competitor cells must not lie: each is rewritten from the competitor's official pages, read during this work,
   with the sources and the reading date stated under the table.
6. The humour about public companies and public figures stays (archetype cards, quotes, punchlines): the owner
   judges it harmless. It must still not assert a falsehood.
7. The table takes the landing's charter (cosmos skin, theme colour, Lucide icons), not the file's amber and emoji.

## Goals, non-goals, anti-goals

- Goals: hero → positioning → video → five argument tiles → comparison → gallery; six locales; keyboard and
  screen-reader use of the comparison; no horizontal page scroll at 320 px.
- Non-goals: the file's theme, language and slide toggles (the site has its own), its "face-à-face" cards and its
  four bottom pillars (they repeat the five tiles), its brick modal (the living map already is that explorer).
- Anti-goals: a claim the code or the competitor's documentation contradicts; a second, hand-copied list of bricks;
  a version number on a showcase surface.

## Approaches considered

- **Port the HTML as an island** (its CSS and script inside a component): fastest, but a second design system,
  emoji chrome, untranslatable strings and a hand-copied brick list. Rejected.
- **CSS-only toggles on a server table**: no client JavaScript, but the duel filter and the reading modes need
  state that radio-hack CSS cannot announce to assistive technology. Rejected.
- **Typed data + locale keys + one client explorer** (chosen): criteria, contenders, statuses and brick ids live in
  one language-neutral module; every word lives in the locales; a server section resolves brick names from the
  living map's data (server-only) and hands them to one client component that owns the filters.

## Design

- `CosmosHero` loses `LandingConstellation` and the maps frame; the component, its unit test, its CSS rules and
  the e2e journey that exercised it on the home page are deleted. The scroll hint points at the positioning section.
- `PositioningSection` (server), between the hero and the video: two narrative paragraphs and the thesis card.
- `ArgumentsSection` (server), after the video: a heading, five tiles (Lucide icon each, the fifth spanning two
  columns), then `ComparisonExplorer` (client): view filter (all, or one duel), reading mode (full, technical,
  punchlines), contender cards, a semantic table that stacks into cards on narrow screens, a ✓ / ~ / ✕ status with
  a text label, LIA's bricks linked to `/maps/functional#<id>` under LIA's cells, sources and reading date below.
- Data: `comparison-data.ts` (criteria, contenders, statuses, brick ids, bullet counts, reading date). Locale keys
  under `landing.positioning`, `landing.arguments` and `landing.comparison`.
- Guards: every referenced brick id exists in the living map; every referenced locale key exists in the six
  locales; the "60+" floor of each locale is at most the living map's brick count.

## Owner revisions after the first look (2026-11-15)

- Duels only: LIA faces OpenClaw (default), Hermes Agent or Meta Muse; the four-column table was unreadable.
  The duel bar reads « LIA face à » with short names, the reading bar one word per choice, both on one line
  down to 320 px.
- No brick links in the table (« inutile, surcharge »): `bricks.ts` became `brick-floor.ts`, the floor alone.
- The products' real marks (`public/comparison-icons/`, NOTICE.md), on a white chip whatever the theme.
- Positioning tiles stacked; argument tiles without numbers, the last two sharing the second row equally.
- The home page's titles AND texts take their section's full width (27 width caps removed in 17 files, chapter
  titles above both columns), and one type scale across the page (`mobile:text-4xl` section titles, base-size
  ledes): a landing-wide change the owner asked for.
- The hero keeps its tagline alone (the free/paid sentence and its key `landing.hero.home_value` left).

## Owner revisions after the arena (2026-11-15)

- The arena replaced the « basique » look (approved « ok »): challenger tiles, a stage with « VS », the
  positioning's market bands with the products' marks and a thesis framed beside its « 60+ », one vignette per
  argument tile.
- « Lecture » is useless: everything is shown. The reading filter and the per-criterion « Voir / Masquer les
  faits » folds are gone with their six keys; status, head line, punchline and facts are always displayed, and
  the three challenger tiles are the only controls.
- The positioning title is centred, under the hero's centred tagline.
- Optimised without degrading (« taille, mémoire, cpu ») : the criteria are ONE structure at every width (the
  table and the stacked list rendered every sentence twice: comparison 1 054 → 526 elements, 50 → 20 icons,
  everything now shown); the pitch's words leave every page's payload but the home's comparison
  (`i18n/scoped-translations.ts`); the Hermes mark is a lossless palette PNG (8 684 → 6 912 bytes). The
  argument tiles keep the charter's glass (`cosmos-glass`), shared with the page's other cards.

- Then « ok pour toutes » for the three follow-ups: the four engineering principles as tiles; ONE
  forced-colours media query and listener for every facade icon (home page: 1 985 → 1 454 JS listeners); the
  `landing` subtree off the pages that never read it in the browser (server-only subtrees shipped nowhere,
  the home page's own scoped on its route; RSC payload: home −17 %, FAQ −22 %, blog −35 %).

## Left to the builder

Exact class names, icon choices, tile and table spacing, and the stacked layout's breakpoint, judged in the browser
against the neighbouring sections in both themes.
