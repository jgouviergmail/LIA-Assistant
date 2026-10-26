'use client';
import { useCallback, useState, useSyncExternalStore } from 'react';

export type JoystickPreference = 'auto' | 'show' | 'hide';
const KEY = 'lia-world-joystick';
const CHANGED = 'lia-world-joystick-changed';
export function isJoystickPreference(value: unknown): value is JoystickPreference {
  return value === 'auto' || value === 'show' || value === 'hide';
}
export function shouldShowJoystick(
  preference: JoystickPreference,
  touch: boolean,
  paused: boolean
): boolean {
  if (paused) return false;
  return preference === 'show' || (preference === 'auto' && touch);
}
function subscribe(listener: () => void) {
  window.addEventListener('storage', listener);
  window.addEventListener(CHANGED, listener);
  return () => {
    window.removeEventListener('storage', listener);
    window.removeEventListener(CHANGED, listener);
  };
}
function serverPreference(): JoystickPreference {
  return 'auto';
}
export function useJoystickPreference() {
  const [fallback, setFallback] = useState<JoystickPreference>('auto');
  const snapshot = useCallback((): JoystickPreference => {
    try {
      const saved = localStorage.getItem(KEY);
      return isJoystickPreference(saved) ? saved : 'auto';
    } catch {
      return fallback;
    }
  }, [fallback]);
  const preference = useSyncExternalStore(subscribe, snapshot, serverPreference);
  const update = useCallback((value: JoystickPreference) => {
    setFallback(value);
    try {
      localStorage.setItem(KEY, value);
    } catch {
      /* Session controls remain available. */
    }
    window.dispatchEvent(new Event(CHANGED));
  }, []);
  return [preference, update] as const;
}
