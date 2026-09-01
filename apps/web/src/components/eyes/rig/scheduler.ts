/**
 * One animation clock for the whole page.
 *
 * Several rigs can be alive at once — the chat widget plus the twelve live
 * previews of the style picker — and giving each one its own
 * `requestAnimationFrame` loop would mean twelve callbacks, twelve deltas and
 * twelve slightly different timelines. They share one loop instead: a single
 * frame request, one delta computed once, every subscriber stepped with it.
 *
 * The loop still stops itself. A subscriber returns whether it is still
 * moving; the last one to settle takes the frame request down with it, so an
 * idle page costs nothing at all.
 */

/**
 * What a subject needs after being stepped.
 *  - `active` — something is actually travelling: every frame counts.
 *  - `idle`   — only the perpetual loops are running (breath, drift).
 *               Those are multi-second cycles, so a third of the frames
 *               samples them indistinguishably, and the widget is on
 *               screen for the entire session.
 *  - `stop`   — nothing left to do; drop the subscription.
 */
export type FrameDemand = 'active' | 'idle' | 'stop';

/** Steps one animated subject and says what it needs next. */
export type FrameSubscriber = (dtMs: number) => FrameDemand;

/** Frame budget cap. A background tab, a GC pause or a blocked main thread
 * hands the loop a huge delta; the analytic springs survive it, but a timed
 * beat would be skipped whole. Clamping keeps the beats legible. */
export const MAX_FRAME_MS = 64;

/** Frame budget while nothing but the perpetual loops is running. */
export const IDLE_FRAME_MS = 33;

const subscribers = new Set<FrameSubscriber>();
const demands = new Map<FrameSubscriber, FrameDemand>();
let frame: number | null = null;
let lastTime: number | null = null;
let pending = 0;

function stop(): void {
  if (frame !== null) cancelAnimationFrame(frame);
  frame = null;
  lastTime = null;
  pending = 0;
}

/** True while at least one subject is genuinely travelling. */
function anyActive(): boolean {
  for (const demand of demands.values()) if (demand === 'active') return true;
  return false;
}

function tick(now: number): void {
  const delta = lastTime === null ? 0 : Math.min(now - lastTime, MAX_FRAME_MS);
  lastTime = now;
  pending += delta;
  // Nothing is travelling: sample the perpetual loops on the idle budget
  // instead of every frame. The elapsed time is CARRIED, never dropped, so
  // a slower cadence changes the sampling rate and not the timeline.
  if (!anyActive() && pending < IDLE_FRAME_MS) {
    frame = requestAnimationFrame(tick);
    return;
  }
  const step = pending;
  pending = 0;
  // Iterate a copy: a subscriber may unsubscribe itself (or a sibling) while
  // being stepped — an unmount landing mid-frame.
  for (const subscriber of [...subscribers]) {
    const demand = subscriber(step);
    // `!subscribers.has` matters as much as the demand: a subject that
    // unsubscribed from inside its own step must not leave a demand behind.
    // A stale `active` entry there would hold the WHOLE page at full frame
    // rate forever, which is the one thing this table exists to prevent.
    if (demand === 'stop' || !subscribers.has(subscriber)) {
      subscribers.delete(subscriber);
      demands.delete(subscriber);
    } else {
      demands.set(subscriber, demand);
    }
  }
  if (subscribers.size === 0) {
    stop();
    return;
  }
  frame = requestAnimationFrame(tick);
}

/** Ask for frames. Idempotent: subscribing twice still steps once. */
export function requestFrames(subscriber: FrameSubscriber): void {
  subscribers.add(subscriber);
  // A newcomer is assumed to be travelling: whatever woke it up deserves
  // full frames until it says otherwise.
  demands.set(subscriber, 'active');
  if (frame !== null) return;
  lastTime = null;
  frame = requestAnimationFrame(tick);
}

/** Stop asking for frames (unmount, or a subject that went to sleep). */
export function releaseFrames(subscriber: FrameSubscriber): void {
  subscribers.delete(subscriber);
  demands.delete(subscriber);
  if (subscribers.size === 0) stop();
}

/** How many subjects are being animated — for tests and diagnostics. */
export function activeFrameSubscribers(): number {
  return subscribers.size;
}
