/**
 * The landing's « attention + latent space » canvas: one mark per real section
 * on the attention column, ONE still frame under reduced motion, a paused page
 * or a slow device — redrawn on a theme change, never on scroll or pointer
 * (WCAG 2.2.2 / 2.3.3: nothing on the screen moves) —, a beat that lifts the
 * intensity, and a destroy that leaves nothing behind. jsdom has no 2D
 * context, so a recorder stands in for it: every call and every style
 * assignment is kept.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { mountLiaBackground } from '../attention-background';

interface Recorder {
  calls: Array<{ name: string; args: unknown[] }>;
  strokeStyles: string[];
}

function recordingContext(rec: Recorder): CanvasRenderingContext2D {
  const target: Record<string, unknown> = {};
  return new Proxy(target, {
    get(_, prop: string) {
      if (prop in target) return target[prop];
      return (...args: unknown[]) => rec.calls.push({ name: prop, args });
    },
    set(_, prop: string, value: unknown) {
      target[prop] = value;
      if (prop === 'strokeStyle') rec.strokeStyles.push(String(value));
      return true;
    },
  }) as unknown as CanvasRenderingContext2D;
}

const VIEWPORT = { width: 1280, height: 800 };
const DOC_HEIGHT = 6000;

let rec: Recorder;
let frames: FrameRequestCallback[];
let reducedMotion: boolean;
let now: number;

function rect(top: number, height: number): DOMRect {
  return {
    top,
    height,
    bottom: top + height,
    left: 0,
    right: VIEWPORT.width,
    width: VIEWPORT.width,
    x: 0,
    y: top,
    toJSON: () => ({}),
  } as DOMRect;
}

/** Sections at these document offsets, each 800 px tall. */
function addSections(tops: number[]): void {
  for (const top of tops) {
    const el = document.createElement('section');
    el.className = 'probe-section';
    el.getBoundingClientRect = () => rect(top - window.scrollY, 800);
    document.body.append(el);
  }
}

/** Runs the scheduled frames once, far enough apart to pass the fps gate. */
function frame(): void {
  now += 100;
  const pending = frames.splice(0);
  for (const cb of pending) cb(now);
}

function sectionMarks(): string[] {
  return rec.calls
    .filter(call => call.name === 'fillText')
    .map(call => String(call.args[0]))
    .filter(text => text === '⟨s⟩' || /^§\d+$/.test(text));
}

beforeEach(() => {
  rec = { calls: [], strokeStyles: [] };
  frames = [];
  reducedMotion = false;
  now = 0;
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(
    () => recordingContext(rec) as never
  );
  vi.spyOn(HTMLCanvasElement.prototype, 'getBoundingClientRect').mockReturnValue(
    rect(0, VIEWPORT.height)
  );
  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => frames.push(cb));
  vi.stubGlobal('cancelAnimationFrame', vi.fn());
  // jsdom has no Path2D: the points' paths are only handed to the recorder.
  vi.stubGlobal(
    'Path2D',
    class {
      moveTo() {}
      arc() {}
    }
  );
  vi.stubGlobal(
    'matchMedia',
    vi.fn((query: string) => ({
      get matches() {
        return query.includes('reduced-motion') ? reducedMotion : false;
      },
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }))
  );
  Object.defineProperty(document.documentElement, 'scrollHeight', {
    configurable: true,
    get: () => DOC_HEIGHT,
  });
  Object.defineProperty(window, 'innerHeight', { configurable: true, value: VIEWPORT.height });
  window.scrollY = 0;
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  document.body.replaceChildren();
  window.scrollY = 0;
});

describe('mountLiaBackground', () => {
  it('mounts one decorative fixed canvas in the given parent, on the given layer', () => {
    const host = document.createElement('div');
    document.body.append(host);
    const bg = mountLiaBackground({ mount: host, zIndex: -1 });

    const canvas = host.querySelector('canvas');
    expect(canvas).not.toBeNull();
    expect(canvas?.getAttribute('aria-hidden')).toBe('true');
    expect(canvas?.style.position).toBe('fixed');
    expect(canvas?.style.zIndex).toBe('-1');
    expect(canvas?.style.pointerEvents).toBe('none');
    // The large viewport where the engine knows it; anchored top and bottom
    // otherwise — never a box that would cover half the screen.
    expect(canvas?.style.top).toBe('0px');
    expect(canvas?.style.bottom).toBe('0px');
    bg.destroy();
  });

  it('writes no language of its own: a caller that passes no labels gets none drawn', () => {
    const bg = mountLiaBackground({ readout: true });
    frame();
    const texts = rec.calls
      .filter(call => call.name === 'fillText')
      .map(call => String(call.args[0]));
    expect(texts.some(text => /m[ée]moire|voix|agenda/.test(text))).toBe(false);
    bg.destroy();
  });

  it('draws one mark per real section on the attention column', () => {
    addSections([1200, 2400, 3600, 4800]);
    const bg = mountLiaBackground({ sections: '.probe-section', readout: false });
    frame();

    expect(sectionMarks()).toEqual(['⟨s⟩', '§1', '§2', '§3', '§4']);
    bg.destroy();
  });

  it('keeps the token column without the heads when asked, and no head readout', () => {
    addSections([1200, 2400]);
    const bg = mountLiaBackground({ sections: '.probe-section', attentionHeads: false });
    frame();

    expect(rec.calls.some(call => call.name === 'bezierCurveTo')).toBe(false);
    expect(sectionMarks()).toEqual(['⟨s⟩', '§1', '§2']);
    const texts = rec.calls
      .filter(call => call.name === 'fillText')
      .map(call => String(call.args[0]));
    expect(texts.some(text => text.startsWith('h') && text.includes(' → '))).toBe(false);
    // The latent readout is unaffected.
    expect(texts.some(text => text.startsWith('q · top-k'))).toBe(true);
    bg.destroy();
  });

  it('draws no attention column when its intensity is 0 (phones)', () => {
    addSections([1200, 2400]);
    const bg = mountLiaBackground({ sections: '.probe-section', intensityAttention: 0 });
    frame();

    expect(sectionMarks()).toEqual([]);
    expect(rec.calls.some(call => call.name === 'bezierCurveTo')).toBe(false);
    bg.destroy();
  });

  it('stays still under reduced motion: one frame, never redrawn for the scroll or the pointer', () => {
    reducedMotion = true;
    let dark = false;
    const bg = mountLiaBackground({ isDark: () => dark });
    const clears = () => rec.calls.filter(call => call.name === 'clearRect').length;

    frame();
    expect(clears()).toBe(1);
    frame();
    frame();
    expect(clears()).toBe(1);

    window.scrollY = 900;
    frame();
    window.dispatchEvent(
      Object.assign(new Event('pointermove'), { pointerType: 'mouse', clientX: 300, clientY: 300 })
    );
    frame();
    expect(clears()).toBe(1);

    // A theme change is not motion: the same still frame, in the other palette.
    dark = true;
    frame();
    expect(clears()).toBe(2);
    frame();
    expect(clears()).toBe(2);
    bg.destroy();
  });

  it('holds still while the page is paused, and moves again when it resumes', () => {
    let paused = false;
    const bg = mountLiaBackground({ paused: () => paused });
    const clears = () => rec.calls.filter(call => call.name === 'clearRect').length;

    frame();
    frame();
    expect(clears()).toBe(2);

    paused = true;
    frame();
    const still = clears();
    expect(still).toBe(3); // the one frame that settles the still state
    window.scrollY = 1200;
    frame();
    frame();
    expect(clears()).toBe(still);

    paused = false;
    frame();
    frame();
    expect(clears()).toBe(still + 2);
    bg.destroy();
  });

  it('lifts the intensity on the beat, and never under reduced motion', () => {
    const alphaOfQueryLink = () => {
      // The first violet stroke: the query's nearest neighbour, rgba(<violet>, 0.34 * k).
      const style = rec.strokeStyles.find(s => s.startsWith('rgba(124,92,246,') && s.endsWith(')'));
      return Number(style?.slice(style.lastIndexOf(',') + 1, -1));
    };
    let beat = 0;
    const bg = mountLiaBackground({ beat: () => beat, beatGain: 0.5, isDark: () => false });
    frame();
    const rest = alphaOfQueryLink();

    rec.strokeStyles = [];
    beat = 1;
    frame();
    expect(alphaOfQueryLink()).toBeGreaterThan(rest);

    bg.destroy();
    reducedMotion = true;
    rec.strokeStyles = [];
    const still = mountLiaBackground({ beat: () => 1, beatGain: 0.5, isDark: () => false });
    frame();
    expect(alphaOfQueryLink()).toBeCloseTo(rest, 5);
    still.destroy();
  });

  it('stops moving on a device whose frames cost more than the budget', () => {
    const clears = () => rec.calls.filter(call => call.name === 'clearRect').length;
    /** Every render takes `cost` ms on the clock the module reads. */
    const renderCost = (cost: number) => {
      let calls = 0;
      vi.spyOn(performance, 'now').mockImplementation(() => (calls++ % 2 === 0 ? 0 : cost));
    };
    const animatedFrames = 5 + 30; // warm-up + sample

    renderCost(2);
    const cheap = mountLiaBackground({ frameBudgetMs: 5 });
    for (let i = 0; i < animatedFrames + 10; i++) frame();
    // Within budget: every frame is drawn, the background keeps moving.
    expect(clears()).toBe(animatedFrames + 10);
    cheap.destroy();

    rec.calls = [];
    renderCost(9);
    const costly = mountLiaBackground({ frameBudgetMs: 5 });
    for (let i = 0; i < animatedFrames; i++) frame();
    const decided = clears();
    expect(decided).toBe(animatedFrames);
    // Past the budget: still from now on — one settling frame, then nothing,
    // not even for the scroll, exactly as under reduced motion.
    for (let i = 0; i < 10; i++) frame();
    expect(clears()).toBeLessThanOrEqual(decided + 1);
    const settled = clears();
    window.scrollY = 1500;
    frame();
    expect(clears()).toBe(settled);
    costly.destroy();
  });

  it('leaves nothing behind once destroyed: no canvas, no listener, no frame', () => {
    const removeWindow = vi.spyOn(window, 'removeEventListener');
    const removeRoot = vi.spyOn(document.documentElement, 'removeEventListener');
    const host = document.createElement('div');
    document.body.append(host);
    const bg = mountLiaBackground({ mount: host });
    frame();

    bg.destroy();
    expect(host.querySelector('canvas')).toBeNull();
    expect(cancelAnimationFrame).toHaveBeenCalled();
    expect(removeWindow.mock.calls.map(call => call[0]).sort()).toEqual(['pointermove', 'resize']);
    expect(removeRoot.mock.calls.map(call => call[0])).toEqual(['pointerleave']);

    const drawsBefore = rec.calls.length;
    frame();
    expect(rec.calls.length).toBe(drawsBefore);
  });

  it('mounts nothing when the browser has no 2D context', () => {
    vi.mocked(HTMLCanvasElement.prototype.getContext).mockReturnValue(null);
    const host = document.createElement('div');
    const bg = mountLiaBackground({ mount: host });
    expect(host.childElementCount).toBe(0);
    expect(() => bg.destroy()).not.toThrow();
  });
});
