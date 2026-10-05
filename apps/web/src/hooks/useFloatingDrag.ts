'use client';

/**
 * useFloatingDrag — pointer drag, keyboard moves and re-clamping for a
 * floating widget whose position is stored as viewport percentages.
 *
 * Extracted from the eyes widget's drag hook (ADR-277) so the shortcuts dock
 * moves exactly as the eyes do — one geometry state machine, two widgets.
 * The hook owns no store: the caller hands it the committed position and the
 * setter, so each widget keeps its own persisted slot.
 *
 * Contract:
 *  - pointer: capture on the surface; a press on an interactive DESCENDANT
 *    (a button, a link, a field) is never a drag — those keep their own
 *    semantics — while a surface that is itself a button (a folded widget)
 *    drags like any other; < DRAG_THRESHOLD_PX of travel stays a click, a
 *    real drag commits the position as viewport percentages
 *  - keyboard: arrow keys on the SURFACE ITSELF move it by fixed steps — not
 *    from a focused descendant, where the arrows belong to the control
 *  - viewport corrections are temporary; only a human move writes preferences
 *  - `wasRecentDrag()` lets the caller suppress a click-like gesture right
 *    after a drop (the eyes' dblclick wink, the dock's tap)
 */

import {
  useCallback,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
  type RefObject,
} from 'react';

/** Pointer travel below this stays a click. */
export const DRAG_THRESHOLD_PX = 5;
/** Arrow-key move step. */
export const KEYBOARD_STEP_PX = 16;
/** A click-like gesture landing this soon after a drag drop is not one. */
export const DRAG_DBLCLICK_SUPPRESS_MS = 400;

/** What a press on one of these starts is theirs, never a drag. */
const INTERACTIVE_SELECTOR = 'button, a, input, select, textarea, [role="button"]';

import {
  clampToViewport,
  type FloatingPosition,
  type PixelPosition,
} from '@/lib/floating-position';
import { createFloatingLayout } from './floating-layout';
export { clampToViewport } from '@/lib/floating-position';
export type { FloatingPosition, PixelPosition } from '@/lib/floating-position';

export interface FloatingDrag<T extends HTMLElement = HTMLElement> {
  /** Live pixel position during a drag (null → committed position). */
  dragPos: PixelPosition | null;
  /** Visible layout position; keyboard/pan/rotation never overwrites the saved spot. */
  displayPos: PixelPosition | null;
  onPointerDown: (e: React.PointerEvent<T>) => void;
  onPointerMove: (e: React.PointerEvent<T>) => void;
  onPointerUp: (e: React.PointerEvent<T>) => void;
  onKeyDown: (e: React.KeyboardEvent<T>) => void;
  /** True right after a drag drop (click-suppression window). */
  wasRecentDrag: () => boolean;
}

/**
 * Drive a floating widget.
 *
 * Args:
 *   rootRef: The surface that is dragged — its rect is the widget's size.
 *   position: The committed position, or null for the caller's default spot.
 *   setPosition: Where a committed position goes (a persisted store slot).
 *
 * Returns:
 *   The handlers to spread on the surface, the live drag position and the
 *   recent-drop predicate.
 */
export function useFloatingDrag<T extends HTMLElement>(
  rootRef: RefObject<T | null>,
  position: FloatingPosition | null,
  setPosition: (position: FloatingPosition) => void,
  active = true,
  bottomAnchorHeight = 0
): FloatingDrag<T> {
  const [dragPos, setDragPos] = useState<PixelPosition | null>(null);
  const lastDragEndRef = useRef(0);
  const dragStateRef = useRef<{
    pointerId: number;
    startX: number;
    startY: number;
    originX: number;
    originY: number;
    moved: boolean;
    position: PixelPosition | null;
  } | null>(null);

  const commitPosition = useCallback(
    (pos: PixelPosition) => {
      setPosition({
        xPct: window.innerWidth > 0 ? (pos.x / window.innerWidth) * 100 : 0,
        yPct: window.innerHeight > 0 ? (pos.y / window.innerHeight) * 100 : 0,
      });
    },
    [setPosition]
  );

  const layout = useMemo(
    () => createFloatingLayout(position, active, bottomAnchorHeight),
    [active, position, bottomAnchorHeight]
  );
  // A folded/unfolded or hidden/restored surface can replace the ref's node.
  // Check attachment after commits; an unchanged node performs no layout read.
  useLayoutEffect(() => layout.refreshElement(rootRef.current));
  const measured = useSyncExternalStore(layout.subscribe, layout.getSnapshot, () => '');
  const displayPos = useMemo(() => {
    const [x, y] = measured.split(',').map(Number);
    return dragPos ?? (measured ? { x, y } : null);
  }, [dragPos, measured]);

  /** Current top-left in pixels (custom position or measured default spot). */
  const currentPixelPosition = useCallback((): PixelPosition => {
    if (displayPos) return displayPos;
    if (position) {
      return {
        x: (position.xPct / 100) * window.innerWidth,
        y: (position.yPct / 100) * window.innerHeight,
      };
    }
    const rect = rootRef.current?.getBoundingClientRect();
    return rect ? { x: rect.left, y: rect.top } : { x: 0, y: 0 };
  }, [displayPos, position, rootRef]);

  const onPointerDown = (e: React.PointerEvent<T>) => {
    // Interactive DESCENDANTS keep their own semantics — only the surface
    // drags. The surface itself may be a button (a folded widget is one): a
    // press on it is a drag when it travels, a click when it does not.
    const hit = (e.target as HTMLElement).closest(INTERACTIVE_SELECTOR);
    if (hit && hit !== rootRef.current) return;
    const rect = rootRef.current?.getBoundingClientRect();
    if (!rect) return;
    dragStateRef.current = {
      pointerId: e.pointerId,
      startX: e.clientX,
      startY: e.clientY,
      originX: rect.left,
      originY: rect.top,
      moved: false,
      position: null,
    };
    rootRef.current?.setPointerCapture?.(e.pointerId);
  };

  const onPointerMove = (e: React.PointerEvent<T>) => {
    const drag = dragStateRef.current;
    if (!drag || drag.pointerId !== e.pointerId) return;
    const dx = e.clientX - drag.startX;
    const dy = e.clientY - drag.startY;
    if (!drag.moved && Math.hypot(dx, dy) < DRAG_THRESHOLD_PX) return;
    drag.moved = true;
    const rect = rootRef.current?.getBoundingClientRect();
    drag.position = clampToViewport(
      { x: drag.originX + dx, y: drag.originY + dy },
      { w: rect?.width ?? 0, h: rect?.height ?? 0 }
    );
    setDragPos(drag.position);
  };

  const onPointerUp = (e: React.PointerEvent<T>) => {
    const drag = dragStateRef.current;
    if (!drag || drag.pointerId !== e.pointerId) return;
    dragStateRef.current = null;
    rootRef.current?.releasePointerCapture?.(e.pointerId);
    if (drag.moved && drag.position) {
      commitPosition(drag.position);
      lastDragEndRef.current = Date.now();
    }
    setDragPos(null);
  };

  const onKeyDown = (e: React.KeyboardEvent<T>) => {
    // A focused link or button inside the widget owns its arrow keys.
    if (e.target !== e.currentTarget) return;
    const steps: Record<string, [number, number]> = {
      ArrowLeft: [-KEYBOARD_STEP_PX, 0],
      ArrowRight: [KEYBOARD_STEP_PX, 0],
      ArrowUp: [0, -KEYBOARD_STEP_PX],
      ArrowDown: [0, KEYBOARD_STEP_PX],
    };
    const step = steps[e.key];
    if (!step) return;
    e.preventDefault();
    const rect = rootRef.current?.getBoundingClientRect();
    const pos = currentPixelPosition();
    commitPosition(
      clampToViewport(
        { x: pos.x + step[0], y: pos.y + step[1] },
        { w: rect?.width ?? 0, h: rect?.height ?? 0 }
      )
    );
  };

  const wasRecentDrag = useCallback(
    () => Date.now() - lastDragEndRef.current < DRAG_DBLCLICK_SUPPRESS_MS,
    []
  );

  return {
    dragPos,
    displayPos,
    onPointerDown,
    onPointerMove,
    onPointerUp,
    onKeyDown,
    wasRecentDrag,
  };
}
