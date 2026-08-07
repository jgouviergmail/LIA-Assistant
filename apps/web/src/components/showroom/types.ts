/**
 * Bounded contracts for the multi-mission guided showroom.
 *
 * Everything here is a closed union or a small counter: the mission state
 * machine stores no free text, no timestamps, no identifiers — only enum
 * values and bounded integers. The email-edit draft text lives transiently in
 * the view layer and never enters this state (honesty + privacy contract of
 * the public-web-showroom program).
 *
 * Mission DEFINITIONS are pure static data (deep-frozen, i18n keys + bounded
 * 'HH:MM' literals) mirrored by the backend `SHOWROOM_MISSION_IDS` registry —
 * both sides are guarded so a mission cannot exist without its two bounded
 * per-mission funnel events.
 */

import type { ShowroomMissionId } from '@/lib/product-telemetry';

export type { ShowroomMissionId };

/** Mission phases, in canonical order. `decision` covers 1..N HITL steps. */
export type ShowroomPhase = 'ready' | 'reading_sources' | 'planning' | 'decision' | 'receipt';

/** Visitor decision kinds (drafts support all three; tools have no edit). */
export type ShowroomDecisionKind = 'confirm' | 'edit' | 'cancel';

/** Deterministic mission state — a small, serializable, bounded object. */
export interface ShowroomState {
  phase: ShowroomPhase;
  /** Increments on each explicit START — drives per-run event semantics. */
  runId: number;
  /** 0..sources.length progressive reveal inside reading_sources. */
  sourcesRead: number;
  /** Index of the pending decision — meaningful only while phase==='decision'. */
  decisionIndex: number;
  /** One bounded slot per mission decision, filled strictly in order. */
  decisions: readonly (ShowroomDecisionKind | null)[];
}

/** Discriminated mission events. DECIDE carries NO text payload by design. */
export type ShowroomEvent =
  | { type: 'START' }
  | { type: 'ADVANCE' }
  | { type: 'DECIDE'; index: number; decision: ShowroomDecisionKind }
  | { type: 'RESTART' };

// ---------------------------------------------------------------------------
// Mission definition (pure static data — guarded by fixtures.test.ts)
// ---------------------------------------------------------------------------

export interface ShowroomSourceItem {
  /** i18n key describing the fact. */
  labelKey: string;
  /** Optional bounded time literal shown next to the label. */
  time?: string;
  /** Optional second time literal (ranges). */
  endTime?: string;
}

export interface ShowroomSource {
  /** Bounded slug — used only as a React key. */
  id: string;
  labelKey: string;
  emoji: string;
  items: readonly ShowroomSourceItem[];
}

/** A planning finding (conflict, applied preference, risk) + bounded times. */
export interface ShowroomFinding {
  labelKey: string;
  time?: string;
  endTime?: string;
}

/** Bounded icon slugs a decision/receipt row may reference. */
export type ShowroomDecisionIcon = 'mail' | 'calendar' | 'phone' | 'bell' | 'settings' | 'task';

interface ShowroomDecisionBase {
  /** Bounded per-mission slug (React keys + synthetic message ids). */
  id: string;
  /** Decision kinds the reducer accepts for this step. */
  allowed: readonly ShowroomDecisionKind[];
  /** Announced/displayed while this decision is pending. */
  phaseLabelKey: string;
  /** Short receipt row label (dt) for this decision. */
  receiptLabelKey: string;
  icon: ShowroomDecisionIcon;
  /** Receipt line per outcome (edit falls back to confirm when absent). */
  outcome: {
    confirm: string;
    edit?: string;
    cancel: string;
  };
}

/** Email-like draft — renders as the chat draft_critique card. */
export interface ShowroomDraftDecision extends ShowroomDecisionBase {
  kind: 'draft';
  /** Always an example.invalid address (fixture guard). */
  to: string;
  subjectKey: string;
  bodyKey: string;
}

/** One bounded tool argument row: literal value OR i18n-resolved value. */
export interface ShowroomToolArg {
  labelKey: string;
  value?: string;
  valueKey?: string;
}

/** Bounded action — renders as the chat tool_confirmation card. */
export interface ShowroomToolDecision extends ShowroomDecisionBase {
  kind: 'tool';
  toolNameKey: string;
  args: readonly ShowroomToolArg[];
}

export type ShowroomDecisionSpec = ShowroomDraftDecision | ShowroomToolDecision;

/** A complete synthetic mission — versioned, immutable, i18n-key-driven. */
export interface ShowroomMissionDefinition {
  id: ShowroomMissionId;
  fixtureVersion: `${ShowroomMissionId}-v${number}`;
  /** Picker card title. */
  titleKey: string;
  /** Picker card one-liner. */
  taglineKey: string;
  /** The differentiating mechanism this mission demonstrates (picker badge). */
  mechanismKey: string;
  /** Canonical visitor request — or the proactive trigger line. */
  requestKey: string;
  /** True when LIA initiates (request renders as a notification, not a quote). */
  proactive: boolean;
  sources: readonly ShowroomSource[];
  findings: readonly ShowroomFinding[];
  /** Four storyboard trace step labels (routing/sources/planning/proposals). */
  traceKeys: readonly [string, string, string, string];
  /** 1..N HITL decisions, decided strictly in order. */
  decisions: readonly ShowroomDecisionSpec[];
  /** Receipt header lines (what was read / what was proposed). */
  receipt: { readsKey: string; proposedKey: string };
  /**
   * The pedagogical demo note shown BESIDE LIA's reply, never inside it:
   * the reply keeps the assistant's task voice, the note explains the
   * mechanism demonstrated and where it lives in the product.
   */
  noteKey: string;
}
