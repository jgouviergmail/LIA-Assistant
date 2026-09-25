'use client';

/**
 * ResizableDebugPanel — the debug panel beside the conversation, at the width
 * the person dragged it to (owner request 2026-09-24).
 *
 * A handle on the panel's left edge, in the gap: dragged, it widens the panel
 * INTO the conversation, which keeps its floor (`utils/panel-width.ts`); focused
 * — it is a window splitter, a real stop in the tab order — the arrows move it
 * (Shift for larger steps), Home/End reach the bounds, Enter or a double-click
 * restores the default. The width is a preference of the DEVICE
 * (`debugPanelStore`), clamped to what the current row can hold and kept as
 * chosen, so a wider window gets it back. Resizing re-renders the frame only:
 * the panel itself arrives as `children`, an element this component never
 * rebuilds.
 */

import {
  useCallback,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent,
  type ReactNode,
} from 'react';
import { useTranslation } from 'react-i18next';

import { useDebugPanelStore } from '@/stores/debugPanelStore';

import { DEBUG_PANEL_WIDTH_DEFAULT, DEBUG_PANEL_WIDTH_STEP } from './utils/constants';
import { clampPanelWidth, debugPanelBounds, type PanelWidthBounds } from './utils/panel-width';

type WidthMove = (width: number, step: number, bounds: PanelWidthBounds) => number;

/** The panel sits on the RIGHT: moving its left edge left widens it. */
const KEY_MOVES: Record<string, WidthMove> = {
  ArrowLeft: (width, step) => width + step,
  ArrowRight: (width, step) => width - step,
  Home: (_width, _step, bounds) => bounds.min,
  End: (_width, _step, bounds) => bounds.max,
};

interface DragStart {
  clientX: number;
  width: number;
}

export function ResizableDebugPanel({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const stored = useDebugPanelStore(state => state.width);
  const setWidth = useDebugPanelStore(state => state.setWidth);
  const reset = useDebugPanelStore(state => state.reset);
  const frameRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<DragStart | null>(null);
  const panelId = useId();
  const [bounds, setBounds] = useState<PanelWidthBounds>(() => debugPanelBounds(0));
  const width = clampPanelWidth(stored ?? DEBUG_PANEL_WIDTH_DEFAULT, bounds);

  // Measure the row holding the conversation and the panel, and follow it: a
  // resized window or a folded sidebar changes how wide the panel may be.
  useLayoutEffect(() => {
    const row = frameRef.current?.parentElement;
    if (!row) return;
    const measure = () => setBounds(debugPanelBounds(row.getBoundingClientRect().width));
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(row);
    return () => observer.disconnect();
  }, []);

  const commit = useCallback(
    (next: number) => setWidth(clampPanelWidth(next, bounds)),
    [bounds, setWidth]
  );

  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    event.currentTarget.setPointerCapture(event.pointerId);
    dragRef.current = { clientX: event.clientX, width };
  };
  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    const start = dragRef.current;
    if (start) commit(start.width + start.clientX - event.clientX);
  };
  const endDrag = (event: PointerEvent<HTMLDivElement>) => {
    dragRef.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  };
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      reset();
      return;
    }
    const move = KEY_MOVES[event.key];
    if (!move) return;
    event.preventDefault();
    commit(move(width, DEBUG_PANEL_WIDTH_STEP * (event.shiftKey ? 4 : 1), bounds));
  };

  return (
    <div ref={frameRef} className="relative flex-none" style={{ width }}>
      <div
        role="separator"
        aria-orientation="vertical"
        aria-label={t('chat.debug_panel.resize')}
        aria-controls={panelId}
        aria-valuenow={width}
        aria-valuemin={bounds.min}
        aria-valuemax={bounds.max}
        tabIndex={0}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        onDoubleClick={reset}
        onKeyDown={onKeyDown}
        className="group absolute inset-y-0 -left-4 z-10 flex w-4 cursor-col-resize touch-none items-center justify-center rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <span
          aria-hidden="true"
          className="h-12 w-1 rounded-full bg-border transition-colors group-hover:bg-primary/60 group-focus-visible:bg-primary"
        />
      </div>
      <div
        id={panelId}
        className="h-full overflow-hidden rounded-xl border border-border/50 bg-background shadow-lg"
      >
        {children}
      </div>
    </div>
  );
}
