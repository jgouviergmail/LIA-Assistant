/**
 * debugPanelStore — the width the person dragged the debug panel to, per
 * device (a display preference outside the purge registry).
 */
import { beforeEach, describe, expect, it } from 'vitest';

import { DEBUG_PANEL_PREFS_KEY } from '@/lib/constants';
import { useDebugPanelStore } from '@/stores/debugPanelStore';

beforeEach(() => {
  localStorage.removeItem(DEBUG_PANEL_PREFS_KEY);
  useDebugPanelStore.getState().reset();
});

describe('debugPanelStore', () => {
  it('starts at the default width', () => {
    expect(useDebugPanelStore.getState().width).toBeNull();
  });

  it('persists the chosen width under its own key, in whole pixels', () => {
    useDebugPanelStore.getState().setWidth(612.4);

    expect(useDebugPanelStore.getState().width).toBe(612);
    const persisted = JSON.parse(localStorage.getItem(DEBUG_PANEL_PREFS_KEY) ?? '{}');
    expect(persisted.state).toEqual({ width: 612 });
  });

  it('never stores a width that is not a number', () => {
    useDebugPanelStore.getState().setWidth(Number.NaN);

    expect(useDebugPanelStore.getState().width).toBeNull();
  });

  it('reset returns to the default', () => {
    useDebugPanelStore.getState().setWidth(700);
    useDebugPanelStore.getState().reset();

    expect(useDebugPanelStore.getState().width).toBeNull();
  });
});
