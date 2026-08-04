/**
 * One place decides which badge tone a status deserves.
 *
 * Before this module, three components each carried their own
 * `Record<string, string>` of Tailwind classes for the same job — a status
 * label. They drifted in three ways at once, all of them visible:
 *
 *  - `high` and `medium` both rendered as a 10 %-opacity tint, and the two
 *    tokens they use are 23° apart in OKLCH hue (`--color-destructive` at 27°,
 *    `--color-warning` at 50°). At that opacity the reader cannot tell them
 *    apart — measured on real data: 89 `high` and 113 `medium` rows that all
 *    looked the same;
 *  - the classes were hand-written, so none of them went through the
 *    design-system contrast guard that covers `Badge`'s variants across five
 *    themes × light/dark;
 *  - a fourth status added by the backend fell through to whatever the map's
 *    fallback happened to be.
 *
 * The fix is not another map: it is to name the TONE and let `Badge` render
 * it, so a status label is the same object everywhere and inherits the guard.
 * Density carries the hierarchy that hue alone could not — `destructive` is a
 * solid fill, `warning` a tint, `secondary` neutral.
 */

import { describe, it, expect } from 'vitest';

import {
  directionTone,
  outcomeTone,
  priorityTone,
  type BadgeTone,
} from '../status-tone';

/** Every tone this module may return must exist as a `Badge` variant. */
const BADGE_VARIANTS: readonly BadgeTone[] = [
  'default',
  'alert',
  'secondary',
  'success',
  'destructive',
  'warning',
  'info',
  'outline',
] as const;

describe('priorityTone', () => {
  it('separates the three levels by DENSITY, not by hue alone', () => {
    // `alert` FILLS (saturated ground, light text), `warning` tints,
    // `secondary` stays neutral. Measured on screen: `destructive` and
    // `warning` are both PALE grounds — red-100 against warning/10 — so
    // "haute" and "moyenne" still read as one level. A solid fill is the only
    // difference that survives two hues 23° apart in OKLCH.
    expect(priorityTone('high')).toBe('alert');
    expect(priorityTone('medium')).toBe('warning');
    expect(priorityTone('low')).toBe('secondary');
  });

  it('gives an unknown level the neutral tone, never an alarming one', () => {
    // A priority the backend adds later must not arrive shouting: reading
    // "critical" as red because it is unknown would be an invented claim.
    expect(priorityTone('critical')).toBe('secondary');
    expect(priorityTone('')).toBe('secondary');
  });
});

describe('outcomeTone', () => {
  it('tells apart what produced a belief, what confirmed it and what doubted it', () => {
    expect(outcomeTone('origin')).toBe('info');
    expect(outcomeTone('evidence')).toBe('success');
    expect(outcomeTone('contradiction')).toBe('warning');
  });

  it('falls back to neutral for an outcome this build does not know', () => {
    expect(outcomeTone('speculation')).toBe('secondary');
  });
});

describe('directionTone', () => {
  it('separates what you sent from what you received', () => {
    // The single most-asked-for distinction in a timeline: at a glance, which
    // side of the exchange a line belongs to.
    expect(directionTone('sent')).toBe('info');
    expect(directionTone('received')).toBe('success');
  });

  it('stays neutral when the direction is unknown', () => {
    expect(directionTone('unknown')).toBe('secondary');
  });
});

describe('every tone is renderable', () => {
  it('returns only tones `Badge` declares', () => {
    const produced = [
      priorityTone('high'),
      priorityTone('medium'),
      priorityTone('low'),
      priorityTone('nope'),
      outcomeTone('origin'),
      outcomeTone('evidence'),
      outcomeTone('contradiction'),
      outcomeTone('nope'),
      directionTone('sent'),
      directionTone('received'),
      directionTone('nope'),
    ];

    for (const tone of produced) {
      expect(BADGE_VARIANTS).toContain(tone);
    }
  });
});
