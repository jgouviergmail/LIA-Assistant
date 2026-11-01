/**
 * workbenchPanesStore — the widths the person dragged the « Tools » panes to,
 * per device (a display preference outside the purge registry): one width per
 * declared pane, whole pixels, and nothing read back that is not one.
 */
import { beforeEach, describe, expect, it } from 'vitest';

import { WORKBENCH_PANES_PREFS_KEY } from '@/lib/constants';
import { useWorkbenchPanesStore } from '@/stores/workbenchPanesStore';

beforeEach(() => {
  localStorage.removeItem(WORKBENCH_PANES_PREFS_KEY);
  useWorkbenchPanesStore.setState({ widths: {} });
});

describe('workbenchPanesStore', () => {
  it('starts with every pane at its layout’s own width', () => {
    expect(useWorkbenchPanesStore.getState().widths).toEqual({});
  });

  it('keeps each pane’s width apart, in whole pixels, under its own key', () => {
    useWorkbenchPanesStore.getState().setWidth('mail.folders', 300.6);
    useWorkbenchPanesStore.getState().setWidth('files.list', 500);

    expect(useWorkbenchPanesStore.getState().widths).toEqual({
      'mail.folders': 301,
      'files.list': 500,
    });
    const persisted = JSON.parse(localStorage.getItem(WORKBENCH_PANES_PREFS_KEY) ?? '{}');
    expect(persisted.state).toEqual({ widths: { 'mail.folders': 301, 'files.list': 500 } });
  });

  it('never stores a width that is not a number', () => {
    useWorkbenchPanesStore.getState().setWidth('mail.list', Number.NaN);

    expect(useWorkbenchPanesStore.getState().widths).toEqual({});
  });

  it('gives one pane back its layout’s width, leaving the others', () => {
    useWorkbenchPanesStore.getState().setWidth('mail.folders', 300);
    useWorkbenchPanesStore.getState().setWidth('mail.list', 500);
    useWorkbenchPanesStore.getState().reset('mail.folders');

    expect(useWorkbenchPanesStore.getState().widths).toEqual({ 'mail.list': 500 });
  });

  it('reads back only declared panes holding a number', async () => {
    localStorage.setItem(
      WORKBENCH_PANES_PREFS_KEY,
      JSON.stringify({
        state: {
          widths: { 'mail.folders': 280, 'mail.reader': 600, 'files.list': 'wide', toString: 9 },
        },
        version: 0,
      })
    );

    await useWorkbenchPanesStore.persist.rehydrate();

    expect(useWorkbenchPanesStore.getState().widths).toEqual({ 'mail.folders': 280 });
  });
});
