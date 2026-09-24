/**
 * Pure builders of the living maps' views.
 *
 * The pages read `MapsData` (structure + one language + facts) and hand their
 * client components a VIEW in which every reference is resolved: a chip knows
 * its name and tone, a brick knows who depends on it and which decisions shaped
 * it. Nothing here touches the filesystem, so every rule is unit-testable on a
 * synthetic `MapsData`.
 */

import {
  TONES,
  type BrickMapKind,
  type BrickMapView,
  type BrickRef,
  type BrickView,
  type DecisionRef,
  type FamilyStructure,
  type FamilyView,
  type FlowStructure,
  type FlowText,
  type FlowView,
  type HistoryView,
  type MapPage,
  type MapsData,
  type MapsFacts,
  type MapsSummary,
  type NamedText,
  type Tone,
} from './types';

/** How many decisions a brick's detail lists before pointing at the history. */
export const DRAWER_DECISIONS = 10;

/** How many bricks of the other map a brick's detail relates it to. */
export const RELATED_BRICKS = 6;

/** A tone read from the data, refused when the vocabulary does not know it. */
export function asTone(value: string): Tone {
  if ((TONES as readonly string[]).includes(value)) return value as Tone;
  throw new Error(`maps: unknown tone ${JSON.stringify(value)}`);
}

/** The text of a unit, refused when the language lacks it (the guard should have). */
function textOf<T>(units: Record<string, T>, id: string, where: string): T {
  const unit = units[id];
  if (unit === undefined) throw new Error(`maps: ${where} has no text for ${id}`);
  return unit;
}

/** The map a brick id belongs to. */
export function kindOf(id: string): BrickMapKind {
  return id.startsWith('t.') ? 'technical' : 'functional';
}

/** Counts the pages quote, all computed from the tree by `doc_maps.py`. */
export function factsOf(data: MapsData): MapsFacts {
  return {
    version: data.facts.version,
    releaseDate: data.facts.releaseDate,
    releases: data.facts.releases,
    domains: data.facts.domains,
    infra: data.facts.infra,
    decisions: data.history.entries.length,
  };
}

/** Every brick of both maps, as a chip names it. */
export function brickRefs(data: MapsData): Record<string, BrickRef> {
  const refs: Record<string, BrickRef> = {};
  const groupTone = new Map(data.functional.groups.map(g => [g.id, asTone(g.tone)]));
  const layerTone = new Map(data.technical.layers.map(l => [l.id, asTone(l.tone)]));
  for (const b of data.functional.bricks) {
    refs[b.id] = {
      id: b.id,
      kind: 'functional',
      name: textOf(data.text.functional.bricks, b.id, 'functional').name,
      icon: b.icon,
      tone: groupTone.get(b.group) ?? 'slate',
    };
  }
  for (const b of data.technical.bricks) {
    refs[b.id] = {
      id: b.id,
      kind: 'technical',
      name: textOf(data.text.technical.bricks, b.id, 'technical').name,
      icon: b.icon,
      tone: layerTone.get(b.layer) ?? 'slate',
    };
  }
  return refs;
}

function familyViews(
  families: FamilyStructure[],
  text: Record<string, NamedText>,
  memberCount: (id: string) => number,
  where: string
): FamilyView[] {
  return families.map(f => {
    const unit = textOf(text, f.id, where);
    return {
      id: f.id,
      name: unit.name,
      summary: unit.summary,
      icon: f.icon,
      tone: asTone(f.tone),
      count: memberCount(f.id),
    };
  });
}

function flowViews(
  flows: FlowStructure[],
  text: Record<string, FlowText>,
  where: string
): FlowView[] {
  return flows.map(f => {
    const unit = textOf(text, f.id, where);
    return {
      id: f.id,
      name: unit.name,
      summary: unit.summary,
      icon: f.icon,
      steps: f.steps.map((brick, i) => ({ brick, text: unit.steps[i] ?? '' })),
    };
  });
}

/** Who depends on each brick — the reverse of every `deps` list of one map. */
export function reverseDeps(
  bricks: ReadonlyArray<{ id: string; deps: string[] }>
): Map<string, string[]> {
  const out = new Map<string, string[]>(bricks.map(b => [b.id, []]));
  for (const b of bricks) {
    for (const d of b.deps) out.get(d)?.push(b.id);
  }
  return out;
}

/** The decisions that shaped each brick, newest first. */
export function decisionsByBrick(data: MapsData): Map<string, DecisionRef[]> {
  const themeTone = new Map(data.history.themes.map(t => [t.id, asTone(t.tone)]));
  const out = new Map<string, DecisionRef[]>();
  for (const e of data.history.entries) {
    const ref: DecisionRef = {
      adr: e.adr,
      title: textOf(data.text.history.entries, String(e.adr), 'history').title,
      date: e.date,
      tone: themeTone.get(e.theme) ?? 'slate',
    };
    for (const id of [...e.functional, ...e.technical]) {
      const list = out.get(id) ?? [];
      list.push(ref);
      out.set(id, list);
    }
  }
  for (const list of out.values()) list.sort((a, b) => b.adr - a.adr);
  return out;
}

/**
 * Bricks of the OTHER map that the same decisions shaped, most shared first —
 * the bridge from what LIA does to how it is built, and back.
 */
export function relatedBricks(data: MapsData, id: string): string[] {
  const other = kindOf(id) === 'functional' ? 'technical' : 'functional';
  const counts = new Map<string, number>();
  for (const e of data.history.entries) {
    if (!e.functional.includes(id) && !e.technical.includes(id)) continue;
    for (const o of e[other]) counts.set(o, (counts.get(o) ?? 0) + 1);
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, RELATED_BRICKS)
    .map(([o]) => o);
}

interface BrickSource {
  id: string;
  family: string;
  icon: string;
  deps: string[];
  name: string;
  role: string;
  goal: string | null;
  stack: string[];
  domains: string[];
  surfaces: string[];
  paths: string[];
}

function brickSources(data: MapsData, kind: BrickMapKind): BrickSource[] {
  if (kind === 'functional') {
    return data.functional.bricks.map(b => {
      const unit = textOf(data.text.functional.bricks, b.id, 'functional');
      return {
        id: b.id,
        family: b.group,
        icon: b.icon,
        deps: b.deps,
        name: unit.name,
        role: unit.role,
        goal: unit.goal,
        stack: [],
        domains: b.domains ?? [],
        surfaces: b.surfaces ?? [],
        paths: [],
      };
    });
  }
  return data.technical.bricks.map(b => {
    const unit = textOf(data.text.technical.bricks, b.id, 'technical');
    return {
      id: b.id,
      family: b.layer,
      icon: b.icon,
      deps: b.deps,
      name: unit.name,
      role: unit.role,
      goal: null,
      stack: unit.stack,
      domains: b.domains ?? [],
      surfaces: [],
      paths: b.paths ?? [],
    };
  });
}

/** The functional or the technical map, every reference resolved, in one language. */
export function buildBrickMap(data: MapsData, kind: BrickMapKind): BrickMapView {
  const sources = brickSources(data, kind);
  const structure = kind === 'functional' ? data.functional : data.technical;
  const families = kind === 'functional' ? data.functional.groups : data.technical.layers;
  const familyText =
    kind === 'functional' ? data.text.functional.groups : data.text.technical.layers;
  const flows = flowViews(structure.flows, data.text[kind].flows, kind);
  const usedBy = reverseDeps(sources);
  const decisions = decisionsByBrick(data);
  const familyViewsList = familyViews(
    families,
    familyText,
    id => sources.filter(s => s.family === id).length,
    kind
  );
  const toneOfFamily = new Map(familyViewsList.map(f => [f.id, f.tone]));

  const bricks: BrickView[] = sources.map(s => {
    const shaped = decisions.get(s.id) ?? [];
    return {
      ...s,
      kind,
      tone: toneOfFamily.get(s.family) ?? 'slate',
      usedBy: usedBy.get(s.id) ?? [],
      flows: flows.filter(f => f.steps.some(step => step.brick === s.id)).map(f => f.id),
      related: relatedBricks(data, s.id),
      decisions: shaped.slice(0, DRAWER_DECISIONS),
      decisionCount: shaped.length,
    };
  });

  return {
    kind,
    lede: data.text[kind].intro.lede,
    families: familyViewsList,
    bricks,
    flows,
    refs: brickRefs(data),
    repo: data.technical.repo,
    facts: factsOf(data),
  };
}

/** The decision history, every reference resolved, in one language. */
export function buildHistory(data: MapsData): HistoryView {
  const { history, text } = data;
  return {
    lede: text.history.intro.lede,
    themes: familyViews(
      history.themes,
      text.history.themes,
      id => history.entries.filter(e => e.theme === id).length,
      'history'
    ),
    eras: history.eras.map(era => {
      const unit = textOf(text.history.eras, era.id, 'history');
      return { id: era.id, name: unit.name, summary: unit.summary, from: era.from, to: era.to };
    }),
    decisions: history.entries.map(e => {
      const unit = textOf(text.history.entries, String(e.adr), 'history');
      return {
        adr: e.adr,
        date: e.date,
        theme: e.theme,
        title: unit.title,
        summary: unit.summary,
        bricks: [...e.functional, ...e.technical],
        file: data.facts.adrFiles[String(e.adr)] ?? null,
      };
    }),
    releases: data.facts.milestones,
    refs: brickRefs(data),
    repo: data.technical.repo,
    facts: factsOf(data),
  };
}

/** What the section's home page shows about the three maps. */
export function buildSummary(data: MapsData): MapsSummary {
  const lede: Record<MapPage, string> = {
    functional: data.text.functional.intro.lede,
    technical: data.text.technical.intro.lede,
    history: data.text.history.intro.lede,
  };
  return {
    lede,
    facts: factsOf(data),
    functional: {
      bricks: data.functional.bricks.length,
      families: data.functional.groups.length,
      flows: data.functional.flows.length,
    },
    technical: {
      bricks: data.technical.bricks.length,
      layers: data.technical.layers.length,
      flows: data.technical.flows.length,
    },
    history: {
      decisions: data.history.entries.length,
      themes: data.history.themes.length,
      eras: data.history.eras.length,
    },
  };
}
