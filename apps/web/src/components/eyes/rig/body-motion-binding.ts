/** Event-driven travel bounds and interaction priority; no animation clock. */
import { bodyMotionSpace, type BodyBox, type BodyViewport } from '../body-motion-geometry';
import type { EyeRig } from './runtime';
import type { RigWriter } from './apply';

export function bindBodyMotion(
  element: HTMLElement,
  rig: EyeRig,
  writer: RigWriter,
  wake: () => void
): () => void {
  const host = element.closest<HTMLElement>('.lia-eyes-widget');
  const measure = () => {
    const rect = element.getBoundingClientRect();
    const fontSize = parseFloat(getComputedStyle(element).fontSize) || 16;
    const box: BodyBox = {
      left: rect.left,
      top: rect.top,
      width: rect.width,
      height: rect.height,
      fontSize,
    };
    const visible = window.visualViewport;
    const viewport: BodyViewport = host
      ? {
          left: visible?.offsetLeft ?? 0,
          top: visible?.offsetTop ?? 0,
          width: visible?.width ?? window.innerWidth,
          height: visible?.height ?? window.innerHeight,
        }
      : {
          // Local previews need room for the diagonal of a full revolution;
          // bodyMotionSpace still caps their translation at 0.7 em.
          left: box.left - fontSize * 2.4,
          top: box.top - fontSize * 2.4,
          width: box.width + fontSize * 4.8,
          height: box.height + fontSize * 4.8,
        };
    rig.setBodySpace(bodyMotionSpace(box, viewport, Boolean(host)));
    writer.setBodyFrame(box, viewport);
    // A suspended clock still needs the new layout painted after re-clamping.
    writer.write(rig.values());
    wake();
  };
  const resize = typeof ResizeObserver === 'function' ? new ResizeObserver(measure) : null;
  resize?.observe(element);
  measure();
  // A comparison card has local geometry only. It neither listens to every
  // document interaction nor measures the viewport whenever the page scrolls.
  if (!host) return () => resize?.disconnect();

  let hovered = host.matches(':hover');
  let pressed = false;
  let focused = host.contains(document.activeElement);
  const syncPriority = () => {
    rig.setLifePaused(hovered || pressed || focused);
    wake();
  };
  syncPriority();
  const enter = () => {
    hovered = true;
    syncPriority();
  };
  const leave = () => {
    hovered = false;
    syncPriority();
  };
  const down = () => {
    pressed = true;
    syncPriority();
  };
  const up = () => {
    pressed = false;
    syncPriority();
  };
  const focus = () => {
    focused = true;
    syncPriority();
  };
  const blur = (event: FocusEvent) => {
    focused = !!(event.relatedTarget instanceof Node && host.contains(event.relatedTarget));
    syncPriority();
  };
  const userActivity = () => {
    rig.pauseLifeFor(1500);
    wake();
  };
  const events = ['pointerdown', 'keydown', 'wheel'] as const;
  for (const name of events)
    document.addEventListener(name, userActivity, { capture: true, passive: true });
  host.addEventListener('pointerenter', enter);
  host.addEventListener('pointerleave', leave);
  host.addEventListener('pointerdown', down);
  document.addEventListener('pointerup', up);
  document.addEventListener('pointercancel', up);
  host.addEventListener('focusin', focus);
  host.addEventListener('focusout', blur);
  window.addEventListener('resize', measure);
  document.addEventListener('scroll', measure, { capture: true, passive: true });
  window.visualViewport?.addEventListener('resize', measure);
  window.visualViewport?.addEventListener('scroll', measure);
  const anchor = typeof MutationObserver === 'function' ? new MutationObserver(measure) : null;
  anchor?.observe(host, {
    attributes: true,
    attributeFilter: ['style', 'class', 'data-dragging'],
  });
  return () => {
    resize?.disconnect();
    anchor?.disconnect();
    for (const name of events) document.removeEventListener(name, userActivity, true);
    host.removeEventListener('pointerenter', enter);
    host.removeEventListener('pointerleave', leave);
    host.removeEventListener('pointerdown', down);
    document.removeEventListener('pointerup', up);
    document.removeEventListener('pointercancel', up);
    host.removeEventListener('focusin', focus);
    host.removeEventListener('focusout', blur);
    window.removeEventListener('resize', measure);
    document.removeEventListener('scroll', measure, true);
    window.visualViewport?.removeEventListener('resize', measure);
    window.visualViewport?.removeEventListener('scroll', measure);
  };
}
