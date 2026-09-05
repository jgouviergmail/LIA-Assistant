/**
 * The bubble states what the REGISTER recorded (ADR-263).
 *
 * One parser feeds both paths — the live `done` chunk and a reloaded history
 * row — so a message cannot say one thing while streaming and another after a
 * refresh. Everything else here is about surviving payloads written by an
 * older backend, which a history row will keep serving for as long as the
 * conversation exists.
 */

import { describe, expect, it } from 'vitest';

import { performedEffectsFromMetadata } from '@/lib/performed-effects-hydration';
import { MAX_DISPLAYED_EFFECTS } from '@/types/performed-effects';

const ONE_EFFECT = {
  label_key: 'effects.labels.draft.email',
  values: { recipient: 'Marie' },
  status: 'succeeded',
  tool_name: 'draft:email',
};

describe('performedEffectsFromMetadata', () => {
  it('hydrates a recorded effect into its display shape', () => {
    const effects = performedEffectsFromMetadata({ performed_effects: [ONE_EFFECT] });

    expect(effects).toEqual([
      {
        labelKey: 'effects.labels.draft.email',
        values: { recipient: 'Marie' },
        status: 'succeeded',
        toolName: 'draft:email',
      },
    ]);
  });

  it('keeps a failed effect: an attempt that failed still happened', () => {
    const effects = performedEffectsFromMetadata({
      performed_effects: [{ ...ONE_EFFECT, status: 'failed' }],
    });

    expect(effects?.[0].status).toBe('failed');
  });

  it.each(['refused', 'claimed', 'abandoned', 'anything'])(
    'drops the %s status: only what happened is stated',
    status => {
      const effects = performedEffectsFromMetadata({
        performed_effects: [{ ...ONE_EFFECT, status }],
      });

      expect(effects).toBeUndefined();
    }
  );

  it('returns undefined when there is no metadata at all', () => {
    expect(performedEffectsFromMetadata(undefined)).toBeUndefined();
    expect(performedEffectsFromMetadata(null)).toBeUndefined();
    expect(performedEffectsFromMetadata({})).toBeUndefined();
  });

  it.each([
    ['not an array', { performed_effects: 'nope' }],
    ['an entry that is not an object', { performed_effects: [42] }],
    ['an entry with no label key', { performed_effects: [{ status: 'succeeded' }] }],
    ['an entry with an empty label key', { performed_effects: [{ ...ONE_EFFECT, label_key: '' }] }],
  ])('degrades to undefined on %s', (_case, metadata) => {
    expect(performedEffectsFromMetadata(metadata as Record<string, unknown>)).toBeUndefined();
  });

  it('keeps only scalar values: an object would break interpolation', () => {
    const effects = performedEffectsFromMetadata({
      performed_effects: [{ ...ONE_EFFECT, values: { recipient: 'Marie', nested: { a: 1 } } }],
    });

    expect(effects?.[0].values).toEqual({ recipient: 'Marie' });
  });

  it('survives a missing tool name (older payload)', () => {
    const { tool_name: _dropped, ...withoutTool } = ONE_EFFECT;
    const effects = performedEffectsFromMetadata({ performed_effects: [withoutTool] });

    expect(effects?.[0].toolName).toBe('');
  });

  it('caps the list: a bubble states, the journal enumerates', () => {
    const many = Array.from({ length: MAX_DISPLAYED_EFFECTS + 4 }, () => ONE_EFFECT);

    expect(performedEffectsFromMetadata({ performed_effects: many })).toHaveLength(
      MAX_DISPLAYED_EFFECTS
    );
  });

  it('ignores an entry that cannot be displayed but keeps the others', () => {
    const effects = performedEffectsFromMetadata({
      performed_effects: [ONE_EFFECT, { status: 'succeeded' }, { ...ONE_EFFECT, status: 'failed' }],
    });

    expect(effects).toHaveLength(2);
  });
});
