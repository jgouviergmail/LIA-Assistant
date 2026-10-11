'use client';

import { useLayoutEffect, useRef } from 'react';
import { readScopedSelection, type TextSelectionSnapshot } from '@/hooks/useTextSelection';
import {
  placeSelectionMenu,
  selectionMenuSpace,
  selectionViewport,
} from '@/lib/selection-position';

/** Measure the rendered menu; no guessed size, transformed ancestor or stale scroll anchor. */
export function useSelectionMenuPosition(snapshot: TextSelectionSnapshot | null) {
  const ref = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const menu = ref.current;
    if (!menu || !snapshot) return;
    const measure = () => {
      const { scrollTop, scrollLeft } = menu;
      const viewport = selectionViewport();
      const anchor = readScopedSelection(document)?.rect ?? snapshot.rect;
      menu.style.maxWidth = `${Math.max(0, viewport.width - 16)}px`;
      menu.style.maxHeight = `${Math.max(0, viewport.height - 16)}px`;
      const space = selectionMenuSpace(anchor, menu.getBoundingClientRect(), viewport);
      if (!space) {
        menu.style.visibility = 'hidden';
        return;
      }
      menu.style.maxWidth = `${space.width}px`;
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
  }, [snapshot]);
  return ref;
}
