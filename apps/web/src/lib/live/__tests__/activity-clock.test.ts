/**
 * ActivityClock — idle is « nobody does anything », not « the microphone is quiet ».
 *
 *  - a silence of `idleMs` ends in `onIdle`, and the last `countdownMs` are announced;
 *  - any touch clears the countdown and starts the silence over;
 *  - a hold (speaking, delegating, processing) suspends the clock; releasing
 *    the LAST hold starts the silence over — never from before the hold;
 *  - stop() forgets everything and announces nothing further.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { ActivityClock } from '../activity-clock';

function build(idleMs = 10_000, countdownMs = 5_000) {
  const onCountdown = vi.fn();
  const onIdle = vi.fn();
  const clock = new ActivityClock({ idleMs, countdownMs, tickMs: 1_000, onCountdown, onIdle });
  return { clock, onCountdown, onIdle };
}

describe('ActivityClock', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('ends a silence after idleMs and announces the last stretch', () => {
    const { clock, onCountdown, onIdle } = build();
    clock.start();
    vi.advanceTimersByTime(4_999);
    expect(onCountdown).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(onCountdown).toHaveBeenLastCalledWith(5_000);
    vi.advanceTimersByTime(3_000);
    expect(onCountdown).toHaveBeenLastCalledWith(2_000);
    expect(onIdle).not.toHaveBeenCalled();
    vi.advanceTimersByTime(2_000);
    expect(onIdle).toHaveBeenCalledTimes(1);
    expect(onCountdown).toHaveBeenLastCalledWith(null);
  });

  it('a touch during the countdown clears it and starts the silence over', () => {
    const { clock, onCountdown, onIdle } = build();
    clock.start();
    vi.advanceTimersByTime(8_000);
    expect(onCountdown).toHaveBeenLastCalledWith(2_000);
    clock.touch();
    expect(onCountdown).toHaveBeenLastCalledWith(null);
    vi.advanceTimersByTime(9_999);
    expect(onIdle).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(onIdle).toHaveBeenCalledTimes(1);
  });

  it('a hold suspends the clock and the last release starts the silence over', () => {
    const { clock, onCountdown, onIdle } = build();
    clock.start();
    vi.advanceTimersByTime(7_000);
    clock.hold('speaking');
    expect(onCountdown).toHaveBeenLastCalledWith(null);
    clock.hold('delegating');
    vi.advanceTimersByTime(60_000);
    expect(onIdle).not.toHaveBeenCalled();
    clock.release('speaking');
    vi.advanceTimersByTime(60_000);
    expect(onIdle).not.toHaveBeenCalled();
    expect(clock.quiet).toBe(false);
    clock.release('delegating');
    expect(clock.quiet).toBe(true);
    vi.advanceTimersByTime(9_999);
    expect(onIdle).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(onIdle).toHaveBeenCalledTimes(1);
  });

  it('releasing a hold never taken changes nothing, and stop() silences everything', () => {
    const { clock, onCountdown, onIdle } = build();
    clock.start();
    vi.advanceTimersByTime(6_000);
    clock.release('nobody');
    expect(onCountdown).toHaveBeenLastCalledWith(4_000);
    clock.stop();
    expect(onCountdown).toHaveBeenLastCalledWith(null);
    vi.advanceTimersByTime(60_000);
    expect(onIdle).not.toHaveBeenCalled();
  });
});
