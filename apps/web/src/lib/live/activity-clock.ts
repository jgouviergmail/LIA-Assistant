/**
 * When is a live session idle? (wave 2 spec A8.)
 *
 * Not when the microphone is quiet: when NOBODY is doing anything — the
 * person is not speaking, LIA is not speaking, no delegation runs, the
 * provider is not processing. Each of those is a HOLD; the clock only runs
 * while no hold is open, from the last activity. The last stretch is
 * announced as a countdown so the banner can show it, and any activity
 * clears it. A provider that bills the session's duration (GPT-Live) tolls
 * through a silence — this is the one honest way to stop paying for it.
 */

export interface ActivityClockOptions {
  /** The silence after which the session ends. */
  idleMs: number;
  /** The last stretch announced through `onCountdown`. */
  countdownMs: number;
  /** How often the countdown is refreshed. */
  tickMs?: number;
  /** Milliseconds left in the countdown, or null when it is not running. */
  onCountdown: (msLeft: number | null) => void;
  onIdle: () => void;
  now?: () => number;
}

const DEFAULT_TICK_MS = 250;

export class ActivityClock {
  private readonly holds = new Set<string>();
  private lastActivity = 0;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private counting = false;
  private running = false;

  constructor(private readonly options: ActivityClockOptions) {}

  /** Start counting from now. */
  start(): void {
    this.running = true;
    this.touch();
  }

  /** Stop for good: no idle, no countdown, every hold forgotten. */
  stop(): void {
    this.running = false;
    this.holds.clear();
    this.clearTimer();
    this.announce(null);
  }

  /** Something happened: the silence starts over. */
  touch(): void {
    this.lastActivity = this.now();
    this.announce(null);
    this.schedule();
  }

  /** Someone is busy (speaking, delegating, processing): the clock waits. */
  hold(key: string): void {
    this.holds.add(key);
    this.clearTimer();
    this.announce(null);
  }

  /** That someone is done; the silence starts over only when nobody is busy. */
  release(key: string): void {
    if (!this.holds.delete(key)) return;
    if (this.holds.size === 0) this.touch();
  }

  get quiet(): boolean {
    return this.holds.size === 0;
  }

  private now(): number {
    return this.options.now ? this.options.now() : Date.now();
  }

  private announce(msLeft: number | null): void {
    if (msLeft === null && !this.counting) return;
    this.counting = msLeft !== null;
    this.options.onCountdown(msLeft);
  }

  private clearTimer(): void {
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
  }

  private schedule(): void {
    this.clearTimer();
    if (!this.running || this.holds.size > 0) return;
    const left = this.options.idleMs - (this.now() - this.lastActivity);
    if (left <= 0) {
      this.announce(null);
      this.running = false;
      this.options.onIdle();
      return;
    }
    if (left <= this.options.countdownMs) {
      this.announce(left);
      const tick = this.options.tickMs ?? DEFAULT_TICK_MS;
      this.timer = setTimeout(() => this.schedule(), Math.min(tick, left));
      return;
    }
    this.timer = setTimeout(() => this.schedule(), left - this.options.countdownMs);
  }
}
