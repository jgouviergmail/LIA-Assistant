'use client';

/**
 * useDrillDownFocus — the focus of a list whose detail opens beside it or in
 * its place (ADR-369).
 *
 * When a detail opens, `opened` takes the focus (the way back of a detail that
 * replaced the list); when it closes — whichever way: its own link, the
 * browser's back, the URL — the row that opened it gets the focus back, else
 * `fallback`. Where list and detail stay side by side the caller passes
 * `enabled: false`: nothing is moved there.
 */
import { type RefObject, useCallback, useEffect, useRef } from 'react';

export interface DrillDownFocusOptions {
  /** Whether the focus follows the detail at all (e.g. only below `lg`). */
  enabled?: boolean;
  /** What takes the focus when a detail opens; nothing moves when absent. */
  opened?: RefObject<HTMLElement | null>;
  /** What takes it back when the row that opened the detail is gone. */
  fallback?: RefObject<HTMLElement | null>;
}

/**
 * @param openId - The open detail's id, or null.
 * @param options - See `DrillDownFocusOptions`.
 * @returns The ref callback each row hands its link to, with its id.
 */
export function useDrillDownFocus(
  openId: string | null,
  { enabled = true, opened, fallback }: DrillDownFocusOptions = {}
): (id: string, element: HTMLElement | null) => void {
  const rows = useRef(new Map<string, HTMLElement>());
  const last = useRef(openId);
  const rowRef = useCallback((id: string, element: HTMLElement | null) => {
    if (element) rows.current.set(id, element);
    else rows.current.delete(id);
  }, []);

  useEffect(() => {
    const closed = last.current;
    last.current = openId;
    if (!enabled || openId === closed) return;
    if (openId) opened?.current?.focus({ preventScroll: true });
    else if (closed) (rows.current.get(closed) ?? fallback?.current)?.focus({ preventScroll: true });
  }, [openId, enabled, opened, fallback]);

  return rowRef;
}
