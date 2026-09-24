/**
 * The decision history: the chart, the filters, the address a link gives it.
 */

import { act, fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { buildHistory } from '@/lib/maps/model';
import { mapsDataFixture } from '@/lib/maps/__tests__/fixtures';

import { HistoryMap } from '../HistoryMap';

const view = buildHistory(mapsDataFixture());

/** The decisions the timeline shows, by number, in order. */
const shownDecisions = () => screen.queryAllByRole('article').map(a => a.id.replace('adr-', ''));
const releases = () => screen.queryAllByRole('link', { name: /maps\.history\.release/ });

function navigateTo(hash: string): void {
  act(() => {
    window.history.replaceState(null, '', hash);
    window.dispatchEvent(new HashChangeEvent('hashchange'));
  });
}

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
});

afterEach(() => {
  window.history.replaceState(null, '', window.location.pathname);
});

describe('HistoryMap', () => {
  it('tells every decision in its chapter and month, with the releases of the span', () => {
    render(<HistoryMap view={view} lng="fr" />);
    expect(shownDecisions()).toEqual(['1', '2', '3']);
    expect(screen.getByRole('region', { name: 'Les fondations' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Un graphe' })).toBeInTheDocument();
    // 1.0.0 falls inside the decisions' span; 1.2.0 comes after the last one.
    expect(releases()).toHaveLength(1);
    // A decision without a file links to the ADR index.
    const third = screen.getByRole('article', { name: 'Un cache' });
    expect(within(third).getByRole('link', { name: /maps\.history\.in_index/ })).toHaveAttribute(
      'href',
      'https://example.test/blob/main/docs/architecture/ADR_INDEX.md#adr-003'
    );
    expect(within(third).getByRole('link', { name: 'Notifications' })).toHaveAttribute(
      'href',
      '/maps/functional#f.three'
    );
  });

  it('filters by theme, and leaves the releases out while filtered', async () => {
    const user = userEvent.setup();
    render(<HistoryMap view={view} lng="fr" />);
    const themes = screen.getByRole('group', { name: 'maps.history.themes_label' });
    const voice = within(themes).getByRole('button', { name: /Voix/ });
    await user.click(voice);
    expect(voice).toHaveAttribute('aria-pressed', 'true');
    expect(shownDecisions()).toEqual(['2']);
    expect(releases()).toHaveLength(0);
    await user.click(screen.getByRole('button', { name: 'maps.history.reset' }));
    expect(shownDecisions()).toEqual(['1', '2', '3']);
  });

  it('searches words and decision numbers, and offers a way back from nothing', async () => {
    const user = userEvent.setup();
    render(<HistoryMap view={view} lng="fr" />);
    const search = screen.getByRole('searchbox', { name: 'maps.history.search_label' });
    await user.type(search, 'adr-002');
    expect(shownDecisions()).toEqual(['2']);
    await user.clear(search);
    await user.type(search, 'introuvable');
    expect(screen.getByText('maps.history.empty')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'maps.history.reset_filters' }));
    expect(shownDecisions()).toEqual(['1', '2', '3']);
  });

  it('reads newest first, and hides the releases on request', async () => {
    const user = userEvent.setup();
    render(<HistoryMap view={view} lng="fr" />);
    await user.click(screen.getByRole('checkbox', { name: 'maps.history.newest_first' }));
    expect(shownDecisions()).toEqual(['3', '2', '1']);
    await user.click(screen.getByRole('checkbox', { name: 'maps.history.show_releases' }));
    expect(releases()).toHaveLength(0);
  });

  it('shows only the decisions that shaped the brick its address names', async () => {
    const user = userEvent.setup();
    window.history.replaceState(null, '', '#f.two');
    render(<HistoryMap view={view} lng="fr" />);
    expect(shownDecisions()).toEqual(['2']);
    expect(screen.getByText('maps.history.brick_filter')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'maps.history.clear_brick_filter' }));
    expect(window.location.hash).toBe('');
    expect(shownDecisions()).toEqual(['1', '2', '3']);
  });

  it('brings a decision a link points at into view, clearing the filters that hid it', async () => {
    const user = userEvent.setup();
    render(<HistoryMap view={view} lng="fr" />);
    await user.click(screen.getByRole('button', { name: /Voix/ }));
    expect(shownDecisions()).toEqual(['2']);
    navigateTo('#adr-3');
    expect(shownDecisions()).toEqual(['1', '2', '3']);
    expect(screen.getByRole('article', { name: 'Un cache' })).toHaveClass('is-target');
    expect(Element.prototype.scrollIntoView).toHaveBeenCalled();
  });

  it('breaks a month down by theme under the pointer, and jumps to it on click', () => {
    render(<HistoryMap view={view} lng="fr" />);
    const chart = screen.getByRole('img', { name: 'maps.history.chart_label' });
    const bars = chart.querySelectorAll('.lm-bar');
    expect(bars).toHaveLength(3);
    fireEvent.mouseMove(bars[1], { clientX: 10, clientY: 10 });
    expect(document.querySelector('.lm-tip')).toHaveTextContent('maps.history.tip_line');
    fireEvent.click(bars[1]);
    expect(Element.prototype.scrollIntoView).toHaveBeenCalled();
    fireEvent.mouseLeave(chart);
    expect(document.querySelector('.lm-tip')).toBeNull();
  });
});
