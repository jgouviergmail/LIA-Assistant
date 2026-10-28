import { useEffect } from 'react';
import { selectionViewport } from '@/lib/selection-position';

/** The layout viewport does not shrink with the keyboard on every mobile browser. */
export function useCompactConversationDock(host: HTMLElement | null, active: boolean) {
  useEffect(() => {
    const parent = host?.parentElement;
    if (!host || !parent || !active) return;
    const measure = () => {
      const viewport = selectionViewport();
      const bounds = parent.getBoundingClientRect();
      const bottom = viewport.top + viewport.height;
      const covered = Math.max(0, bounds.bottom - bottom);
      const keyboard = covered > 80;
      host.setAttribute('data-keyboard', String(keyboard));
      if (keyboard) host.style.setProperty('bottom', covered + 8 + 'px');
      else host.style.removeProperty('bottom');
      const reserved = keyboard
        ? 16
        : (Number.parseFloat(getComputedStyle(host).bottom) || 112) + 8;
      const height = Math.max(
        0,
        Math.min(
          320,
          Math.min(bottom, bounds.bottom) - Math.max(bounds.top, viewport.top) - reserved
        )
      );
      host.style.setProperty('--world-compact-height', height + 'px');
    };
    measure();
    const viewport = window.visualViewport;
    const observer = new ResizeObserver(measure);
    observer.observe(parent);
    window.addEventListener('resize', measure);
    viewport?.addEventListener('resize', measure);
    viewport?.addEventListener('scroll', measure);
    return () => {
      observer.disconnect();
      window.removeEventListener('resize', measure);
      viewport?.removeEventListener('resize', measure);
      viewport?.removeEventListener('scroll', measure);
      host.style.removeProperty('bottom');
      host.style.removeProperty('--world-compact-height');
      host.removeAttribute('data-keyboard');
    };
  }, [host, active]);
}
