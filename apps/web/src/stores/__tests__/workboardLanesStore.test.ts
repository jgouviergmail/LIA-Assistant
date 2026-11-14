/**
 * workboardLanesStore — which lanes of the board this device folded, and
 * whether it unfolded the board's figures.
 *
 * A display preference of the DEVICE, like the shortcuts dock's fold: the
 * categories themselves are the account's and never land here. Two things
 * could go wrong quietly: the list growing forever with the keys of lanes
 * deleted long ago, and a corrupted stored value breaking the board.
 */
import { describe, it, expect, beforeEach } from 'vitest';

import { WORKBOARD_LANES_PREFS_KEY } from '@/lib/constants';
import { useWorkboardLanesStore } from '@/stores/workboardLanesStore';

beforeEach(() => {
  localStorage.removeItem(WORKBOARD_LANES_PREFS_KEY);
  useWorkboardLanesStore.setState({ collapsed: [], summaryOpen: null });
});

describe('workboardLanesStore', () => {
  it('starts with every lane open', () => {
    expect(useWorkboardLanesStore.getState().collapsed).toEqual([]);
  });

  it('folds a lane, then unfolds it', () => {
    const { toggle } = useWorkboardLanesStore.getState();

    toggle('home', ['unfiled', 'home']);
    expect(useWorkboardLanesStore.getState().collapsed).toEqual(['home']);

    toggle('home', ['unfiled', 'home']);
    expect(useWorkboardLanesStore.getState().collapsed).toEqual([]);
  });

  it('forgets the lanes that are gone whenever it writes', () => {
    // A deleted category leaves a key nobody will ever fold or unfold again:
    // without pruning, the stored list only grows.
    useWorkboardLanesStore.setState({ collapsed: ['deleted-long-ago', 'home'] });

    useWorkboardLanesStore.getState().toggle('work', ['unfiled', 'home', 'work']);

    expect(useWorkboardLanesStore.getState().collapsed).toEqual(['home', 'work']);
  });

  it('persists the folds under its own key', () => {
    useWorkboardLanesStore.getState().toggle('home', ['home']);

    const persisted = JSON.parse(localStorage.getItem(WORKBOARD_LANES_PREFS_KEY) ?? '{}');
    expect(persisted.state).toEqual({ collapsed: ['home'], summaryOpen: null });
  });

  it('has no opinion on the figures until the person chose, then keeps the choice', () => {
    // `null` is « never chosen »: the screen's size decides, shut on a phone.
    expect(useWorkboardLanesStore.getState().summaryOpen).toBeNull();

    useWorkboardLanesStore.getState().setSummaryOpen(false);

    const persisted = JSON.parse(localStorage.getItem(WORKBOARD_LANES_PREFS_KEY) ?? '{}');
    expect(persisted.state).toEqual({ collapsed: [], summaryOpen: false });
    // Folding a lane afterwards does not forget it.
    useWorkboardLanesStore.getState().toggle('home', ['home']);
    expect(useWorkboardLanesStore.getState().summaryOpen).toBe(false);
  });

  it('restores the choice made on this device', async () => {
    localStorage.setItem(
      WORKBOARD_LANES_PREFS_KEY,
      JSON.stringify({ state: { collapsed: [], summaryOpen: true }, version: 0 })
    );

    await useWorkboardLanesStore.persist.rehydrate();

    expect(useWorkboardLanesStore.getState().summaryOpen).toBe(true);
  });

  it('reads a stored choice that is no boolean as « never chosen »', async () => {
    localStorage.setItem(
      WORKBOARD_LANES_PREFS_KEY,
      JSON.stringify({ state: { collapsed: [], summaryOpen: 'yes' }, version: 0 })
    );

    await useWorkboardLanesStore.persist.rehydrate();

    expect(useWorkboardLanesStore.getState().summaryOpen).toBeNull();
  });

  it('reads a corrupted stored value as « nothing folded »', async () => {
    localStorage.setItem(
      WORKBOARD_LANES_PREFS_KEY,
      JSON.stringify({ state: { collapsed: 'home' }, version: 0 })
    );

    await useWorkboardLanesStore.persist.rehydrate();

    expect(useWorkboardLanesStore.getState().collapsed).toEqual([]);
  });

  it('keeps only the strings of a half-valid stored list', async () => {
    localStorage.setItem(
      WORKBOARD_LANES_PREFS_KEY,
      JSON.stringify({ state: { collapsed: ['home', 7, null] }, version: 0 })
    );

    await useWorkboardLanesStore.persist.rehydrate();

    expect(useWorkboardLanesStore.getState().collapsed).toEqual(['home']);
  });
});
