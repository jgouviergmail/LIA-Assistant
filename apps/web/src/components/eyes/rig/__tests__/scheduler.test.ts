/**
 * The shared frame clock: one loop, many subjects, an idle page that costs
 * nothing — and a slower cadence for the motion that never arrives.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  activeFrameSubscribers,
  IDLE_FRAME_MS,
  MAX_CATCH_UP_MS,
  MAX_FRAME_MS,
  releaseFrames,
  requestFrames,
  stepInSlices,
  type FrameDemand,
} from '@/components/eyes/rig/scheduler';

/** A subject that always needs full frames. */
const active = (): FrameDemand => 'active';

/**
 * Frames fired by hand, at the instants the test chooses.
 *
 * The fake timers fire one frame every 16 ms however far the clock is
 * advanced, so they can never hand the loop a LONG frame — and a long frame
 * is the whole subject of the cap. (The previous cap test advanced two
 * minutes, saw seven thousand frames of 16 ms and proved nothing.)
 */
function manualFrames() {
  let queued: FrameRequestCallback[] = [];
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
    queued.push(callback);
    return queued.length;
  });
  vi.stubGlobal('cancelAnimationFrame', () => {
    queued = [];
  });
  return {
    fire(nowMs: number) {
      const due = queued;
      queued = [];
      due.forEach(callback => callback(nowMs));
    },
  };
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('frame scheduler', () => {
  it('steps every subscriber with the same delta, from one loop', () => {
    const deltas: Array<[string, number]> = [];
    const first = (dt: number): FrameDemand => {
      deltas.push(['first', dt]);
      return 'active';
    };
    const second = (dt: number): FrameDemand => {
      deltas.push(['second', dt]);
      return 'active';
    };
    requestFrames(first);
    requestFrames(second);
    vi.advanceTimersByTime(32);

    expect(deltas.length).toBeGreaterThanOrEqual(4);
    const byFrame = new Map<number, number[]>();
    deltas.forEach(([, dt], index) => {
      const frame = Math.floor(index / 2);
      byFrame.set(frame, [...(byFrame.get(frame) ?? []), dt]);
    });
    byFrame.forEach(values => expect(new Set(values).size).toBe(1));

    releaseFrames(first);
    releaseFrames(second);
  });

  it('drops a subscriber that reports it has settled', () => {
    let frames = 0;
    const settling = (): FrameDemand => {
      frames += 1;
      return frames < 2 ? 'active' : 'stop';
    };
    requestFrames(settling);
    vi.advanceTimersByTime(160);
    expect(frames).toBe(2);
    expect(activeFrameSubscribers()).toBe(0);
  });

  it('stops the loop entirely once nobody needs it', () => {
    const cancel = vi.spyOn(globalThis, 'cancelAnimationFrame');
    requestFrames(active);
    vi.advanceTimersByTime(16);
    releaseFrames(active);
    expect(activeFrameSubscribers()).toBe(0);
    expect(cancel).toHaveBeenCalled();
    cancel.mockRestore();
  });

  it('subscribing twice still steps once', () => {
    let calls = 0;
    const subject = (): FrameDemand => {
      calls += 1;
      return 'active';
    };
    requestFrames(subject);
    requestFrames(subject);
    vi.advanceTimersByTime(16);
    expect(calls).toBe(1);
    releaseFrames(subject);
  });

  it('carries a long frame whole instead of throwing most of it away', () => {
    // A busy main thread hands the loop a 200 ms frame. Capped at 64 ms, the
    // face played at a third of its speed for as long as the page was slow —
    // measured on a slowed-down device: 8.6 s lost out of 15.
    const frames = manualFrames();
    const seen: number[] = [];
    const subject = (dt: number): FrameDemand => {
      seen.push(dt);
      return 'active';
    };
    requestFrames(subject);
    frames.fire(1000);
    frames.fire(1016);
    frames.fire(1216);
    releaseFrames(subject);
    expect(seen).toEqual([0, 16, 200]);
  });

  it('still drops the time of a tab that slept for minutes', () => {
    const frames = manualFrames();
    const seen: number[] = [];
    const subject = (dt: number): FrameDemand => {
      seen.push(dt);
      return 'active';
    };
    requestFrames(subject);
    frames.fire(1000);
    frames.fire(1016);
    frames.fire(121_016);
    releaseFrames(subject);
    expect(seen).toEqual([0, 16, MAX_CATCH_UP_MS]);
  });

  it('survives a subscriber unsubscribing from inside its own step', () => {
    const survivor = vi.fn((): FrameDemand => 'active');
    const suicidal = (): FrameDemand => {
      releaseFrames(suicidal);
      releaseFrames(survivor);
      return 'active';
    };
    requestFrames(suicidal);
    requestFrames(survivor);
    expect(() => vi.advanceTimersByTime(48)).not.toThrow();
    expect(activeFrameSubscribers()).toBe(0);
  });

  it('leaves NO demand behind when a subject unsubscribes mid-step', () => {
    // A stale demand from a departed subject would hold the whole page at full
    // frame rate for the rest of the session — the exact cost this scheduler
    // exists to avoid. Proven by the observable effect: a purely idle subject
    // registered afterwards must still be throttled.
    const suicidal = (): FrameDemand => {
      releaseFrames(suicidal);
      return 'active';
    };
    requestFrames(suicidal);
    vi.advanceTimersByTime(32);

    let steps = 0;
    const idle = (): FrameDemand => {
      steps += 1;
      return 'idle';
    };
    requestFrames(idle);
    vi.advanceTimersByTime(320);
    releaseFrames(idle);
    expect(steps).toBeLessThan(320 / 16 / 1.8);
  });
});

describe('integration slices', () => {
  it.each([
    [0, [0]],
    [16, [16]],
    [64, [64]],
    [96, [48, 48]],
    [200, [50, 50, 50, 50]],
    [256, [64, 64, 64, 64]],
  ])('hands a %d ms frame to the integrator as %j', (frameMs, slices) => {
    const handed: number[] = [];
    stepInSlices(frameMs, sliceMs => {
      handed.push(sliceMs);
      return true;
    });
    expect(handed).toEqual(slices);
  });

  it('never hands the integrator more than it could read before the cap was lifted', () => {
    for (let frameMs = 1; frameMs <= MAX_CATCH_UP_MS; frameMs += 1) {
      let longest = 0;
      let total = 0;
      stepInSlices(frameMs, sliceMs => {
        longest = Math.max(longest, sliceMs);
        total += sliceMs;
        return true;
      });
      expect(longest).toBeLessThanOrEqual(MAX_FRAME_MS);
      expect(total).toBeCloseTo(frameMs, 9);
    }
  });

  it('hands a frame it cannot measure as ONE step, never an endless loop', () => {
    // The loop runs on the main thread: a count that is not a number would
    // freeze the whole page, not just the face.
    for (const frameMs of [Number.POSITIVE_INFINITY, Number.NaN]) {
      const handed: number[] = [];
      stepInSlices(frameMs, sliceMs => {
        handed.push(sliceMs);
        if (handed.length > 8) throw new Error('endless slicing');
        return true;
      });
      expect(handed).toEqual([frameMs]);
    }
  });

  it('answers with what the LAST slice said', () => {
    const answers = ['moving', 'moving', 'settled'];
    expect(stepInSlices(150, () => answers.shift())).toBe('settled');
    expect(answers).toEqual([]);
  });
});

describe('idle cadence', () => {
  it('steps an idle subject far less often than an active one', () => {
    let idleSteps = 0;
    const idle = (): FrameDemand => {
      idleSteps += 1;
      return 'idle';
    };
    requestFrames(idle);
    vi.advanceTimersByTime(1000);
    releaseFrames(idle);

    let activeSteps = 0;
    const busy = (): FrameDemand => {
      activeSteps += 1;
      return 'active';
    };
    requestFrames(busy);
    vi.advanceTimersByTime(1000);
    releaseFrames(busy);

    // Breathing is a multi-second cycle: a third of the frames samples it
    // indistinguishably, and this widget is on screen for the whole session.
    expect(idleSteps).toBeLessThan(activeSteps / 1.8);
    expect(idleSteps).toBeGreaterThan(1000 / IDLE_FRAME_MS / 2);
  });

  it('CARRIES the skipped time instead of dropping it', () => {
    const seen: number[] = [];
    const idle = (dt: number): FrameDemand => {
      seen.push(dt);
      return 'idle';
    };
    requestFrames(idle);
    vi.advanceTimersByTime(1000);
    releaseFrames(idle);
    // The timeline must not slow down just because it is sampled less often:
    // a breath paced by dropped frames would drift out of step with the clock.
    const total = seen.reduce((sum, dt) => sum + dt, 0);
    expect(total).toBeGreaterThan(900);
  });

  it('gives full frames back the moment one subject starts travelling again', () => {
    let steps = 0;
    let travelling = false;
    const subject = (): FrameDemand => {
      steps += 1;
      return travelling ? 'active' : 'idle';
    };
    requestFrames(subject);
    vi.advanceTimersByTime(300);
    const idleSteps = steps;
    travelling = true;
    // One idle step is enough for the scheduler to learn it is active again.
    vi.advanceTimersByTime(300);
    releaseFrames(subject);
    expect(steps - idleSteps).toBeGreaterThan(idleSteps);
  });

  it('assumes a newcomer is travelling until it says otherwise', () => {
    const seen: FrameDemand[] = [];
    const subject = (): FrameDemand => {
      seen.push('idle');
      return 'idle';
    };
    requestFrames(subject);
    // The very first frame after waking is granted immediately: whatever woke
    // the subject up deserves to be seen without a third of a frame of delay.
    vi.advanceTimersByTime(16);
    releaseFrames(subject);
    expect(seen).toHaveLength(1);
  });
});
