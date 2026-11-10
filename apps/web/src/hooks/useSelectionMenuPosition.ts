'use client';

import { useLayoutEffect, useRef } from 'react';
import {
  placeSelectionMenu,
  selectionMenuSpace,
  selectionViewport,
  type SelectionRect,
} from '@/lib/selection-position';

/** Measure the real target in its scrollport and the visual viewport, preserving menu scroll. */
export function useSelectionMenuPosition(anchorOf: () => SelectionRect) {
  const ref = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const menu = ref.current;
    if (!menu) return;
    menu.style.left = '0px';
    menu.style.top = '0px';
    const measure = () => {
      const { scrollTop, scrollLeft } = menu;
      const viewport = selectionViewport();
      const clientAnchor = anchorOf();
      menu.style.maxWidth = `min(var(--selection-max-width, 100vw), ${Math.max(0, viewport.width - 16)}px)`;
      menu.style.maxHeight = `${Math.max(0, viewport.height - 16)}px`;
      const rect = menu.getBoundingClientRect();
      // During an iOS keyboard pan, client rects and fixed CSS coordinates can
      // have different origins. Measure their translation from this overlay;
      // do not infer it from the engine or add a viewport offset twice.
      const dx = parseFloat(menu.style.left) - rect.left;
      const dy = parseFloat(menu.style.top) - rect.top;
      const anchor = {
        ...clientAnchor,
        left: clientAnchor.left + dx,
        top: clientAnchor.top + dy,
        bottom: clientAnchor.bottom + dy,
      };
      const space = selectionMenuSpace(anchor, rect, viewport);
      if (!space) {
        menu.style.visibility = 'hidden';
        return;
      }
      menu.style.maxWidth = `min(var(--selection-max-width, 100vw), ${space.width}px)`;
      menu.style.maxHeight = `${space.height}px`;
      const position = placeSelectionMenu(anchor, menu.getBoundingClientRect(), space);
      menu.style.left = `${position.left}px`;
      menu.style.top = `${position.top}px`;
      menu.style.visibility = 'visible';
      menu.scrollTop = scrollTop;
      menu.scrollLeft = scrollLeft;
    };
    const onScroll = (event: Event) => {
      if (event.target instanceof Node && menu.contains(event.target)) return;
      measure();
    };
    measure();
    const observer = typeof ResizeObserver === 'function' ? new ResizeObserver(measure) : null;
    observer?.observe(menu);
    const viewport = window.visualViewport;
    window.addEventListener('resize', measure);
    document.addEventListener('scroll', onScroll, true);
    viewport?.addEventListener('resize', measure);
    viewport?.addEventListener('scroll', measure);
    return () => {
      observer?.disconnect();
      window.removeEventListener('resize', measure);
      document.removeEventListener('scroll', onScroll, true);
      viewport?.removeEventListener('resize', measure);
      viewport?.removeEventListener('scroll', measure);
    };
  }, [anchorOf]);
  return ref;
}
