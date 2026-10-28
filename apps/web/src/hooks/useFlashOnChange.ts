'use client';

import { useEffect, useState } from 'react';

/**
 * True for `visibleMs` after `cue` last changed — never on the first render.
 *
 * The change is noticed during render, from the value it follows (React's
 * "adjust state when a prop changes" shape): an effect that detects it and sets
 * state synchronously renders every change twice and is what the react-hooks
 * rules refuse. Only the timer lowers the flag, and a newer change before it
 * fires keeps the flag up for `visibleMs` from that change.
 *
 * @param cue - The value whose every change raises the flag.
 * @param visibleMs - How long the flag stays up after the latest change.
 * @returns Whether the flag is up.
 */
export function useFlashOnChange(cue: unknown, visibleMs: number): boolean {
  const [seen, setSeen] = useState({ cue, changes: 0 });
  if (!Object.is(seen.cue, cue)) setSeen({ cue, changes: seen.changes + 1 });
  const [settled, setSettled] = useState(0);
  const flashing = seen.changes > settled;
  useEffect(() => {
    if (!flashing) return;
    const changes = seen.changes;
    const timer = setTimeout(() => setSettled(changes), visibleMs);
    return () => clearTimeout(timer);
  }, [flashing, seen.changes, visibleMs]);
  return flashing;
}
