'use client';

/**
 * The tools' keyboard shortcuts (ADR-369, lot 2).
 *
 * One letter acts, so a shortcut listens only where a person is not typing, stays
 * out of what a dialog is doing, leaves the browser's own chords alone, and can
 * be switched off on this device (WCAG 2.1.4): a preference of the device, like the
 * list's density, wrapped because a private window refuses storage.
 */
import { useEffect, useEffectEvent, useSyncExternalStore } from 'react';

const SHORTCUTS_KEY = 'lia_workbench_shortcuts';
const OFF = 'off';
const ON = 'on';
/** Dispatched on `window` after every change, for `useSyncExternalStore`. */
const CHANGED = 'lia:workbench-shortcuts';

/** One key of a tool: what it is called in the help, and what it does. */
export interface ToolShortcut {
  /** The key as the keyboard spells it (`KeyboardEvent.key`). */
  key: string;
  labelKey: string;
  run: () => void;
}

/** The choice where storage is refused: switched off still means off, for this page. */
let chosen: boolean | null = null;

function readEnabled(): boolean {
  try {
    return window.localStorage.getItem(SHORTCUTS_KEY) !== OFF;
  } catch {
    return chosen ?? true;
  }
}

/** Before hydration nothing is listened to, so nothing is switched on. */
const serverEnabled = (): boolean => false;

function subscribe(onChange: () => void): () => void {
  const onStorage = (event: StorageEvent) => {
    if (event.key === SHORTCUTS_KEY) onChange();
  };
  window.addEventListener(CHANGED, onChange);
  window.addEventListener('storage', onStorage);
  return () => {
    window.removeEventListener(CHANGED, onChange);
    window.removeEventListener('storage', onStorage);
  };
}

/** Remembers the choice (a refused storage keeps it for the page only). */
export function writeShortcutsEnabled(enabled: boolean): void {
  chosen = enabled;
  try {
    window.localStorage.setItem(SHORTCUTS_KEY, enabled ? ON : OFF);
  } catch {
    // Storage unavailable (private window, blocked site data): nothing to keep.
  }
  window.dispatchEvent(new Event(CHANGED));
}

/** @returns Whether this device has the shortcuts on, following any change of it. */
export function useShortcutsEnabled(): boolean {
  return useSyncExternalStore(subscribe, readEnabled, serverEnabled);
}

/** Whether the key belongs to something else than the page's shortcuts. */
function taken(event: KeyboardEvent): boolean {
  if (event.repeat || event.defaultPrevented) return true;
  if (event.ctrlKey || event.metaKey || event.altKey) return true;
  const target = event.target;
  if (!(target instanceof HTMLElement)) return false;
  return (
    ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName) ||
    target.closest(
      '[contenteditable="true"],[role="dialog"],[role="alertdialog"],[role="menu"]'
    ) !== null
  );
}

/** @param shortcuts - What this screen answers. */
export function useToolShortcuts(shortcuts: readonly ToolShortcut[]): void {
  const enabled = useShortcutsEnabled();
  const answer = useEffectEvent((event: KeyboardEvent) => {
    if (taken(event)) return;
    const shortcut = shortcuts.find(item => item.key === event.key);
    if (!shortcut) return;
    event.preventDefault();
    shortcut.run();
  });
  useEffect(() => {
    if (!enabled) return;
    const listen = (event: KeyboardEvent) => answer(event);
    window.addEventListener('keydown', listen);
    return () => window.removeEventListener('keydown', listen);
  }, [enabled]);
}
