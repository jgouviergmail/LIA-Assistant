'use client';

/**
 * PaneSeparator — the window splitter for a pane a person sizes by hand (the
 * debug panel, the « Tools » panes).
 *
 * A WAI-ARIA « separator » that is a real stop in the tab order: dragged, it
 * moves the pane's edge; focused, the arrows move it (Shift for larger steps),
 * Home/End reach the bounds, Enter or a double-click restores the default.
 * Which way widens depends on the edge it sits on: on a pane's right edge
 * (`end`) moving right widens it, on its left edge (`start`) moving left does.
 * The width belongs to the caller; this only proposes the next one, always
 * inside the bounds.
 */

import { useRef, type KeyboardEvent, type PointerEvent } from 'react';

import { clampPaneWidth, type PaneBounds } from '@/lib/pane-width';
import { cn } from '@/lib/utils';

export interface PaneSeparatorProps {
  /** The edge of the pane it sits on: `end` its right edge, `start` its left one. */
  edge: 'start' | 'end';
  /** The pane's width now. */
  width: number;
  bounds: PaneBounds;
  /** One arrow press, in pixels (four with Shift). */
  step: number;
  /** Already translated: names the pane it sizes. */
  label: string;
  /** The pane's id. */
  controls: string;
  onResize: (width: number) => void;
  onReset: () => void;
  /** Where it sits: position, hit area and visibility are the caller's. */
  className?: string;
}

interface DragStart {
  clientX: number;
  width: number;
}

export function PaneSeparator({
  edge,
  width,
  bounds,
  step,
  label,
  controls,
  onResize,
  onReset,
  className,
}: PaneSeparatorProps) {
  const dragRef = useRef<DragStart | null>(null);
  // Moving right widens a pane whose right edge this is; left, one whose left edge it is.
  const widening = edge === 'end' ? 1 : -1;
  const propose = (next: number) => onResize(clampPaneWidth(next, bounds));

  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    event.currentTarget.setPointerCapture(event.pointerId);
    dragRef.current = { clientX: event.clientX, width };
  };
  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    const start = dragRef.current;
    if (start) propose(start.width + widening * (event.clientX - start.clientX));
  };
  const endDrag = (event: PointerEvent<HTMLDivElement>) => {
    dragRef.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  };
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const stride = step * (event.shiftKey ? 4 : 1);
    const moves: Record<string, () => number> = {
      ArrowRight: () => width + widening * stride,
      ArrowLeft: () => width - widening * stride,
      Home: () => bounds.min,
      End: () => bounds.max,
    };
    if (event.key === 'Enter') {
      event.preventDefault();
      onReset();
      return;
    }
    const move = moves[event.key];
    if (!move) return;
    event.preventDefault();
    propose(move());
  };

  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label={label}
      aria-controls={controls}
      aria-valuenow={width}
      aria-valuemin={bounds.min}
      aria-valuemax={bounds.max}
      tabIndex={0}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={endDrag}
      onPointerCancel={endDrag}
      onDoubleClick={onReset}
      onKeyDown={onKeyDown}
      className={cn(
        'group z-10 cursor-col-resize touch-none items-center justify-center focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        className
      )}
    >
      <span
        aria-hidden="true"
        className="h-12 w-1 rounded-full bg-border transition-colors group-hover:bg-primary/60 group-focus-visible:bg-primary"
      />
    </div>
  );
}
