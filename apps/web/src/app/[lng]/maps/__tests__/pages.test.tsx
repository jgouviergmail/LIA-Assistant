/**
 * The four pages of `/maps`: what search engines read (metadata in every
 * language) and what a reader lands on (the hero, the section's own tabs, the
 * map). Translations and data are the REAL ones — the pages introduce the
 * `maps.*` keys and the per-language map text, and a stubbed translator would
 * pass even if a language were missing. The interactive maps are mocked to
 * markers: each has its own tests.
 */

import { render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/components/landing/LandingHeader', () => ({
  LandingHeader: () => <div data-testid="landing-header" />,
}));
vi.mock('@/components/layout/PublicFooter', () => ({
  PublicFooter: () => <div data-testid="public-footer" />,
}));
vi.mock('@/components/seo/JsonLd', () => ({
  BreadcrumbJsonLd: ({ items }: { items: Array<{ name: string }> }) => (
    <div data-testid="breadcrumb">{items.map(i => i.name).join(' > ')}</div>
  ),
}));
vi.mock('@/components/maps/FunctionalMap', () => ({
  FunctionalMap: ({ map }: { map: { bricks: unknown[] } }) => (
    <div data-testid="functional-map" data-bricks={map.bricks.length} />
  ),
}));
vi.mock('@/components/maps/TechnicalMap', () => ({
  TechnicalMap: ({ map }: { map: { bricks: unknown[] } }) => (
    <div data-testid="technical-map" data-bricks={map.bricks.length} />
  ),
}));
vi.mock('@/components/maps/HistoryMap', () => ({
  HistoryMap: ({ view }: { view: { decisions: unknown[] } }) => (
    <div data-testid="history-map" data-decisions={view.decisions.length} />
  ),
}));

import { mapsData } from '@/lib/maps/data';

import MapsPage, { generateMetadata as hubMetadata } from '../page';
import FunctionalMapPage, { generateMetadata as functionalMetadata } from '../functional/page';
import HistoryMapPage, { generateMetadata as historyMetadata } from '../history/page';
import TechnicalMapPage, { generateMetadata as technicalMetadata } from '../technical/page';

const ORIGIN = 'https://lia.test';
// Counts come from the data, never typed here: the maps grow with the code.
const FUNCTIONAL_BRICKS = String(mapsData('fr').functional.bricks.length);
const TECHNICAL_BRICKS = String(mapsData('fr').technical.bricks.length);
const DECISIONS = String(mapsData('fr').history.entries.length);
const paramsFor = (lng: string) => ({ params: Promise.resolve({ lng }) });

describe('/maps metadata', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('declares each page canonical URL and one alternate per language', async () => {
    vi.stubEnv('APP_URL_SERVER', ORIGIN);
    const hub = await hubMetadata(paramsFor('fr'));
    expect(hub.title).toBe('Les cartes de LIA');
    expect(hub.alternates?.canonical).toBe(`${ORIGIN}/maps`);
    expect(hub.alternates?.languages).toMatchObject({
      en: `${ORIGIN}/en/maps`,
      zh: `${ORIGIN}/zh/maps`,
      'x-default': `${ORIGIN}/maps`,
    });
    const history = await historyMetadata(paramsFor('de'));
    expect(history.title).toBe('Entscheidungschronik von LIA');
    expect(history.alternates?.canonical).toBe(`${ORIGIN}/de/maps/history`);
  });

  it('describes each map with its own lede, in the page language', async () => {
    const functional = await functionalMetadata(paramsFor('en'));
    expect(functional.title).toBe("LIA's functional map");
    expect(functional.description).toMatch(/\w/);
    const technical = await technicalMetadata(paramsFor('zh'));
    expect(technical.title).toBe('LIA 技术地图');
    expect(technical.description).toMatch(/[一-鿿]/);
  });
});

describe('/maps pages', () => {
  it('opens the section on its three maps, in the cosmos calm scope', async () => {
    const { container } = render(await MapsPage(paramsFor('fr')));
    expect(container.querySelector('.landing-page.cosmos.cosmos-calm.lia-maps')).not.toBeNull();
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
      'Trois cartes pour comprendre LIA'
    );
    const tabs = screen.getByRole('navigation', { name: 'Les cartes de LIA' });
    expect(within(tabs).getByRole('link', { name: 'Cartes' })).toHaveAttribute(
      'aria-current',
      'page'
    );
    const cards = screen.getAllByRole('article');
    expect(cards).toHaveLength(3);
    expect(
      within(cards[2]).getByRole('link', { name: 'Historique des décisions' })
    ).toHaveAttribute('href', '/maps/history');
    expect(screen.getByTestId('breadcrumb')).toHaveTextContent('LIA > Cartes');
  });

  it('hands each map its view, under its hero and with its tab current', async () => {
    render(await FunctionalMapPage(paramsFor('en')));
    expect(screen.getByTestId('functional-map')).toHaveAttribute('data-bricks', FUNCTIONAL_BRICKS);
    expect(
      within(screen.getByRole('navigation', { name: "LIA's maps" })).getByRole('link', {
        name: 'Functional map',
      })
    ).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('What LIA can do');
  });

  it('renders the technical map and the history, prefixed for a non-default language', async () => {
    const technical = render(await TechnicalMapPage(paramsFor('it')));
    expect(screen.getByTestId('technical-map')).toHaveAttribute('data-bricks', TECHNICAL_BRICKS);
    expect(screen.getByRole('link', { name: 'Storia delle decisioni' })).toHaveAttribute(
      'href',
      '/it/maps/history'
    );
    technical.unmount();
    render(await HistoryMapPage(paramsFor('es')));
    expect(screen.getByTestId('history-map')).toHaveAttribute('data-decisions', DECISIONS);
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('La historia de LIA');
  });
});
