/**
 * AlertsViewActions — the header the Alerts hub and the Activity timeline
 * share (owner request 2026-10-21).
 *
 * What a reader would notice being broken: the switch leads to the OTHER view
 * and sits first; the actions journal and the refresh stand beside it on both
 * pages, at one height; a switch to a view the instance does not serve is
 * absent; a refresh already in flight ignores a second press without leaving
 * the tab order.
 */

import { describe, it, expect, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'fr' } }),
}));

import { AlertsViewActions, type AlertsView } from '../AlertsViewActions';

function renderActions(
  over: Partial<{ view: AlertsView; switchable: boolean; busy: boolean }> = {}
) {
  const onRefresh = vi.fn();
  const utils = renderWithProviders(
    <AlertsViewActions
      lng="fr"
      view={over.view ?? 'hub'}
      switchable={over.switchable ?? true}
      busy={over.busy ?? false}
      onRefresh={onRefresh}
    />
  );
  return { ...utils, onRefresh };
}

/** The three controls, in reading order. */
function controls(): HTMLElement[] {
  return [...screen.getAllByRole('link'), screen.getByRole('button', { name: 'common.refresh' })];
}

describe('AlertsViewActions', () => {
  it('leads from the hub to the timeline, then the journal, then a refresh', () => {
    renderActions({ view: 'hub' });

    const [toTimeline, journal, refresh] = controls();
    expect(toTimeline).toHaveAccessibleName('activity.hub_cta');
    expect(toTimeline).toHaveAttribute('href', '/fr/dashboard/activity');
    expect(journal).toHaveAccessibleName('effects.journal.title');
    expect(journal).toHaveAttribute('href', '/fr/dashboard/actions');
    expect(refresh).toHaveAccessibleName('common.refresh');
  });

  it('leads from the timeline back to the hub, with the same two beside it', () => {
    renderActions({ view: 'activity' });

    const [toHub, journal] = controls();
    expect(toHub).toHaveAccessibleName('activity.hub_back');
    expect(toHub).toHaveAttribute('href', '/fr/dashboard/notifications');
    expect(journal).toHaveAttribute('href', '/fr/dashboard/actions');
  });

  it('gives the three controls one height', () => {
    renderActions();

    for (const control of controls()) expect(control).toHaveClass('min-h-11');
  });

  it('offers no switch to a view the instance does not serve', () => {
    renderActions({ switchable: false });

    expect(screen.queryByRole('link', { name: 'activity.hub_cta' })).toBeNull();
    expect(screen.getByRole('link', { name: 'effects.journal.title' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'common.refresh' })).toBeInTheDocument();
  });

  it('refreshes on a press', async () => {
    const { user, onRefresh } = renderActions();

    await user.click(screen.getByRole('button', { name: 'common.refresh' }));

    expect(onRefresh).toHaveBeenCalledOnce();
  });

  it('ignores a press while a read is in flight, and keeps the control focusable', async () => {
    const { user, onRefresh } = renderActions({ busy: true });
    const refresh = screen.getByRole('button', { name: 'common.refresh' });

    await user.click(refresh);

    expect(onRefresh).not.toHaveBeenCalled();
    expect(refresh).toHaveAttribute('aria-disabled', 'true');
    // `aria-disabled`, never `disabled`: the press must not throw focus away.
    expect(refresh).not.toBeDisabled();
    expect(refresh).toHaveFocus();
    expect(refresh.querySelector('svg')).toHaveClass('animate-spin');
  });
});
