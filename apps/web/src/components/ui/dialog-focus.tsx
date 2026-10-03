'use client';

import { createContext, useContext, useRef } from 'react';

export const DialogModalContext = createContext(true);

/** Manual modal openers have no Radix Trigger; non-modal outside focus stays untouched. */
export function useDialogFocusReturn(
  onOpenAutoFocus?: (event: Event) => void,
  onCloseAutoFocus?: (event: Event) => void
) {
  const modal = useContext(DialogModalContext);
  const opener = useRef<HTMLElement | null>(null);
  return {
    onOpenAutoFocus(event: Event) {
      const active = document.activeElement;
      opener.current = active instanceof HTMLElement && active !== document.body ? active : null;
      onOpenAutoFocus?.(event);
    },
    onCloseAutoFocus(event: Event) {
      onCloseAutoFocus?.(event);
      if (!modal || event.defaultPrevented) return;
      const active = document.activeElement;
      // Completed actions can deliberately focus the surviving panel before
      // closing. Preserve that destination rather than returning to its old row.
      if (
        active instanceof HTMLElement &&
        active !== document.body &&
        event.target instanceof Node &&
        !event.target.contains(active)
      ) {
        event.preventDefault();
        return;
      }
      if (!opener.current?.isConnected) return;
      event.preventDefault();
      opener.current.focus({ preventScroll: true });
    },
  };
}
