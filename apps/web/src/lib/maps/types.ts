/**
 * Types of the living maps (`/maps`).
 *
 * Two families of types live here. The DATA types mirror the files of
 * `src/data/maps/` — the language-neutral structure and the words of one
 * language — exactly as `scripts/audit/doc_maps.py` checks them. The VIEW types
 * are what the pages hand to their client components: one language, every
 * reference resolved, nothing left to join in the browser.
 */

/** The tones a family, a layer or a theme may wear (`doc_maps.TONES`). */
export const TONES = [
  'blue',
  'violet',
  'emerald',
  'amber',
  'rose',
  'cyan',
  'slate',
  'indigo',
  'orange',
  'teal',
  'fuchsia',
  'lime',
  'sky',
] as const;

export type Tone = (typeof TONES)[number];

/** The two maps made of building blocks. */
export type BrickMapKind = 'functional' | 'technical';

/** The three pages of the section, in their navigation order. */
export const MAP_PAGES = ['functional', 'technical', 'history'] as const;
export type MapPage = (typeof MAP_PAGES)[number];

// --------------------------------------------------------------------------- data

/** A family (functional) or a layer (technical), as the structure declares it. */
export interface FamilyStructure {
  id: string;
  icon: string;
  tone: string;
}

/** A journey: an ordered walk through the bricks of one map. */
export interface FlowStructure {
  id: string;
  icon: string;
  steps: string[];
}

export interface FunctionalBrickStructure {
  id: string;
  group: string;
  icon: string;
  domains?: string[];
  surfaces?: string[];
  deps: string[];
}

export interface TechnicalBrickStructure {
  id: string;
  layer: string;
  icon: string;
  paths?: string[];
  domains?: string[];
  infra?: string[];
  deps: string[];
}

export interface FunctionalStructure {
  groups: FamilyStructure[];
  bricks: FunctionalBrickStructure[];
  flows: FlowStructure[];
}

export interface TechnicalStructure {
  repo: string;
  layers: FamilyStructure[];
  bricks: TechnicalBrickStructure[];
  flows: FlowStructure[];
}

export interface EraStructure {
  id: string;
  from: string;
  to: string | null;
}

export interface EntryStructure {
  adr: number;
  date: string;
  theme: string;
  functional: string[];
  technical: string[];
  nofile?: string;
}

export interface HistoryStructure {
  themes: FamilyStructure[];
  eras: EraStructure[];
  entries: EntryStructure[];
}

/** Every translated unit may carry the fingerprint of the French it translates. */
interface Stamped {
  src?: string;
}

export interface NamedText extends Stamped {
  name: string;
  summary: string;
}

export interface FlowText extends NamedText {
  steps: string[];
}

export interface IntroText extends Stamped {
  lede: string;
}

export interface FunctionalText {
  intro: IntroText;
  groups: Record<string, NamedText>;
  bricks: Record<string, Stamped & { name: string; role: string; goal: string }>;
  flows: Record<string, FlowText>;
}

export interface TechnicalText {
  intro: IntroText;
  layers: Record<string, NamedText>;
  bricks: Record<string, Stamped & { name: string; role: string; stack: string[] }>;
  flows: Record<string, FlowText>;
}

export interface HistoryText {
  intro: IntroText;
  themes: Record<string, NamedText>;
  eras: Record<string, NamedText>;
  entries: Record<string, Stamped & { title: string; summary: string }>;
}

/** The words of the three maps in one language. */
export interface MapsText {
  functional: FunctionalText;
  technical: TechnicalText;
  history: HistoryText;
}

/** `facts.json` — generated from the tree by `doc_maps.py`, never typed by hand. */
export interface MapsFactsData {
  version: string;
  releaseDate: string;
  releases: number;
  milestones: ReleaseView[];
  domains: number;
  infra: number;
  /** ADR number (as a string) → file name under `docs/architecture/`. */
  adrFiles: Record<string, string>;
}

/** Everything one language of the maps is made of. */
export interface MapsData {
  functional: FunctionalStructure;
  technical: TechnicalStructure;
  history: HistoryStructure;
  text: MapsText;
  facts: MapsFactsData;
}

// --------------------------------------------------------------------------- views

/** A building block as a chip draws it — enough to name it and link to it. */
export interface BrickRef {
  id: string;
  kind: BrickMapKind;
  name: string;
  icon: string;
  tone: Tone;
}

/** A family or a layer, with the number of bricks it holds. */
export interface FamilyView {
  id: string;
  name: string;
  summary: string;
  icon: string;
  tone: Tone;
  count: number;
}

export interface FlowStepView {
  brick: string;
  text: string;
}

export interface FlowView {
  id: string;
  name: string;
  summary: string;
  icon: string;
  steps: FlowStepView[];
}

/** A decision as a brick's detail lists it. */
export interface DecisionRef {
  adr: number;
  title: string;
  date: string;
  tone: Tone;
}

/** One building block, every reference it makes already resolved. */
export interface BrickView {
  id: string;
  kind: BrickMapKind;
  family: string;
  name: string;
  icon: string;
  tone: Tone;
  role: string;
  /** The functional map states a goal; the technical map does not. */
  goal: string | null;
  /** Technologies (technical map only). */
  stack: string[];
  deps: string[];
  usedBy: string[];
  /** Journeys of the same map this brick takes part in. */
  flows: string[];
  domains: string[];
  surfaces: string[];
  paths: string[];
  /** Bricks of the OTHER map the same decisions shaped, most shared first. */
  related: string[];
  /** The most recent decisions that shaped it (at most `DRAWER_DECISIONS`). */
  decisions: DecisionRef[];
  /** How many decisions shaped it in total. */
  decisionCount: number;
}

/** The counts a page quotes, computed from the tree (`facts.json`). */
export interface MapsFacts {
  version: string;
  releaseDate: string;
  releases: number;
  domains: number;
  infra: number;
  decisions: number;
}

/** The functional or the technical map, in one language. */
export interface BrickMapView {
  kind: BrickMapKind;
  lede: string;
  families: FamilyView[];
  bricks: BrickView[];
  flows: FlowView[];
  /** Every brick of both maps, for the chips that cross from one to the other. */
  refs: Record<string, BrickRef>;
  repo: string;
  facts: MapsFacts;
}

export interface ThemeView {
  id: string;
  name: string;
  summary: string;
  icon: string;
  tone: Tone;
  count: number;
}

export interface EraView {
  id: string;
  name: string;
  summary: string;
  from: string;
  to: string | null;
}

export interface DecisionView {
  adr: number;
  date: string;
  theme: string;
  title: string;
  summary: string;
  /** The bricks it shaped: functional first, then technical. */
  bricks: string[];
  /** Its file under `docs/architecture/`, or null when it has none (ADR-008). */
  file: string | null;
}

export interface ReleaseView {
  version: string;
  date: string;
}

/** The decision history, in one language. */
export interface HistoryView {
  lede: string;
  themes: ThemeView[];
  eras: EraView[];
  decisions: DecisionView[];
  /** The milestone releases the timeline interleaves with the decisions. */
  releases: ReleaseView[];
  refs: Record<string, BrickRef>;
  repo: string;
  facts: MapsFacts;
}

/** What the section's home page shows about each map. */
export interface MapsSummary {
  lede: Record<MapPage, string>;
  facts: MapsFacts;
  functional: { bricks: number; families: number; flows: number };
  technical: { bricks: number; layers: number; flows: number };
  history: { decisions: number; themes: number; eras: number };
}
