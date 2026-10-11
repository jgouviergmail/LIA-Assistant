/** Free rectangles around selected text, in layout-viewport coordinates. */
export interface SelectionRect {
  top: number;
  left: number;
  width: number;
  bottom: number;
}

export interface SelectionViewport {
  top: number;
  left: number;
  width: number;
  height: number;
}

const MARGIN = 8;
const GAP = 8;

const clamp = (value: number, min: number, max: number) => Math.max(min, Math.min(value, max));

export function selectionViewport(): SelectionViewport {
  const viewport = window.visualViewport;
  return {
    top: viewport?.offsetTop ?? 0,
    left: viewport?.offsetLeft ?? 0,
    width: viewport?.width ?? window.innerWidth,
    height: viewport?.height ?? window.innerHeight,
  };
}

/** Prefer above/below; constrain and scroll the menu when no full-size slot fits. */
export function selectionMenuSpace(
  anchor: SelectionRect,
  size: { width: number; height: number },
  viewport: SelectionViewport
) {
  const left = viewport.left + MARGIN;
  const top = viewport.top + MARGIN;
  const right = viewport.left + viewport.width - MARGIN;
  const bottom = viewport.top + viewport.height - MARGIN;
  const anchorRight = anchor.left + anchor.width;
  if (anchor.bottom < top || anchor.top > bottom || anchorRight < left || anchor.left > right)
    return null;

  const spaces = [
    { side: 'above', left, top, right, bottom: Math.min(bottom, anchor.top - GAP) },
    { side: 'below', left, top: Math.max(top, anchor.bottom + GAP), right, bottom },
    { side: 'right', left: Math.max(left, anchorRight + GAP), top, right, bottom },
    { side: 'left', left, top, right: Math.min(right, anchor.left - GAP), bottom },
  ].map(space => ({
    ...space,
    width: Math.max(0, space.right - space.left),
    height: Math.max(0, space.bottom - space.top),
  }));
  const full = spaces.find(space => space.width >= size.width && space.height >= size.height);
  // Avoid unusable slivers: the smallest interactive control needs a free slot.
  const usable = spaces.filter(space => space.width >= 40 && space.height >= 40);
  return (
    full ??
    usable.sort(
      (a, b) =>
        Math.min(b.width, size.width) * Math.min(b.height, size.height) -
        Math.min(a.width, size.width) * Math.min(a.height, size.height)
    )[0] ??
    null
  );
}

export function placeSelectionMenu(
  anchor: SelectionRect,
  size: { width: number; height: number },
  space: NonNullable<ReturnType<typeof selectionMenuSpace>>
) {
  const left =
    space.side === 'left'
      ? space.right - size.width
      : space.side === 'right'
        ? space.left
        : clamp(anchor.left, space.left, space.right - size.width);
  const top =
    space.side === 'above'
      ? space.bottom - size.height
      : space.side === 'below'
        ? space.top
        : clamp(anchor.top, space.top, space.bottom - size.height);
  return { left, top };
}
