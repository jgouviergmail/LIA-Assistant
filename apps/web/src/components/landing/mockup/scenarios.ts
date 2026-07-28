/**
 * Timeline data for the animated hero conversation (InteractiveChatMockup).
 *
 * Four acts, each proving several real product strengths at once:
 *  1. orchestrate — one sentence fans out to parallel agents, memory resolves
 *     "my wife", the HITL gate holds the flow until approval (amber bubble),
 *     double cross-domain success with the per-message token/cost footer.
 *  2. anticipate — weather card, then LIA crosses agenda × forecast on its own
 *     and the initiative completes into a real event card.
 *  3. call — agentic telephony (ADR-127): approval first, then the flow leaves
 *     the frame to place a real phone call; written summary card at the end.
 *  4. create — a skill mini-app is generated from a voice request and runs
 *     inside the chat (interactive hydration widget).
 *
 * While LIA "thinks", a glass overlay (the backstage) reveals the actual
 * orchestration instead of dead waiting time — see Backstage.tsx.
 *
 * Pacing: reading time rules. The glass holds 7–8.5 s per act and every
 * explanatory note stays on screen at least ~4.5 s; resolution bubbles get
 * ~3 s before the next beat. Prefer a longer loop over an unreadable one.
 *
 * All user-visible strings live in `landing.chat_mockup.*` (6 locales); this
 * module only holds identifiers, timings and numbers.
 */

export type ScenarioId = 'orchestrate' | 'anticipate' | 'call' | 'create';

export interface TimelineStep {
  /** Milestone identifier consumed by the act renderers. */
  kind: string;
  /** Reveal time, in ms from scenario start. */
  at: number;
}

/** Conversation-level counters shown in the token bar (fresh per act). */
export interface TokenbarState {
  totalTokens: number;
  messages: number;
  costEur: number;
}

/** Per-response footer, mirroring the real ChatMessage token/cost line. */
export interface MessageFooter {
  time: string;
  tokensIn: number;
  tokensOut: number;
  costEur: number;
}

export interface Scenario {
  id: ScenarioId;
  /** i18n suffix (under `landing.chat_mockup.`) of the benefit chip. */
  chipKey: string;
  /** i18n suffix of the user message typed into the input bar. */
  userKey: string;
  /** Dictated by voice: the mic pulses while the transcription types in. */
  voice?: boolean;
  steps: TimelineStep[];
  /** Scenario display time before the cross-fade to the next act. */
  holdMs: number;
  /** Token bar flips from `start` to `end` when `tickAt` is reached. */
  tokenbar: { start: TokenbarState; end: TokenbarState; tickAt: string };
  /**
   * [from, to) step-kind windows during which the send button shows Stop
   * (a HITL interrupt ends the stream, approval starts a new one — ADR-117).
   */
  streamWindows: [string, string][];
}

/** A brand-new conversation: the token bar honestly starts at zero. */
const FRESH: TokenbarState = { totalTokens: 0, messages: 0, costEur: 0 };

export const SCENARIOS: Scenario[] = [
  {
    id: 'orchestrate',
    chipKey: 's1_chip',
    userKey: 's1_user',
    steps: [
      { kind: 'type', at: 300 },
      { kind: 'user', at: 1500 },
      { kind: 'wait', at: 2100 },
      { kind: 'bs', at: 3300 },
      { kind: 'bs_c1', at: 4600 },
      { kind: 'bs_c2', at: 5900 },
      { kind: 'bs_gate', at: 7200 },
      { kind: 'bs_end', at: 11800 },
      { kind: 'hitl', at: 12100 },
      { kind: 'approve', at: 15300 },
      { kind: 'done', at: 16600 },
    ],
    holdMs: 20600,
    tokenbar: {
      start: FRESH,
      end: { totalTokens: 1450, messages: 4, costEur: 0.003 },
      tickAt: 'done',
    },
    streamWindows: [
      ['user', 'hitl'],
      ['approve', 'done'],
    ],
  },
  {
    id: 'anticipate',
    chipKey: 's2_chip',
    userKey: 's2_user',
    steps: [
      { kind: 'type', at: 300 },
      { kind: 'user', at: 1500 },
      { kind: 'bs', at: 2600 },
      { kind: 'bs_c1', at: 3900 },
      { kind: 'bs_wire', at: 5100 },
      { kind: 'bs_spark', at: 6100 },
      { kind: 'bs_end', at: 10600 },
      { kind: 'weather', at: 10900 },
      { kind: 'initiative', at: 12900 },
      { kind: 'approve', at: 16100 },
      { kind: 'done', at: 17400 },
    ],
    holdMs: 21400,
    tokenbar: {
      start: FRESH,
      end: { totalTokens: 1035, messages: 4, costEur: 0.002 },
      tickAt: 'done',
    },
    streamWindows: [
      ['user', 'weather'],
      ['approve', 'done'],
    ],
  },
  {
    id: 'call',
    chipKey: 's3_chip',
    userKey: 's3_user',
    steps: [
      { kind: 'type', at: 300 },
      { kind: 'user', at: 1500 },
      { kind: 'hitl', at: 2600 },
      { kind: 'approve', at: 5400 },
      { kind: 'bs', at: 6400 },
      { kind: 'bs_call', at: 7700 },
      { kind: 'bs_end', at: 13400 },
      { kind: 'done', at: 13700 },
    ],
    holdMs: 18200,
    tokenbar: {
      start: FRESH,
      end: { totalTokens: 2300, messages: 4, costEur: 0.004 },
      tickAt: 'done',
    },
    streamWindows: [
      ['user', 'hitl'],
      ['approve', 'done'],
    ],
  },
  {
    id: 'create',
    chipKey: 's4_chip',
    userKey: 's4_user',
    voice: true,
    steps: [
      { kind: 'type', at: 300 },
      { kind: 'user', at: 1500 },
      { kind: 'bs', at: 2500 },
      { kind: 'bs_rail', at: 4800 },
      { kind: 'bs_end', at: 9800 },
      { kind: 'reply', at: 10100 },
      { kind: 'fill', at: 12600 },
    ],
    holdMs: 16100,
    tokenbar: {
      start: FRESH,
      end: { totalTokens: 3090, messages: 2, costEur: 0.004 },
      tickAt: 'reply',
    },
    streamWindows: [['user', 'reply']],
  },
];

/** Per-response footers (single LLM turn per act, like the real app). */
export const SCENARIO_FOOTERS: Record<ScenarioId, MessageFooter> = {
  orchestrate: { time: '19:42', tokensIn: 1240, tokensOut: 210, costEur: 0.003 },
  anticipate: { time: '07:15', tokensIn: 890, tokensOut: 145, costEur: 0.002 },
  call: { time: '18:20', tokensIn: 1980, tokensOut: 320, costEur: 0.004 },
  create: { time: '12:03', tokensIn: 2310, tokensOut: 780, costEur: 0.004 },
};

/** Live cost line at the bottom of each backstage pane. */
export const BACKSTAGE_COSTS: Record<ScenarioId, { tokens: number; costEur: number }> = {
  orchestrate: { tokens: 1240, costEur: 0.003 },
  anticipate: { tokens: 890, costEur: 0.002 },
  call: { tokens: 1980, costEur: 0.004 },
  create: { tokens: 2310, costEur: 0.004 },
};

/**
 * Static render used under `prefers-reduced-motion`: act 1 at its resolution
 * moment (the richest single frame), without glass, typing or stream chrome.
 */
export const REDUCED_MOTION_KINDS: ReadonlySet<string> = new Set([
  'user',
  'hitl',
  'approve',
  'done',
]);
