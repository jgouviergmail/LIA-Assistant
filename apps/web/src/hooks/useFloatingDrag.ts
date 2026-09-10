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
 *  - a committed position is re-clamped on screen at mount and on resize
 *    (change-guarded: an unconditional commit would loop — commit stores a
 *    fresh object, which re-runs the effect)
 *  - `wasRecentDrag()` lets the caller suppress a click-like gesture right
 *    after a drop (the eyes' dblclick wink, the dock's tap)
 */

import { useCallback, useEffect, useRef, useState, type RefObject } from 'react';

/** Pointer travel below this stays a click. */
export const DRAG_THRESHOLD_PX = 5;
/** Arrow-key move step. */
export const KEYBOARD_STEP_PX = 16;
/** A click-like gesture landing this soon after a drag drop is not one. */
export const DRAG_DBLCLICK_SUPPRESS_MS = 400;

/** What a press on one of these starts is theirs, never a drag. */
const INTERACTIVE_SELECTOR = 'button, a, input, select, textarea, [role="button"]';

/** Widget anchor position as percentages of the viewport (top-left corner). */
export interface FloatingPosition {
  xPct: number;
  yPct: number;
}

export interface PixelPosition {
  x: number;
  y: number;
}

/** Clamp a top-left pixel position so the widget stays fully on screen. */
export function clampToViewport(pos: PixelPosition, size: { w: number; h: number }): PixelPosition {
  return {
    x: Math.min(Math.max(0, pos.x), Math.max(0, window.innerWidth - size.w)),
    y: Math.min(Math.max(0, pos.y), Math.max(0, window.innerHeight - size.h)),
  };
}

export interface FloatingDrag<T extends HTMLElement = HTMLElement> {
  /** Live pixel position during a drag (null → committed position). */
  dragPos: PixelPosition | null;
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
  setPosition: (position: FloatingPosition) => void
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

  /** Current top-left in pixels (custom position or measured default spot). */
  const currentPixelPosition = useCallback((): PixelPosition => {
    if (dragPos) return dragPos;
    if (position) {
      return {
        x: (position.xPct / 100) * window.innerWidth,
        y: (position.yPct / 100) * window.innerHeight,
      };
    }
    const rect = rootRef.current?.getBoundingClientRect();
    return rect ? { x: rect.left, y: rect.top } : { x: 0, y: 0 };
  }, [dragPos, position, rootRef]);

  // Re-clamp a custom position on screen — at mount (a position saved on a
  // larger screen may sit off this viewport) and on every resize/rotation.
  useEffect(() => {
    if (!position) return;
    const reclamp = () => {
      const rect = rootRef.current?.getBoundingClientRect();
      const raw = {
        x: (position.xPct / 100) * window.innerWidth,
        y: (position.yPct / 100) * window.innerHeight,
      };
      const clamped = clampToViewport(raw, { w: rect?.width ?? 0, h: rect?.height ?? 0 });
      if (Math.abs(clamped.x - raw.x) > 0.5 || Math.abs(clamped.y - raw.y) > 0.5) {
        commitPosition(clamped);
      }
    };
    reclamp();
    window.addEventListener('resize', reclamp);
    return () => window.removeEventListener('resize', reclamp);
  }, [position, commitPosition, rootRef]);

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
    setDragPos(
      clampToViewport(
        { x: drag.originX + dx, y: drag.originY + dy },
        { w: rect?.width ?? 0, h: rect?.height ?? 0 }
      )
    );
  };

  const onPointerUp = (e: React.PointerEvent<T>) => {
    const drag = dragStateRef.current;
    if (!drag || drag.pointerId !== e.pointerId) return;
    dragStateRef.current = null;
    rootRef.current?.releasePointerCapture?.(e.pointerId);
    if (drag.moved && dragPos) {
      commitPosition(dragPos);
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

  return { dragPos, onPointerDown, onPointerMove, onPointerUp, onKeyDown, wasRecentDrag };
}
