'use client';

/**
 * ResizableDebugPanel — the debug panel beside the conversation, at the width
 * the person dragged it to (owner request 2026-09-24).
 *
 * A handle on the panel's left edge, in the gap: dragged, it widens the panel
 * INTO the conversation, which keeps its floor (`utils/panel-width.ts`); focused
 * — it is a window splitter, a real stop in the tab order (`PaneSeparator`) — the
 * arrows move it (Shift for larger steps), Home/End reach the bounds, Enter or a
 * double-click restores the default. The width is a preference of the DEVICE
 * (`debugPanelStore`), clamped to what the current row can hold and kept as
 * chosen, so a wider window gets it back. Resizing re-renders the frame only:
 * the panel itself arrives as `children`, an element this component never
 * rebuilds.
 */

import { useId, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { PaneSeparator } from '@/components/ui/pane-separator';
import { clampPaneWidth, type PaneBounds } from '@/lib/pane-width';
import { useDebugPanelStore } from '@/stores/debugPanelStore';

import { DEBUG_PANEL_WIDTH_DEFAULT, DEBUG_PANEL_WIDTH_STEP } from './utils/constants';
import { debugPanelBounds } from './utils/panel-width';

export function ResizableDebugPanel({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const stored = useDebugPanelStore(state => state.width);
  const setWidth = useDebugPanelStore(state => state.setWidth);
  const reset = useDebugPanelStore(state => state.reset);
  const frameRef = useRef<HTMLDivElement>(null);
  const panelId = useId();
  const [bounds, setBounds] = useState<PaneBounds>(() => debugPanelBounds(0));
  const width = clampPaneWidth(stored ?? DEBUG_PANEL_WIDTH_DEFAULT, bounds);

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

  return (
    <div ref={frameRef} className="relative flex-none" style={{ width }}>
      {/* The panel sits on the RIGHT: its left edge is the one that moves. */}
      <PaneSeparator
        edge="start"
        width={width}
        bounds={bounds}
        step={DEBUG_PANEL_WIDTH_STEP}
        label={t('chat.debug_panel.resize')}
        controls={panelId}
        onResize={setWidth}
        onReset={reset}
        className="absolute inset-y-0 -left-4 flex w-4 rounded-md"
      />
      <div
        id={panelId}
        className="h-full overflow-hidden rounded-xl border border-border/50 bg-background shadow-lg"
      >
        {children}
      </div>
    </div>
  );
}
