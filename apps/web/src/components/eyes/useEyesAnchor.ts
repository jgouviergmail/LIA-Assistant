'use client';

/**
 * useEyesAnchor — computes the widget's DEFAULT docked position: centered
 * (both axes) between the chat header's search control
 * (`data-eyes-anchor-start` — carried by BOTH its responsive forms, the
 * first visible one wins) and the RAG-knowledge badge
 * (`data-eyes-anchor-end`).
 *
 * The horizontal clamp order is deliberate: NEVER overlap the end landmark
 * (click interception is an e2e-proven trap), then stay right of the start
 * one, then stay on screen. Only consulted while the user has no custom
 * position (drag/arrows override and persist). Re-measures on window resize,
 * when a landmark resizes (ResizeObserver), and on a slow interval — header
 * pills mount/unmount as the conversation evolves. Returns null when a
 * landmark is missing — the caller falls back to a CSS corner.
 */

import { useEffect, useState, type RefObject } from 'react';

/** Breathing room kept between the eyes and each landmark. */
const ANCHOR_MARGIN_PX = 8;
/** Slow safety re-measure — catches landmark mount/unmount (context pill). */
const REMEASURE_INTERVAL_MS = 1200;

export interface AnchorPosition {
  left: number;
  top: number;
}

/** Pure placement math (exported for direct testing). */
export function anchoredPosition(
  start: DOMRect,
  end: DOMRect,
  widget: { w: number; h: number }
): AnchorPosition {
  const midX = (start.right + end.left) / 2;
  const midY = (start.top + start.bottom + end.top + end.bottom) / 4;
  let left = midX - widget.w / 2;
  left = Math.max(left, start.right + ANCHOR_MARGIN_PX);
  // Applied LAST: clearing the delete button outranks every other wish.
  left = Math.min(left, end.left - ANCHOR_MARGIN_PX - widget.w);
  return {
    left: Math.max(ANCHOR_MARGIN_PX, left),
    top: Math.max(ANCHOR_MARGIN_PX, midY - widget.h / 2),
  };
}

export function useEyesAnchor(
  rootRef: RefObject<HTMLDivElement | null>,
  enabled: boolean
): AnchorPosition | null {
  const [position, setPosition] = useState<AnchorPosition | null>(null);

  useEffect(() => {
    // No sync setState on disable (ratchet): the return below derives null
    // instead; the possibly-stale state refreshes on the next enable's rAF.
    if (!enabled) return;
    // A landmark can exist in several responsive forms (the mobile search
    // toggle vs the desktop search field) — dock from the first VISIBLE one.
    const firstVisibleRect = (selector: string): DOMRect | null => {
      for (const el of document.querySelectorAll(selector)) {
        const rect = el.getBoundingClientRect();
        if (rect.width > 0 && rect.height > 0) return rect;
      }
      return null;
    };
    const measure = () => {
      const start = firstVisibleRect('[data-eyes-anchor-start]');
      const end = firstVisibleRect('[data-eyes-anchor-end]');
      if (!start || !end) {
        setPosition(prev => (prev === null ? prev : null));
        return;
      }
      const widgetRect = rootRef.current?.getBoundingClientRect();
      const next = anchoredPosition(start, end, {
        w: widgetRect?.width ?? 0,
        h: widgetRect?.height ?? 0,
      });
      setPosition(prev => (prev && prev.left === next.left && prev.top === next.top ? prev : next));
    };

    // Initial measure is scheduled (rAF): the widget must be laid out first,
    // and a sync setState in an effect trips the shrink-only ratchet.
    const raf = requestAnimationFrame(measure);
    window.addEventListener('resize', measure);
    const interval = setInterval(measure, REMEASURE_INTERVAL_MS);
    const observer = new ResizeObserver(measure);
    document
      .querySelectorAll('[data-eyes-anchor-start], [data-eyes-anchor-end]')
      .forEach(el => observer.observe(el));
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener('resize', measure);
      clearInterval(interval);
      observer.disconnect();
    };
  }, [enabled, rootRef]);

  return enabled ? position : null;
}
