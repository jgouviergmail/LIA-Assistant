/**
 * shortcutsDockStore — where the dock sits and whether it is folded, per
 * device (ADR-277). WHAT is pinned is the account's and never lands here.
 */
import { describe, it, expect, beforeEach } from 'vitest';

import { SHORTCUTS_DOCK_PREFS_KEY } from '@/lib/constants';
import { useShortcutsDockStore } from '@/stores/shortcutsDockStore';

beforeEach(() => {
  localStorage.removeItem(SHORTCUTS_DOCK_PREFS_KEY);
  useShortcutsDockStore.getState().reset();
});

describe('shortcutsDockStore', () => {
  it('starts at the default spot, unfolded', () => {
    expect(useShortcutsDockStore.getState().position).toBeNull();
    expect(useShortcutsDockStore.getState().minimized).toBe(false);
  });

  it('keeps a spot inside the viewport percentages', () => {
    useShortcutsDockStore.getState().setPosition({ xPct: 120, yPct: -5 });

    expect(useShortcutsDockStore.getState().position).toEqual({ xPct: 100, yPct: 0 });
  });

  it('persists the spot and the fold under its own key', () => {
    useShortcutsDockStore.getState().setPosition({ xPct: 40, yPct: 60 });
    useShortcutsDockStore.getState().setMinimized(true);

    const persisted = JSON.parse(localStorage.getItem(SHORTCUTS_DOCK_PREFS_KEY) ?? '{}');
    expect(persisted.state).toEqual({ position: { xPct: 40, yPct: 60 }, minimized: true });
  });

  it('reset returns to the defaults', () => {
    useShortcutsDockStore.getState().setPosition({ xPct: 40, yPct: 60 });
    useShortcutsDockStore.getState().setMinimized(true);

    useShortcutsDockStore.getState().reset();

    expect(useShortcutsDockStore.getState().position).toBeNull();
    expect(useShortcutsDockStore.getState().minimized).toBe(false);
  });
});
