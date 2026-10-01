/**
 * Where the framed player goes (ADR-330 amendment): the slot's rect in
 * DOCUMENT coordinates, so a `position: absolute` player scrolls with the
 * page natively and is only re-measured when the layout moves.
 */

export interface RectLike {
  top: number;
  left: number;
  width: number;
  height: number;
}

export interface Placement {
  top: number;
  left: number;
  width: number;
  height: number;
}

/** The slot's viewport rect plus the scroll offsets, rounded to the pixel. */
export function placementFor(rect: RectLike, scrollX: number, scrollY: number): Placement {
  return {
    top: Math.round(rect.top + scrollY),
    left: Math.round(rect.left + scrollX),
    width: Math.round(rect.width),
    height: Math.round(rect.height),
  };
}
