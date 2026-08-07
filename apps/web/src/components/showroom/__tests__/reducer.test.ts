/**
 * Deterministic showroom mission state machine (multi-mission).
 *
 * What must hold, for EVERY registered mission:
 * - START only from ready; ADVANCE walks reading_sources (one reveal per
 *   source) then planning; decisions are taken strictly in order; RESTART
 *   works from every phase;
 * - every combination of allowed decision kinds reaches the receipt;
 * - a decision kind outside the step's `allowed` list is ignored;
 * - the state stores only bounded enum markers, never free text;
 * - ignored events return the SAME state reference (no phantom re-renders);
 * - the reducer is pure: no timers, no Date, no i18n, no telemetry.
 */

import { describe, expect, it } from 'vitest';

import { SHOWROOM_MISSIONS } from '@/components/showroom/missions';
import { OVERLOADED_MORNING } from '@/components/showroom/missions/overloaded-morning';
import { PHONE_BOOKING } from '@/components/showroom/missions/phone-booking';
import {
  initialStateFor,
  makeShowroomReducer,
} from '@/components/showroom/reducer';
import type {
  ShowroomDecisionKind,
  ShowroomEvent,
  ShowroomMissionDefinition,
  ShowroomState,
} from '@/components/showroom/types';

function runner(def: ShowroomMissionDefinition) {
  const reducer = makeShowroomReducer(def);
  const run = (events: ShowroomEvent[], from?: ShowroomState): ShowroomState =>
    events.reduce(reducer, from ?? initialStateFor(def));
  return { reducer, run };
}

/** START, reveal every source, then planning → first decision. */
function toFirstDecision(def: ShowroomMissionDefinition): ShowroomEvent[] {
  return [
    { type: 'START' },
    ...def.sources.map((): ShowroomEvent => ({ type: 'ADVANCE' })),
    { type: 'ADVANCE' }, // reading_sources (all read) -> planning
    { type: 'ADVANCE' }, // planning -> decision[0]
  ];
}

/** Every combination of allowed kinds across the mission's decisions. */
function decisionCombinations(
  def: ShowroomMissionDefinition
): ShowroomDecisionKind[][] {
  return def.decisions.reduce<ShowroomDecisionKind[][]>(
    (acc, spec) => acc.flatMap((prefix) => spec.allowed.map((k) => [...prefix, k])),
    [[]]
  );
}

describe.each(SHOWROOM_MISSIONS.map((m) => [m.id, m] as const))(
  'showroomReducer — %s',
  (_id, def) => {
    const { reducer, run } = runner(def);

    it('starts only from ready', () => {
      const started = run([{ type: 'START' }]);
      expect(started.phase).toBe('reading_sources');
      expect(started.runId).toBe(1);
      expect(reducer(started, { type: 'START' })).toBe(started);
    });

    it('reveals each source one ADVANCE at a time, then plans', () => {
      let state = run([{ type: 'START' }]);
      for (let i = 1; i <= def.sources.length; i++) {
        state = reducer(state, { type: 'ADVANCE' });
        expect(state.phase).toBe('reading_sources');
        expect(state.sourcesRead).toBe(i);
      }
      state = reducer(state, { type: 'ADVANCE' });
      expect(state.phase).toBe('planning');
      state = reducer(state, { type: 'ADVANCE' });
      expect(state.phase).toBe('decision');
      expect(state.decisionIndex).toBe(0);
    });

    it.each(decisionCombinations(def).map((c) => [c.join('+'), c] as const))(
      'reaches a truthful receipt for %s',
      (_label, combo) => {
        const state = run([
          ...toFirstDecision(def),
          ...combo.map(
            (decision, index): ShowroomEvent => ({
              type: 'DECIDE',
              index,
              decision,
            })
          ),
        ]);
        expect(state.phase).toBe('receipt');
        expect(state.decisions).toEqual(combo);
      }
    );

    it('ignores a decision kind the step does not allow', () => {
      const at = run(toFirstDecision(def));
      for (const kind of ['confirm', 'edit', 'cancel'] as const) {
        if (def.decisions[0].allowed.includes(kind)) continue;
        expect(reducer(at, { type: 'DECIDE', index: 0, decision: kind })).toBe(at);
      }
    });

    it('ignores out-of-order, duplicate and unknown events (same reference)', () => {
      const ready = initialStateFor(def);
      expect(
        reducer(ready, { type: 'DECIDE', index: 0, decision: 'confirm' })
      ).toBe(ready);
      expect(reducer(ready, { type: 'ADVANCE' })).toBe(ready);

      const atFirst = run(toFirstDecision(def));
      // ADVANCE cannot skip a pending decision.
      expect(reducer(atFirst, { type: 'ADVANCE' })).toBe(atFirst);
      // A later decision while the first one is pending.
      expect(
        reducer(atFirst, { type: 'DECIDE', index: 1, decision: 'confirm' })
      ).toBe(atFirst);
      // Duplicate decision on an already-decided index.
      const after = reducer(atFirst, {
        type: 'DECIDE',
        index: 0,
        decision: 'cancel',
      });
      expect(reducer(after, { type: 'DECIDE', index: 0, decision: 'confirm' })).toBe(
        after
      );
      // Unknown event type (hostile cast).
      expect(reducer(after, { type: 'NOPE' } as unknown as ShowroomEvent)).toBe(
        after
      );
    });

    it('restarts from every phase and increments runId on the next start', () => {
      const journeys: ShowroomEvent[][] = [
        [{ type: 'START' }],
        toFirstDecision(def),
        [
          ...toFirstDecision(def),
          ...def.decisions.map(
            (spec, index): ShowroomEvent => ({
              type: 'DECIDE',
              index,
              decision: spec.allowed[0],
            })
          ),
        ],
      ];
      for (const journey of journeys) {
        const before = run(journey);
        const after = reducer(before, { type: 'RESTART' });
        expect(after.phase).toBe('ready');
        expect(after.runId).toBe(before.runId);
        expect(after.decisions.every((d) => d === null)).toBe(true);
        const restarted = reducer(after, { type: 'START' });
        expect(restarted.runId).toBe(before.runId + 1);
      }
    });

    it('stores only bounded enum markers, never free text', () => {
      const state = run([
        ...toFirstDecision(def),
        ...def.decisions.map(
          (spec, index): ShowroomEvent => ({
            type: 'DECIDE',
            index,
            decision: spec.allowed[spec.allowed.length - 1],
          })
        ),
      ]);
      expect(JSON.stringify(state).length).toBeLessThan(300);
    });
  }
);

describe('showroomReducer — cross-mission specifics', () => {
  it('the calendar tool step of the original mission still rejects edit', () => {
    const { reducer, run } = runner(OVERLOADED_MORNING);
    const atCalendar = run([
      ...toFirstDecision(OVERLOADED_MORNING),
      { type: 'DECIDE', index: 0, decision: 'confirm' },
    ]);
    expect(atCalendar.phase).toBe('decision');
    expect(atCalendar.decisionIndex).toBe(1);
    expect(
      reducer(atCalendar, { type: 'DECIDE', index: 1, decision: 'edit' })
    ).toBe(atCalendar);
  });

  it('a single-decision mission goes straight from decision to receipt', () => {
    const { run } = runner(PHONE_BOOKING);
    const state = run([
      ...toFirstDecision(PHONE_BOOKING),
      { type: 'DECIDE', index: 0, decision: 'cancel' },
    ]);
    expect(state.phase).toBe('receipt');
    expect(state.decisions).toEqual(['cancel']);
  });

  it('is deterministic: two identical runs produce identical states', () => {
    const { run } = runner(OVERLOADED_MORNING);
    const journey: ShowroomEvent[] = [
      ...toFirstDecision(OVERLOADED_MORNING),
      { type: 'DECIDE', index: 0, decision: 'edit' },
      { type: 'DECIDE', index: 1, decision: 'cancel' },
    ];
    expect(run(journey)).toEqual(run(journey));
  });
});
