import { panCamera, screenToWorld, zoomCamera } from './geometry';
import type { Camera, Point } from './types';
export interface WorldInput {
  direction(): Point;
  hold(source: string, direction: Point): void;
  release(source: string): void;
  clear(): void;
  dispose(): void;
}
interface InputHandlers {
  walk(point: Point, running?: boolean): void;
  changed(): void;
  interact?(): void;
  hover?(point: Point | null): void;
}
interface Contact {
  start: Point;
  last: Point;
  moved: boolean;
}
const KEYS: Readonly<Record<string, Point>> = {
  KeyW: { x: 0, y: -1 },
  KeyZ: { x: 0, y: -1 },
  ArrowUp: { x: 0, y: -1 },
  KeyS: { x: 0, y: 1 },
  ArrowDown: { x: 0, y: 1 },
  KeyA: { x: -1, y: 0 },
  KeyQ: { x: -1, y: 0 },
  ArrowLeft: { x: -1, y: 0 },
  KeyD: { x: 1, y: 0 },
  ArrowRight: { x: 1, y: 0 },
};
export function createInput(
  canvas: HTMLCanvasElement,
  camera: Camera,
  handlers: InputHandlers
): WorldInput {
  const held = new Map<string, Point>();
  const contacts = new Map<number, Contact>();
  const cleanups: (() => void)[] = [];
  let stopped = false;
  let lastTap: { point: Point; at: number; type: string } | null = null;
  let pinch: { distance: number; zoom: number; midpoint: Point } | null = null;
  const clear = () => {
    handlers.hover?.(null);
    lastTap = null;
    held.clear();
    contacts.clear();
    pinch = null;
  };
  const local = (e: PointerEvent): Point => {
    const rect = canvas.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  };
  const keyDown = (e: KeyboardEvent) => {
    if (stopped || document.activeElement !== canvas || e.altKey || e.ctrlKey || e.metaKey) return;
    if (e.code === 'KeyE') {
      if (!e.repeat) {
        e.preventDefault();
        handlers.interact?.();
      }
      return;
    }
    if (!KEYS[e.code]) return;
    e.preventDefault();
    held.set(e.code, KEYS[e.code]);
  };
  const keyUp = (e: KeyboardEvent) => {
    held.delete(e.code);
  };
  const down = (e: PointerEvent) => {
    if (stopped || e.button > 0) return;
    handlers.hover?.(null);
    e.preventDefault();
    canvas.focus({ preventScroll: true });
    canvas.setPointerCapture?.(e.pointerId);
    const point = local(e);
    contacts.set(e.pointerId, { start: point, last: point, moved: false });
    if (contacts.size > 1) {
      for (const contact of contacts.values()) contact.moved = true;
      updatePinch();
    }
  };
  const move = (e: PointerEvent) => {
    const contact = contacts.get(e.pointerId);
    if (stopped) return;
    if (!contact) {
      if (e.pointerType !== 'touch') handlers.hover?.(local(e));
      return;
    }
    const point = local(e);
    if (contacts.size >= 2) {
      contact.last = point;
      updatePinch();
    } else {
      if (Math.hypot(point.x - contact.start.x, point.y - contact.start.y) > 7)
        contact.moved = true;
      if (contact.moved) {
        panCamera(camera, { x: point.x - contact.last.x, y: point.y - contact.last.y });
        handlers.changed();
      }
      contact.last = point;
    }
  };
  function updatePinch(): void {
    const [a, b] = [...contacts.values()];
    const distance = Math.hypot(a.last.x - b.last.x, a.last.y - b.last.y);
    const midpoint = { x: (a.last.x + b.last.x) / 2, y: (a.last.y + b.last.y) / 2 };
    if (!pinch) {
      pinch = { distance: Math.max(1, distance), zoom: camera.zoom, midpoint };
      return;
    }
    zoomCamera(camera, (pinch.zoom * distance) / pinch.distance, midpoint);
    panCamera(camera, { x: midpoint.x - pinch.midpoint.x, y: midpoint.y - pinch.midpoint.y });
    pinch.midpoint = midpoint;
    handlers.changed();
  }
  const up = (e: PointerEvent) => {
    const contact = contacts.get(e.pointerId);
    contacts.delete(e.pointerId);
    if (contact && !contact.moved && !pinch && !stopped) {
      const point = local(e),
        type = e.pointerType || 'mouse',
        delay = lastTap ? e.timeStamp - lastTap.at : Infinity;
      const running =
        lastTap !== null &&
        delay >= 0 &&
        delay <= 350 &&
        type === lastTap.type &&
        Math.hypot(point.x - lastTap.point.x, point.y - lastTap.point.y) <= 24;
      lastTap = running ? null : { point, at: e.timeStamp, type };
      if (running) handlers.walk(screenToWorld(point, camera), true);
      else handlers.walk(screenToWorld(point, camera));
    } else lastTap = null;
    pinch = null;
    if (canvas.hasPointerCapture?.(e.pointerId)) canvas.releasePointerCapture(e.pointerId);
  };
  const wheel = (e: WheelEvent) => {
    e.preventDefault();
    const rect = canvas.getBoundingClientRect();
    const delta = Math.max(-120, Math.min(120, e.deltaY * (e.deltaMode === 1 ? 16 : 1)));
    zoomCamera(camera, camera.zoom * Math.exp(-delta * 0.0015), {
      x: e.clientX - rect.left,
      y: e.clientY - rect.top,
    });
    camera.following = false;
    handlers.changed();
  };
  function listen(
    target: EventTarget,
    type: string,
    handler: EventListener,
    options?: AddEventListenerOptions
  ): void {
    target.addEventListener(type, handler, options);
    cleanups.push(() => target.removeEventListener(type, handler, options));
  }
  listen(window, 'keydown', keyDown as EventListener);
  listen(window, 'keyup', keyUp as EventListener);
  listen(window, 'blur', clear);
  listen(canvas, 'blur', clear);
  listen(document, 'visibilitychange', clear);
  listen(canvas, 'pointerdown', down as EventListener);
  listen(canvas, 'pointermove', move as EventListener);
  listen(canvas, 'pointerleave', () => handlers.hover?.(null));
  listen(canvas, 'pointerup', up as EventListener);
  listen(canvas, 'pointercancel', clear);
  listen(canvas, 'lostpointercapture', ((event: PointerEvent) => {
    // A normal pointerup already removed that contact. It must not cancel the
    // other finger when a pinch becomes a one-finger camera drag.
    if (contacts.has(event.pointerId)) clear();
  }) as EventListener);
  listen(canvas, 'dblclick', e => e.preventDefault());
  listen(canvas, 'wheel', wheel as EventListener, { passive: false });
  return {
    direction: () => {
      const result = { x: 0, y: 0 };
      for (const p of held.values()) {
        result.x += p.x;
        result.y += p.y;
      }
      return { x: Math.max(-1, Math.min(1, result.x)), y: Math.max(-1, Math.min(1, result.y)) };
    },
    hold: (source, p) => {
      if (!stopped) held.set(source, p);
    },
    release: source => {
      held.delete(source);
    },
    clear,
    dispose: () => {
      stopped = true;
      clear();
      for (const cleanup of cleanups) cleanup();
    },
  };
}
