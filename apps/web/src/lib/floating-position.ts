/** Device placement preferences; temporary visual viewport corrections live in the hook. */
export interface FloatingPosition {
  xPct: number;
  yPct: number;
}
export interface PixelPosition {
  x: number;
  y: number;
}

/** Clamp against the visible viewport, including the mobile keyboard's pan. */
export function clampToViewport(pos: PixelPosition, size: { w: number; h: number }): PixelPosition {
  const viewport = window.visualViewport;
  const left = viewport?.offsetLeft ?? 0;
  const top = viewport?.offsetTop ?? 0;
  return {
    x: Math.min(
      Math.max(left, pos.x),
      Math.max(left, left + (viewport?.width ?? window.innerWidth) - size.w)
    ),
    y: Math.min(
      Math.max(top, pos.y),
      Math.max(top, top + (viewport?.height ?? window.innerHeight) - size.h)
    ),
  };
}
export function normalizeFloatingPosition(value: unknown): FloatingPosition | null {
  if (!value || typeof value !== 'object' || !('xPct' in value) || !('yPct' in value)) return null;
  if (
    typeof value.xPct !== 'number' ||
    typeof value.yPct !== 'number' ||
    !Number.isFinite(value.xPct) ||
    !Number.isFinite(value.yPct)
  )
    return null;
  return {
    xPct: Math.min(100, Math.max(0, value.xPct)),
    yPct: Math.min(100, Math.max(0, value.yPct)),
  };
}
export function sameFloatingPosition(
  a: FloatingPosition | null,
  b: FloatingPosition | null
): boolean {
  return a?.xPct === b?.xPct && a?.yPct === b?.yPct;
}
