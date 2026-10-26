'use client';

import { useCallback, useEffect, useRef } from 'react';

/** A private dialog's resumed focus scope must not discard the person's place. */
export function useWorldVerificationFocus(
  hidden: boolean,
  changed: boolean,
  refetch: () => Promise<void>
) {
  const bookmark = useRef<HTMLElement | null>(null);
  const verify = useCallback(async () => {
    // A confirmed foreign owner stays withdrawn until explicit document reload.
    // Further focus checks must not remove the focused recovery action.
    if (changed) return;
    const active = document.activeElement;
    if (!bookmark.current && active instanceof HTMLElement && active !== document.body)
      bookmark.current = active;
    await refetch();
  }, [changed, refetch]);
  useEffect(() => {
    if (changed) bookmark.current = null;
    if (hidden || !bookmark.current) return;
    const target = bookmark.current;
    bookmark.current = null;
    const frame = requestAnimationFrame(() => {
      if (!document.hasFocus()) return;
      const active = document.activeElement;
      const resumedDialog = target.closest('[role="dialog"]')?.contains(active);
      if (!target.isConnected || (active !== document.body && !resumedDialog)) return;
      if (typeof target.checkVisibility === 'function' && !target.checkVisibility()) return;
      target.focus({ preventScroll: true });
    });
    return () => cancelAnimationFrame(frame);
  }, [changed, hidden]);
  return verify;
}
