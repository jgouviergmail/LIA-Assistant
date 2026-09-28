'use client';

import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import type { ProductSceneId, ProductScenePhase } from './scenes';

const MOTION_QUERY = '(prefers-reduced-motion: reduce)';
function subscribeMotion(onChange: () => void) {
  const media = window.matchMedia(MOTION_QUERY);
  media.addEventListener('change', onChange);
  return () => media.removeEventListener('change', onChange);
}

/** One short explanation per selection; the finished result remains available to read. */
export function useProductDemo() {
  const ref = useRef<HTMLDivElement>(null);
  const [sceneId, setSceneId] = useState<ProductSceneId>('decision');
  const [phase, setPhase] = useState<ProductScenePhase>(0);
  const [paused, setPaused] = useState(false);
  const [visible, setVisible] = useState(false);
  const [run, setRun] = useState(0);
  const reducedMotion = useSyncExternalStore(
    subscribeMotion,
    () => window.matchMedia(MOTION_QUERY).matches,
    () => false
  );

  useEffect(() => {
    if (!ref.current) return;
    const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting), {
      threshold: 0.15,
    });
    observer.observe(ref.current);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (reducedMotion || paused || !visible || phase === 2) return;
    const timeout = window.setTimeout(
      () => setPhase(phase === 0 ? 1 : 2),
      phase === 0 ? 1700 : 2400
    );
    return () => window.clearTimeout(timeout);
  }, [phase, paused, reducedMotion, visible, run]);

  return {
    ref,
    sceneId,
    phase: reducedMotion ? (2 as const) : phase,
    reducedMotion,
    paused: paused || phase === 2,
    select(id: ProductSceneId) {
      if (id === sceneId) return;
      setSceneId(id);
      setPhase(0);
      setPaused(false);
      setRun(previous => previous + 1);
    },
    replay() {
      setPhase(0);
      setPaused(false);
      setRun(previous => previous + 1);
    },
    togglePause() {
      if (phase === 2) setPhase(0);
      setPaused(phase === 2 ? false : !paused);
    },
  };
}
