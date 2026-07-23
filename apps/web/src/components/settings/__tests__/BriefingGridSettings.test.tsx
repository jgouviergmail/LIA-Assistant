/**
 * BriefingGridSettings (UXR Lot 5, B4) — visibility switches and keyboard
 * reordering persist through the preferences hook; edges disabled; polite
 * position announcement.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import type { BriefingPreferences } from '@/types/briefing';

const save = vi.fn(async () => true);
const state: { preferences: BriefingPreferences | null } = { preferences: null };

vi.mock('@/hooks/useBriefingPreferences', async importOriginal => {
  const original = await importOriginal<typeof import('@/hooks/useBriefingPreferences')>();
  return {
    ...original,
    useBriefingPreferences: () => ({
      preferences: state.preferences,
      loading: false,
      error: false,
      save,
    }),
  };
});

import { BriefingGridSettings } from '../BriefingGridSettings';

beforeEach(() => {
  vi.clearAllMocks();
  state.preferences = {
    order: ['weather', 'agenda', 'mails'],
    hidden: ['mails'],
  } as BriefingPreferences;
});

function renderSettings() {
  return render(<BriefingGridSettings lng="fr" collapsible={false} />);
}

describe('BriefingGridSettings', () => {
  it('lists every section of the stored order with its visibility state', () => {
    renderSettings();
    expect(screen.getAllByRole('listitem')).toHaveLength(3);
    const switches = screen.getAllByRole('switch');
    expect(switches[0]).toBeChecked(); // weather visible
    expect(switches[2]).not.toBeChecked(); // mails hidden
  });

  it('persists a visibility toggle through the hook', () => {
    renderSettings();
    fireEvent.click(screen.getAllByRole('switch')[0]);
    expect(save).toHaveBeenCalledWith(
      expect.objectContaining({ hidden: ['mails', 'weather'] })
    );
  });

  it('persists a keyboard move through the hook', () => {
    renderSettings();
    // The i18n stub echoes keys without interpolation — every down button
    // shares the same accessible name; index 0 is the weather row.
    fireEvent.click(
      screen.getAllByRole('button', { name: 'settings.briefing_grid.move_down' })[0]
    );
    expect(save).toHaveBeenCalledWith(
      expect.objectContaining({ order: ['agenda', 'weather', 'mails'] })
    );
  });

  it('disables the edge buttons (first cannot go up, last cannot go down)', () => {
    renderSettings();
    const ups = screen.getAllByRole('button', { name: /move_up/ });
    const downs = screen.getAllByRole('button', { name: /move_down/ });
    expect(ups[0]).toBeDisabled();
    expect(downs[downs.length - 1]).toBeDisabled();
  });
});
