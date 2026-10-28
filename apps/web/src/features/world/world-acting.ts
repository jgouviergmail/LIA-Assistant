/** Native expression resolution with private, current execution evidence. No timer or IO. */
import {
  deriveExpression,
  resolveIdleFamily,
  sleepPolicyFrame,
  type ExpressionInputs,
  type Gaze,
} from '@/components/eyes/expression-engine';
import { recentActivity, type Activity, type ActivityRecord } from '@/components/eyes/activity';
import { NEUTRAL_CONTEXT, type ActingContext } from '@/components/eyes/rig/direction';
import type { RigPose } from '@/components/eyes/rig/runtime';
import { COMPANION_WORK_FRESH_MS, type CompanionWorkSample } from '@/stores/companionActivityStore';
import type { WorldActingState } from './types';
export type { WorldActingState } from './types';
export const WORLD_ACTING_ACCENT_MS = 800;
export interface WorldActingFrame {
  pose: RigPose;
  gaze: Gaze | null;
  context: ActingContext;
  state: WorldActingState;
  eventKey: string | null;
  accentAlive: boolean;
}
export interface WorldActingInputs {
  ownerId: string;
  signalOwnerId: string | null;
  enabled: boolean;
  now: number;
  expression: ExpressionInputs;
  context: ActingContext;
  runId: string | null;
  recent: ActivityRecord | null;
  background: CompanionWorkSample | null;
  emphasis: number;
  responseWeight: number;
}
export const NEUTRAL_WORLD_ACTING: Readonly<WorldActingFrame> = {
  pose: { expression: 'neutral', styleId: 'billes', family: 'calm' },
  gaze: null,
  context: NEUTRAL_CONTEXT,
  accentAlive: false,
  state: 'idle',
  eventKey: null,
};
function currentTerminal(input: WorldActingInputs): Activity | null {
  const record = input.recent;
  if (!record || record.event.run_id !== input.runId || record.event.phase !== 'finished')
    return null;
  const age = input.now - record.at;
  return age >= 0 && age < 6000 ? record.event : null;
}
function resolvedInputs(input: WorldActingInputs, terminal: Activity | null): ExpressionInputs {
  const expression = input.expression;
  if (expression.chatStatus !== 'idle' || expression.activity || expression.voiceState !== 'idle')
    return expression;
  if (terminal?.outcome === 'failed') return { ...expression, chatStatus: 'error' };
  if (terminal?.outcome === 'waiting') return { ...expression, hitlAwaiting: true };
  const background = input.background;
  if (
    background?.working &&
    input.now >= background.at &&
    input.now - background.at < COMPANION_WORK_FRESH_MS
  )
    return { ...expression, chatStatus: 'streaming', streamPhase: 'progress' };
  return expression;
}
function liveState(input: ExpressionInputs): WorldActingState | null {
  if (input.chatStatus === 'error') return 'error';
  if (input.hitlAwaiting) return 'waiting';
  if (input.voiceState === 'speaking') return 'speaking';
  if (input.voiceState === 'recording') return 'listening';
  if (input.voiceState === 'processing') return 'thinking';
  if (input.chatStatus === 'streaming') return streamedState(input);
  if (input.chatStatus === 'sending' || input.chatStatus === 'compacting') return 'thinking';
  return null;
}
function streamedState(input: ExpressionInputs): WorldActingState {
  if (input.streamPhase === 'answer') return 'responding';
  if (input.activity === 'reading') return 'reading';
  return input.activity === 'creating' ? 'creating' : 'thinking';
}
function terminalState(terminal: Activity | null): WorldActingState {
  if (terminal?.outcome === 'prepared') return 'prepared';
  return terminal?.intent === 'act' && terminal.outcome === 'succeeded' ? 'success' : 'idle';
}
function bounded(value: number, fallback: number, min: number, max: number): number {
  return Number.isFinite(value) ? Math.max(min, Math.min(max, value)) : fallback;
}
function completionAccentAlive(input: WorldActingInputs, state: WorldActingState): boolean {
  return (
    state === 'success' &&
    input.recent !== null &&
    input.now - input.recent.at < WORLD_ACTING_ACCENT_MS
  );
}
export function deriveWorldActing(input: WorldActingInputs): WorldActingFrame {
  if (!input.enabled || input.ownerId !== input.signalOwnerId || !Number.isFinite(input.now))
    return NEUTRAL_WORLD_ACTING;
  const terminal = currentTerminal(input);
  const expression = resolvedInputs(input, terminal);
  const frame = sleepPolicyFrame(deriveExpression(expression), false);
  const state = liveState(expression) ?? terminalState(terminal);
  const recent = terminal ? recentActivity(input.recent, input.now) : null;
  const accentAlive = completionAccentAlive(input, state);
  const eventKey = accentAlive && terminal ? terminal.run_id + ':' + terminal.invocation_id : null;
  return {
    pose: {
      expression: frame.expression,
      styleId: 'billes',
      family: resolveIdleFamily(expression.moodLabel, frame.expression),
      emphasis: bounded(input.emphasis, 1, 0.5, 1.5),
      responseWeight: bounded(input.responseWeight, 1, 0, 1),
    },
    gaze: frame.gaze,
    state,
    eventKey,
    accentAlive,
    context: {
      ...input.context,
      activity: expression.activity ?? null,
      accomplished: state === 'success',
      recentFamily: recent?.family ?? null,
      recentWeight: recent?.weight ?? 0,
    },
  };
}
/** Retained above the renderer, so recreating an atlas cannot replay a completion. */
export class WorldActingEvents {
  private readonly seen = new Set<string>();
  get size(): number {
    return this.seen.size;
  }
  take(key: string | null): boolean {
    if (!key || this.seen.has(key)) return false;
    if (this.seen.size >= 128) {
      const first = this.seen.values().next().value;
      if (first !== undefined) this.seen.delete(first);
    }
    this.seen.add(key);
    return true;
  }
}
