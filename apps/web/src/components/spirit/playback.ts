import { useEffect, useRef, useState, useSyncExternalStore } from 'react';

const listeners = new Set<() => void>();
let motionQuery: MediaQueryList | null = null;
const notify = () => listeners.forEach(listener => listener());
const paused = () => false;
const inertSubscription = () => () => {};

function playbackAllowed() {
  if (typeof document === 'undefined' || document.visibilityState !== 'visible') return false;
  const query = motionQuery ?? window.matchMedia('(prefers-reduced-motion: reduce)');
  return !query.matches;
}

/** One document/motion subscription for all playing avatars, released with the last one. */
function subscribePlayback(listener: () => void) {
  if (listeners.size === 0) {
    motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    motionQuery.addEventListener('change', notify);
    document.addEventListener('visibilitychange', notify);
  }
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
    if (listeners.size > 0) return;
    motionQuery?.removeEventListener('change', notify);
    document.removeEventListener('visibilitychange', notify);
    motionQuery = null;
  };
}

const targets = new Map<Element, (visible: boolean) => void>();
let observer: IntersectionObserver | null = null;

function observeAvatar(target: Element, onVisibility: (visible: boolean) => void) {
  if (typeof IntersectionObserver === 'undefined') return () => {};
  observer ??= new IntersectionObserver(entries => {
    entries.forEach(entry => targets.get(entry.target)?.(entry.isIntersecting));
  });
  targets.set(target, onVisibility);
  observer.observe(target);
  return () => {
    observer?.unobserve(target);
    targets.delete(target);
    if (targets.size > 0) return;
    observer?.disconnect();
    observer = null;
  };
}

export function useSpiritPlayback(requested: boolean) {
  const rootRef = useRef<HTMLSpanElement>(null);
  const [inViewport, setInViewport] = useState(false);
  const allowed = useSyncExternalStore(
    requested ? subscribePlayback : inertSubscription,
    requested ? playbackAllowed : paused,
    paused
  );
  useEffect(() => {
    if (!rootRef.current) return;
    return observeAvatar(rootRef.current, setInViewport);
  }, []);
  return { rootRef, playing: requested && inViewport && allowed };
}
