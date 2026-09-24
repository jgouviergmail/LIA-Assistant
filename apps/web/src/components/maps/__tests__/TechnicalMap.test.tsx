/**
 * The technical map: its layers, the connectors it measures and draws, and a
 * brick's technologies and files.
 */

import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { buildBrickMap } from '@/lib/maps/model';
import { mapsDataFixture } from '@/lib/maps/__tests__/fixtures';

import { TechnicalMap } from '../TechnicalMap';

const map = buildBrickMap(mapsDataFixture(), 'technical');

/** The overlay the board draws its connectors into. */
const drawnPaths = (container: HTMLElement) => container.querySelectorAll('.lm-links-layer g path');

const brickButton = (name: string) =>
  within(screen.getByRole('region', { name: 'Socle' })).getByRole('button', {
    name: new RegExp(`^${name}`),
  });

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
  vi.stubGlobal(
    'matchMedia',
    vi.fn(() => ({ matches: true }))
  );
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      disconnect() {}
      unobserve() {}
    }
  );
});

afterEach(() => {
  window.history.replaceState(null, '', window.location.pathname);
  vi.unstubAllGlobals();
});

describe('TechnicalMap', () => {
  it('draws each layer as a named region holding its bricks', () => {
    render(<TechnicalMap map={map} lng="fr" />);
    const layer = screen.getByRole('region', { name: 'Socle' });
    expect(within(layer).getAllByRole('button')).toHaveLength(2);
  });

  it('draws the links of the brick under the pointer, and clears them after', async () => {
    const user = userEvent.setup();
    const { container } = render(<TechnicalMap map={map} lng="fr" />);
    expect(drawnPaths(container)).toHaveLength(0);
    await user.hover(brickButton('FastAPI'));
    // FastAPI depends on nothing and Redis uses it: one incoming link.
    const paths = drawnPaths(container);
    expect(paths).toHaveLength(1);
    expect(paths[0]).toHaveAttribute('class', 'lm-in');
    expect(brickButton('Redis')).toHaveClass('is-near');
    await user.unhover(brickButton('FastAPI'));
    expect(drawnPaths(container)).toHaveLength(0);
  });

  it('shows a brick technologies and where it lives in the repository', async () => {
    const user = userEvent.setup();
    render(<TechnicalMap map={map} lng="fr" />);
    await user.click(brickButton('FastAPI'));
    const dialog = await screen.findByRole('dialog', { name: 'FastAPI' });
    expect(within(dialog).getByText('Pydantic v2')).toBeInTheDocument();
    expect(within(dialog).getByRole('link', { name: /apps\/api\/src\/core/ })).toHaveAttribute(
      'href',
      'https://example.test/blob/main/apps/api/src/core'
    );
    expect(within(dialog).getByText('maps.drawer.layer · Socle')).toBeInTheDocument();
    // The functional side of the same decisions.
    expect(within(dialog).getByRole('link', { name: 'Conversation' })).toHaveAttribute(
      'href',
      '/maps/functional#f.one'
    );
  });

  it('numbers the steps of a journey and draws its path up to the current step', async () => {
    const user = userEvent.setup();
    const { container } = render(<TechnicalMap map={map} lng="fr" />);
    await user.click(screen.getByRole('button', { name: 'Une requête' }));
    expect(brickButton('FastAPI')).toHaveTextContent('1');
    expect(drawnPaths(container)).toHaveLength(0);
    await user.click(screen.getByRole('button', { name: 'maps.player.next' }));
    expect(drawnPaths(container)).toHaveLength(1);
    expect(drawnPaths(container)[0]).toHaveAttribute('class', 'lm-flow is-animated');
    act(() => brickButton('Redis').focus());
    // A journey being played keeps the map, whatever the pointer does.
    expect(drawnPaths(container)[0]).toHaveAttribute('class', 'lm-flow is-animated');
  });
});
