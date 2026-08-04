/**
 * The capability map — constellation, list, and the promise both make.
 *
 * The rules a reader would notice being broken:
 *
 *  - a node lights up when the capability is genuinely USABLE, not when it
 *    exists. The light is the map's whole promise;
 *  - everything reachable is a real link with a translated name; the drawing
 *    is decorative and hidden from assistive technology (a `<circle>` with an
 *    onClick looks identical and cannot be used without a mouse);
 *  - the layout is DETERMINISTIC — the same account draws the same picture
 *    twice, which is what lets someone build a mental image of it;
 *  - a phone, or a reader who asked for stillness, gets the LIST: same data,
 *    same order, same destinations;
 *  - nothing anywhere is a level, an XP total or a comparison with anyone.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { settingsSectionHref } from '@/lib/settings-sections';
import { layoutCapabilities, CAPABILITY_ORDER } from '../constellation-layout';
import type { CapabilityNode } from '@/hooks/useCapabilities';

const { useApiQuery } = vi.hoisted(() => ({ useApiQuery: vi.fn() }));
vi.mock('@/hooks/useApiQuery', () => ({ useApiQuery }));

const { useMediaQuery } = vi.hoisted(() => ({ useMediaQuery: vi.fn() }));
vi.mock('@/hooks/useMediaQuery', () => ({ useMediaQuery }));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts
        ? `${key}|${Object.entries(opts)
            .map(([k, v]) => `${k}=${v}`)
            .join('|')}`
        : key,
    i18n: { language: 'fr' },
  }),
}));

import { CapabilityMapView } from '../CapabilityMapView';

/**
 * The constellation's own canvas.
 *
 * Targeted by its viewBox, not by `querySelector('svg')`: the LIST carries
 * chevron icons, which are svg elements too, and the crude selector matched
 * them — an oracle that says "there is an svg" answers a question nobody asked.
 */
function constellationCanvas(): Element | null {
  return document.querySelector('svg[viewBox="0 0 100 100"]');
}

const NODES: CapabilityNode[] = [
  { key: 'connectors', active: true, detail: 3 },
  { key: 'memory', active: true, detail: 12 },
  { key: 'voice', active: false, detail: null },
  { key: 'routines', active: false, detail: null },
];

function answer(nodes: CapabilityNode[] | undefined, over: Record<string, unknown> = {}) {
  useApiQuery.mockReturnValue({
    data: nodes
      ? { nodes, live: nodes.filter(n => n.active).length, total: nodes.length }
      : undefined,
    loading: nodes === undefined,
    error: null,
    refetch: vi.fn(),
    ...over,
  });
}

/** Wide screen, motion allowed → the constellation. */
function onDesktop() {
  useMediaQuery.mockImplementation((query: string) => query.includes('min-width'));
}

/** Narrow screen → the list. */
function onPhone() {
  useMediaQuery.mockReturnValue(false);
}

/** Wide screen, but the reader asked for stillness. */
function withReducedMotion() {
  useMediaQuery.mockImplementation(() => true);
}

beforeEach(() => {
  useApiQuery.mockReset();
  useMediaQuery.mockReset();
  answer(NODES);
  onDesktop();
});

describe('the constellation layout', () => {
  it('is deterministic — the same input draws the same picture', () => {
    const first = layoutCapabilities(['memory', 'routines', 'voice']);
    const second = layoutCapabilities(['memory', 'routines', 'voice']);

    expect(first).toEqual(second);
  });

  it('places every node inside the box', () => {
    const positions = layoutCapabilities(CAPABILITY_ORDER.map(entry => entry.key));

    expect(positions).toHaveLength(CAPABILITY_ORDER.length);
    for (const position of positions) {
      expect(position.x).toBeGreaterThan(0);
      expect(position.x).toBeLessThan(100);
      expect(position.y).toBeGreaterThan(0);
      expect(position.y).toBeLessThan(100);
    }
  });

  it('keeps the declared order and drops what it cannot name', () => {
    // A capability the client has no label for would render as an unlabelled
    // dot; absent is honest, unlabelled is not.
    const positions = layoutCapabilities(['routines', 'memory', 'not-a-capability']);

    expect(positions.map(p => p.key)).toEqual(['memory', 'routines']);
  });

  it('does not move a node when another one is added', () => {
    // Adding a capability must not reshuffle the map someone already knows.
    const before = layoutCapabilities(['memory', 'voice']);
    const after = layoutCapabilities(['memory', 'voice']);

    expect(before).toEqual(after);
  });
});

describe('CapabilityMapView', () => {
  it('draws the constellation on a wide screen', () => {
    renderWithProviders(<CapabilityMapView lng="fr" />);

    expect(screen.getByText('capabilities.map_title')).toBeInTheDocument();
    // The drawing itself is decorative: nothing in it is reachable.
    expect(constellationCanvas()).toHaveAttribute('aria-hidden', 'true');
  });

  it('names a live node with its state and its count', () => {
    renderWithProviders(<CapabilityMapView lng="fr" />);

    expect(
      screen.getByRole('link', {
        name: 'capabilities.node_active|name=capabilities.nodes.memory|count=12',
      })
    ).toBeInTheDocument();
  });

  it('names a dormant node as something to set up', () => {
    renderWithProviders(<CapabilityMapView lng="fr" />);

    expect(
      screen.getByRole('link', {
        name: 'capabilities.node_dormant|name=capabilities.nodes.voice',
      })
    ).toBeInTheDocument();
  });

  it('sends each node to where that capability is set up', () => {
    renderWithProviders(<CapabilityMapView lng="fr" />);

    expect(screen.getByRole('link', { name: /nodes\.connectors/ })).toHaveAttribute(
      'href',
      settingsSectionHref('fr', 'connectors')
    );
  });

  it('counts this account only — never a percentage of completion', () => {
    renderWithProviders(<CapabilityMapView lng="fr" />);

    expect(screen.getByText('capabilities.map_count|live=2|total=4')).toBeInTheDocument();
  });

  it('falls back to the list on a phone, with the same data and order', () => {
    onPhone();
    renderWithProviders(<CapabilityMapView lng="fr" />);

    expect(constellationCanvas()).toBeNull();
    const links = screen.getAllByRole('link');
    // Declared order, not payload order: two surfaces describing one thing
    // must not sequence it differently.
    expect(links[0]).toHaveTextContent('capabilities.nodes.connectors');
    expect(links[1]).toHaveTextContent('capabilities.nodes.memory');
  });

  it('keeps the chart under a request for stillness, and silences it', () => {
    // Asking for stillness is not asking for less information: the figure, the
    // magnitudes and the states stay, simply at rest.
    withReducedMotion();
    renderWithProviders(<CapabilityMapView lng="fr" />);

    expect(constellationCanvas()).not.toBeNull();
    // …and nothing in it is animated.
    expect(document.querySelector('.capability-field')).toBeNull();
    expect(document.querySelector('.capability-halo')).toBeNull();
  });

  it('states the state in WORDS in the list, not only as a coloured dot', () => {
    onPhone();
    renderWithProviders(<CapabilityMapView lng="fr" />);

    expect(screen.getByText('capabilities.state_active|count=3')).toBeInTheDocument();
    expect(screen.getAllByText('capabilities.state_dormant').length).toBeGreaterThan(0);
  });

  it('reports a failed read instead of claiming LIA can do nothing', () => {
    answer(undefined, { loading: false, error: new Error('boom') });
    renderWithProviders(<CapabilityMapView lng="fr" />);

    expect(screen.getByRole('alert')).toHaveTextContent('capabilities.error');
    expect(screen.queryByText('capabilities.empty')).toBeNull();
  });

  it('says so when the instance offers nothing', () => {
    answer([]);
    renderWithProviders(<CapabilityMapView lng="fr" />);

    expect(screen.getByText('capabilities.empty')).toBeInTheDocument();
  });

  it('shows no level, XP or comparison anywhere', () => {
    renderWithProviders(<CapabilityMapView lng="fr" />);

    const text = (document.body.textContent ?? '').toLowerCase();
    for (const forbidden of ['xp', 'level', 'rank', 'badge', 'streak', 'leaderboard']) {
      expect(text).not.toContain(forbidden);
    }
  });
});
