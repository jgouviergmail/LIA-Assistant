/**
 * One animation clock for the whole page.
 *
 * Several rigs can be alive at once — the chat widget plus the visible live
 * previews of the style picker — and giving each one its own
 * `requestAnimationFrame` loop would mean separate callbacks, deltas and
 * slightly different timelines. They share one loop instead: a single
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

/** Steps one animated subject and says what it needs next. `dtMs` is the
 * whole time the frame carries, which a busy page makes longer than a beat:
 * a subject with timed beats integrates it through `stepInSlices`. */
export type FrameSubscriber = (dtMs: number) => FrameDemand;

/** The longest step an integrator is handed at once. The analytic springs
 * survive any delta, but a timed beat shorter than the step would be skipped
 * whole: a blink that never closed. A longer frame is cut into equal slices
 * no longer than this (`stepInSlices`), so a slow page costs frames, never
 * beats. */
export const MAX_FRAME_MS = 64;

/**
 * The wall time one frame may carry.
 *
 * It used to be `MAX_FRAME_MS` itself: a longer frame was truncated to it,
 * which is a face playing in slow motion for as long as the page is busy.
 * Measured on the public page with a processor four times slower
 * (2026-11-11): frames of 130 ms at the median, and the face's own clock 8.6 s
 * behind after 15 s — a blink lasting twice its length. Time is now carried
 * whole up to four slices; past that it is a tab that slept or a debugger
 * that stopped the world, and that time is dropped as before.
 */
export const MAX_CATCH_UP_MS = 4 * MAX_FRAME_MS;

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

/**
 * Integrate one frame in equal slices no longer than `MAX_FRAME_MS`.
 *
 * A frame the cap used to truncate is integrated in full instead: the subject
 * ends where the elapsed time takes it, having read every beat on the way,
 * and its host draws once. A frame no longer than `MAX_FRAME_MS` is one slice,
 * exactly as before. Answers with what the last slice said — whether anything
 * is still moving is a question about where the subject ended up. A duration
 * that is not a finite number is handed over as one step: this loop runs on
 * the main thread, and an endless count would freeze the page, not the face.
 */
export function stepInSlices<T>(dtMs: number, step: (sliceMs: number) => T): T {
  const count = Number.isFinite(dtMs) ? Math.max(1, Math.ceil(dtMs / MAX_FRAME_MS)) : 1;
  const sliceMs = dtMs / count;
  let answer = step(sliceMs);
  for (let index = 1; index < count; index += 1) answer = step(sliceMs);
  return answer;
}

function tick(now: number): void {
  const delta = lastTime === null ? 0 : Math.min(now - lastTime, MAX_CATCH_UP_MS);
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
