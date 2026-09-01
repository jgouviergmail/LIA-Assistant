/**
 * Dynamics presets — HOW an emotion arrives, as physics rather than duration.
 *
 * The CSS system these replace expressed arrival as `transition-duration`
 * (650 / 950 / 500 / 190 / 380 ms) and a bezier. The rig expresses the same
 * intent as a spring frequency and a damping ratio, which additionally
 * survives an interruption. These tests pin the ORDERING that carries the
 * intent — sadness slower than the base, a reflex the fastest, anger with no
 * bounce at all — rather than the exact numbers, which are art direction.
 */

import { describe, it, expect } from 'vitest';
import {
  DYNAMICS,
  DYNAMICS_FOR_EXPRESSION,
  FAMILY_DYNAMICS,
  GROUP_LEAD_MS,
  dynamicsFor,
  type DynamicsName,
} from '@/components/eyes/rig/dynamics';
import { CHANNELS, CHANNEL_KEYS } from '@/components/eyes/rig/channels';
import { EYE_EXPRESSIONS } from '@/components/eyes/expression-engine';

const NAMES = Object.keys(DYNAMICS) as DynamicsName[];

describe('dynamics presets', () => {
  it('covers every channel group with a usable spring', () => {
    NAMES.forEach(name => {
      CHANNEL_KEYS.forEach(key => {
        const config = DYNAMICS[name][CHANNELS[key].group];
        expect(config.frequency).toBeGreaterThan(0);
        expect(config.damping).toBeGreaterThan(0);
      });
    });
  });

  it('orders arrival speed the way the emotions read', () => {
    const pose = (name: DynamicsName) => DYNAMICS[name].pose.frequency;
    expect(pose('slow')).toBeLessThan(pose('base'));
    expect(pose('base')).toBeLessThan(pose('quick'));
    expect(pose('quick')).toBeLessThan(pose('strike'));
    expect(pose('strike')).toBeLessThan(pose('reflex'));
  });

  it('gives anger a hard landing and joy a real bounce', () => {
    expect(DYNAMICS.strike.pose.damping).toBeGreaterThanOrEqual(1);
    expect(DYNAMICS.quick.pose.damping).toBeLessThan(0.8);
    expect(DYNAMICS.slow.pose.damping).toBeGreaterThanOrEqual(1);
  });

  it('keeps the gaze quicker than the mass it belongs to (overlapping action)', () => {
    NAMES.forEach(name => {
      expect(DYNAMICS[name].gaze.frequency).toBeGreaterThan(DYNAMICS[name].mass.frequency);
      expect(DYNAMICS[name].lid.frequency).toBeLessThan(DYNAMICS[name].pose.frequency);
    });
  });

  it('assigns a dynamic to every expression', () => {
    EYE_EXPRESSIONS.forEach(expression => {
      expect(NAMES).toContain(DYNAMICS_FOR_EXPRESSION[expression]);
    });
  });

  it('maps the emotions onto the dynamics their CSS ancestors used', () => {
    expect(DYNAMICS_FOR_EXPRESSION.sad).toBe('slow');
    expect(DYNAMICS_FOR_EXPRESSION.sleep).toBe('slow');
    expect(DYNAMICS_FOR_EXPRESSION.joy).toBe('quick');
    expect(DYNAMICS_FOR_EXPRESSION.surprise).toBe('reflex');
    expect(DYNAMICS_FOR_EXPRESSION.fear).toBe('reflex');
    expect(DYNAMICS_FOR_EXPRESSION.anger).toBe('strike');
    expect(DYNAMICS_FOR_EXPRESSION.neutral).toBe('base');
  });

  it('resolves the spring of a channel from its expression', () => {
    expect(dynamicsFor('sad', 'syL')).toEqual(DYNAMICS.slow.pose);
    expect(dynamicsFor('joy', 'gazeX')).toEqual(DYNAMICS.quick.gaze);
  });
});

describe('overlapping action and exaggeration tables', () => {
  it('makes what FOLLOWS wait, and what is WILLED leave at once', () => {
    expect(GROUP_LEAD_MS.pose).toBe(0);
    expect(GROUP_LEAD_MS.mass).toBe(0);
    expect(GROUP_LEAD_MS.gaze).toBe(0);
    expect(GROUP_LEAD_MS.lid).toBeGreaterThan(0);
    expect(GROUP_LEAD_MS.radius).toBeGreaterThan(GROUP_LEAD_MS.lid);
    expect(GROUP_LEAD_MS.aura).toBeGreaterThan(GROUP_LEAD_MS.radius);
  });

  it('covers every channel group with a lead', () => {
    CHANNEL_KEYS.forEach(key => {
      expect(GROUP_LEAD_MS[CHANNELS[key].group]).toBeGreaterThanOrEqual(0);
    });
  });

  it('scales motion by mood: lively bigger and faster, drowsy smaller and slower', () => {
    expect(FAMILY_DYNAMICS.lively.amplitude).toBeGreaterThan(FAMILY_DYNAMICS.calm.amplitude);
    expect(FAMILY_DYNAMICS.lively.frequency).toBeGreaterThan(FAMILY_DYNAMICS.calm.frequency);
    expect(FAMILY_DYNAMICS.drowsy.amplitude).toBeLessThan(FAMILY_DYNAMICS.calm.amplitude);
    expect(FAMILY_DYNAMICS.drowsy.frequency).toBeLessThan(FAMILY_DYNAMICS.calm.frequency);
    expect(FAMILY_DYNAMICS.calm).toEqual({ frequency: 1, amplitude: 1 });
  });
});
