/**
 * Validation of a typed spend ceiling.
 *
 * Extracted as a pure function so the rule is testable without a render, and
 * so the card stays under the complexity ratchet.
 */

import { describe, it, expect } from 'vitest';

import { parseCeilingDraft } from '@/hooks/useInstanceBudget';

describe('parseCeilingDraft', () => {
  it('treats an empty field as clearing the operator ceiling', () => {
    // Not an error: removing the operator value leaves the deployment bound
    // (if any) in force.
    expect(parseCeilingDraft('')).toEqual({ valid: true, value: null });
    expect(parseCeilingDraft('   ')).toEqual({ valid: true, value: null });
  });

  it('keeps the typed decimal verbatim so no precision is invented', () => {
    // "0.50" is sent as typed: reformatting through a float would be the one
    // place a money value could drift.
    expect(parseCeilingDraft('0.50')).toEqual({ valid: true, value: '0.50' });
    expect(parseCeilingDraft(' 1 ')).toEqual({ valid: true, value: '1' });
  });

  it.each(['0', '-1', '-0.01'])('refuses %s: a bound nobody can satisfy', draft => {
    // "Allow nothing" is expressed by disabling the feature, not by a zero
    // ceiling that would block every visitor with a confusing message.
    expect(parseCeilingDraft(draft)).toEqual({ valid: false });
  });

  it.each(['abc', '1,50', '1e', ''.padEnd(3, '.')])('refuses the unparsable %s', draft => {
    expect(parseCeilingDraft(draft).valid).toBe(false);
  });

  it('refuses a non-finite value', () => {
    expect(parseCeilingDraft('Infinity')).toEqual({ valid: false });
  });
});
