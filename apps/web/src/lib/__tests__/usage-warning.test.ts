/**
 * Warning before the quota wall (A5).
 *
 * The backend already grades usage (`warning` ≥80 %, `critical` ≥95 %) and
 * returns every dimension. The chat read two booleans and discarded the rest,
 * so the limit went from invisible to absolute in one step.
 *
 * The rule has three sharp edges, each tested here:
 *  - it must name the BINDING dimension, since any single one blocks the whole
 *    account — warning about the wrong one gives the wrong deadline;
 *  - it must stay silent once the user is actually blocked (that banner owns
 *    the state) and while everything is fine;
 *  - it must never promise a reset date for an ABSOLUTE limit, which no cycle
 *    boundary ever resets.
 */

import { describe, it, expect } from 'vitest';

import { usageWarningOf, USAGE_DIMENSIONS } from '../usage-warning';
import type { UserUsageLimitResponse, LimitDetail } from '@/types/usage-limits';

const CYCLE_END = '2026-08-01T00:00:00Z';

/** A dimension at `pct` of its limit (null = unlimited). */
function detail(pct: number | null): LimitDetail {
  return {
    current: pct ?? 0,
    limit: pct === null ? null : 100,
    usage_pct: pct,
    exceeded: pct !== null && pct >= 100,
  };
}

/** A payload whose dimensions default to unlimited. */
function limits(overrides: Partial<UserUsageLimitResponse> = {}): UserUsageLimitResponse {
  return {
    status: 'ok',
    is_blocked: false,
    blocked_reason: null,
    cycle_tokens: detail(null),
    cycle_messages: detail(null),
    cycle_cost: detail(null),
    absolute_tokens: detail(null),
    absolute_messages: detail(null),
    absolute_cost: detail(null),
    cycle_start: '2026-07-01T00:00:00Z',
    cycle_end: CYCLE_END,
    ...overrides,
  } as UserUsageLimitResponse;
}

describe('usageWarningOf — when to speak', () => {
  it('says nothing without data', () => {
    // Feature disabled (404) — the hook returns null.
    expect(usageWarningOf(null)).toBeNull();
  });

  it('says nothing while usage is fine', () => {
    expect(usageWarningOf(limits({ status: 'ok', cycle_tokens: detail(42) }))).toBeNull();
  });

  it('warns at the warning grade', () => {
    const warning = usageWarningOf(limits({ status: 'warning', cycle_tokens: detail(83) }));
    expect(warning).toEqual({
      level: 'warning',
      dimension: 'cycle_tokens',
      usagePct: 83,
      cycleEnd: CYCLE_END,
    });
  });

  it('escalates at the critical grade', () => {
    const warning = usageWarningOf(limits({ status: 'critical', cycle_cost: detail(97) }));
    expect(warning?.level).toBe('critical');
  });

  it('stays silent once the user is actually blocked', () => {
    // The blocking banner already says it, and better. Two messages about the
    // same wall is noise at the worst possible moment.
    expect(
      usageWarningOf(
        limits({ status: 'blocked_limit', is_blocked: true, cycle_tokens: detail(100) })
      )
    ).toBeNull();
  });

  it('stays silent on a manual block', () => {
    expect(
      usageWarningOf(
        limits({ status: 'blocked_manual', is_blocked: true, cycle_tokens: detail(12) })
      )
    ).toBeNull();
  });
});

describe('usageWarningOf — which dimension', () => {
  it('names the dimension that will actually block', () => {
    // Any dimension blocks the account, so the binding one is the highest.
    const warning = usageWarningOf(
      limits({
        status: 'warning',
        cycle_tokens: detail(81),
        cycle_messages: detail(92),
        cycle_cost: detail(85),
      })
    );
    expect(warning?.dimension).toBe('cycle_messages');
    expect(warning?.usagePct).toBe(92);
  });

  it('ignores unlimited dimensions', () => {
    const warning = usageWarningOf(
      limits({ status: 'warning', cycle_tokens: detail(null), absolute_cost: detail(88) })
    );
    expect(warning?.dimension).toBe('absolute_cost');
  });

  it('never promises a reset for an absolute limit', () => {
    // Absolute limits do not reset with the billing cycle; naming a date would
    // be a lie the user would plan around.
    const warning = usageWarningOf(limits({ status: 'warning', absolute_tokens: detail(90) }));
    expect(warning?.cycleEnd).toBeNull();
  });

  it('offers the reset date for a cycle limit', () => {
    const warning = usageWarningOf(limits({ status: 'warning', cycle_messages: detail(90) }));
    expect(warning?.cycleEnd).toBe(CYCLE_END);
  });

  it('says nothing when the grade names no measurable dimension', () => {
    // Trust the dimensions over the label: a warning that names nothing is
    // unactionable, and would render "you have used NaN%".
    expect(usageWarningOf(limits({ status: 'warning' }))).toBeNull();
  });

  it('survives a non-finite percentage', () => {
    const warning = usageWarningOf(
      limits({
        status: 'warning',
        cycle_tokens: { ...detail(0), usage_pct: Number.POSITIVE_INFINITY },
        cycle_cost: detail(84),
      })
    );
    expect(warning?.dimension).toBe('cycle_cost');
  });

  it('never reports beyond 100 %', () => {
    // Overage can exceed the limit before the block lands; "112 %" reads as a
    // bug to the user.
    const warning = usageWarningOf(limits({ status: 'critical', cycle_tokens: detail(112) }));
    expect(warning?.usagePct).toBe(100);
  });

  it('rounds rather than printing a decimal', () => {
    const warning = usageWarningOf(limits({ status: 'warning', cycle_tokens: detail(83.6) }));
    expect(warning?.usagePct).toBe(84);
  });
});

describe('USAGE_DIMENSIONS — the contract', () => {
  it('covers every dimension the API returns', () => {
    // A dimension missing from this list would be invisible to the warning:
    // the account would block on a limit the UI never mentioned.
    const payload = limits();
    for (const dimension of USAGE_DIMENSIONS) {
      expect(payload, `${dimension} is not in the payload`).toHaveProperty(dimension);
    }
    const apiDimensions = Object.keys(payload).filter(
      key => key.startsWith('cycle_') || key.startsWith('absolute_')
    );
    const measurable = apiDimensions.filter(key => key !== 'cycle_start' && key !== 'cycle_end');
    expect([...USAGE_DIMENSIONS].sort()).toEqual(measurable.sort());
  });
});
