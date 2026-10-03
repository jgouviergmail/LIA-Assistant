'use client';

import { useCallback, useRef, useState, type KeyboardEvent, type TouchEvent } from 'react';
import { CAROUSEL_SWIPE_THRESHOLD_PX } from '@/lib/constants';
import { isImageLoaded, markImageLoaded } from '@/lib/image-cache';

function boundedIndex(index: number, count: number): number {
  return Number.isFinite(index) ? Math.max(0, Math.min(count - 1, Math.trunc(index))) : 0;
}

export function usePlaceGallery(images: readonly string[], initialIndex: number) {
  const [selected, setSelected] = useState(() => {
    const index = boundedIndex(initialIndex, images.length);
    return { index, url: images[index] ?? '' };
  });
  const [loaded, setLoaded] = useState<Set<string>>(() => new Set());
  const [failed, setFailed] = useState<Set<string>>(() => new Set());
  const gesture = useRef<{
    start: { x: number; y: number };
    end?: { x: number; y: number };
  } | null>(null);
  // Track the selected URL, so reorder/replacement cannot show an invalid index.
  const currentIndex =
    images[selected.index] === selected.url
      ? selected.index
      : Math.max(0, images.indexOf(selected.url));
  const currentImage = images[currentIndex] ?? '';
  const select = useCallback(
    (requested: number) => {
      const index = boundedIndex(requested, images.length);
      setSelected({ index, url: images[index] ?? '' });
    },
    [images]
  );
  const previous = useCallback(
    () => select((currentIndex + images.length - 1) % images.length),
    [currentIndex, images.length, select]
  );
  const next = useCallback(
    () => select((currentIndex + 1) % images.length),
    [currentIndex, images.length, select]
  );

  const onLoad = useCallback((url: string) => {
    markImageLoaded(url);
    setLoaded(old => new Set(old).add(url));
    setFailed(old => {
      if (!old.has(url)) return old;
      const next = new Set(old);
      next.delete(url);
      return next;
    });
  }, []);
  const onError = useCallback((url: string) => setFailed(old => new Set(old).add(url)), []);
  const onTouchStart = useCallback((event: TouchEvent) => {
    const touch = event.touches[0];
    gesture.current = touch ? { start: { x: touch.clientX, y: touch.clientY } } : null;
  }, []);
  const onTouchMove = useCallback((event: TouchEvent) => {
    const touch = event.touches[0];
    if (gesture.current && touch) gesture.current.end = { x: touch.clientX, y: touch.clientY };
  }, []);
  const onTouchEnd = useCallback(() => {
    const completed = gesture.current;
    gesture.current = null;
    if (!completed?.end) return;
    const x = completed.start.x - completed.end.x;
    const y = completed.start.y - completed.end.y;
    if (Math.abs(x) <= CAROUSEL_SWIPE_THRESHOLD_PX || Math.abs(x) <= Math.abs(y)) return;
    if (x > 0) next();
    else previous();
  }, [next, previous]);
  const onKeyDown = useCallback(
    (event: KeyboardEvent) => {
      switch (event.key) {
        case 'ArrowLeft':
          event.preventDefault();
          previous();
          break;
        case 'ArrowRight':
          event.preventDefault();
          next();
          break;
        case 'Home':
          event.preventDefault();
          select(0);
          break;
        case 'End':
          event.preventDefault();
          select(images.length - 1);
          break;
      }
    },
    [next, previous, select, images.length]
  );

  return {
    currentIndex,
    currentImage,
    select,
    previous,
    next,
    onLoad,
    onError,
    onTouchStart,
    onTouchMove,
    onTouchEnd,
    onKeyDown,
    isLoaded: loaded.has(currentImage) || isImageLoaded(currentImage),
    isFailed: failed.has(currentImage),
  };
}
