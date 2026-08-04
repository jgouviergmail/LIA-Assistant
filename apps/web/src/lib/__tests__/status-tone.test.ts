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
  callOutcomeTone,
  skillTraitTone,
  directionTone,
  lifecycleTone,
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

/**
 * The lifecycle vocabulary — the half of the problem ADR-205 did not reach.
 *
 * `priorityTone` fixed ONE family of statuses. Every other screen kept
 * deciding on its own, and the same meaning ended up wearing three different
 * colours: "running fine" was `default` (blue) on MCP servers and scheduled
 * actions, `success` (green) on Drive sources, documents and spaces, and plain
 * GREY on recent calls — where `failed` and `completed` were, as a result,
 * indistinguishable. "In flight" was `info` on Drive, `outline` on actions and
 * documents, and an inline blue tint on calls.
 *
 * Statuses are not per-screen inventions: `error`, `completed`, `active`,
 * `syncing`, `pending` mean the same thing wherever the backend emits them. So
 * ONE table maps that shared vocabulary to a tone, and a screen only adds a
 * mapping when its domain genuinely names something new.
 */
describe('lifecycleTone', () => {
  it('separates a failure from a success — the defect that started this', () => {
    // Recent calls rendered both as the same grey pill.
    expect(lifecycleTone('failed')).not.toBe(lifecycleTone('completed'));
    expect(lifecycleTone('failed')).toBe('destructive');
    expect(lifecycleTone('completed')).toBe('success');
  });

  it('gives one tone per semantic family, across every domain', () => {
    // Succeeded / running.
    for (const status of ['active', 'completed', 'connected', 'succeeded', 'ready']) {
      expect(lifecycleTone(status)).toBe('success');
    }
    // In flight.
    for (const status of [
      'dialing',
      'in_progress',
      'executing',
      'syncing',
      'processing',
      'reindexing',
      'pending',
    ]) {
      expect(lifecycleTone(status)).toBe('info');
    }
    // Failed.
    for (const status of ['error', 'failed']) {
      expect(lifecycleTone(status)).toBe('destructive');
    }
    // Needs attention, but not broken.
    for (const status of ['auth_required', 'partial', 'degraded']) {
      expect(lifecycleTone(status)).toBe('warning');
    }
    // Inert: nothing happened, nothing is wrong.
    for (const status of ['inactive', 'disabled', 'idle', 'cancelled', 'no_answer', 'voicemail']) {
      expect(lifecycleTone(status)).toBe('secondary');
    }
  });

  it('renders an unknown status NEUTRAL, never alarming', () => {
    // A status the backend adds later must not arrive shouting.
    expect(lifecycleTone('quantum_entangled')).toBe('secondary');
    expect(lifecycleTone('')).toBe('secondary');
  });

  it('never returns the solid `alert` fill', () => {
    // `alert` is reserved for the priority hierarchy (ADR-205), where two pale
    // tints could not be told apart. A lifecycle status is not an alarm.
    const every = [
      'active',
      'completed',
      'connected',
      'succeeded',
      'dialing',
      'in_progress',
      'executing',
      'syncing',
      'processing',
      'pending',
      'error',
      'failed',
      'auth_required',
      'partial',
      'degraded',
      'inactive',
      'disabled',
      'idle',
      'cancelled',
      'no_answer',
      'voicemail',
      'unknown',
    ];
    for (const status of every) expect(lifecycleTone(status)).not.toBe('alert');
  });
});

describe('callOutcomeTone', () => {
  it('reads a refusal as a fact, not as a failure', () => {
    // A callee who declines is a normal outcome of a phone call. Painting it
    // red would tell the reader something went wrong when nothing did.
    expect(callOutcomeTone('declined')).toBe('secondary');
    expect(callOutcomeTone('unreachable')).toBe('secondary');
  });

  it('distinguishes a met objective from a partial one', () => {
    expect(callOutcomeTone('objective_met')).toBe('success');
    expect(callOutcomeTone('partial')).toBe('warning');
  });

  it('renders an unknown outcome NEUTRAL', () => {
    expect(callOutcomeTone('renegotiated')).toBe('secondary');
  });
});

/**
 * Skill trait badges — the same label was already drifting between the user
 * gallery and the admin section (`always_loaded` secondary here, outline
 * there). Traits are typed, so the TYPE decides the tone:
 *
 *  - identity (the category)      -> primary tint, follows the theme
 *  - cost signal (always loaded)  -> warning — it occupies context permanently
 *  - plain capability             -> neutral
 */
describe('skillTraitTone', () => {
  it('tones by trait type', () => {
    expect(skillTraitTone('category')).toBe('default');
    expect(skillTraitTone('always_loaded')).toBe('warning');
    for (const trait of ['has_scripts', 'dialogue', 'has_plan_template', 'channel'] as const) {
      expect(skillTraitTone(trait)).toBe('secondary');
    }
  });
});
