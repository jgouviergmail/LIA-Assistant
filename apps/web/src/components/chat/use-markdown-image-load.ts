'use client';

import { useEffect, useState } from 'react';
import { isImageLoaded, markImageLoaded } from '@/lib/image-cache';

/** LIA images load through their visible DOM image; Avatar still needs a preload. */
export function useMarkdownImageLoad(
  src: string,
  crossOrigin: 'use-credentials' | undefined,
  preload: boolean
) {
  const [loadedSource, setLoadedSource] = useState<string | null>(null);
  const [failedSource, setFailedSource] = useState<string | null>(null);
  const loaded = Boolean(src) && (loadedSource === src || isImageLoaded(src));

  useEffect(() => {
    if (!preload || !src || loaded) return;
    let active = true;
    const image = new Image();
    image.referrerPolicy = 'no-referrer';
    if (crossOrigin) image.crossOrigin = crossOrigin;
    image.onload = () => {
      if (!active) return;
      markImageLoaded(src);
      setLoadedSource(src);
    };
    image.src = src;
    return () => {
      active = false;
      image.onload = null;
    };
  }, [src, crossOrigin, preload, loaded]);

  const onLoad = () => {
    if (!src) return;
    markImageLoaded(src);
    setFailedSource(null);
    setLoadedSource(src);
  };
  const onError = () => setFailedSource(src);
  return { loaded, onLoad, failed: Boolean(src) && failedSource === src, onError };
}
