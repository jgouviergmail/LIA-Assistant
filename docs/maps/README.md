# Living maps

Three maps that explain LIA to someone who has never opened the code — and that
cannot silently stop being true.

| Map | What it answers |
|---|---|
| Functional map | What LIA does: every functional brick grouped in families, its role, its goal, what it relies on, what relies on it, and nine commented journeys (a request becoming an action, a ReAct question, LIA taking the initiative, a live voice session…). |
| Technical map | How LIA is built: ten layers from the screen to the database, each brick with its stack, its paths in this repository and its dependencies, and six technical journeys (a chat message, a model call, a background job, a live session, a delivery, an incident). |
| Decision history | Why LIA is the way it is: every architecture decision told in a few plain sentences, filed under one of twelve themes, grouped in chapters, placed among the releases, and linked to the bricks it shaped. |

They are published twice, from ONE set of data:

- **On the public site**, in the six languages of the site and in the one the
  reader chose: the "Maps" section of the site header opens `/maps`, the home of
  the section, then `/maps/functional`, `/maps/technical` and `/maps/history`
  (React components in `apps/web/src/components/maps/`, pages in
  `apps/web/src/app/[lng]/maps/`).
- **Here, as three self-contained French documents** —
  [functional-map.html](functional-map.html),
  [technical-map.html](technical-map.html) and
  [adr-history.html](adr-history.html) — offline presentation material that
  needs nothing but a browser.

Both are interactive (search, focus, animated journeys, filters, deep links such
as `#f.memory` on a map or `#adr-305` on the history) and follow the reader's
light or dark theme.

## Where the content lives

Everything is **generated or checked** from the data. Never edit an `.html` file
by hand. The data lives with the web application, because the web container
sees nothing else of the repository:

| Path | Holds |
|---|---|
| `apps/web/src/data/maps/functional.json` | The STRUCTURE of the functional map: families, bricks (icon, backend domains, screens, dependencies), journeys (the bricks they cross). |
| `apps/web/src/data/maps/technical.json` | The structure of the technical map: layers, bricks (repository paths, backend domains, infrastructure modules, dependencies), journeys. |
| `apps/web/src/data/maps/history.json` | The twelve themes, the chapters, and one entry per ADR (date, theme, the bricks it shaped). |
| `apps/web/src/data/maps/text/<map>.<lang>.json` | The WORDS, one file per map and language: names, roles, goals, stacks, journey steps, theme and chapter names, and each decision's title and plain summary. French (`fr`) is the source. |
| `apps/web/src/data/maps/facts.json` | GENERATED: the version, the release date and milestones, the counts (backend domains, infrastructure modules) and the file of every ADR — computed from the tree, never typed. |
| `templates/` | The French documents' skeleton, stylesheet, script, LIA mark and vendored Lucide icons (`icons.json`). |

`scripts/audit/doc_maps.py` checks the data against the tree, writes
`facts.json`, and renders the three French documents.

## Keeping them true

`task lint:docs` runs the same script as a gate, and fails when:

- an ADR file has no history entry, or an entry names neither a file nor, in
  `nofile`, the reason it has none;
- a backend domain (`apps/api/src/domains/*`) or an infrastructure module
  (`apps/api/src/infrastructure/*`) is claimed by no brick, or a brick claims one
  that no longer exists;
- a repository path a technical brick points at, or a screen a functional brick
  names, does not exist;
- a reference between bricks, families, layers, themes, chapters and journeys
  does not resolve, or an icon of the documents is not vendored;
- a unit of text is missing from one of the six languages, or names nothing in
  the structure;
- a translation is **stale**: every non-French unit carries `src`, the
  fingerprint of the French it translates, and a French sentence that changed no
  longer matches it;
- a translation is the French sentence copied as is;
- `facts.json` or a document is not exactly what the data renders.

So the rule for every commit is short:

1. A new ADR gets its entry in `history.json` (date, theme, the bricks it
   shaped) and its words in the six `text/history.<lang>.json` — a title and two
   or three plain sentences, the French first.
2. A new backend domain or infrastructure module is claimed by the brick it
   belongs to (or a new brick, with its role and its dependencies, in the six
   languages).
3. Run `task docs:maps`: it stamps the fingerprint of every unit translated for
   the first time, rewrites `facts.json` and the French documents. Commit
   everything.

When a French sentence changes, its translations become stale and the gate names
them. Translate them again, then accept them explicitly — a stale fingerprint is
never refreshed implicitly:

```bash
python scripts/audit/doc_maps.py --restamp history/entries/263 functional/bricks/f.memory
```

`task docs:maps` also re-vendors the documents' icons when the data names a new
one (`--refresh-icons`, which reads `apps/web/node_modules`); the site draws the
same Lucide icons through `components/maps/map-icons.tsx`, whose test fails on
an icon it does not know. `release:bump` and `release:sync-counts` run
`task docs:maps` themselves, because a release moves the version stamp and the
release milestones.
