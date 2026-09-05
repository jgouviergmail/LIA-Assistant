'use client';

/**
 * useEyesDrag — pointer drag, keyboard moves and position persistence for the
 * eyes widget. Extracted from EyesWidget as a cohesive unit (the CC ratchet
 * is shrink-only; the widget keeps rendering concerns, this hook keeps the
 * geometry state machine).
 *
 * Contract:
 *  - pointer: capture on the surface (toolbar buttons excluded by the caller
 *    structure — they are <button>s), < DRAG_THRESHOLD_PX of travel stays a
 *    click, a real drag commits the position as viewport percentages
 *  - keyboard: arrow keys move by fixed steps from the current spot
 *  - a committed position is re-clamped on screen at mount and on resize
 *    (change-guarded: an unconditional commit would loop — commit stores a
 *    fresh object, which re-runs the effect)
 *  - `wasRecentDrag()` lets the caller suppress the dblclick wink right
 *    after a drop
 */

import { useCallback, useEffect, useRef, useState, type RefObject } from 'react';

import { useEyesWidgetStore, type EyesSurface } from '@/stores/eyesWidgetStore';

/** Pointer travel below this stays a click (enables the dblclick wink). */
export const DRAG_THRESHOLD_PX = 5;
/** Arrow-key move step. */
export const KEYBOARD_STEP_PX = 16;
/** A dblclick landing this soon after a drag drop is not a wink request. */
export const DRAG_DBLCLICK_SUPPRESS_MS = 400;

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

export interface EyesDrag {
  /** Live pixel position during a drag (null → committed store position). */
  dragPos: PixelPosition | null;
  onPointerDown: (e: React.PointerEvent<HTMLDivElement>) => void;
  onPointerMove: (e: React.PointerEvent<HTMLDivElement>) => void;
  onPointerUp: (e: React.PointerEvent<HTMLDivElement>) => void;
  onKeyDown: (e: React.KeyboardEvent<HTMLDivElement>) => void;
  /** True right after a drag drop (dblclick-wink suppression window). */
  wasRecentDrag: () => boolean;
}

export function useEyesDrag(
  rootRef: RefObject<HTMLDivElement | null>,
  surface: EyesSurface = 'chat'
): EyesDrag {
  // Each surface keeps its own spot (see `EyesSurface`).
  const position = useEyesWidgetStore(s =>
    surface === 'landing' ? s.landingPosition : s.position
  );
  const setPosition = useEyesWidgetStore(s =>
    surface === 'landing' ? s.setLandingPosition : s.setPosition
  );

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

  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    // Toolbar buttons keep their own semantics — only the surface drags.
    if ((e.target as HTMLElement).closest('button')) return;
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

  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
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

  const onPointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
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

  const onKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
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
