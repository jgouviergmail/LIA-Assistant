import { useCallback } from 'react';
import { selectionViewport } from '@/lib/selection-position';
import { WORLD_CONVERSATION_WIDTH } from './conversation-layout';

/** Keep the conversation inside the visible viewport, including a phone keyboard. */
export function useWorldConversationDock(
  active: boolean,
  maximumWidth = WORLD_CONVERSATION_WIDTH,
  maximumHeight = 760
) {
  return useCallback(
    (element: HTMLDivElement | null) => {
      if (!active || !element) return;
      const measure = () => {
        const viewport = selectionViewport();
        const width = Math.max(0, Math.min(maximumWidth, viewport.width - 16));
        const height = Math.max(0, Math.min(maximumHeight, viewport.height - 16));
        element.style.width = width + 'px';
        element.style.height = height + 'px';
        element.style.left = viewport.left + viewport.width - width - 8 + 'px';
        element.style.top = viewport.top + viewport.height - height - 8 + 'px';
      };
      measure();
      const viewport = window.visualViewport;
      window.addEventListener('resize', measure);
      viewport?.addEventListener('resize', measure);
      viewport?.addEventListener('scroll', measure);
      return () => {
        window.removeEventListener('resize', measure);
        viewport?.removeEventListener('resize', measure);
        viewport?.removeEventListener('scroll', measure);
        for (const property of ['width', 'height', 'left', 'top'])
          element.style.removeProperty(property);
      };
    },
    [active, maximumWidth, maximumHeight]
  );
}

export function returnWorldFocus(event: Event, opener: HTMLElement | null): void {
  event.preventDefault();
  const active = document.activeElement;
  if (
    active instanceof HTMLElement &&
    active !== document.body &&
    event.target instanceof Node &&
    !event.target.contains(active)
  )
    return;
  if (!opener?.isConnected) return;
  opener.focus({ preventScroll: true });
  if (document.activeElement === opener) return;
  // Mobile may have folded the original toolbar action since the panel opened.
  const controls = opener
    .closest('.world-session-strip')
    ?.parentElement?.querySelector<HTMLButtonElement>('.world-hud-toggle');
  controls?.focus({ preventScroll: true });
}
