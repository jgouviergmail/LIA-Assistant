/**
 * The functional map, driven the way a reader drives it: search, isolate a
 * family, open a brick (by click, by keyboard, by address), play a journey.
 * i18n is the global echoing stub, so labels are asserted by key.
 */

import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { buildBrickMap } from '@/lib/maps/model';
import { mapsDataFixture } from '@/lib/maps/__tests__/fixtures';

import { FunctionalMap } from '../FunctionalMap';

const map = buildBrickMap(mapsDataFixture(), 'functional');

function renderMap() {
  const user = userEvent.setup();
  const view = render(<FunctionalMap map={map} lng="fr" />);
  return { user, ...view };
}

const constellation = () =>
  screen.getByRole('group', { name: 'maps.functional.constellation_label' });
const node = (name: string) =>
  within(constellation()).getByRole('button', { name: new RegExp(`^${name} — `) });
/** A brick's row in its family card. */
const row = (family: string, name: string) =>
  within(screen.getByRole('article', { name: family })).getByRole('button', {
    name: new RegExp(`^${name}`),
  });

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
  vi.stubGlobal(
    'matchMedia',
    vi.fn(() => ({ matches: true }))
  );
});

afterEach(() => {
  window.history.replaceState(null, '', window.location.pathname);
  vi.unstubAllGlobals();
});

describe('FunctionalMap', () => {
  it('draws the constellation, the families and every journey', () => {
    renderMap();
    expect(within(constellation()).getAllByRole('button')).toHaveLength(3);
    expect(screen.getByRole('heading', { name: 'Converser' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Prévenir' })).toBeInTheDocument();
    expect(screen.getByRole('article', { name: 'Une demande' })).toBeInTheDocument();
  });

  it('narrows the families to the search and says when nothing matches', async () => {
    const { user } = renderMap();
    const search = screen.getByRole('searchbox', { name: 'maps.common.search_label' });
    await user.type(search, 'memoire');
    expect(row('Converser', 'Mémoire')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Prévenir' })).toBeNull();
    expect(constellation()).toHaveClass('is-focus');
    await user.clear(search);
    await user.type(search, 'introuvable');
    expect(screen.getByText('maps.common.no_match')).toBeInTheDocument();
  });

  it('opens the first match on Enter, and the detail says everything about it', async () => {
    const { user } = renderMap();
    await user.type(screen.getByRole('searchbox'), 'conversation{Enter}');
    const dialog = await screen.findByRole('dialog', { name: 'Conversation' });
    expect(window.location.hash).toBe('#f.one');
    expect(within(dialog).getByText('Le fil de discussion.')).toBeInTheDocument();
    expect(within(dialog).getByText('Répondre juste.')).toBeInTheDocument();
    // Its dependency and its user, both as local hash links.
    expect(within(dialog).getByRole('link', { name: 'Mémoire' })).toHaveAttribute('href', '#f.two');
    expect(within(dialog).getByRole('link', { name: 'Notifications' })).toHaveAttribute(
      'href',
      '#f.three'
    );
    // The other map's brick crosses pages; the decisions point at the history.
    expect(within(dialog).getByRole('link', { name: 'FastAPI' })).toHaveAttribute(
      'href',
      '/maps/technical#t.one'
    );
    expect(within(dialog).getByRole('link', { name: /ADR-002/ })).toHaveAttribute(
      'href',
      '/maps/history#adr-2'
    );
    expect(within(dialog).getByRole('link', { name: /^alpha/ })).toHaveAttribute(
      'href',
      'https://example.test/blob/main/apps/api/src/domains/alpha'
    );
    expect(within(dialog).getByText('/dashboard/chat')).toBeInTheDocument();
  });

  it('closes the detail on Escape, clears the address and gives focus back', async () => {
    const { user } = renderMap();
    const notifications = row('Prévenir', 'Notifications');
    await user.click(notifications);
    expect(await screen.findByRole('dialog', { name: 'Notifications' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'maps.drawer.close' })).toHaveFocus();
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(window.location.hash).toBe('');
    expect(notifications).toHaveFocus();
  });

  it('opens a brick from the keyboard on its node, and traces it on focus', async () => {
    const { user } = renderMap();
    act(() => node('Conversation').focus());
    expect(node('Conversation')).toHaveClass('is-on');
    expect(node('Mémoire')).toHaveClass('is-near');
    await user.keyboard('{Enter}');
    expect(await screen.findByRole('dialog', { name: 'Conversation' })).toBeInTheDocument();
  });

  it('opens the brick its address names, on arrival', async () => {
    window.history.replaceState(null, '', '#f.three');
    renderMap();
    expect(await screen.findByRole('dialog', { name: 'Notifications' })).toBeInTheDocument();
  });

  it('isolates a family from the legend', async () => {
    const { user } = renderMap();
    const toggle = screen.getByRole('button', { name: /^Prévenir/ });
    await user.click(toggle);
    expect(toggle).toHaveAttribute('aria-pressed', 'true');
    expect(node('Notifications')).toHaveClass('is-on');
    expect(node('Conversation')).not.toHaveClass('is-on');
    await user.click(toggle);
    expect(toggle).toHaveAttribute('aria-pressed', 'false');
  });

  it('plays a journey step by step, and leaves it', async () => {
    const { user } = renderMap();
    const list = screen.getByRole('list', { name: 'maps.player.flows_label' });
    await user.click(within(list).getByRole('button', { name: 'Une demande' }));
    expect(within(list).getByRole('button', { name: 'Une demande' })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    // Reduced motion (stubbed): the reader steps by hand from step 1.
    const steps = screen.getAllByRole('button', { name: /Tu écris\.|Elle se souvient\./ });
    expect(steps[0]).toHaveAttribute('aria-current', 'step');
    await user.click(screen.getByRole('button', { name: 'maps.player.next' }));
    expect(screen.getByRole('button', { name: /Elle se souvient\./ })).toHaveAttribute(
      'aria-current',
      'step'
    );
    expect(node('Mémoire')).toHaveClass('is-on');
    await user.click(screen.getByRole('button', { name: 'maps.player.play' }));
    expect(screen.getByRole('button', { name: 'maps.player.pause' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'maps.player.quit' }));
    expect(screen.queryByRole('button', { name: 'maps.player.next' })).toBeNull();
  });

  it('replays a journey from its card, and from a brick detail', async () => {
    const { user } = renderMap();
    await user.click(screen.getByRole('button', { name: 'maps.player.replay' }));
    expect(screen.getByRole('button', { name: 'maps.player.quit' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'maps.player.quit' }));

    await user.click(row('Converser', 'Mémoire'));
    const dialog = await screen.findByRole('dialog', { name: 'Mémoire' });
    await user.click(within(dialog).getByRole('button', { name: 'Une demande' }));
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.getByRole('button', { name: 'maps.player.quit' })).toBeInTheDocument();
  });
});
