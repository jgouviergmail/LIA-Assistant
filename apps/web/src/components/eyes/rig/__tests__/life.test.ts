/**
 * The moving hold, measured where it is judged: on screen.
 *
 * "Alive, not agitated" is a budget, and a budget is a number. A resting face
 * must MOVE — the measured baseline before this work was 0.47 px of mouth and
 * 0 px of brow over a full minute at the medium size, which is a still image
 * — and it must never move enough to read as a tic. Both halves are pinned
 * here in pixels, through the stylesheet's own arithmetic, for every resting
 * expression, every mood family and the three widget sizes.
 */

import { describe, it, expect } from 'vitest';

import { createEyeRig } from '@/components/eyes/rig/runtime';
import { resolveLoops } from '@/components/eyes/rig/poses';
import {
  faceMetrics,
  SIZE_PX,
  spread,
  type FaceMetrics,
} from '@/components/eyes/rig/__tests__/screen';
import type { EyeExpression, IdleMoodFamily } from '@/components/eyes/expression-engine';

/** One idle minute at 16 ms, after the arrival has settled. */
function idleMinute(expression: EyeExpression, family: IdleMoodFamily, px: number): FaceMetrics[] {
  const rig = createEyeRig({ initial: { expression, styleId: 'cozmo', family } });
  const frames: FaceMetrics[] = [];
  for (let frame = 0; frame < 3750; frame += 1) {
    rig.step(16);
    frames.push(faceMetrics(rig.values(), px));
  }
  return frames;
}

/** A resting pose HOLDS; `thinking` is the one that WORKS its mouth (the
 * chew), and a working mouth is allowed a little more travel than a hold. */
type Budget = 'hold' | 'working';

const RESTING: readonly [EyeExpression, IdleMoodFamily, Budget][] = [
  ['neutral', 'calm', 'hold'],
  ['neutral', 'lively', 'hold'],
  ['neutral', 'drowsy', 'hold'],
  ['attentive', 'lively', 'hold'],
  ['thinking', 'calm', 'working'],
  ['tender', 'calm', 'hold'],
  ['bored', 'calm', 'hold'],
  ['tired', 'drowsy', 'hold'],
];

/** Sub-pixel is a still image; past two pixels a hold is a fidget. A mouth
 * chewing on a thought may travel a third more, and tilt a little further. */
const VISIBLE_PX = 0.6;
const FIDGET_PX: Record<Budget, number> = { hold: 2, working: 3 };
const TILT_DEG: Record<Budget, number> = { hold: 4, working: 6 };

describe('the moving hold, in pixels', () => {
  it('moves the mouth visibly at rest, and never enough to fidget (medium size)', () => {
    RESTING.forEach(([expression, family, budget]) => {
      const frames = idleMinute(expression, family, SIZE_PX.md);
      const height = spread(frames.map(frame => frame.mouthHeight));
      const width = spread(frames.map(frame => frame.mouthWidth));
      const tilt = spread(frames.map(frame => frame.mouthTilt));
      expect({ expression, family, visible: height + width >= VISIBLE_PX }).toEqual({
        expression,
        family,
        visible: true,
      });
      expect({
        expression,
        family,
        height: height <= FIDGET_PX[budget],
        width: width <= FIDGET_PX[budget],
        tilt: tilt <= TILT_DEG[budget],
      }).toEqual({ expression, family, height: true, width: true, tilt: true });
    });
  });

  it('moves the brows with the breath, under the fidget line, at every size', () => {
    (['sm', 'md', 'lg'] as const).forEach(size => {
      RESTING.forEach(([expression, family]) => {
        const frames = idleMinute(expression, family, SIZE_PX[size]);
        const left = spread(frames.map(frame => frame.browY.left));
        const right = spread(frames.map(frame => frame.browY.right));
        expect({ size, expression, family, breathes: left > 0.1 && right > 0.1 }).toEqual({
          size,
          expression,
          family,
          breathes: true,
        });
        expect({
          size,
          expression,
          family,
          calm: left <= FIDGET_PX.hold && right <= FIDGET_PX.hold,
        }).toEqual({ size, expression, family, calm: true });
      });
    });
  });

  it('holds a concentrating face still — the budget is for rest, not for focus', () => {
    const rig = createEyeRig({
      initial: { expression: 'focused', styleId: 'cozmo', family: 'calm' },
    });
    const frames: FaceMetrics[] = [];
    for (let frame = 0; frame < 600; frame += 1) {
      rig.step(16);
      frames.push(faceMetrics(rig.values(), SIZE_PX.md));
    }
    expect(spread(frames.map(frame => frame.mouthHeight))).toBe(0);
    expect(spread(frames.map(frame => frame.browY.left))).toBe(0);
  });

  it('never repeats: no resting loop shares a period with another on the same channel', () => {
    RESTING.forEach(([expression, family]) => {
      const byChannel = new Map<string, number[]>();
      resolveLoops(expression, family).forEach(loop => {
        const periods = byChannel.get(loop.channel) ?? [];
        periods.push(loop.periodMs);
        byChannel.set(loop.channel, periods);
      });
      byChannel.forEach((periods, channel) => {
        expect({ channel, distinct: new Set(periods).size }).toEqual({
          channel,
          distinct: periods.length,
        });
      });
    });
  });
});
