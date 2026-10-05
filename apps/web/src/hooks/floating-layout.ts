import { clampToViewport, type FloatingPosition } from '@/lib/floating-position';

/** DOM is sampled by geometry events and attachment, never by React's getSnapshot. */
export function createFloatingLayout(
  position: FloatingPosition | null,
  active: boolean,
  bottomAnchorHeight: number
) {
  let snapshot = '';
  let target: HTMLElement | null = null;
  let observer: ResizeObserver | null = null;
  let changed = () => {};
  const measure = () => {
    const rect = target?.getBoundingClientRect();
    if (!position || !rect) return;
    const point = clampToViewport(
      {
        x: (position.xPct / 100) * window.innerWidth,
        y:
          (position.yPct / 100) * window.innerHeight -
          (bottomAnchorHeight ? Math.max(0, rect.height - bottomAnchorHeight) : 0),
      },
      { w: rect.width, h: rect.height }
    );
    const next = `${point.x},${point.y}`;
    if (next === snapshot) return;
    snapshot = next;
    changed();
  };
  const refreshElement = (element: HTMLElement | null) => {
    const next = active && position ? element : null;
    if (next === target) return;
    observer?.disconnect();
    target = next;
    if (target) observer?.observe(target);
    measure();
  };
  return {
    getSnapshot: () => snapshot,
    refreshElement,
    subscribe(listener: () => void) {
      changed = listener;
      if (!active || !position) return () => {};
      const viewport = window.visualViewport;
      observer = typeof ResizeObserver === 'function' ? new ResizeObserver(measure) : null;
      if (target) observer?.observe(target);
      window.addEventListener('resize', measure);
      viewport?.addEventListener('resize', measure);
      viewport?.addEventListener('scroll', measure);
      return () => {
        changed = () => {};
        observer?.disconnect();
        observer = null;
        target = null;
        window.removeEventListener('resize', measure);
        viewport?.removeEventListener('resize', measure);
        viewport?.removeEventListener('scroll', measure);
      };
    },
  };
}
