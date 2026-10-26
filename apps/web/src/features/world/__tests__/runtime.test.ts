import { afterEach, describe, expect, it, vi } from 'vitest';
import { FrameMeter } from '../performance';
import { createInput } from '../input';
import { createCamera } from '../geometry';
import { WORLD } from '../definition';

afterEach(() => {
  document.body.replaceChildren();
  vi.restoreAllMocks();
});
describe('frame evidence', () => {
  it('keeps a visible long frame in its performance evidence', () => {
    const meter = new FrameMeter();
    for (let i = 0; i < 10; i++) meter.add(16, 2);
    meter.add(600, 30);
    expect(meter.read(0, 0).frameP95).toBe(600);
  });
  it('reports frame interval separately from render execution and keeps a bounded sample', () => {
    const meter = new FrameMeter();
    for (let i = 0; i < 1200; i++) meter.add(1000 / 60, 2);
    const result = meter.read(12, 1024);
    expect(result.fps).toBeCloseTo(60);
    expect(result.frameP95).toBeCloseTo(1000 / 60);
    expect(result.renderP95).toBe(2);
    expect(result.textureBytes).toBe(1024);
  });
  it('ignores invalid and suspended samples rather than claiming a zero-cost frame', () => {
    const meter = new FrameMeter();
    meter.add(Number.NaN, 5);
    meter.add(30000, 1);
    expect(meter.read(0, 0).fps).toBe(0);
    meter.add(33, 5);
    expect(meter.read(0, 0).fps).toBeCloseTo(1000 / 33);
    meter.reset();
    expect(meter.read(0, 0).fps).toBe(0);
  });
});

describe('input ownership and teardown', () => {
  it('opens a place once on E only while the canvas owns focus, never while typing', () => {
    const canvas = document.createElement('canvas');
    canvas.tabIndex = 0;
    const field = document.createElement('textarea');
    document.body.append(canvas, field);
    const interact = vi.fn();
    const input = createInput(canvas, createCamera({ width: 800, height: 600 }, WORLD.spawn), {
      walk: vi.fn(),
      changed: vi.fn(),
      interact,
    });
    field.focus();
    window.dispatchEvent(new KeyboardEvent('keydown', { code: 'KeyE' }));
    expect(interact).not.toHaveBeenCalled();
    canvas.focus();
    window.dispatchEvent(new KeyboardEvent('keydown', { code: 'KeyE' }));
    window.dispatchEvent(new KeyboardEvent('keydown', { code: 'KeyE', repeat: true }));
    expect(interact).toHaveBeenCalledTimes(1);
    input.dispose();
  });
  function setup() {
    const canvas = document.createElement('canvas');
    canvas.tabIndex = 0;
    document.body.append(canvas);
    const camera = createCamera({ width: 800, height: 600 }, WORLD.spawn);
    const walk = vi.fn();
    const changed = vi.fn();
    const input = createInput(canvas, camera, { walk, changed });
    return { canvas, input, walk, camera, changed };
  }
  it('accepts keyboard movement only while the world owns focus', () => {
    const { canvas, input } = setup();
    window.dispatchEvent(new KeyboardEvent('keydown', { code: 'KeyW' }));
    expect(input.direction()).toEqual({ x: 0, y: 0 });
    canvas.focus();
    window.dispatchEvent(new KeyboardEvent('keydown', { code: 'KeyW' }));
    expect(input.direction().y).toBe(-1);
    window.dispatchEvent(new Event('blur'));
    expect(input.direction()).toEqual({ x: 0, y: 0 });
    input.dispose();
  });
  it('releases keys on focus transfer and ignores obsolete input after disposal', () => {
    const { canvas, input } = setup();
    canvas.focus();
    window.dispatchEvent(new KeyboardEvent('keydown', { code: 'ArrowRight' }));
    expect(input.direction().x).toBe(1);
    const field = document.createElement('input');
    document.body.append(field);
    field.focus();
    canvas.dispatchEvent(new FocusEvent('blur'));
    expect(input.direction()).toEqual({ x: 0, y: 0 });
    input.dispose();
    canvas.focus();
    window.dispatchEvent(new KeyboardEvent('keydown', { code: 'ArrowLeft' }));
    expect(input.direction()).toEqual({ x: 0, y: 0 });
  });
  it('combines and releases owned touch control sources without affecting unrelated inputs', () => {
    const { input } = setup();
    input.hold('pad-up', { x: 0, y: -1 });
    input.hold('pad-right', { x: 1, y: 0 });
    expect(input.direction()).toEqual({ x: 1, y: -1 });
    input.release('pad-up');
    expect(input.direction()).toEqual({ x: 1, y: 0 });
    input.clear();
    expect(input.direction()).toEqual({ x: 0, y: 0 });
    input.dispose();
  });
  function pointer(canvas: HTMLCanvasElement, type: string, id: number, x: number, y: number) {
    const event = new MouseEvent(type, { clientX: x, clientY: y, bubbles: true, cancelable: true });
    Object.defineProperty(event, 'pointerId', { value: id });
    canvas.dispatchEvent(event);
  }
  it('walks on a tap, pans on a drag and never walks after cancellation', () => {
    const { canvas, input, camera, walk } = setup();
    pointer(canvas, 'pointerdown', 1, 100, 100);
    pointer(canvas, 'pointerup', 1, 101, 101);
    expect(walk).toHaveBeenCalledTimes(1);
    const center = { ...camera.center };
    pointer(canvas, 'pointerdown', 2, 100, 100);
    pointer(canvas, 'pointermove', 2, 150, 130);
    pointer(canvas, 'pointerup', 2, 150, 130);
    expect(camera.following).toBe(false);
    expect(camera.center).not.toEqual(center);
    expect(walk).toHaveBeenCalledTimes(1);
    pointer(canvas, 'pointerdown', 3, 200, 200);
    canvas.dispatchEvent(new Event('pointercancel'));
    pointer(canvas, 'pointerup', 3, 200, 200);
    expect(walk).toHaveBeenCalledTimes(1);
    input.dispose();
  });
  it('applies the first pinch movement, suppresses accidental walking and bounds wheel zoom', () => {
    const { canvas, input, camera, walk } = setup();
    const initial = camera.zoom;
    pointer(canvas, 'pointerdown', 1, 100, 100);
    pointer(canvas, 'pointerdown', 2, 200, 100);
    pointer(canvas, 'pointermove', 2, 250, 100);
    expect(camera.zoom).toBeCloseTo(initial * 1.5);
    pointer(canvas, 'pointerup', 1, 100, 100);
    pointer(canvas, 'lostpointercapture', 1, 100, 100);
    const center = { ...camera.center };
    pointer(canvas, 'pointermove', 2, 260, 100);
    expect(camera.center.x).toBeLessThan(center.x);
    pointer(canvas, 'pointerup', 2, 250, 100);
    expect(walk).not.toHaveBeenCalled();
    for (let i = 0; i < 50; i++)
      canvas.dispatchEvent(new WheelEvent('wheel', { deltaY: -120, clientX: 150, clientY: 100 }));
    expect(camera.zoom).toBe(1.8);
    expect(camera.following).toBe(false);
    input.dispose();
  });
});
