import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createRuntime } from '../runtime';
import { WORLD } from '../definition';
import type { Camera, Quality, WorldDefinition } from '../types';
import type { Simulation } from '../simulation';
import type { WorldDriver } from '../shared-simulation';

const graphics = vi.hoisted(() => ({ destroy: vi.fn(), render: vi.fn(), disconnect: vi.fn() }));
vi.mock('../renderer', () => ({
  WorldRenderer: class {
    drawCount = 0;
    textureBytes = 0;
    reducedMotion = false;
    constructor(
      _canvas: HTMLCanvasElement,
      _world: WorldDefinition,
      _quality: Quality,
      _labels: { player: string; bip: string }
    ) {}
    resize(_width: number, _height: number) {}
    setQuality(_quality: Quality) {}
    setHome() {}
    setAtmosphere() {}
    render(camera: Camera, sim: Simulation) {
      graphics.render(camera, sim);
    }
    destroy() {
      graphics.destroy();
    }
  },
}));
const frames: FrameRequestCallback[] = [];
beforeEach(() => {
  frames.length = 0;
  vi.clearAllMocks();
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
    frames.push(callback);
    return frames.length;
  });
  vi.stubGlobal('cancelAnimationFrame', vi.fn());
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      disconnect() {
        graphics.disconnect();
      }
    }
  );
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  document.body.replaceChildren();
});

describe('world resource ownership', () => {
  function mount(onFailure = vi.fn(), driver?: WorldDriver) {
    const canvas = document.createElement('canvas');
    canvas.tabIndex = 0;
    document.body.append(canvas);
    const onSnapshot = vi.fn();
    const runtime = createRuntime(canvas, WORLD, {
      labels: { player: 'You', bip: 'BIP' },
      reducedMotion: false,
      onSnapshot,
      onFailure,
      driver,
    });
    return { canvas, runtime, onFailure, onSnapshot };
  }
  function advance(count: number, start = 100) {
    for (let i = 0; i < count; i++) frames.shift()?.(start + i * (1000 / 60));
  }
  it('keeps visible shared animation fluid while private panels block local input', () => {
    const step = vi.fn<WorldDriver['step']>();
    const { runtime } = mount(vi.fn(), { step });
    runtime.setPaused(true);
    advance(61);
    expect(step.mock.calls.length).toBeGreaterThan(30);
    expect(graphics.render.mock.calls.length).toBeGreaterThanOrEqual(30);
    expect(graphics.render.mock.calls.length).toBeLessThanOrEqual(32);
    runtime.destroy();
  });
  it('keeps local scenery animated while a panel owns movement', () => {
    const { runtime } = mount();
    const initial = runtime.snapshot().player;
    runtime.setPaused(true);
    advance(61);
    expect(graphics.render.mock.lastCall?.[1].time).toBeGreaterThan(0.8);
    expect(runtime.snapshot().player).toEqual(initial);
    runtime.destroy();
  });
  it('retains fractional frame time instead of drifting below the low quality cadence', () => {
    const { runtime } = mount();
    runtime.setQuality('low');
    for (let i = 0; i < 300; i++) frames.shift()?.(100 + i * 21);
    expect(graphics.render.mock.calls.length).toBeGreaterThanOrEqual(186);
    expect(graphics.render.mock.calls.length).toBeLessThanOrEqual(190);
    runtime.destroy();
  });
  it('continues receiving shared projections while an editor pauses local input', () => {
    const step = vi.fn<WorldDriver['step']>();
    const { canvas, runtime } = mount(vi.fn(), { step });
    advance(2);
    step.mockClear();
    runtime.setPaused(true);
    canvas.focus();
    window.dispatchEvent(new KeyboardEvent('keydown', { code: 'ArrowRight' }));
    step.mockImplementation(sim => {
      sim.visitors = [];
      sim.bip.position = { x: 12, y: 13 };
    });
    advance(10, 150);
    expect(step).toHaveBeenCalled();
    expect(step.mock.calls.every(call => call[2].x === 0 && call[2].y === 0)).toBe(true);
    expect(runtime.snapshot().bip).toEqual({ x: 12, y: 13 });
    runtime.destroy();
  });
  it('keeps continuous camera gestures outside React publication until the bounded snapshot tick', () => {
    const { canvas, runtime, onSnapshot } = mount();
    advance(1);
    for (let i = 0; i < 60; i++) canvas.dispatchEvent(new WheelEvent('wheel', { deltaY: -120 }));
    expect(onSnapshot).not.toHaveBeenCalled();
    advance(15, 117);
    expect(onSnapshot.mock.calls.length).toBeLessThanOrEqual(2);
    expect(onSnapshot.mock.lastCall?.[0].zoom).toBe(1.8);
    runtime.destroy();
  });
  it('advances a held direction, pauses without drift and resumes after visibility restoration', () => {
    const { canvas, runtime } = mount();
    runtime.explore({ x: 10, y: 10 });
    expect(runtime.snapshot().following).toBe(false);
    canvas.focus();
    window.dispatchEvent(new KeyboardEvent('keydown', { code: 'ArrowRight' }));
    const initial = runtime.snapshot().player.x;
    advance(30);
    expect(runtime.snapshot().following).toBe(true);
    expect(runtime.snapshot().player.x).toBeGreaterThan(initial);
    runtime.setPaused(true);
    const paused = runtime.snapshot().player;
    advance(10, 600);
    expect(runtime.snapshot().player).toEqual(paused);
    runtime.setPaused(false);
    vi.spyOn(document, 'hidden', 'get').mockReturnValue(true);
    document.dispatchEvent(new Event('visibilitychange'));
    const old = frames.splice(0);
    for (const callback of old) callback(1000);
    expect(runtime.snapshot().player).toEqual(paused);
    vi.spyOn(document, 'hidden', 'get').mockReturnValue(false);
    document.dispatchEvent(new Event('visibilitychange'));
    advance(5, 5000);
    expect(runtime.snapshot().player).toEqual(paused);
    runtime.destroy();
  });
  it('surfaces a graphics failure once, stops the loop and frees all owned resources', () => {
    const { runtime, onFailure } = mount();
    graphics.render.mockImplementationOnce(() => {
      throw new Error('context lost');
    });
    advance(1);
    expect(onFailure).toHaveBeenCalledTimes(1);
    expect(graphics.destroy).toHaveBeenCalledTimes(1);
    advance(2);
    expect(graphics.render).toHaveBeenCalledTimes(1);
    runtime.destroy();
  });
  it('keeps invalid camera commands inert and restores follow mode explicitly', () => {
    const { runtime } = mount();
    const before = runtime.snapshot();
    runtime.zoom(Number.NaN);
    runtime.zoom(-1);
    runtime.explore({ x: Infinity, y: 2 });
    expect(runtime.snapshot()).toEqual(before);
    runtime.explore({ x: 20, y: 20 });
    expect(runtime.snapshot().following).toBe(false);
    runtime.recenter();
    expect(runtime.snapshot().following).toBe(true);
    runtime.setQuality('low');
    advance(30);
    expect(runtime.snapshot().metrics.fps).toBeLessThanOrEqual(31);
    runtime.destroy();
  });
  it('releases partial initialization if the viewport observer cannot start', () => {
    vi.stubGlobal(
      'ResizeObserver',
      class {
        constructor() {
          throw new Error('observer unavailable');
        }
      }
    );
    const add = vi.spyOn(window, 'addEventListener'),
      remove = vi.spyOn(window, 'removeEventListener');
    const canvas = document.createElement('canvas');
    expect(() =>
      createRuntime(canvas, WORLD, {
        labels: { player: 'You', bip: 'BIP' },
        reducedMotion: false,
        onSnapshot: vi.fn(),
      })
    ).toThrow('observer unavailable');
    expect(graphics.destroy).toHaveBeenCalledTimes(1);
    for (const [name, callback] of add.mock.calls)
      expect(remove.mock.calls.some(call => call[0] === name && call[1] === callback)).toBe(true);
  });

  it('disposes all resources once and refuses retained commands after disposal', () => {
    const canvas = document.createElement('canvas');
    const notify = vi.fn();
    const runtime = createRuntime(canvas, WORLD, {
      labels: { player: 'You', bip: 'BIP' },
      reducedMotion: false,
      onSnapshot: notify,
    });
    runtime.destroy();
    runtime.destroy();
    expect(graphics.destroy).toHaveBeenCalledTimes(1);
    expect(graphics.disconnect).toHaveBeenCalledTimes(1);
    const before = runtime.snapshot();
    runtime.explore({ x: 10, y: 10 });
    runtime.callBip();
    runtime.zoom(1.2);
    expect(runtime.snapshot()).toEqual(before);
    expect(notify).not.toHaveBeenCalled();
  });
});
