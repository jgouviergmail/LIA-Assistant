/**
 * useEyesRig — what the React binding hands the rig.
 *
 * The rig is mocked at its factory so the test reads the OPTIONS the hook
 * passes; the motion itself is the rig's own suite. One contract matters
 * here and no rig test can see it: the sketch clock outlives the face. A
 * living face mounted, unmounted and mounted again must receive the SAME
 * clock, so a page navigation never restarts the wait for a scene — and a
 * preview, which has no life, must receive none.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render } from '@testing-library/react';

import type { RigOptions } from '@/components/eyes/rig/runtime';

const seen = vi.hoisted(() => ({ options: [] as RigOptions[], played: [] as Tape[][] }));

vi.mock('@/components/eyes/rig/runtime', async importOriginal => {
  const actual = await importOriginal<typeof import('@/components/eyes/rig/runtime')>();
  return {
    ...actual,
    createEyeRig: (options: RigOptions = {}) => {
      seen.options.push(options);
      const rig = actual.createEyeRig(options);
      return {
        ...rig,
        play(...tapes: readonly Tape[]) {
          seen.played.push([...tapes]);
          rig.play(...tapes);
        },
      };
    },
  };
});

import { ExpressiveEyes } from '../ExpressiveEyes';
import { blinkTapes, maskBlinkTapes } from '@/components/eyes/rig/gestures';
import type { Tape } from '@/components/eyes/rig/tape';

beforeEach(() => {
  seen.options = [];
  seen.played = [];
});

describe('useEyesRig — the sketch clock', () => {
  it('hands every LIVING face the same clock across mounts, and a preview none', () => {
    const first = render(<ExpressiveEyes expression="neutral" gaze={null} size="md" />);
    first.unmount();
    const second = render(<ExpressiveEyes expression="neutral" gaze={null} size="md" />);
    second.unmount();
    const preview = render(<ExpressiveEyes expression="joy" gaze={null} size="sm" life={false} />);
    preview.unmount();

    expect(seen.options).toHaveLength(3);
    const [a, b, c] = seen.options;
    expect(a.sketchClock).toBeDefined();
    expect(a.sketchClock).toBe(b.sketchClock);
    expect(a.lifeRandom).toBeDefined();
    expect(c.sketchClock).toBeUndefined();
    expect(c.lifeRandom).toBeUndefined();
  });
});

describe('useEyesRig — the blink', () => {
  it('plays the MASK blink when the host is swapping the face, the spontaneous one otherwise', () => {
    const { rerender } = render(<ExpressiveEyes expression="neutral" gaze={null} size="md" />);
    rerender(<ExpressiveEyes expression="neutral" gaze={null} size="md" blinking />);
    expect(seen.played.at(-1)).toEqual(blinkTapes());
    rerender(<ExpressiveEyes expression="neutral" gaze={null} size="md" />);
    rerender(<ExpressiveEyes expression="neutral" gaze={null} size="md" blinking blinkMask />);
    expect(seen.played.at(-1)).toEqual(maskBlinkTapes());
    // The mask is a property of the rising edge: holding the flag replays nothing.
    const count = seen.played.length;
    rerender(<ExpressiveEyes expression="neutral" gaze={null} size="md" blinking blinkMask />);
    expect(seen.played).toHaveLength(count);
  });

  it('holds the lids shut again when a mask arrives in the middle of a spontaneous blink', () => {
    const { rerender } = render(<ExpressiveEyes expression="neutral" gaze={null} size="md" />);
    rerender(<ExpressiveEyes expression="neutral" gaze={null} size="md" blinking />);
    expect(seen.played.at(-1)).toEqual(blinkTapes());
    // The face is swapped while the blink is still on: no rising edge on
    // `blinking`, but one on the mask — the closure is played again.
    rerender(<ExpressiveEyes expression="neutral" gaze={null} size="md" blinking blinkMask />);
    expect(seen.played.at(-1)).toEqual(maskBlinkTapes());
  });
});
